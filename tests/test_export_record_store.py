"""``ExportRecord`` (Story 6.2, extended by Story 6.3): an in-memory SQLite
engine stands in for Postgres, mirroring ``tests/test_gate_result_store.py``.
Covers the row's own shape, ``store_export_record()``'s write, the
``before_update`` immutability guard, that ``export_record`` joins the
FR-29 Client-deletion cascade, and (Story 6.3) ``elapsed_seconds``'s
persistence plus ``record_send_disposition()``'s set-once/no-op/missing-row
behavior.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import StatementError
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
from shell.adapters.postgres.export_record import (
    ExportRecord,
    record_send_disposition,
    store_export_record,
)
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_client(session: Session) -> Client:
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
    return create_client_with_chart(
        session,
        name="Ada Lovelace",
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


def _create_passed_report(session: Session) -> tuple[Client, ReportRun, Report]:
    client = _create_client(session)
    run = _create_run(session, client)
    report = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash="e" * 64,
    )
    session.commit()
    return client, run, report


# --- ExportRecord row shape ------------------------------------------------


def test_an_export_record_id_is_uuidv7(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_export_record_persists_the_export(session: Session) -> None:
    client, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_id == report.id
    assert reloaded.format == "pdf"
    assert reloaded.created_at is not None


def test_store_export_record_persists_elapsed_seconds(session: Session) -> None:
    """Story 6.3: ``elapsed_seconds`` is the caller's own computation
    (``download_report_pdf``, Client selection to export) -- this function
    only stores whatever whole-second value it is given."""
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=317)
    session.commit()

    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.elapsed_seconds == 317


def test_a_freshly_stored_export_record_has_no_disposition(session: Session) -> None:
    """Story 6.3: ``disposition`` starts ``NULL`` -- it can only be known
    after Francesco actually sends the Report, later, via
    ``record_send_disposition``."""
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.disposition is None


def test_store_export_record_only_flushes_never_commits(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    stored_id = stored.id
    session.rollback()

    assert session.get(ExportRecord, stored_id) is None


def test_a_report_can_be_exported_more_than_once(session: Session) -> None:
    """Unlike ``Report.report_run_id`` (unique), ``ExportRecord.report_id``
    is indexed but not unique -- an export a second time writes a second
    row (this story's Matrix row 4)."""
    _, _run, report = _create_passed_report(session)

    store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    stored = session.exec(select(ExportRecord).where(ExportRecord.report_id == report.id)).all()
    assert len(stored) == 2


# --- Immutability ----------------------------------------------------------------


def test_mutating_and_committing_a_persisted_export_record_raises(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    stored.format = "markdown"
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- Story 6.3: record_send_disposition -------------------------------------------


def test_record_send_disposition_sets_the_disposition_the_first_time(session: Session) -> None:
    _, run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    updated = record_send_disposition(session, run_id=run.id, disposition="as_generated")
    session.commit()

    assert updated is True
    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.disposition == "as_generated"


def test_record_send_disposition_is_a_no_op_once_already_set(session: Session) -> None:
    """The ``WHERE disposition IS NULL`` clause makes a second call match
    zero rows -- idempotent, not an error, and the first recorded choice is
    never silently overwritten by a second, different one."""
    _, run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    first = record_send_disposition(session, run_id=run.id, disposition="as_generated")
    session.commit()
    second = record_send_disposition(session, run_id=run.id, disposition="edited")
    session.commit()

    assert first is True
    assert second is False
    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.disposition == "as_generated"


def test_record_send_disposition_acts_on_the_latest_export_record(session: Session) -> None:
    """Story 6.3's Boundaries: the route/adapter act on the **latest**
    ``ExportRecord`` for the run, by ``created_at`` descending -- not the
    first one written. Explicit, well-separated ``created_at`` values (built
    directly, bypassing ``store_export_record``'s own ``datetime.now(UTC)``
    default) make the ordering deterministic rather than relying on two
    wall-clock reads landing far enough apart."""
    client, run, report = _create_passed_report(session)
    first_export = ExportRecord(
        client_id=client.id,
        report_id=report.id,
        format="pdf",
        elapsed_seconds=10,
        created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    second_export = ExportRecord(
        client_id=client.id,
        report_id=report.id,
        format="pdf",
        elapsed_seconds=20,
        created_at=datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC),
    )
    session.add(first_export)
    session.add(second_export)
    session.commit()

    updated = record_send_disposition(session, run_id=run.id, disposition="edited")
    session.commit()

    assert updated is True
    reloaded_first = session.get(ExportRecord, first_export.id)
    reloaded_second = session.get(ExportRecord, second_export.id)
    assert reloaded_first is not None and reloaded_first.disposition is None
    assert reloaded_second is not None and reloaded_second.disposition == "edited"


def test_record_send_disposition_returns_false_for_a_run_with_no_export(
    session: Session,
) -> None:
    """No ``ExportRecord`` exists yet for the run's ``Report`` -- the route
    tells this apart from the already-set no-op by checking existence
    itself before calling this function."""
    _, run, _report = _create_passed_report(session)

    updated = record_send_disposition(session, run_id=run.id, disposition="as_generated")

    assert updated is False


def test_record_send_disposition_returns_false_for_an_unknown_run(session: Session) -> None:
    updated = record_send_disposition(session, run_id=uuid4(), disposition="as_generated")

    assert updated is False


def test_record_send_disposition_never_mutates_through_the_orm_object(session: Session) -> None:
    """Sets the column through the Core-level ``UPDATE`` even though the
    row's own ``before_update`` listener unconditionally forbids an
    ORM-driven mutation -- proves this is the deliberate, narrow bypass the
    Design Notes describe, not an accidental change to the guard."""
    _, run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    record_send_disposition(session, run_id=run.id, disposition="as_generated")
    session.commit()  # would raise RuntimeError/StatementError if this went through the ORM

    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.disposition == "as_generated"


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_export_records(session: Session) -> None:
    client, _run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(Report, report.id) is None
    assert session.get(ExportRecord, stored.id) is None


def test_delete_client_and_derived_does_not_persist_export_record_deletion_without_a_commit(
    session: Session,
) -> None:
    client, _run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf", elapsed_seconds=42)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(ExportRecord, stored.id) is not None


def test_the_cascade_constant_includes_export_record() -> None:
    """Story 6.2: ``export_record`` must join ``_CLIENT_CASCADE_TABLES`` --
    a regression on top of the general invariant test in
    ``tests/test_client_store.py``, naming the table this story added
    explicitly."""
    assert "export_record" in client_module._CLIENT_CASCADE_TABLES
