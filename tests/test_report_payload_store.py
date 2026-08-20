"""``ReportPayload`` (Story 3.8): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_report_run_store.py``. Covers the row's own
shape, ``store_report_payload()``'s writes, the ``before_update`` immutability
guard, and that ``report_payload`` joins the FR-29 Client-deletion cascade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, SQLModel, create_engine

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.payload.freeze import freeze_payload
from core.types.day_lists import DayLists
from core.types.payload import Payload, SectionPayload
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report_payload import ReportPayload, store_report_payload
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.sections import load_sections_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py and tests/test_report_run_store.py use.
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


def _empty_section() -> SectionPayload:
    return SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )


def _empty_payload() -> Payload:
    return Payload(
        energia_generale=_empty_section(),
        amore=_empty_section(),
        lavoro=_empty_section(),
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )


def _a_frozen_payload() -> dict:
    return freeze_payload(
        _empty_payload(),
        DayLists(giorni_favorevoli=(), giorni_di_attenzione=()),
        config=_COMPUTATION_CONFIG,
        sections_config=_SECTIONS_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


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


# --- ReportPayload row shape --------------------------------------------------


def test_a_report_payload_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_payload(session, run=run, frozen=_a_frozen_payload())
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_report_payload_persists_identity_metadata_and_the_whole_frozen_dict(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    frozen = _a_frozen_payload()

    stored = store_report_payload(session, run=run, frozen=frozen)
    session.commit()

    reloaded = session.get(ReportPayload, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.schema_version == frozen["schema_version"]
    assert reloaded.computation_config_version == frozen["computation_config_version"]
    assert reloaded.computation_config_content_hash == frozen["computation_config_content_hash"]
    assert reloaded.sections_config_version == frozen["sections_config_version"]
    assert reloaded.sections_config_content_hash == frozen["sections_config_content_hash"]
    assert reloaded.ephemeris_files == frozen["ephemeris_files"]
    assert reloaded.payload == frozen
    assert reloaded.created_at is not None


def test_store_report_payload_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_payload(session, run=run, frozen=_a_frozen_payload())
    stored_id = stored.id
    session.rollback()

    assert session.get(ReportPayload, stored_id) is None


# --- Immutability --------------------------------------------------------------


def test_mutating_and_committing_a_persisted_report_payload_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_payload(session, run=run, frozen=_a_frozen_payload())
    session.commit()

    stored.schema_version = 999
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    # The underlying RuntimeError may arrive wrapped by SQLAlchemy's flush
    # machinery (StatementError) depending on dialect -- either way, our own
    # message must be present, proving the guard fired rather than some
    # unrelated failure.
    assert "immutable" in str(caught.value)


# --- Uniqueness --------------------------------------------------------------------


def test_a_second_report_payload_for_the_same_report_run_id_raises_integrity_error(
    session: Session,
) -> None:
    """PRD FR-14: every stored Report has exactly one stored Report Payload --
    enforced by a unique index on `report_run_id`, not merely by
    `store_report_payload()` only ever being called once per `ReportRun` in
    `shell/runner/driver.py`'s `payload_ready` stage."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_report_payload(session, run=run, frozen=_a_frozen_payload())
    session.commit()

    # `store_report_payload()` flushes internally (Boundaries & Constraints:
    # "add()+flush() only"), so the unique-index violation surfaces there,
    # before any explicit `commit()` -- not a separate step after it.
    with pytest.raises(IntegrityError):
        store_report_payload(session, run=run, frozen=_a_frozen_payload())

    session.rollback()


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_report_payloads(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_payload(session, run=run, frozen=_a_frozen_payload())
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None
    assert session.get(ReportPayload, stored.id) is None


def test_delete_client_and_derived_does_not_persist_report_payload_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_payload(session, run=run, frozen=_a_frozen_payload())
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(ReportPayload, stored.id) is not None


def test_every_table_with_a_client_id_foreign_key_includes_report_payload() -> None:
    tables_with_client_fk = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table.name == "client" and foreign_key.column.name == "id"
    }
    assert "report_payload" in tables_with_client_fk
