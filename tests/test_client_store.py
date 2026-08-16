"""``Client``/``StoredNatalChart`` -- an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_place_cache.py``. Covers the I/O & Edge-Case
Matrix's persistence rows: AC3 (immutable snapshot, one transaction, UUIDv7),
AC5 (duplicate name), AC6 (ComputationConfig + EphemerisIdentity recorded).
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
from shell.adapters.postgres.client import Client, StoredNatalChart, create_client_with_chart
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- reused as a real,
# known-good input, mirroring tests/test_natal_chart.py's own choice.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),  # CST; not read by create_client_with_chart
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


def _create(session: Session, *, name: str = "Ada Lovelace") -> Client:
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


def test_a_client_and_its_natal_chart_persist_together(session: Session) -> None:
    client = _create(session)
    session.commit()

    assert session.get(Client, client.id) is not None
    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    assert chart is not None


def test_client_and_chart_ids_are_uuidv7(session: Session) -> None:
    client = _create(session)
    session.commit()

    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()

    assert isinstance(client.id, UUID) and client.id.version == 7
    assert isinstance(chart.id, UUID) and chart.id.version == 7


def test_the_client_stores_its_own_immutable_place_snapshot(session: Session) -> None:
    client = _create(session)
    session.commit()

    stored = session.get(Client, client.id)
    assert stored is not None
    assert stored.latitude == _LATITUDE
    assert stored.longitude == _LONGITUDE
    assert stored.iana_zone == "America/Chicago"


def test_nothing_persists_without_an_explicit_commit(session: Session) -> None:
    """``create_client_with_chart()`` only flushes -- the caller decides the
    transaction boundary (AD-16). Rolling back (or simply never committing)
    must leave no row of either table behind."""
    client = _create(session)
    assert session.get(Client, client.id) is not None  # visible within the flush

    session.rollback()

    assert session.get(Client, client.id) is None
    assert (
        session.exec(
            select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
        ).first()
        is None
    )


def test_two_clients_with_the_same_name_persist_as_distinct_rows(session: Session) -> None:
    first = _create(session, name="Maria Mitchell")
    second = _create(session, name="Maria Mitchell")
    session.commit()

    assert first.id != second.id
    assert session.get(Client, first.id) is not None
    assert session.get(Client, second.id) is not None


def test_the_stored_chart_records_the_computation_config_version_and_hash(
    session: Session,
) -> None:
    client = _create(session)
    session.commit()

    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    assert chart.computation_config_version == _COMPUTATION_CONFIG.version
    assert chart.computation_config_content_hash == _COMPUTATION_CONFIG.content_hash


def test_the_stored_chart_records_the_verified_ephemeris_identity(session: Session) -> None:
    client = _create(session)
    session.commit()

    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    assert {file["filename"] for file in chart.ephemeris_files} == {
        file.filename for file in _EPHEMERIS_IDENTITY.files
    }
    assert {file["sha256"] for file in chart.ephemeris_files} == {
        file.sha256 for file in _EPHEMERIS_IDENTITY.files
    }


def test_decimal_fields_inside_the_json_columns_serialize_as_strings(session: Session) -> None:
    """JSON has no native Decimal type -- every Decimal inside
    planets/houses/aspects must round-trip through a string, matching the
    precision-preserving pattern used throughout core/ephemeris/chart.py."""
    client = _create(session)
    session.commit()

    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()

    assert chart.planets, "fixture produced no planets -- test is vacuous"
    for planet in chart.planets:
        assert isinstance(planet["longitude"], str)
        assert isinstance(planet["degree"], str)
        # A round trip through Decimal must not raise and must be exact.
        assert Decimal(planet["longitude"]) >= 0

    for house in chart.houses:
        assert isinstance(house["longitude"], str)

    for aspect in chart.aspects:
        assert isinstance(aspect["orb"], str)


def test_ascendant_and_midheaven_are_recorded(session: Session) -> None:
    natal_chart = _a_natal_chart()
    client = create_client_with_chart(
        session,
        name="Grace Hopper",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()

    chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    assert chart.ascendant == natal_chart.ascendant
    assert chart.midheaven == natal_chart.midheaven
