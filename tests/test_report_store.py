"""``Report`` (Story 5.3): an in-memory SQLite engine stands in for Postgres,
mirroring ``tests/test_report_draft_store.py``. Covers the row's own shape,
``store_report()``'s writes, the ``before_update`` immutability guard,
uniqueness on ``report_run_id``, and that ``report`` joins the FR-29
Client-deletion cascade.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py and tests/test_report_draft_store.py use.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

# A stand-in for ``GateVocabulary.content_hash`` -- a 64-char sha256 hex
# digest (epic-5-retro item 45).
_VOCABULARY_CONTENT_HASH = hashlib.sha256(b"epic-5-retro-item-45").hexdigest()


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_client(session: Session, *, name: str = "Ada Lovelace") -> Client:
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
    return create_client_with_chart(
        session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _create_run(session: Session, client: Client) -> ReportRun:
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()
    return run


# --- Report row shape --------------------------------------------------------


def test_a_report_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_report_persists_identity_and_every_recorded_version(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report(
        session,
        run=run,
        style_guide_version=3,
        payload_schema_version=2,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    reloaded = session.get(Report, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.style_guide_version == 3
    assert reloaded.payload_schema_version == 2
    assert reloaded.gate_vocabulary_version == 1
    assert reloaded.gate_vocabulary_content_hash == _VOCABULARY_CONTENT_HASH
    assert reloaded.created_at is not None


def test_store_report_persists_the_gate_vocabulary_content_hash(session: Session) -> None:
    """The digest threaded from ``GateVocabulary.content_hash`` survives a
    write/read round-trip on its own column (epic-5-retro item 45)."""
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    reloaded = session.get(Report, stored.id)
    assert reloaded is not None
    assert reloaded.gate_vocabulary_content_hash == _VOCABULARY_CONTENT_HASH


def test_a_report_row_written_without_the_hash_reads_back_none(session: Session) -> None:
    """A row inserted before migration ``0021`` -- modelled here by building
    ``Report`` directly without the new field -- reads the new column as
    ``None``, never crashing (epic-5-retro item 45; mirrors ``0020``'s
    nullable ``month``)."""
    client = _create_client(session)
    run = _create_run(session, client)

    report = Report(
        client_id=client.id,
        report_run_id=run.id,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
    )
    session.add(report)
    session.commit()

    reloaded = session.get(Report, report.id)
    assert reloaded is not None
    assert reloaded.gate_vocabulary_content_hash is None


def test_store_report_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    stored_id = stored.id
    session.rollback()

    assert session.get(Report, stored_id) is None


# --- Immutability --------------------------------------------------------------


def test_mutating_and_committing_a_persisted_report_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    stored.style_guide_version = 99
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- Uniqueness ------------------------------------------------------------------


def test_a_second_report_for_the_same_report_run_id_raises_integrity_error(
    session: Session,
) -> None:
    """Exactly one ``Report`` per ``ReportRun``, enforced by a unique index
    on ``report_run_id`` -- not merely by ``store_report()`` only ever being
    called once per ``ReportRun`` in ``shell/runner/driver.py``'s
    ``gate_passed`` stage."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    with pytest.raises(IntegrityError):
        store_report(
            session,
            run=run,
            style_guide_version=1,
            payload_schema_version=1,
            gate_vocabulary_version=1,
            gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
        )

    session.rollback()


def test_two_report_runs_for_one_client_each_get_their_own_report_row(session: Session) -> None:
    client = _create_client(session)
    first_run = _create_run(session, client)
    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()

    store_report(
        session,
        run=first_run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    store_report(
        session,
        run=second_run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    stored_reports = session.exec(select(Report).where(Report.client_id == client.id)).all()
    assert {stored.report_run_id for stored in stored_reports} == {first_run.id, second_run.id}


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_reports(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None
    assert session.get(Report, stored.id) is None


def test_delete_client_and_derived_does_not_persist_report_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash=_VOCABULARY_CONTENT_HASH,
    )
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(Report, stored.id) is not None


def test_the_cascade_constant_includes_report() -> None:
    """Story 5.3: ``report`` must join ``_CLIENT_CASCADE_TABLES`` -- a
    regression on top of the general invariant test in
    ``tests/test_client_store.py``, naming the table this story added
    explicitly."""
    assert "report" in client_module._CLIENT_CASCADE_TABLES


def test_every_table_with_a_client_id_foreign_key_includes_report() -> None:
    tables_with_client_fk = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table.name == "client" and foreign_key.column.name == "id"
    }
    assert "report" in tables_with_client_fk
