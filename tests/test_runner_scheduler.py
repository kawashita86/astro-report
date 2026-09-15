"""``shell/runner/scheduler.py`` -- Story 3.11's ``background``-mode
selection/dispatch/isolation behavior (AD-20's amendment).

This module does not re-test stage behavior -- ``tests/test_runner_driver.py``
already covers ``advance()`` itself -- only ``_run_pending_report_runs``'s own
query predicate (including the ``NULL``-stage row the ``or_(...)`` clause
exists for) and its per-row isolation. ``shell.runner.scheduler.advance`` is
monkeypatched to a recording fake for every test here, mirroring
``tests/test_runner_advisory_lock.py``'s own self-contained in-memory SQLite
setup and ``tests/test_runner_driver.py::_create_client_and_chart`` for
fixture rows.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import shell.runner.scheduler as scheduler_module
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import create_client_with_chart
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.config import Environment, ReportRunMode, Settings
from shell.gate import DEFAULT_VOCABULARY_PATH, load_gate_vocabulary
from shell.runner.scheduler import _run_pending_report_runs
from shell.sections import load_sections_config

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()
_SECTIONS_CONFIG = load_sections_config()
_VOCABULARY = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)

_SETTINGS = Settings(
    environment=Environment.LOCAL,
    database_url="postgresql://astro:astro@localhost:5432/astro_report",
    port=8000,
    auth_password_hash=(
        "$argon2id$v=19$m=65536,t=3,p=4$hQD4AS+0CkX36kCpbKWmRg$"
        "5qiPb5sRKvlOqu1vvnP861fs5dcBQgq8OJvSlHPL3Mo"
    ),
    session_secret_key="test-session-secret-key-at-least-32-chars-long",
    gemini_api_key="test-gemini-api-key",
    gemini_data_terms_verified_at="2026-01-15",
    report_run_mode=ReportRunMode.BACKGROUND,
)

# Fort Worth, TX, 2026-01-01 00:00 America/Chicago (UTC-6) -- the same
# known-good input tests/test_runner_driver.py uses.
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


def _create_client(session: Session):
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
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
    return client


def _tick(engine) -> None:
    _run_pending_report_runs(
        engine,
        config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
        sections_config=_SECTIONS_CONFIG,
        vocabulary=_VOCABULARY,
        settings=_SETTINGS,
    )


class _RecordingFakeAdvance:
    """Records the ``run.id`` of every ``advance()`` call it receives, and --
    for ids in ``raise_for`` -- raises instead, proving one bad row never
    aborts the rest of the tick."""

    def __init__(self, raise_for: frozenset = frozenset()) -> None:
        self.raise_for = raise_for
        self.calls: list = []

    def __call__(self, session, run, **kwargs):
        self.calls.append(run.id)
        if run.id in self.raise_for:
            raise RuntimeError(f"boom: {run.id}")
        run.stage = "transits_ready" if run.stage is None else run.stage
        session.add(run)
        session.commit()
        return run


def test_a_null_stage_run_is_selected(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ``or_(...)`` clause exists exactly for this row: SQL
    ``NULL != 'gate_passed'`` is not ``TRUE``, so a run that never had a
    first poll must still be picked up."""
    client = _create_client(session)
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == [run.id]


def test_a_mid_pipeline_run_is_selected(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _create_client(session)
    run = ReportRun(client_id=client.id, month="2026-01", stage="natal_ready")
    session.add(run)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == [run.id]


def test_a_terminally_failed_run_is_excluded(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _create_client(session)
    run = ReportRun(
        client_id=client.id,
        month="2026-01",
        stage="natal_ready",
        failed_at=datetime.now(UTC),
        failure_reason="terminally failed for the test",
    )
    session.add(run)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == []


def test_a_gate_passed_run_is_excluded(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _create_client(session)
    run = ReportRun(client_id=client.id, month="2026-01", stage="gate_passed")
    session.add(run)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == []


def test_one_rows_failure_does_not_stop_the_rest_of_the_tick(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _create_client(session)
    failing_run = ReportRun(client_id=client.id, month="2026-01")
    healthy_run = ReportRun(client_id=client.id, month="2026-02")
    session.add(failing_run)
    session.add(healthy_run)
    session.commit()

    fake = _RecordingFakeAdvance(raise_for=frozenset({failing_run.id}))
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert set(fake.calls) == {failing_run.id, healthy_run.id}
    with Session(engine) as fresh_session:
        refreshed_healthy = fresh_session.get(ReportRun, healthy_run.id)
        assert refreshed_healthy is not None
        assert refreshed_healthy.stage == "transits_ready"


def test_a_run_whose_client_has_no_stored_chart_is_isolated(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row whose client/chart lookup itself fails (before ``advance()`` is
    even called) must be marked terminally failed, not merely logged and
    skipped (review-loop 1) -- never abort the tick either, proven here by a
    second, healthy run for a different Client still reaching ``advance()``
    in the same tick."""
    from shell.adapters.postgres.client import StoredNatalChart

    chartless_client = _create_client(session)
    healthy_client = _create_client(session)

    chartless_run = ReportRun(client_id=chartless_client.id, month="2026-01")
    healthy_run = ReportRun(client_id=healthy_client.id, month="2026-01")
    session.add(chartless_run)
    session.add(healthy_run)
    session.commit()

    # Supersede the first Client's only chart so `current_chart_for_client`
    # finds none for it -- simulating "client/chart missing" without
    # deleting the row outright.
    stored_chart = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == chartless_client.id)
    ).one()
    stored_chart.superseded_at = datetime.now(UTC)
    session.add(stored_chart)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == [healthy_run.id]
    with Session(engine) as fresh_session:
        refreshed_chartless = fresh_session.get(ReportRun, chartless_run.id)
        assert refreshed_chartless is not None
        assert refreshed_chartless.failed_at is not None
        assert refreshed_chartless.failure_reason is not None
        assert "no stored chart" in refreshed_chartless.failure_reason
        refreshed_healthy = fresh_session.get(ReportRun, healthy_run.id)
        assert refreshed_healthy is not None
        assert refreshed_healthy.failed_at is None


def test_a_run_whose_client_row_does_not_exist_at_all_is_isolated(
    session: Session, engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distinct from the missing-chart case above (review-loop 1): a
    ``ReportRun`` whose ``client_id`` references no ``Client`` row at all --
    e.g. a hand-corrupted row, or a Client hard-deleted out from under a
    still-pending run -- must also be marked terminally failed rather than
    retried forever, and must not abort the rest of the tick either."""
    healthy_client = _create_client(session)

    orphaned_run = ReportRun(client_id=uuid4(), month="2026-01")
    healthy_run = ReportRun(client_id=healthy_client.id, month="2026-01")
    session.add(orphaned_run)
    session.add(healthy_run)
    session.commit()

    fake = _RecordingFakeAdvance()
    monkeypatch.setattr(scheduler_module, "advance", fake)

    _tick(engine)

    assert fake.calls == [healthy_run.id]
    with Session(engine) as fresh_session:
        refreshed_orphaned = fresh_session.get(ReportRun, orphaned_run.id)
        assert refreshed_orphaned is not None
        assert refreshed_orphaned.failed_at is not None
        assert refreshed_orphaned.failure_reason is not None
        assert "missing Client" in refreshed_orphaned.failure_reason
        refreshed_healthy = fresh_session.get(ReportRun, healthy_run.id)
        assert refreshed_healthy is not None
        assert refreshed_healthy.failed_at is None


# --- `_scheduler_loop`'s own outer-loop isolation ------------------------------


class _StubAppState:
    def __init__(self) -> None:
        self.engine = None
        self.computation_config = _COMPUTATION_CONFIG
        self.ephemeris_identity = _EPHEMERIS_IDENTITY
        self.sections_config = _SECTIONS_CONFIG
        self.gate_vocabulary = _VOCABULARY
        self.settings = _SETTINGS


class _StubApp:
    def __init__(self) -> None:
        self.state = _StubAppState()


def test_scheduler_loop_survives_a_bad_tick_and_calls_again_on_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_scheduler_loop`'s own outer `try/except Exception` around the tick
    (distinct from `_run_pending_report_runs`'s per-row isolation) must keep
    the task alive and ticking even when a whole tick raises -- proven here
    by making `_run_pending_report_runs` raise on its first call and succeed
    on its second, then asserting it was called at least twice and the task
    is still alive (not done, not cancelled on its own)."""
    calls: list[int] = []

    def _fake_run_pending_report_runs(*args: object, **kwargs: object) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom: simulated tick failure")

    # Patched to return immediately rather than actually waiting
    # `_TICK_INTERVAL_SECONDS` (2s) -- but still a real checkpoint
    # (`_real_sleep(0)`, captured before patching), so this test's own
    # polling loop below (which awaits the very same `asyncio.sleep`) keeps
    # cooperatively yielding to the scheduler task instead of spinning
    # forever with the task never getting a turn.
    _real_sleep = asyncio.sleep

    async def _fast_sleep(_seconds: float) -> None:
        await _real_sleep(0)

    monkeypatch.setattr(
        scheduler_module, "_run_pending_report_runs", _fake_run_pending_report_runs
    )
    monkeypatch.setattr(scheduler_module.asyncio, "sleep", _fast_sleep)

    async def _drive() -> None:
        task = asyncio.create_task(scheduler_module._scheduler_loop(_StubApp()))
        try:
            while len(calls) < 2:
                await asyncio.sleep(0)
            assert not task.done()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(_drive())

    assert len(calls) >= 2
