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
from shell.adapters.postgres.report_theme import (
    StoredReportTheme,
    most_recent_prior_report_theme,
    store_report_theme,
)
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


def _create_run(session: Session, client: Client, *, month: str = "2026-01") -> ReportRun:
    run = ReportRun(client_id=client.id, month=month)
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



# --- most_recent_prior_report_theme (Story 4.7) -------------------------------


def _theme_tagged(natal_house: int) -> ReportTheme:
    """A minimal ``ReportTheme`` distinguishable from another only by its
    Lunation's ``natal_house`` -- lets a test assert *which* row's theme was
    returned without depending on the full shape ``_a_theme()`` builds."""
    return ReportTheme(
        dominant_aspects=(),
        lunations=(ThemeLunation(kind="new_moon", natal_house=natal_house),),
        standing_retrogrades=(),
    )


def test_most_recent_prior_report_theme_finds_the_immediately_preceding_month(
    session: Session,
) -> None:
    client = _create_client(session)
    run_jan = _create_run(session, client, month="2026-01")
    store_report_theme(session, run=run_jan, theme=_theme_tagged(1))
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-02")

    assert found is not None
    assert found.report_run_id == run_jan.id
    assert found.theme["lunations"] == [{"kind": "new_moon", "natal_house": 1}]


def test_most_recent_prior_report_theme_survives_a_skipped_month(session: Session) -> None:
    """A genuinely still-active slow transit must not be reset to "first
    Report" behavior just because a month was skipped (Story 4.7 Design
    Notes): the most recent prior run ("2026-01") is still found even when
    the immediately preceding month ("2026-02") was never driven."""
    client = _create_client(session)
    run_jan = _create_run(session, client, month="2026-01")
    store_report_theme(session, run=run_jan, theme=_theme_tagged(1))
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-03")

    assert found is not None
    assert found.report_run_id == run_jan.id


def test_most_recent_prior_report_theme_is_none_for_a_clients_first_report(
    session: Session,
) -> None:
    client = _create_client(session)

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-01")

    assert found is None


def test_most_recent_prior_report_theme_is_none_when_no_prior_run_reached_payload_ready(
    session: Session,
) -> None:
    """A ``ReportRun`` can exist for a Client without ever reaching
    ``payload_ready`` (so no ``StoredReportTheme`` row was ever written for
    it) -- that run must not be mistaken for prior continuity."""
    client = _create_client(session)
    _create_run(session, client, month="2026-01")  # no StoredReportTheme for this run

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-02")

    assert found is None


def test_most_recent_prior_report_theme_never_leaks_across_clients(session: Session) -> None:
    """The ``ReportRun.client_id == client_id`` filter must exclude a
    different Client's ``StoredReportTheme`` rows entirely -- Client B has a
    row for a month earlier than what's queried for Client A, but that row
    must never be returned for Client A."""
    client_a = _create_client(session, name="Ada Lovelace")
    client_b = _create_client(session, name="Grace Hopper")
    run_b = _create_run(session, client_b, month="2025-06")
    store_report_theme(session, run=run_b, theme=_theme_tagged(6))
    session.commit()

    found = most_recent_prior_report_theme(session, client_a.id, before_month="2026-01")

    assert found is None


def test_most_recent_prior_report_theme_orders_by_report_run_month_not_creation_order(
    session: Session,
) -> None:
    """Multiple prior ``ReportRun``s can be persisted out of creation order
    (Story 4.7 I/O Matrix): "2026-01" and "2026-03" are both persisted before
    "2026-02" is requested, and the query must still pick "2026-01" as the
    most recent prior run relative to "2026-02" -- ordering by
    ``ReportRun.month``, not by row-creation order."""
    client = _create_client(session)
    run_mar = _create_run(session, client, month="2026-03")
    store_report_theme(session, run=run_mar, theme=_theme_tagged(3))
    run_jan = _create_run(session, client, month="2026-01")
    store_report_theme(session, run=run_jan, theme=_theme_tagged(1))
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-02")

    assert found is not None
    assert found.report_run_id == run_jan.id


def test_most_recent_prior_report_theme_holds_across_a_year_boundary(session: Session) -> None:
    """Zero-padded ``"YYYY-MM"`` string comparison must hold across a year
    rollover: ``"2025-12"`` sorts before ``"2026-01"``."""
    client = _create_client(session)
    run_dec = _create_run(session, client, month="2025-12")
    store_report_theme(session, run=run_dec, theme=_theme_tagged(12))
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-01")

    assert found is not None
    assert found.report_run_id == run_dec.id


def test_most_recent_prior_report_theme_picks_the_later_of_two_prior_runs(
    session: Session,
) -> None:
    client = _create_client(session)
    run_jan = _create_run(session, client, month="2026-01")
    store_report_theme(session, run=run_jan, theme=_theme_tagged(1))
    run_feb = _create_run(session, client, month="2026-02")
    store_report_theme(session, run=run_feb, theme=_theme_tagged(2))
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-03")

    assert found is not None
    assert found.report_run_id == run_feb.id


def test_most_recent_prior_report_theme_breaks_a_same_month_tie_deterministically(
    session: Session,
) -> None:
    """Item 28: two ``StoredReportTheme`` rows for one Client and the same
    month are ordered by ``created_at`` then ``id`` descending, so the later
    row wins regardless of insertion order."""
    client = _create_client(session)
    run_older = _create_run(session, client, month="2026-01")
    run_newer = _create_run(session, client, month="2026-01")

    def _tagged_theme(natal_house: int) -> dict[str, object]:
        return {
            "dominant_aspects": [],
            "lunations": [{"kind": "new_moon", "natal_house": natal_house}],
            "standing_retrogrades": [],
        }

    newer = StoredReportTheme(
        client_id=client.id,
        report_run_id=run_newer.id,
        theme=_tagged_theme(9),
        created_at=datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
    )
    older = StoredReportTheme(
        client_id=client.id,
        report_run_id=run_older.id,
        theme=_tagged_theme(1),
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    # Insert the newer row first: the result must not depend on insert order.
    session.add(newer)
    session.add(older)
    session.commit()

    found = most_recent_prior_report_theme(session, client.id, before_month="2026-02")

    assert found is not None
    assert found.report_run_id == run_newer.id
    assert found.theme["lunations"] == [{"kind": "new_moon", "natal_house": 9}]


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
