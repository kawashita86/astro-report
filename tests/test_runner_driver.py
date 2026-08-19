"""``shell/runner/driver.py::drive()`` -- Story 3.5's own I/O & Edge-Case
Matrix rows for advancing a ``ReportRun``.

An in-memory SQLite engine stands in for Postgres, mirroring
``tests/test_client_store.py``; the Natal Chart, ``ComputationConfig`` and
``EphemerisIdentity`` are all real (the same known-good Fort Worth fixture
``tests/test_client_store.py`` uses), since these two registered stages
(``natal_ready``, ``transits_ready``) call real ``core/`` code -- only the
*failure* scenarios below inject a fake stage function, mirroring the
story's own Design Notes ("no live external call demonstrates the backoff").
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine

import shell.runner.driver as driver_module
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import create_client_with_chart, deserialize_natal_chart
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.runner.driver import _STAGE_FUNCTIONS, drive

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_client_store.py uses.
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
def engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as session:
        yield session


def _a_natal_chart():
    return compute_natal_chart(_BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG)


def _create_client_and_chart(session: Session):
    natal_chart = _a_natal_chart()
    client = create_client_with_chart(
        session,
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )
    session.commit()
    return client, natal_chart


def _drive(session: Session, run: ReportRun, natal_chart):
    return drive(
        session,
        run,
        natal_chart=natal_chart,
        config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


# --- Fresh run, both stages succeed -------------------------------------------------


def test_fresh_run_advances_through_both_registered_stages(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "transits_ready"
    assert result.month_start_utc == datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)
    assert result.month_end_utc == datetime(2026, 2, 1, 6, 0, 0, tzinfo=UTC)
    assert isinstance(result.transit_events, list)
    assert result.transit_events, "fixture produced no transit events -- test is vacuous"
    assert {event["kind"] for event in result.transit_events} <= {
        "aspect",
        "station",
        "standing_retrograde",
        "ingress",
        "lunation",
    }


def test_lunation_events_keep_their_own_new_or_full_kind_distinct_from_the_wrapper_tag(
    session: Session,
) -> None:
    """Lunation (core/types/transits.py) carries its own `kind` field
    ("new_moon"/"full_moon") -- a real name collision with `_serialize_event`'s
    outer "kind" tag ("lunation"), not the same value twice. Both must survive
    the collision distinctly."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    lunations = [event for event in result.transit_events if event["kind"] == "lunation"]
    assert lunations, "fixture produced no lunations -- test is vacuous"
    for lunation in lunations:
        assert lunation["kind"] == "lunation"
        assert lunation["lunation_kind"] in {"new_moon", "full_moon"}


def test_a_completed_run_is_persisted_to_the_database(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _drive(session, run, natal_chart)

    stored = session.get(ReportRun, run.id)
    assert stored is not None
    assert stored.stage == "transits_ready"
    assert stored.transit_events is not None


# --- Re-drive after natal_ready alone ------------------------------------------------


def test_re_drive_after_natal_ready_alone_runs_transits_ready_next_without_recomputing_it(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    # Stop right after natal_ready by making transits_ready fail every
    # attempt for this first drive() call only.
    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)
    _drive(session, run, natal_chart)
    assert run.stage == "natal_ready", "fixture did not stop at natal_ready -- test is vacuous"
    recorded_start, recorded_end = run.month_start_utc, run.month_end_utc

    monkeypatch.undo()

    # natal_ready must not be recomputed: prove it by making the function it
    # calls raise if it is ever invoked again.
    def _raise_if_called(*args, **kwargs):
        raise AssertionError("client_month_interval_utc must not be called again")

    monkeypatch.setattr(driver_module, "client_month_interval_utc", _raise_if_called)

    result = _drive(session, run, natal_chart)

    assert result.stage == "transits_ready"
    assert result.month_start_utc == recorded_start
    assert result.month_end_utc == recorded_end
    assert result.transit_events is not None


# --- Re-drive after full completion --------------------------------------------------


def test_re_drive_after_full_completion_is_a_noop(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    _drive(session, run, natal_chart)
    assert run.stage == "transits_ready", "fixture did not complete -- test is vacuous"
    events_before = run.transit_events
    updated_at_before = run.updated_at

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("a completed stage must not be called again")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _raise_if_called)
    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _raise_if_called)

    result = _drive(session, run, natal_chart)

    assert result is run
    assert result.stage == "transits_ready"
    assert result.transit_events == events_before
    assert result.updated_at == updated_at_before


# --- A transiently failing stage still advances normally via with_backoff -----------


def test_a_stage_that_fails_once_then_succeeds_still_advances_run_stage_within_one_drive_call(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``tests/test_runner_backoff.py`` proves ``with_backoff`` itself
    retries a fail-once-then-succeed function in isolation. This proves the
    same thing through ``drive()``: a registered stage function that raises
    once and then succeeds must still be retried transparently and let
    ``run.stage`` advance normally within the same ``drive()`` call -- not
    leave the run stuck as if it had failed permanently."""
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    real_natal_ready = _STAGE_FUNCTIONS["natal_ready"]
    calls: list[int] = []

    def _fails_once_then_succeeds(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("simulated transient failure")
        return real_natal_ready(*args, **kwargs)

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _fails_once_then_succeeds)

    result = _drive(session, run, natal_chart)

    assert len(calls) == 2, "the stage function must have been retried, not just called once"
    assert result.stage == "transits_ready"
    assert result.month_start_utc is not None
    assert result.transit_events is not None


# --- Stage raises past backoff's attempts --------------------------------------------


def test_a_persistently_failing_stage_leaves_the_run_unadvanced(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    calls: list[int] = []

    def _always_fail(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("simulated permanent failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "natal_ready", _always_fail)

    with caplog.at_level(logging.ERROR, logger=driver_module._logger.name):
        result = _drive(session, run, natal_chart)

    # No exception escaped drive() -- the call above completing at all is
    # part of what this test proves.
    assert result.stage is None
    assert result.month_start_utc is None
    assert len(calls) == 3, "with_backoff's default max_attempts is 3"
    assert str(run.id) in caplog.text


def test_a_stage_failing_after_a_prior_success_leaves_stage_at_the_last_success(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    def _always_fail(*args, **kwargs):
        raise RuntimeError("simulated permanent failure")

    monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)

    result = _drive(session, run, natal_chart)

    assert result.stage == "natal_ready"
    assert result.month_start_utc is not None
    assert result.transit_events is None


# --- Process killed between stages -----------------------------------------------------


def test_process_killed_between_stages_resumes_at_transits_ready_reading_the_row_back(
    engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(engine) as first_session:
        client, natal_chart = _create_client_and_chart(first_session)
        run = ReportRun(client_id=client.id, month="2026-01")
        first_session.add(run)
        first_session.commit()

        def _always_fail(*args, **kwargs):
            raise RuntimeError("process killed here, simulated")

        monkeypatch.setitem(_STAGE_FUNCTIONS, "transits_ready", _always_fail)
        _drive(first_session, run, natal_chart)
        assert run.stage == "natal_ready", "fixture did not stop at natal_ready -- test is vacuous"
        run_id = run.id
        recorded_start, recorded_end = run.month_start_utc, run.month_end_utc

    monkeypatch.undo()

    # A brand new session against the same engine -- simulates the process
    # restarting and reading the row back from Postgres, never from anything
    # held in memory.
    with Session(engine) as second_session:
        reloaded_run = second_session.get(ReportRun, run_id)
        assert reloaded_run is not None
        assert reloaded_run.stage == "natal_ready"
        assert reloaded_run.month_start_utc == recorded_start
        assert reloaded_run.month_end_utc == recorded_end

        result = _drive(second_session, reloaded_run, natal_chart)

        assert result.stage == "transits_ready"
        assert result.month_start_utc == recorded_start, "month bounds must not be recomputed"
        assert result.month_end_utc == recorded_end
        assert result.transit_events is not None


# --- Stops cleanly at the first unregistered stage ------------------------------------


def test_drive_stops_cleanly_once_it_reaches_an_unregistered_stage(session: Session) -> None:
    client, natal_chart = _create_client_and_chart(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    # payload_ready has no registered function this story -- drive() must
    # stop there without raising.
    assert result.stage == "transits_ready"


# --- deserialize_natal_chart interop --------------------------------------------------


def test_drive_works_against_a_deserialized_natal_chart(session: Session) -> None:
    """The natal_chart drive() takes is the deserialized round trip
    (Boundaries & Constraints), not the freshly-computed value directly --
    proves the two interoperate."""
    from sqlmodel import select

    from shell.adapters.postgres.client import StoredNatalChart

    client, _ = _create_client_and_chart(session)
    stored_chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).one()
    natal_chart = deserialize_natal_chart(stored_chart)

    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    result = _drive(session, run, natal_chart)

    assert result.stage == "transits_ready"
    assert result.transit_events
