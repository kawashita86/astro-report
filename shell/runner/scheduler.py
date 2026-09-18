"""The in-process ``background``-mode scheduler (AD-20, amended for Story
3.11): a single ``asyncio.Task``, started at app startup and stopped at
shutdown, that ticks ``shell/runner/driver.py::advance()`` for every
incomplete ``ReportRun``, on the same fixed cadence the poll fragment already
uses while a tab is open (``report_run_poll.html``'s ``hx-trigger="every
2s"``).

**Why a plain ``asyncio.Task``, not a library.** AD-20's amendment rules out
a queue or a second deployable; a bare task on the app's own event loop,
ticking synchronous work via ``asyncio.to_thread`` -- Starlette/FastAPI
dispatches every sync route handler here through AnyIO's own worker thread
pool, a *separate* pool from ``asyncio.to_thread``'s default executor, not
literally the same one; the analogy is the off-loop-thread pattern, not the
pool itself (review-loop 1) -- needs no new dependency.

**Why one ``Session`` per tick, not one per run.** ``advance()`` already
commits per stage transition; reusing one ``Session`` sequentially across a
tick's runs is ordinary SQLAlchemy usage (at the cost of SQLAlchemy's default
``expire_on_commit`` re-fetching each already-loaded row's attributes again
after every other row's commit/rollback in the same tick -- still cheaper
than a fresh connection per run), and a ``session.rollback()`` inside each
run's ``except`` block returns it to a clean state for the next run.

**Why ``generator_for_settings`` lives here.** The ``Environment.LOCAL``
branch guards real Gemini spend; this is the one function both the poll
route (``shell/http/routes/report_runs.py::get_generator``) and this
module's own tick call, so the decision can never drift between the two call
sites. Called once per tick, only when there is at least one pending run
(review-loop 2) -- an idle tick with nothing to advance must never construct
a real ``GeminiGenerator`` for no reason, the same waste review-loop 1 just
removed from the poll route.

**Accepted, not addressed here (review-loop 2).** A systemic Gemini outage
or rate-limit event now retries against every affected run on this module's
own 2s cadence rather than only when a human happens to poll -- unchanged
from ``poll`` mode, ``with_backoff``'s per-stage retry/backoff and
``_MAX_STAGE_FAILURES`` (Story 4.8, ``shell/runner/driver.py``) are still the
only throttle, and this story does not add a cross-run circuit breaker on
top of them. Similarly, ``stop_scheduler`` cannot interrupt a tick already
in flight inside ``asyncio.to_thread`` -- cancellation only takes effect at
the next ``await``, so shutdown blocks until that tick's current run (and
its own bounded backoff) finishes; a dyno restart mid-tick loses only the
scheduler's timer, never persisted stage data, exactly the restart risk
AD-20's amendment already accepts.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import Engine, or_
from sqlmodel import Session, select

from core.ephemeris.identity import EphemerisIdentity
from core.types.computation import ComputationConfig
from core.types.gate import GateVocabulary
from core.types.sections import SectionsConfig
from shell.adapters.gemini.generator import GeminiGenerator
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.adapters.postgres.client import (
    Client,
    current_chart_for_client,
    deserialize_natal_chart,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.config import Environment, ReportRunMode, Settings
from shell.ports.generator import Generator
from shell.runner.driver import advance

__all__ = [
    "generator_for_settings",
    "start_scheduler",
    "stop_scheduler",
]

_logger = logging.getLogger(__name__)

#: Mirrors ``report_run_poll.html``'s existing ``hx-trigger="every 2s"``, so
#: background progress reads the same speed as watching the tab (this
#: story's Design Notes).
_TICK_INTERVAL_SECONDS = 2.0


def generator_for_settings(settings: Settings) -> Generator:
    """The ``Environment.LOCAL`` -> ``RecordedResponseGenerator()`` / else
    ``GeminiGenerator(settings.gemini_api_key)`` branch, shared by
    ``shell/http/routes/report_runs.py::get_generator`` and
    :func:`_run_pending_report_runs` so both call sites can never drift.

    ``settings.use_real_gemini_locally`` (Story 4.9's own opt-out) is the one
    exception: a developer who has explicitly set ``USE_REAL_GEMINI_LOCALLY``
    still gets a real ``GeminiGenerator`` under ``Environment.LOCAL`` --
    deliberate and explicit, never a deployment default."""
    if settings.environment is Environment.LOCAL and not settings.use_real_gemini_locally:
        return RecordedResponseGenerator()
    return GeminiGenerator(settings.gemini_api_key)


def _run_pending_report_runs(
    engine: Engine,
    *,
    config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
    sections_config: SectionsConfig,
    vocabulary: GateVocabulary,
    settings: Settings,
) -> None:
    """One tick: advance every ``ReportRun`` with ``failed_at IS NULL`` and
    ``stage`` not ``"gate_passed"`` by at most one stage each, sharing a
    single ``Session`` across the whole tick.

    The ``or_(...)`` in the query is required, not decorative: SQL
    ``NULL != 'gate_passed'`` is not ``TRUE``, so without it a run that never
    had a first poll (``stage IS NULL``) would silently never be picked up
    here.

    Each row's client/chart lookup and ``advance()`` call is wrapped in its
    own ``try/except Exception``: on failure, the exception is logged and the
    session rolled back, and the loop continues to the next row -- one bad
    run must never abort the tick or leave the shared session unusable for
    the rest of it.

    Unrecoverable per-run lookup failure (review-loop 1): when the row's
    ``Client`` or its current stored chart is missing -- the two checks below
    that raise ``RuntimeError`` before ``advance()`` is ever called -- that
    specific failure is caught separately from the generic per-row
    ``except Exception`` and the run is marked terminally failed in the same
    transaction (``failed_at``/``failure_reason`` set, committed, no
    rollback) instead of only logged and rolled back -- mirroring
    ``shell/runner/driver.py``'s own terminal-failure shape, so this case is
    never silently retried forever. An exception raised by ``advance()``
    itself still falls through to the generic per-row ``except Exception``
    below unchanged.

    ``generator_for_settings(settings)`` is called once per tick, before the
    loop, not once per run (review-loop 1): it carries no per-run state, so
    building a fresh ``Generator`` for every pending run every tick would be
    pure waste (see this story's Design Notes).
    """
    with Session(engine) as session:
        runs = session.exec(
            select(ReportRun)
            .where(ReportRun.failed_at.is_(None))
            .where(or_(ReportRun.stage.is_(None), ReportRun.stage != "gate_passed"))
        ).all()

        if not runs:
            return

        generator = generator_for_settings(settings)

        for run in runs:
            try:
                client = session.get(Client, run.client_id)
                if client is None:
                    raise RuntimeError(f"ReportRun {run.id} references a missing Client.")
                stored_chart = current_chart_for_client(session, client.id)
                if stored_chart is None:
                    raise RuntimeError(
                        f"ReportRun {run.id}'s Client {client.id} has no stored chart."
                    )
            except RuntimeError as error:
                now = datetime.now(UTC)
                run.failed_at = now
                run.updated_at = now
                run.failure_reason = str(error)
                session.add(run)
                session.commit()
                # `.error`, not `.exception` (mirrors `shell/runner/driver.py`'s own
                # convention): this is an anticipated, handled condition -- the run
                # is marked terminally failed right here -- not an unexpected
                # exception that needs its own traceback.
                _logger.error(
                    "background scheduler tick found a missing Client/chart for "
                    "report run, marking it terminally failed: %s",
                    run.id,
                )
                continue

            try:
                natal_chart = deserialize_natal_chart(stored_chart)
                advance(
                    session,
                    run,
                    natal_chart=natal_chart,
                    natal_chart_id=stored_chart.id,
                    config=config,
                    ephemeris_identity=ephemeris_identity,
                    sections_config=sections_config,
                    generator=generator,
                    vocabulary=vocabulary,
                )
            except Exception:
                session.rollback()
                _logger.exception(
                    "background scheduler tick failed for report run, continuing "
                    "with the rest of the tick: %s",
                    run.id,
                )


async def _scheduler_loop(application: FastAPI) -> None:
    """``while True``: run one tick in a worker thread, then sleep
    :data:`_TICK_INTERVAL_SECONDS`, forever, until cancelled.

    The tick itself is wrapped in its own ``try/except Exception`` -- outer-
    loop isolation, distinct from :func:`_run_pending_report_runs`'s own
    per-run isolation: this task must never die silently, since a dead task
    means ``background`` mode silently reverts to no progress at all.
    """
    state = application.state
    while True:
        try:
            await asyncio.to_thread(
                _run_pending_report_runs,
                state.engine,
                config=state.computation_config,
                ephemeris_identity=state.ephemeris_identity,
                sections_config=state.sections_config,
                vocabulary=state.gate_vocabulary,
                settings=state.settings,
            )
        except Exception:
            _logger.exception("background scheduler tick raised, continuing")
        await asyncio.sleep(_TICK_INTERVAL_SECONDS)


def start_scheduler(application: FastAPI) -> None:
    """Start the scheduler task when ``settings.report_run_mode`` is
    ``ReportRunMode.BACKGROUND``, else set ``application.state.scheduler_task``
    to ``None``. Called before ``yield`` in ``shell/http/app.py::_lifespan``,
    mirroring where ``application.state.engine`` is already set (in
    ``create_app``, not in ``_lifespan``)."""
    settings: Settings = application.state.settings
    if settings.report_run_mode is ReportRunMode.BACKGROUND:
        application.state.scheduler_task = asyncio.create_task(_scheduler_loop(application))
    else:
        application.state.scheduler_task = None


async def stop_scheduler(application: FastAPI) -> None:
    """Cancel and await the scheduler task, or no-op when none was started.
    Called after ``yield``, before ``application.state.engine.dispose()`` --
    the scheduler must be fully stopped before the engine it uses is
    disposed."""
    task = application.state.scheduler_task
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
