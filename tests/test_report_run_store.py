"""``ReportRun`` (Story 3.5): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_client_store.py``. Covers the row's own
shape, ``deserialize_natal_chart``'s round trip with ``_serialize``, and
that ``report_run`` joins the FR-29 Client-deletion cascade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    StoredNatalChart,
    create_client_with_chart,
    delete_client_and_derived,
    deserialize_natal_chart,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same real,
# known-good input tests/test_client_store.py already uses.
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


def _a_natal_chart():
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG)


def _create_client(session: Session, *, name: str = "Ada Lovelace") -> Client:
    return create_client_with_chart(
        session,
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_a_natal_chart(),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _current_chart(session: Session, client_id: UUID) -> StoredNatalChart:
    return session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client_id)
    ).one()


# --- ReportRun row shape -----------------------------------------------------------


def test_a_report_run_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    session.commit()

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    assert isinstance(run.id, UUID) and run.id.version == 7


def test_a_fresh_report_run_has_no_stage_and_no_month_boundaries(session: Session) -> None:
    client = _create_client(session)
    session.commit()

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    stored = session.get(ReportRun, run.id)
    assert stored is not None
    assert stored.stage is None
    assert stored.month_start_utc is None
    assert stored.month_end_utc is None
    assert stored.transit_events is None
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_a_report_run_persists_its_stage_and_transit_events(session: Session) -> None:
    client = _create_client(session)
    session.commit()

    run = ReportRun(
        client_id=client.id,
        month="2026-01",
        stage="transits_ready",
        month_start_utc=datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC),
        month_end_utc=datetime(2026, 2, 1, 6, 0, 0, tzinfo=UTC),
        transit_events=[{"kind": "lunation", "occurred_at": "2026-01-13T05:03:12+00:00"}],
    )
    session.add(run)
    session.commit()

    stored = session.get(ReportRun, run.id)
    assert stored is not None
    assert stored.stage == "transits_ready"
    assert stored.month_start_utc == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    assert stored.transit_events == [
        {"kind": "lunation", "occurred_at": "2026-01-13T05:03:12+00:00"}
    ]


# --- deserialize_natal_chart round trip --------------------------------------------


def test_deserialize_natal_chart_round_trips_a_stored_chart(session: Session) -> None:
    original = _a_natal_chart()
    client = create_client_with_chart(
        session,
        name="Grace Hopper",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=original,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()

    stored = _current_chart(session, client.id)
    restored = deserialize_natal_chart(stored)

    assert restored.ascendant == original.ascendant
    assert restored.midheaven == original.midheaven
    assert len(restored.planets) == len(original.planets)
    assert len(restored.houses) == len(original.houses)
    assert len(restored.aspects) == len(original.aspects)

    for restored_planet, original_planet in zip(restored.planets, original.planets, strict=True):
        assert restored_planet == original_planet

    for restored_house, original_house in zip(restored.houses, original.houses, strict=True):
        assert restored_house == original_house

    for restored_aspect, original_aspect in zip(restored.aspects, original.aspects, strict=True):
        assert restored_aspect == original_aspect


def test_deserialize_natal_chart_produces_real_decimal_and_bool_types(session: Session) -> None:
    """Every JSON-decoded field must come back as its real Python type, not
    the string/plain-JSON shape it was stored as -- proves the round trip is
    not merely equal by coincidence of Decimal("x") == "x" never happening to
    be tested."""
    client = _create_client(session)
    session.commit()

    stored = _current_chart(session, client.id)
    restored = deserialize_natal_chart(stored)

    assert isinstance(restored.ascendant, Decimal)
    assert isinstance(restored.midheaven, Decimal)
    for planet in restored.planets:
        assert isinstance(planet.longitude, Decimal)
        assert isinstance(planet.degree, Decimal)
        assert isinstance(planet.house, int)
        assert isinstance(planet.retrograde, bool)
    for house in restored.houses:
        assert isinstance(house.longitude, Decimal)
    for aspect in restored.aspects:
        assert isinstance(aspect.orb, Decimal)
        assert isinstance(aspect.applying, bool)


# --- FR-29 cascade -------------------------------------------------------------------


def test_delete_client_and_derived_removes_its_report_runs(session: Session) -> None:
    client = _create_client(session)
    session.commit()

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None


def test_delete_client_and_derived_removes_multiple_report_runs(session: Session) -> None:
    client = _create_client(session)
    session.commit()

    first = ReportRun(client_id=client.id, month="2026-01")
    second = ReportRun(client_id=client.id, month="2026-02")
    session.add(first)
    session.add(second)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(ReportRun, first.id) is None
    assert session.get(ReportRun, second.id) is None


def test_delete_client_and_derived_does_not_persist_report_run_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    session.commit()

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(ReportRun, run.id) is not None
