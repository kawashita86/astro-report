"""Story 8.5 -- restore a ``GET /backup`` export into an empty database.

Two halves, mirroring the read-the-file style of ``tests/test_data_terms_record.py``
and the in-process round-trip style of ``tests/test_runner_driver.py`` /
``tests/test_http_backup.py`` -- in-memory SQLite, no network, no Docker:

* **Round trip.** Populate a source DB with a real ``gate_passed`` run (reusing
  ``tests/test_runner_driver.py``'s ``_create_client_and_chart`` / ``_drive``
  helpers) plus a ``CorpusEntry``, an ``ExportRecord`` and a second
  ``StyleGuide`` version; serialize it exactly as ``download_backup`` does;
  ``restore_backup`` it into a second, empty, FK-enforcing engine
  (``PRAGMA foreign_keys=ON``, so the ``_BACKUP_MODELS`` FK-safe order is
  genuinely exercised); and assert full fidelity -- per-table row counts,
  byte-identical JSON-column values, ``UUID`` / aware ``datetime`` / ``Decimal``
  field equality -- and that ``GET /report-runs/{run_id}/report`` reopens the
  restored Report with its passing ``StoredGateResult`` intact so every Claim
  stays traceable.

* **Record guard.** ``docs/release-validation/restore-rehearsal.md``'s
  ```` ```toml ```` block parses with exactly the expected keys,
  ``tables_restored`` equals the ``_BACKUP_MODELS`` table names,
  ``report_reopened`` / ``claims_traceable`` are ``true``, ``outcome`` is
  ``"pass"``, and ``checked`` / ``ratified_on`` are non-future ISO dates with
  ``ratified_by`` set.
"""

from __future__ import annotations

import datetime as datetime_module
import json
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.adapters.postgres.corpus_entry import CorpusEntry, add_corpus_entry
from shell.adapters.postgres.export_record import ExportRecord, store_export_record
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme
from shell.adapters.postgres.style_guide import StyleGuide, create_style_guide_version
from shell.config import Environment, Settings
from shell.http.app import create_app, get_session
from shell.http.auth import SESSION_COOKIE_NAME, sign_session
from shell.http.routes.backup import _BACKUP_MODELS
from shell.restore import (
    RestoreTargetNotEmptyError,
    _main,
    load_backup,
    restore_backup,
)
from tests._release_validation import REPO_ROOT, assert_record_not_stale, load_record_meta
from tests.test_runner_driver import _create_client_and_chart, _drive

RECORD_FILE = REPO_ROOT / "docs" / "release-validation" / "restore-rehearsal.md"

#: Max age of `checked` before the record is flagged stale (epic-8-retro-item-62).
_MAX_RECORD_AGE_DAYS = 550

AUTH_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
    "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
)
SESSION_SECRET_KEY = "test-session-secret-key-at-least-32-chars-long"

LOCAL = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=AUTH_PASSWORD_HASH,
    session_secret_key=SESSION_SECRET_KEY,
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
)

#: Every ``model_dump(mode="json")`` string that Pydantic coercion turns back
#: into a ``Decimal`` typed column on restore. SQLite's ``NUMERIC`` affinity
#: reads a stored ``Decimal`` back zero-padded ("32.7358" -> "32.7358000000"),
#: so these columns are compared numerically, not as strings -- the spec asks
#: for ``Decimal`` *field* equality here, and byte-identity only for the JSON
#: columns. (``tests/test_http_backup.py`` compares the same columns the same
#: way, for the same reason.)
_DECIMAL_COLUMNS = frozenset({"latitude", "longitude", "ascendant", "midheaven"})

_TABLE_NAMES = tuple(model.__tablename__ for model in _BACKUP_MODELS)


# --- Engines / source population ----------------------------------------------


def _plain_engine():
    """An in-memory SQLite engine with a shared connection -- the source DB,
    mirroring ``tests/test_runner_driver.py``'s own engine (no FK pragma, so
    ``_drive``'s helpers behave exactly as they do there)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _fk_enforcing_engine():
    """An in-memory SQLite engine with ``PRAGMA foreign_keys=ON`` on every
    connection and a ``StaticPool`` so one connection is shared across the
    fixture thread and ``TestClient``'s worker thread -- the **restore
    target**, mirroring ``tests/test_http_backup.py``'s ``db_session`` fixture
    plus the FK pragma the spec requires so the ``_BACKUP_MODELS`` insert
    order is genuinely exercised."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001, ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    return engine


def _serialize_as_backup(session: Session) -> dict[str, list[dict[str, object]]]:
    """The exact serialization ``shell/http/routes/backup.py::download_backup``
    performs -- every row of every ``_BACKUP_MODELS`` table, ``order_by(id)``,
    ``model_dump(mode="json")``, keyed by ``__tablename__`` -- minus the
    ``store_backup_record`` / ``commit`` / ``Response`` wrapping that is not
    part of the serialization restore has to invert."""
    return {
        model.__tablename__: [
            row.model_dump(mode="json")
            for row in session.exec(select(model).order_by(model.id))
        ]
        for model in _BACKUP_MODELS
    }


def _populate_source(session: Session) -> UUID:
    """A full-depth source DB: a real ``gate_passed`` run (Client -> Natal
    Chart -> ReportRun -> Report / Payload / Draft / Theme / GateResult) plus a
    second ``StyleGuide`` version, a paired ``CorpusEntry`` and an
    ``ExportRecord`` -- the "fully populated database" the AC names. Returns
    the ``run_id`` that reached ``gate_passed``."""
    client, natal_chart = _create_client_and_chart(session)  # + StyleGuide v1
    stored_chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Pass the *real* persisted chart id (not test_runner_driver's placeholder
    # uuid4) so the run's natal_chart_id points at a row that exists -- the
    # restore's FK-enforcing target would otherwise reject a dangling one.
    result = _drive(session, run, natal_chart, natal_chart_id=stored_chart.id)
    assert result.stage == "gate_passed", (
        f"source run did not reach gate_passed (got {result.stage!r}) -- test is vacuous"
    )

    create_style_guide_version(session, "Seconda versione della guida di stile.")
    add_corpus_entry(
        session, content="Cara cliente, il mese scorso...", client_id=client.id
    )
    stored_report = session.exec(
        select(Report).where(Report.report_run_id == run.id)
    ).one()
    store_export_record(session, report=stored_report, format="pdf", elapsed_seconds=42)
    session.commit()
    return run.id


def _assert_table_fidelity(
    table_name: str,
    source_rows: list[dict[str, object]],
    restored_rows: list[dict[str, object]],
) -> None:
    assert len(restored_rows) == len(source_rows), (
        f"{table_name}: restored {len(restored_rows)} rows, source had {len(source_rows)}"
    )
    source_by_id = {row["id"]: row for row in source_rows}
    restored_by_id = {row["id"]: row for row in restored_rows}
    assert restored_by_id.keys() == source_by_id.keys(), (
        f"{table_name}: restored row ids differ from source row ids"
    )
    for row_id, source_row in source_by_id.items():
        restored_row = restored_by_id[row_id]
        assert restored_row.keys() == source_row.keys(), (
            f"{table_name} row {row_id}: column set changed on restore"
        )
        for column, source_value in source_row.items():
            restored_value = restored_row[column]
            if column in _DECIMAL_COLUMNS and source_value is not None:
                assert Decimal(restored_value) == Decimal(source_value), (
                    f"{table_name} row {row_id}: {column} {restored_value!r} != {source_value!r}"
                )
            else:
                assert restored_value == source_value, (
                    f"{table_name} row {row_id}: {column} {restored_value!r} != "
                    f"{source_value!r} (JSON columns must be byte-identical; "
                    "UUID/datetime fields must round-trip equal)"
                )


# --- Round trip: full pipeline export into an empty target -------------------


def test_full_pipeline_export_restores_every_table_with_byte_identical_json() -> None:
    """I/O & Edge-Case Matrix row 1: a ``GET /backup`` export from a fully
    populated database, restored into an empty schema, reconstructs every
    ``_BACKUP_MODELS`` table with the same row count and byte-identical
    JSON-column values; the caller commits once."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, backup)
        target_session.commit()

    # Every table with source rows was inserted; the per-table summary matches.
    assert counts == {name: len(backup[name]) for name in _TABLE_NAMES}
    assert counts["client"] == 1
    assert counts["natal_chart"] == 1
    assert counts["report_run"] == 1
    assert counts["report"] == 1
    assert counts["report_payload"] == 1
    assert counts["report_draft"] == 1
    assert counts["report_theme"] == 1
    assert counts["gate_result"] == 1
    assert counts["export_record"] == 1
    assert counts["corpus_entry"] == 1
    assert counts["style_guide"] == 2

    # Read the target back through a fresh session (a real DB round trip) and
    # re-serialize it the same way -- every table must match the source export.
    with Session(target_engine) as verify_session:
        restored = _serialize_as_backup(verify_session)
    for table_name in _TABLE_NAMES:
        _assert_table_fidelity(table_name, backup[table_name], restored[table_name])


def test_restore_backup_does_not_commit_the_caller_owns_the_transaction() -> None:
    """Boundaries / AC 1: ``restore_backup`` flushes per table but never
    commits -- the caller (the CLI, or a test) owns the transaction and
    commits exactly once."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    restoring_session = Session(target_engine)
    commit_calls: list[int] = []
    real_commit = restoring_session.commit

    def _counting_commit() -> None:
        commit_calls.append(1)
        real_commit()

    restoring_session.commit = _counting_commit  # type: ignore[method-assign]

    counts = restore_backup(restoring_session, backup)
    assert commit_calls == [], "restore_backup committed on its own -- the caller must own that"
    assert sum(counts.values()) > 0

    restoring_session.commit()
    assert commit_calls == [1], "the caller commits exactly once"
    restoring_session.close()

    # A fresh session on a fresh connection sees the committed rows.
    with Session(target_engine) as verify_session:
        assert len(verify_session.exec(select(Client)).all()) == 1
        assert len(verify_session.exec(select(StyleGuide)).all()) == 2


def test_typed_fields_uuid_datetime_and_decimal_round_trip() -> None:
    """I/O & Edge-Case Matrix row 8: JSON-mode strings for ``UUID``, ISO
    ``datetime`` and ``Decimal`` lat/long are coerced back to real types on
    restore -- ``UUID`` / aware ``datetime`` / ``Decimal`` round-trip equal."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        run_id = _populate_source(source_session)
        source_client = source_session.exec(select(Client)).one()
        source_chart = source_session.exec(select(StoredNatalChart)).one()
        source_run = source_session.get(ReportRun, run_id)
        source_created_at = source_run.created_at
        source_month_start_utc = source_run.month_start_utc
        source_latitude = source_client.latitude
        # `_create_client_and_chart` runs a real `compute_natal_chart`, so
        # `ascendant`/`midheaven` are genuine non-null `Decimal` columns
        # (P13) -- assert one of them round-trips, alongside `latitude`.
        source_ascendant = source_chart.ascendant
        assert isinstance(source_ascendant, Decimal)
        source_client_id = source_client.id
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        restore_backup(target_session, backup)
        target_session.commit()

    with Session(target_engine) as verify_session:
        restored_client = verify_session.exec(select(Client)).one()
        restored_chart = verify_session.exec(select(StoredNatalChart)).one()
        restored_run = verify_session.get(ReportRun, run_id)

    assert isinstance(restored_client.id, UUID)
    assert restored_client.id == source_client_id

    assert isinstance(restored_client.latitude, Decimal)
    assert restored_client.latitude == source_latitude
    assert isinstance(restored_client.longitude, Decimal)

    assert isinstance(restored_chart.ascendant, Decimal)
    assert restored_chart.ascendant == source_ascendant

    assert isinstance(restored_run.created_at, datetime_module.datetime)
    assert restored_run.created_at.tzinfo is not None
    assert restored_run.created_at == source_created_at

    assert isinstance(restored_run.month_start_utc, datetime_module.datetime)
    assert restored_run.month_start_utc.tzinfo is not None
    assert restored_run.month_start_utc == source_month_start_utc


# --- Round trip: the Report reopens, Claims stay traceable ------------------


def _authenticated_client(engine) -> TestClient:
    app: FastAPI = create_app(LOCAL)
    session = Session(engine)
    app.dependency_overrides[get_session] = lambda: session
    test_client = TestClient(app)
    expires_at = int(time.time()) + 3600
    test_client.cookies.set(
        SESSION_COOKIE_NAME, sign_session(expires_at, LOCAL.session_secret_key)
    )
    return test_client


def test_report_reopens_after_restore() -> None:
    """I/O & Edge-Case Matrix row 2: on the restored database,
    ``GET /report-runs/{run_id}/report`` for a run that had passed the Gate
    before the export returns 200 (the eight Sections rendered from the
    restored Payload), and ``GET /report-runs/{run_id}/payload`` resolves."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        run_id = _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        restore_backup(target_session, backup)
        target_session.commit()

    client = _authenticated_client(target_engine)
    report_response = client.get(f"/report-runs/{run_id}/report")
    assert report_response.status_code == 200

    payload_response = client.get(f"/report-runs/{run_id}/payload")
    assert payload_response.status_code == 200


def test_claims_are_traceable_after_restore() -> None:
    """I/O & Edge-Case Matrix row 3: the restored passing ``StoredGateResult``
    for that run has ``passed is True``, ``violations == []`` and its
    ``vocabulary_version`` intact -- so every Claim in the reopened Report is
    still traceable to the restored Payload."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        run_id = _populate_source(source_session)
        source_gate = source_session.exec(
            select(StoredGateResult).where(StoredGateResult.report_run_id == run_id)
        ).one()
        source_vocabulary_version = source_gate.vocabulary_version
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        restore_backup(target_session, backup)
        target_session.commit()

    with Session(target_engine) as verify_session:
        restored_gate = verify_session.exec(
            select(StoredGateResult).where(StoredGateResult.report_run_id == run_id)
        ).one()
        restored_payload = verify_session.exec(
            select(ReportPayload).where(ReportPayload.report_run_id == run_id)
        ).one()

    assert restored_gate.passed is True
    assert restored_gate.violations == []
    assert restored_gate.vocabulary_version == source_vocabulary_version
    assert restored_payload.payload  # the Payload the Claims resolve against survived


# --- Round trip: refusals, no-ops, forward-compat --------------------------


def test_empty_export_into_empty_target_is_a_noop() -> None:
    """I/O & Edge-Case Matrix row 4: every table key present, each ``[]`` --
    restore is a no-op and the summary reports 0 for every table."""
    target_engine = _fk_enforcing_engine()
    empty_export = {name: [] for name in _TABLE_NAMES}
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, empty_export)
        target_session.commit()

    assert counts == {name: 0 for name in _TABLE_NAMES}
    with Session(target_engine) as verify_session:
        for model in _BACKUP_MODELS:
            assert verify_session.exec(select(model)).all() == []


def test_non_empty_target_raises_before_writing_anything() -> None:
    """I/O & Edge-Case Matrix row 5: a target already holding any
    ``_BACKUP_MODELS`` row makes ``restore_backup`` raise
    ``RestoreTargetNotEmptyError`` before inserting anything."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        # One pre-existing row anywhere in the covered set is enough.
        target_session.add(
            StyleGuide(version=1, content="A row that was already here.")
        )
        target_session.commit()

        with pytest.raises(RestoreTargetNotEmptyError) as caught:
            restore_backup(target_session, backup)
        assert "style_guide" in str(caught.value)
        target_session.rollback()

    with Session(target_engine) as verify_session:
        # Nothing from the backup was written -- not even the tables that
        # precede style_guide in _BACKUP_MODELS order.
        assert verify_session.exec(select(Client)).all() == []
        assert verify_session.exec(select(ReportRun)).all() == []
        assert len(verify_session.exec(select(StyleGuide)).all()) == 1


def test_a_table_key_absent_from_the_file_restores_as_zero_rows() -> None:
    """I/O & Edge-Case Matrix row 6: an export predating a table joining
    ``/backup`` (its key simply absent) restores that table as 0 rows; the
    others are unaffected."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    backup_without_style_guide = {
        name: rows for name, rows in backup.items() if name != "style_guide"
    }

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, backup_without_style_guide)
        target_session.commit()

    assert counts["style_guide"] == 0
    assert counts["client"] == 1
    assert counts["report_run"] == 1
    with Session(target_engine) as verify_session:
        assert verify_session.exec(select(StyleGuide)).all() == []
        assert len(verify_session.exec(select(Client)).all()) == 1


def test_fk_safe_order_is_exercised_with_foreign_keys_enforced() -> None:
    """I/O & Edge-Case Matrix row 7: with ``PRAGMA foreign_keys=ON`` on the
    target, inserting the export's arrays in ``_BACKUP_MODELS`` order never
    references a missing foreign key -- a regression in that order would raise
    ``IntegrityError`` here."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        run_id = _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        restore_backup(target_session, backup)  # no IntegrityError
        target_session.commit()

    with Session(target_engine) as verify_session:
        run = verify_session.get(ReportRun, run_id)
        assert verify_session.get(Client, run.client_id) is not None
        assert verify_session.get(StoredNatalChart, run.natal_chart_id) is not None
        export_record = verify_session.exec(select(ExportRecord)).one()
        assert verify_session.get(Report, export_record.report_id) is not None
        corpus_entry = verify_session.exec(select(CorpusEntry)).one()
        assert verify_session.get(Client, corpus_entry.client_id) is not None
        theme = verify_session.exec(select(StoredReportTheme)).one()
        assert theme.report_run_id == run_id
        draft = verify_session.exec(select(ReportDraft)).one()
        assert draft.report_run_id == run_id


# --- load_backup: malformed export files ----------------------------------


def test_load_backup_rejects_a_file_that_is_not_json(tmp_path: Path) -> None:
    """I/O & Edge-Case Matrix row 9: not JSON -> ``load_backup`` raises,
    naming the offending path."""
    bad = tmp_path / "not-a-backup.json"
    bad.write_text("this is not json {", encoding="utf-8")
    with pytest.raises(RuntimeError) as caught:
        load_backup(bad)
    assert str(bad) in str(caught.value)


def test_load_backup_rejects_a_json_file_whose_top_level_is_not_an_object(
    tmp_path: Path,
) -> None:
    """I/O & Edge-Case Matrix row 9: top level not an object -> ``load_backup``
    raises, naming the offending path."""
    bad = tmp_path / "array-backup.json"
    bad.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(RuntimeError) as caught:
        load_backup(bad)
    assert str(bad) in str(caught.value)


def test_load_backup_rejects_a_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    with pytest.raises(RuntimeError) as caught:
        load_backup(missing)
    assert str(missing) in str(caught.value)


def test_load_backup_reads_a_well_formed_export(tmp_path: Path) -> None:
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)
    path = tmp_path / "backup-20260827T101500Z.json"
    path.write_text(json.dumps(backup), encoding="utf-8")

    loaded = load_backup(path)

    assert set(loaded.keys()) == set(_TABLE_NAMES)
    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, loaded)
        target_session.commit()
    assert counts["client"] == 1


def test_restore_backup_rejects_a_non_mapping_backup() -> None:
    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session, pytest.raises(RuntimeError):
        restore_backup(target_session, ["not", "a", "mapping"])  # type: ignore[arg-type]


def test_restore_backup_rejects_an_unknown_top_level_key() -> None:
    """P1: a top-level key this build does not recognise (a newer schema's
    table, or a stray ``place_cache`` / ``backup_record``) has nowhere to go
    -- ``restore_backup`` raises ``RuntimeError`` naming it rather than
    silently dropping those rows."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)
    backup["place_cache"] = []

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session, pytest.raises(RuntimeError) as caught:
        restore_backup(target_session, backup)
    assert "place_cache" in str(caught.value)

    with Session(target_engine) as verify_session:
        assert verify_session.exec(select(Client)).all() == []


def test_restore_backup_rejects_a_table_value_that_is_not_a_list() -> None:
    """P2: a known table whose value is not a JSON array (``{...}`` or a
    string) would iterate dict keys / string chars into ``model_validate`` --
    ``restore_backup`` raises ``RuntimeError`` naming the table and the type
    instead."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)
    backup["client"] = {"id": "not-a-list-of-rows"}  # type: ignore[assignment]

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session, pytest.raises(RuntimeError) as caught:
        restore_backup(target_session, backup)
    assert "client" in str(caught.value)
    assert "dict" in str(caught.value)


def test_a_mid_restore_failure_names_the_table_and_rolls_the_whole_restore_back() -> None:
    """P3: force a real failure partway through -- empty the ``client`` list so
    every client-scoped table's rows dangle under FK enforcement.
    ``restore_backup`` re-raises as ``RuntimeError`` naming the table it died
    on, and after the caller ``rollback()`` the target is completely empty
    (the "whole restore rolls back" claim, not just the pre-write guard)."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    broken = {name: (list(rows) if name != "client" else []) for name, rows in backup.items()}

    target_engine = _fk_enforcing_engine()
    restoring_session = Session(target_engine)
    with pytest.raises(RuntimeError) as caught:
        restore_backup(restoring_session, broken)

    message = str(caught.value)
    assert message.startswith("restore: failed while inserting table ")
    # `corpus_entry` is the first client-FK table with rows in _BACKUP_MODELS
    # order, so it is where the dangling-FK insert dies.
    assert "'corpus_entry'" in message
    assert not isinstance(caught.value, RestoreTargetNotEmptyError)

    restoring_session.rollback()
    restoring_session.close()

    with Session(target_engine) as verify_session:
        for model in _BACKUP_MODELS:
            assert verify_session.exec(select(model)).all() == [], (
                f"{model.__tablename__} still holds rows after a rolled-back restore"
            )


def test_round_trip_through_the_real_backup_route_reopens_the_report(tmp_path: Path) -> None:
    """P7: bind the round trip to the *real* ``download_backup`` serializer --
    populate a source DB, download ``GET /backup`` through the app, write the
    response body to a file, then ``load_backup`` -> ``restore_backup`` into an
    empty FK-enforcing target and assert the Report reopens (200). Guards
    against ``_serialize_as_backup`` drifting from the route it copies."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        run_id = _populate_source(source_session)

    source_client = _authenticated_client(source_engine)
    backup_response = source_client.get("/backup")
    assert backup_response.status_code == 200
    backup_file = tmp_path / "backup-from-the-route.json"
    backup_file.write_bytes(backup_response.content)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, load_backup(backup_file))
        target_session.commit()
    assert counts["report"] == 1

    target_client = _authenticated_client(target_engine)
    assert target_client.get(f"/report-runs/{run_id}/report").status_code == 200
    assert target_client.get(f"/report-runs/{run_id}/payload").status_code == 200


# --- The operator CLI (_main), driven in process -------------------------------


def _cli_engine(monkeypatch: pytest.MonkeyPatch):
    """An FK-enforcing in-memory engine that ``shell.restore._main`` will use
    instead of a real Postgres one: ``create_engine`` is patched to return it,
    and its ``dispose`` is neutered so ``_main``'s ``finally`` block does not
    drop the in-memory database before the test can inspect it."""
    engine = _fk_enforcing_engine()
    monkeypatch.setattr(engine, "dispose", lambda: None)
    monkeypatch.setattr("shell.restore.create_engine", lambda *a, **k: engine)
    return engine


def _backup_file(tmp_path: Path, name: str = "backup.json") -> tuple[Path, int]:
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)
    path = tmp_path / name
    path.write_text(json.dumps(backup), encoding="utf-8")
    return path, sum(len(rows) for rows in backup.values())


def test_cli_restores_into_an_empty_target_and_prints_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P6: ``_main`` against an empty target restores every table, commits,
    prints the per-table summary, and exits 0."""
    engine = _cli_engine(monkeypatch)
    path, total = _backup_file(tmp_path)

    exit_code = _main([str(path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert f"restored {total} row(s)" in out
    assert "client: 1" in out
    assert "style_guide: 2" in out
    with Session(engine) as verify_session:
        assert len(verify_session.exec(select(Client)).all()) == 1


def test_cli_exits_2_when_the_target_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5/P6: a non-empty target is a distinct, operator-recoverable failure
    -- exit code 2."""
    engine = _cli_engine(monkeypatch)
    with Session(engine) as seed_session:
        seed_session.add(StyleGuide(version=1, content="Already here."))
        seed_session.commit()
    path, _ = _backup_file(tmp_path)

    exit_code = _main([str(path)])

    assert exit_code == 2
    assert "restore aborted" in capsys.readouterr().out


def test_cli_exits_1_on_a_malformed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5/P6: any non-precondition failure exits 1."""
    _cli_engine(monkeypatch)
    bad = tmp_path / "garbage.json"
    bad.write_text("not json at all {", encoding="utf-8")

    exit_code = _main([str(bad)])

    assert exit_code == 1
    assert "restore failed" in capsys.readouterr().out


def test_cli_traceback_flag_prints_a_stack_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P4: ``--traceback`` adds the full Python traceback to a failure."""
    _cli_engine(monkeypatch)
    bad = tmp_path / "garbage.json"
    bad.write_text("not json at all {", encoding="utf-8")

    exit_code = _main(["--traceback", str(bad)])

    assert exit_code == 1
    err = capsys.readouterr()
    assert "Traceback (most recent call last)" in (err.out + err.err)


def test_cli_dry_run_writes_nothing_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P10: ``--dry-run`` validates the file and the empty target, prints the
    counts it *would* insert, and exits 0 without writing."""
    engine = _cli_engine(monkeypatch)
    path, total = _backup_file(tmp_path)

    exit_code = _main(["--dry-run", str(path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "dry run" in out
    assert f"would restore {total} row(s)" in out
    with Session(engine) as verify_session:
        assert verify_session.exec(select(Client)).all() == []


def test_cli_dry_run_warns_when_the_backup_has_no_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P10: an all-empty backup file gets a prominent "is this the right
    file?" warning."""
    _cli_engine(monkeypatch)
    from shell.restore import _backup_models

    empty = {model.__tablename__: [] for model in _backup_models()}
    path = tmp_path / "empty-backup.json"
    path.write_text(json.dumps(empty), encoding="utf-8")

    exit_code = _main(["--dry-run", str(path)])

    assert exit_code == 0
    assert "contains no rows for any known table" in capsys.readouterr().out


def test_cli_requires_the_backup_file_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """P6: argparse rejects a missing positional / prints --help via SystemExit."""
    _cli_engine(monkeypatch)
    with pytest.raises(SystemExit):
        _main([])
    with pytest.raises(SystemExit):
        _main(["--help"])


# --- Record guard: docs/release-validation/restore-rehearsal.md -------------
# The ```toml``` scaffolding is shared via tests/_release_validation.py.

_EXPECTED_KEYS = {
    "checked",
    "ratified_by",
    "ratified_on",
    "source_backup",
    "target",
    "tables_restored",
    "rows_restored",
    "report_reopened",
    "claims_traceable",
    "outcome",
}


@pytest.fixture(scope="module")
def meta() -> dict[str, object]:
    return load_record_meta(RECORD_FILE, record_label="restore-rehearsal")


def test_record_exists() -> None:
    assert RECORD_FILE.exists(), (
        f"release-validation restore-rehearsal record missing: {RECORD_FILE} -- "
        "Story 8.5 requires a dated, ratified record of the restore rehearsal"
    )


def test_record_is_not_stale(meta: dict[str, object]) -> None:
    assert_record_not_stale(
        meta, max_age_days=_MAX_RECORD_AGE_DAYS, record_label="restore-rehearsal"
    )


def test_toml_block_parses(meta: dict[str, object]) -> None:
    missing = _EXPECTED_KEYS - meta.keys()
    unexpected = meta.keys() - _EXPECTED_KEYS
    assert not missing, f"restore-rehearsal toml block missing keys: {sorted(missing)}"
    assert not unexpected, (
        f"restore-rehearsal toml block has unexpected keys: {sorted(unexpected)} -- "
        "update _EXPECTED_KEYS and the matching assertions if a key was added on purpose"
    )


def test_checked_is_a_non_future_date(meta: dict[str, object]) -> None:
    checked = meta["checked"]
    assert isinstance(checked, datetime_module.date), (
        f"`checked` must be a bare ISO date (parses to datetime.date), got {checked!r}"
    )
    assert checked <= datetime_module.date.today(), (
        f"`checked` = {checked.isoformat()} is in the future -- a rehearsal cannot "
        "have happened yet"
    )


def test_ratified_on_is_a_non_future_date_with_ratified_by_set(
    meta: dict[str, object],
) -> None:
    ratified_on = meta["ratified_on"]
    assert isinstance(ratified_on, datetime_module.date), (
        f"`ratified_on` must be a bare ISO date, got {ratified_on!r}"
    )
    assert ratified_on <= datetime_module.date.today(), (
        f"`ratified_on` = {ratified_on.isoformat()} is in the future"
    )
    assert isinstance(meta["ratified_by"], str) and meta["ratified_by"].strip(), (
        f"`ratified_by` must be a non-empty string, got {meta['ratified_by']!r}"
    )


def test_source_backup_and_target_are_described(meta: dict[str, object]) -> None:
    for key in ("source_backup", "target"):
        assert isinstance(meta[key], str) and meta[key].strip(), (
            f"`{key}` must be a non-empty string describing the rehearsal, got {meta[key]!r}"
        )


def test_tables_restored_equals_the_backup_model_table_names(
    meta: dict[str, object],
) -> None:
    """A table added to ``/backup`` (``_BACKUP_MODELS``) but not re-rehearsed
    must fail this suite -- the guard binds ``tables_restored`` to the sorted
    ``__tablename__``s of ``_BACKUP_MODELS``."""
    assert meta["tables_restored"] == sorted(_TABLE_NAMES), (
        f"`tables_restored` {meta['tables_restored']!r} != sorted _BACKUP_MODELS "
        f"table names {sorted(_TABLE_NAMES)!r} -- re-run the restore rehearsal when "
        "a table joins or leaves GET /backup"
    )


def test_rows_restored_is_a_non_negative_int(meta: dict[str, object]) -> None:
    rows_restored = meta["rows_restored"]
    assert isinstance(rows_restored, int) and not isinstance(rows_restored, bool), (
        f"`rows_restored` must be an integer, got {rows_restored!r}"
    )
    assert rows_restored >= 0, f"`rows_restored` cannot be negative: {rows_restored}"


def test_rows_restored_matches_the_round_trip_count(meta: dict[str, object]) -> None:
    """P8: the record's ``rows_restored`` is the total the round-trip actually
    restores -- rebuild it here so a stale hand-typed value cannot drift."""
    source_engine = _plain_engine()
    with Session(source_engine) as source_session:
        _populate_source(source_session)
        backup = _serialize_as_backup(source_session)

    target_engine = _fk_enforcing_engine()
    with Session(target_engine) as target_session:
        counts = restore_backup(target_session, backup)
        target_session.commit()

    assert sum(counts.values()) == meta["rows_restored"], (
        f"record `rows_restored` = {meta['rows_restored']} but the round trip "
        f"restores {sum(counts.values())} rows -- update the record block"
    )


def test_report_reopened_and_claims_traceable_are_true(meta: dict[str, object]) -> None:
    assert meta["report_reopened"] is True, (
        "`report_reopened` must be true -- Story 8.5 requires a previously exported "
        "Report reopened after the restore"
    )
    assert meta["claims_traceable"] is True, (
        "`claims_traceable` must be true -- the reopened Report's Claims must still "
        "trace to its restored Payload"
    )


def test_outcome_is_valid(meta: dict[str, object]) -> None:
    assert meta["outcome"] in {"pass", "blocked"}, (
        f'`outcome` must be exactly "pass" or "blocked", got {meta["outcome"]!r}'
    )


def test_outcome_permits_release(meta: dict[str, object]) -> None:
    assert meta["outcome"] == "pass", (
        "release blocked until the restore rehearsal passes "
        f'(outcome = {meta["outcome"]!r}, expected "pass")'
    )
