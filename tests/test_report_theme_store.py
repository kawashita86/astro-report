"""``StoredReportTheme`` (Story 4.3): an in-memory SQLite engine stands in
for Postgres, mirroring ``tests/test_report_payload_store.py``. Covers the
row's own shape, ``store_report_theme()``'s writes, the ``before_update``
immutability guard, uniqueness on ``report_run_id``, and that
``report_theme`` joins the FR-29 Client-deletion cascade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, SQLModel, create_engine, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.memory import ReportTheme, ThemeAspect, ThemeLunation
from core.types.place import ResolvedPlace
from core.types.transits import StandingRetrograde
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme, store_report_theme
from shell.computation import load_computation_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py and tests/test_report_payload_store.py use.
_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)

_T0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 10, 6, 0, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _an_empty_theme() -> ReportTheme:
    return ReportTheme(dominant_aspects=(), lunations=(), standing_retrogrades=())


def _a_theme() -> ReportTheme:
    return ReportTheme(
        dominant_aspects=(
            ThemeAspect(
                transiting_body="saturn",
                natal_point="sun",
                aspect="square",
                perfected_at=_T0,
                never_perfected=False,
                orb_entry_at=_T0,
                orb_exit_at=None,
            ),
        ),
        lunations=(ThemeLunation(kind="new_moon", natal_house=3),),
        standing_retrogrades=(
            StandingRetrograde(body="jupiter", retrograde_start_utc=_T0, retrograde_end_utc=_T1),
        ),
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


# --- StoredReportTheme row shape ------------------------------------------------


def test_a_stored_report_theme_id_is_uuidv7(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_theme(session, run=run, theme=_a_theme())
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_store_report_theme_persists_identity_and_the_whole_theme_as_json(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    theme = _a_theme()

    stored = store_report_theme(session, run=run, theme=theme)
    session.commit()

    reloaded = session.get(StoredReportTheme, stored.id)
    assert reloaded is not None
    assert reloaded.client_id == client.id
    assert reloaded.report_run_id == run.id
    assert reloaded.created_at is not None

    dominant_aspects = reloaded.theme["dominant_aspects"]
    assert len(dominant_aspects) == 1
    assert dominant_aspects[0]["transiting_body"] == "saturn"
    assert dominant_aspects[0]["natal_point"] == "sun"
    assert dominant_aspects[0]["perfected_at"] == _T0.isoformat()
    assert dominant_aspects[0]["orb_exit_at"] is None

    lunations = reloaded.theme["lunations"]
    assert lunations == [{"kind": "new_moon", "natal_house": 3}]

    standing_retrogrades = reloaded.theme["standing_retrogrades"]
    assert len(standing_retrogrades) == 1
    assert standing_retrogrades[0]["body"] == "jupiter"
    assert standing_retrogrades[0]["retrograde_start_utc"] == _T0.isoformat()
    assert standing_retrogrades[0]["retrograde_end_utc"] == _T1.isoformat()


def test_an_empty_theme_persists_as_empty_lists(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_theme(session, run=run, theme=_an_empty_theme())
    session.commit()

    reloaded = session.get(StoredReportTheme, stored.id)
    assert reloaded is not None
    assert reloaded.theme == {
        "dominant_aspects": [],
        "lunations": [],
        "standing_retrogrades": [],
    }


def test_store_report_theme_only_flushes_never_commits(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_theme(session, run=run, theme=_a_theme())
    stored_id = stored.id
    session.rollback()

    assert session.get(StoredReportTheme, stored_id) is None


# --- Immutability ------------------------------------------------------------


def test_mutating_and_committing_a_persisted_report_theme_raises(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)

    stored = store_report_theme(session, run=run, theme=_a_theme())
    session.commit()

    stored.theme = {"dominant_aspects": [], "lunations": [], "standing_retrogrades": []}
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    assert "immutable" in str(caught.value)


# --- Uniqueness ----------------------------------------------------------------


def test_a_second_report_theme_for_the_same_report_run_id_raises_integrity_error(
    session: Session,
) -> None:
    """Exactly one ``StoredReportTheme`` per ``ReportRun``, enforced by a
    unique index on ``report_run_id`` -- not merely by ``store_report_theme()``
    only ever being called once per ``ReportRun`` in
    ``shell/runner/driver.py``'s ``payload_ready`` stage."""
    client = _create_client(session)
    run = _create_run(session, client)

    store_report_theme(session, run=run, theme=_a_theme())
    session.commit()

    with pytest.raises(IntegrityError):
        store_report_theme(session, run=run, theme=_a_theme())

    session.rollback()


def test_two_report_runs_for_one_client_each_get_their_own_report_theme_row(
    session: Session,
) -> None:
    client = _create_client(session)
    first_run = _create_run(session, client)
    second_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(second_run)
    session.commit()

    store_report_theme(session, run=first_run, theme=_a_theme())
    store_report_theme(session, run=second_run, theme=_a_theme())
    session.commit()

    stored_themes = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.client_id == client.id)
    ).all()
    assert {stored.report_run_id for stored in stored_themes} == {first_run.id, second_run.id}


# --- FR-29 cascade ---------------------------------------------------------------


def test_delete_client_and_derived_removes_its_report_themes(session: Session) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_theme(session, run=run, theme=_a_theme())
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(ReportRun, run.id) is None
    assert session.get(StoredReportTheme, stored.id) is None


def test_delete_client_and_derived_does_not_persist_report_theme_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _create_client(session)
    run = _create_run(session, client)
    stored = store_report_theme(session, run=run, theme=_a_theme())
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(StoredReportTheme, stored.id) is not None


def test_every_table_with_a_client_id_foreign_key_includes_report_theme() -> None:
    tables_with_client_fk = {
        table.name
        for table in SQLModel.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table.name == "client" and foreign_key.column.name == "id"
    }
    assert "report_theme" in tables_with_client_fk
