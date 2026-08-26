"""``ExportRecord`` (Story 6.2): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_gate_result_store.py``. Covers the row's
own shape, ``store_export_record()``'s write, the ``before_update``
immutability guard, and that ``export_record`` joins the FR-29
Client-deletion cascade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

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
from shell.adapters.postgres.export_record import ExportRecord, store_export_record
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
    )
    session.commit()
    return client, run, report


# --- ExportRecord row shape ------------------------------------------------


def test_an_export_record_id_is_uuidv7(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf")
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_export_record_persists_the_export(session: Session) -> None:
    client, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf")
    session.commit()

    reloaded = session.get(ExportRecord, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_id == report.id
    assert reloaded.format == "pdf"
    assert reloaded.created_at is not None


def test_store_export_record_only_flushes_never_commits(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf")
    stored_id = stored.id
    session.rollback()

    assert session.get(ExportRecord, stored_id) is None


def test_a_report_can_be_exported_more_than_once(session: Session) -> None:
    """Unlike ``Report.report_run_id`` (unique), ``ExportRecord.report_id``
    is indexed but not unique -- an export a second time writes a second
    row (this story's Matrix row 4)."""
    _, _run, report = _create_passed_report(session)

    store_export_record(session, report=report, format="pdf")
    store_export_record(session, report=report, format="pdf")
    session.commit()

    stored = session.exec(select(ExportRecord).where(ExportRecord.report_id == report.id)).all()
    assert len(stored) == 2


# --- Immutability ----------------------------------------------------------------


def test_mutating_and_committing_a_persisted_export_record_raises(session: Session) -> None:
    _, _run, report = _create_passed_report(session)

    stored = store_export_record(session, report=report, format="pdf")
    session.commit()

    stored.format = "markdown"
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_export_records(session: Session) -> None:
    client, _run, report = _create_passed_report(session)
    stored = store_export_record(session, report=report, format="pdf")
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
    stored = store_export_record(session, report=report, format="pdf")
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
