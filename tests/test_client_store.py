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
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    StoredNatalChart,
    correct_client_and_chart,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report_run import ReportRun
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


def test_client_and_chart_string_columns_are_bounded() -> None:
    """Deferred-work item 41: each column's ``Field(max_length=...)``
    becomes an explicit ``VARCHAR(n)`` at the schema level, matching
    ``migrations/versions/0014_bound_client_and_chart_string_columns.py``."""
    assert Client.__table__.c.name.type.length == 200
    assert Client.__table__.c.iana_zone.type.length == 64
    assert StoredNatalChart.__table__.c.computation_config_content_hash.type.length == 64


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


# --- delete_client_and_derived (Story 2.8) -----------------------------------------


def test_delete_client_and_derived_removes_the_client_and_its_current_chart(
    session: Session,
) -> None:
    client = _create(session)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert (
        session.exec(
            select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
        ).first()
        is None
    )


def test_delete_client_and_derived_removes_a_superseded_chart_too(session: Session) -> None:
    client = _create(session)
    session.commit()

    correct_client_and_chart(
        session,
        client=client,
        name="Ada Corrected",
        birth_date=date(2026, 1, 2),
        birth_time=time(1, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=_a_natal_chart(),
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()
    assert (
        len(
            session.exec(
                select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
            ).all()
        )
        == 2
    ), "fixture did not produce a superseded chart -- test is vacuous"

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert (
        session.exec(
            select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
        ).first()
        is None
    )


def test_delete_client_and_derived_does_not_persist_without_an_explicit_commit(
    session: Session,
) -> None:
    client = _create(session)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert (
        session.exec(
            select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
        ).first()
        is not None
    )


def test_the_cascade_constant_includes_report_theme() -> None:
    """Story 4.3: ``report_theme`` must join ``_CLIENT_CASCADE_TABLES`` --
    a regression on top of the general invariant test below, naming the
    table this story added explicitly."""
    assert "report_theme" in client_module._CLIENT_CASCADE_TABLES


def test_the_cascade_constant_includes_report() -> None:
    """Story 5.3: ``report`` must join ``_CLIENT_CASCADE_TABLES`` -- a
    regression on top of the general invariant test below, naming the table
    this story added explicitly. ``tests/test_report_store.py`` covers the
    actual deletion behavior end to end, mirroring
    ``tests/test_report_draft_store.py``'s own cascade tests."""
    assert "report" in client_module._CLIENT_CASCADE_TABLES


def test_the_cascade_constant_includes_gate_result() -> None:
    """Story 5.6: ``gate_result`` must join ``_CLIENT_CASCADE_TABLES`` -- a
    regression on top of the general invariant test below, naming the table
    this story added explicitly. ``tests/test_gate_result_store.py`` covers
    the actual deletion behavior end to end, mirroring
    ``tests/test_report_store.py``'s own cascade tests."""
    assert "gate_result" in client_module._CLIENT_CASCADE_TABLES


def test_the_cascade_constant_includes_export_record() -> None:
    """Story 6.2: ``export_record`` must join ``_CLIENT_CASCADE_TABLES`` --
    a regression on top of the general invariant test below, naming the
    table this story added explicitly. ``tests/test_export_record_store.py``
    covers the actual deletion behavior end to end, mirroring
    ``tests/test_gate_result_store.py``'s own cascade tests."""
    assert "export_record" in client_module._CLIENT_CASCADE_TABLES


def test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant() -> None:
    """The cascade-invariant test: a later story that adds a new table with a
    foreign key to ``client.id`` without also adding it to
    ``_CLIENT_CASCADE_TABLES`` (and ``delete_client_and_derived()``) must fail
    here, not silently leave orphaned rows behind."""
    tables_with_client_fk = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table.name == "client" and foreign_key.column.name == "id"
    }
    assert tables_with_client_fk == client_module._CLIENT_CASCADE_TABLES


# --- Story 6.4 regression: ReportRun.natal_chart_id must not break deletion --------


def test_delete_client_and_derived_succeeds_with_a_report_run_referencing_a_natal_chart() -> None:
    """``ReportRun.natal_chart_id`` (Story 6.4) is a foreign key *to*
    ``natal_chart.id`` -- the opposite direction from every other table in
    this cascade. The module's shared ``session`` fixture's SQLite engine
    does not enforce foreign keys by default (unlike Postgres, this
    codebase's real target), which is exactly why the first implementation
    pass's wrong deletion order -- every ``StoredNatalChart`` deleted before
    every ``ReportRun`` -- passed every other test in this suite while
    silently breaking Client deletion in production for any Client with
    report history (this story's Spec Change Log). This test builds its own
    engine with a ``PRAGMA foreign_keys=ON`` "connect" listener, registered
    before the engine's first connection, so real enforcement is on from the
    start -- mechanically catching that class of ordering bug going forward.
    """
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        client = _create(session)
        session.commit()

        chart = session.exec(
            select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
        ).one()
        run = ReportRun(client_id=client.id, month="2026-01", natal_chart_id=chart.id)
        session.add(run)
        session.commit()

        delete_client_and_derived(session, client=client)
        session.commit()

        assert session.get(Client, client.id) is None
        assert session.get(ReportRun, run.id) is None
        assert (
            session.exec(
                select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
            ).first()
            is None
        )
