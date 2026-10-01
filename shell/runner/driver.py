"""The RunDriver: the one place the server moves a report run on its own (AD-20, AD-21).

A run advances with no page open. ``start(run_id)`` returns at once; a loop per run
calls the idempotent, one-stage-per-call ``advance()`` (``shell/runner/advance.py``)
until the run reaches ``gate_passed`` or ``failed_at``. At ``draft_ready`` the loop
reads the run's Section rows, asks ``core/draft_state.py`` what is claimable, and
submits one job per claimable Section to a generation executor capped at
``GENERATION_CONCURRENCY`` -- the process-wide brake across every run. When all eight
Sections are complete it assembles the one ``ReportDraft`` and carries on to the Gate.

This module is the only place in the codebase allowed to create a thread or an
executor (a guard test enforces it): a loop's work and a generation job are the two
kinds of background work there are. The driver keeps no state the database does not
already hold, so a stop loses nothing -- ``resume()`` restarts every incomplete run
and a lease left by a dead process expires and is reclaimed.

Each loop thread binds the verified ephemeris path before it advances (the Swiss
Ephemeris path is thread-local C state); generation jobs reach no chart code. Every
step opens a fresh ``Session``, never one shared across threads. Logs carry ids only.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Engine, update
from sqlmodel import Session, select

from core.draft_state import (
    CLOSING_ORDINAL,
    SECTION_NAMES,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PENDING,
    claimable_sections,
    is_draft_complete,
    is_exhausted,
    live_lease_expiries,
)
from core.ephemeris.identity import (
    EphemerisIdentity,
    bind_verified_ephemeris_path_to_current_thread,
)
from core.types.computation import ComputationConfig
from core.types.gate import GateVocabulary
from core.types.generation import Sentence
from core.types.sections import SectionsConfig
from shell.adapters.postgres.client import current_chart_for_client, deserialize_natal_chart
from shell.adapters.postgres.report_draft_section import (
    ReportDraftSection,
    section_rows,
    section_state,
    sentences_from_json,
    sentences_to_json,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.config import MAX_SECTION_ATTEMPTS
from shell.ports.generator import Generator
from shell.runner.advance import (
    advance,
    assemble_draft,
    load_generation_inputs,
    open_draft_attempt,
)
from shell.runner.lease import LEASE_TTL, section_claim

__all__ = ["RunDriver"]

_logger = logging.getLogger(__name__)

#: The stages after which a run needs no more driving.
_FINISHED_STAGES = ("gate_passed", "exported")
#: How long a loop waits when a round changed nothing though something looked
#: claimable (another process took it first): never a spin.
_IDLE_RETRY_SECONDS = 1.0
#: Slack after a lease's expiry before the loop looks again.
_EXPIRY_SLACK_SECONDS = 0.05
#: Run loops are few (one operator); they mostly wait on their jobs.
_LOOP_WORKERS = 16
#: Consecutive errors reading a run's rows before its driving is given up.
_MAX_CONSECUTIVE_ERRORS = 5
#: Consecutive rounds that changed nothing before driving is given up (a restart's
#: ``resume()`` picks the run up again): an ``advance`` that is single-flighted away by
#: another caller's advisory lock, or a lease that never frees, must not spin forever.
_MAX_UNCHANGED_ROUNDS = 10
#: ``last_error`` is a diagnostic, not a transcript.
_MAX_ERROR_LENGTH = 500
#: Seconds a Section is held off after its first failed attempt; doubles per further failure.
_RETRY_BASE_DELAY_SECONDS = 2.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _Loop:
    """One run's driving. ``recheck`` is set by a ``start`` that arrives while it runs."""

    recheck: bool = False


class RunDriver:
    """Moves report runs forward in the background; Sections are written in parallel."""

    def __init__(
        self,
        *,
        engine: Engine,
        config: ComputationConfig,
        ephemeris_identity: EphemerisIdentity,
        sections_config: SectionsConfig,
        vocabulary: GateVocabulary,
        generator: Callable[[], Generator],
        concurrency: int,
        now: Callable[[], datetime] = _utc_now,
        max_attempts: int = MAX_SECTION_ATTEMPTS,
        lease_ttl: timedelta = LEASE_TTL,
        retry_base_delay: float = _RETRY_BASE_DELAY_SECONDS,
    ) -> None:
        self._engine = engine
        self._config = config
        self._ephemeris_identity = ephemeris_identity
        self._sections_config = sections_config
        self._vocabulary = vocabulary
        self._generator = generator
        self._now = now
        self._max_attempts = max_attempts
        self._lease_ttl = lease_ttl
        self._retry_base_delay = retry_base_delay
        self._cond = threading.Condition()
        self._loops: dict[UUID, _Loop] = {}
        self._resuming = False
        self._stopped = False
        self._generation = ThreadPoolExecutor(
            max_workers=max(1, concurrency), thread_name_prefix="ar-generate"
        )
        self._runs = ThreadPoolExecutor(max_workers=_LOOP_WORKERS, thread_name_prefix="ar-run")

    # -- the public surface --------------------------------------------------------

    def start(self, run_id: UUID) -> None:
        """Make sure ``run_id`` is being driven; returns at once, changes nothing if it is.

        A loop already running is told to look again before it stops, so a ``start``
        that lands while it decides to stop is never lost."""
        with self._cond:
            if self._stopped:
                return
            running = self._loops.get(run_id)
            if running is not None:
                running.recheck = True
                self._cond.notify_all()
                return
            loop = self._loops[run_id] = _Loop()
        try:
            self._runs.submit(self._drive, run_id, loop)
        except RuntimeError:
            # The executor was shut down between the check and the submit.
            with self._cond:
                self._loops.pop(run_id, None)
                self._cond.notify_all()

    def resume(self) -> None:
        """After a restart, start every run that is not finished or failed; returns at once.

        A run whose Section lease a dead process left behind is picked up too: its loop
        waits for the lease to expire (``LEASE_TTL``) and then reclaims the Section."""
        with self._cond:
            if self._stopped or self._resuming:
                return
            self._resuming = True
        try:
            self._runs.submit(self._resume)
        except RuntimeError:
            with self._cond:
                self._resuming = False
                self._cond.notify_all()

    def stop(self) -> None:
        """Stop starting work and drop the queued jobs; never waits for the model.

        A running job finishes or is cut off with the process; its lease expires and the
        Section stays as the rows say."""
        with self._cond:
            self._stopped = True
            # Queued loops cancelled below never run `_drive`'s cleanup.
            self._loops.clear()
            self._cond.notify_all()
        self._generation.shutdown(wait=False, cancel_futures=True)
        self._runs.shutdown(wait=False, cancel_futures=True)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until no run is being driven and no resume is under way; for tests.
        Whether it got there in time."""
        with self._cond:
            return self._cond.wait_for(lambda: not self._loops and not self._resuming, timeout)

    def is_driving(self, run_id: UUID) -> bool:
        with self._cond:
            return run_id in self._loops

    # -- resume ------------------------------------------------------------------------

    def _resume(self) -> None:
        try:
            with Session(self._engine) as session:
                run_ids = [
                    run.id
                    for run in session.exec(
                        select(ReportRun).where(ReportRun.failed_at.is_(None))  # type: ignore[union-attr]
                    ).all()
                    if run.stage not in _FINISHED_STAGES
                ]
            for run_id in run_ids:
                self.start(run_id)
            _logger.info("driver_resumed runs=%d", len(run_ids))
        except Exception as error:  # noqa: BLE001 -- resuming must never raise
            _logger.warning("driver_resume_error error=%s", type(error).__name__)
        finally:
            with self._cond:
                self._resuming = False
                self._cond.notify_all()

    # -- one run's loop ------------------------------------------------------------------

    def _drive(self, run_id: UUID, loop: _Loop) -> None:
        _logger.info("driver_started run=%s", run_id)
        try:
            # The Swiss Ephemeris path is thread-local; bind it before any chart stage.
            bind_verified_ephemeris_path_to_current_thread()
            self._loop(run_id, loop)
        except Exception as error:  # noqa: BLE001 -- driving must end quietly, never raise
            _logger.warning("driver_error run=%s error=%s", run_id, type(error).__name__)
        finally:
            with self._cond:
                # Fallback only (error, stop, gone): the normal end already removed this
                # loop under the lock; never remove a newer loop a `start` made since.
                if self._loops.get(run_id) is loop:
                    self._loops.pop(run_id, None)
                self._cond.notify_all()
            _logger.info("driver_stopped run=%s", run_id)

    def _loop(self, run_id: UUID, loop: _Loop) -> None:
        errors = 0
        unchanged = 0
        while True:
            with self._cond:
                if self._stopped:
                    return
                loop.recheck = False
            try:
                step = self._step(run_id)
            except Exception as error:  # noqa: BLE001 -- a transient store error
                errors += 1
                _logger.warning(
                    "driver_error run=%s error=%s consecutive=%d",
                    run_id,
                    type(error).__name__,
                    errors,
                )
                if errors >= _MAX_CONSECUTIVE_ERRORS:
                    _logger.warning("driver_gave_up run=%s reason=errors", run_id)
                    return
                self._pause(loop, _IDLE_RETRY_SECONDS)
                continue
            errors = 0
            if step == "end":
                with self._cond:
                    if self._stopped:
                        return
                    if loop.recheck:
                        continue
                    # Decided, and the entry removed, under the lock a `start` takes: it
                    # either set `recheck` before this, or finds no loop and makes a new one.
                    if self._loops.get(run_id) is loop:
                        self._loops.pop(run_id, None)
                    self._cond.notify_all()
                return
            unchanged = unchanged + 1 if step == "unchanged" else 0
            if unchanged >= _MAX_UNCHANGED_ROUNDS:
                _logger.warning("driver_gave_up run=%s reason=no_progress", run_id)
                return
            if step == "unchanged":
                self._pause(loop, _IDLE_RETRY_SECONDS)

    def _step(self, run_id: UUID) -> str:
        """One evaluation: ``end`` (nothing more to drive), ``changed``, ``unchanged``
        (a round changed nothing) or ``idle`` (waited for a lease)."""
        with Session(self._engine) as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                _logger.info("driver_run_gone run=%s", run_id)
                return "end"
            if run.failed_at is not None or run.stage in _FINISHED_STAGES:
                return "end"
            if run.stage == "payload_ready":
                return self._draft_step(session, run)
            return self._advance_step(session, run)

    def _advance_step(self, session: Session, run: ReportRun) -> str:
        """One ``advance()`` call; a missing Client or chart fails the run for good."""
        stored_chart = current_chart_for_client(session, run.client_id)
        if stored_chart is None:
            self._fail(session, run, f"ReportRun {run.id} has no Client or no stored chart.")
            return "end"
        before = (run.stage, run.stage_failure_count, run.failed_at)
        advance(
            session,
            run,
            natal_chart=deserialize_natal_chart(stored_chart),
            natal_chart_id=stored_chart.id,
            config=self._config,
            ephemeris_identity=self._ephemeris_identity,
            sections_config=self._sections_config,
            vocabulary=self._vocabulary,
        )
        after = (run.stage, run.stage_failure_count, run.failed_at)
        return "changed" if after != before else "unchanged"

    def _draft_step(self, session: Session, run: ReportRun) -> str:
        """The ``draft_ready`` work: open the attempt, write what is claimable,
        assemble when complete, fail the run when a Section is out of attempts."""
        run_id = run.id
        attempt = open_draft_attempt(session, run)
        states = [section_state(row) for row in section_rows(session, run.id, attempt)]
        now = self._now()
        if is_draft_complete(states):
            return "changed" if assemble_draft(session, run, attempt) else "unchanged"
        if is_exhausted(states, max_attempts=self._max_attempts):
            self._fail_exhausted(session, run, attempt)
            return "end"
        claimable = claimable_sections(states, max_attempts=self._max_attempts, now=now)
        if claimable:
            # End the transaction first: the wait below can take a minute, and a
            # connection held across it is one the generation jobs cannot use.
            session.rollback()
            return self._round(run_id, attempt, claimable)
        # Another writer's live lease is the only obstacle: look again once it expires.
        expiries = live_lease_expiries(states, now)
        session.rollback()
        self._pause_until(expiries, now)
        return "idle" if expiries else "unchanged"

    def _round(self, run_id: UUID, attempt: int, ordinals: tuple[int, ...]) -> str:
        """One job per claimable Section, at most the cap in flight."""
        futures: list[Future[bool]] = []
        for ordinal in ordinals:
            try:
                futures.append(
                    self._generation.submit(self._write_section, run_id, attempt, ordinal)
                )
            except RuntimeError:
                break  # the executor was shut down by `stop`
        # `result()`, not `wait()`: a future the executor cancels on stop is never
        # "notified", so `wait` would block forever on it.
        wrote = False
        for future in futures:
            try:
                wrote = future.result() or wrote
            except CancelledError:
                continue
        _logger.info("driver_round run=%s attempt=%d sections=%d", run_id, attempt, len(ordinals))
        return "changed" if wrote else "unchanged"

    # -- one Section's job -----------------------------------------------------------

    def _write_section(self, run_id: UUID, attempt: int, ordinal: int) -> bool:
        """Claim one Section, generate it, record the outcome. Whether this call wrote
        anything; never raises. Reaches no chart code -- only storage and the Generator."""
        try:
            with Session(self._engine) as session:
                row = session.exec(
                    select(ReportDraftSection)
                    .where(ReportDraftSection.report_run_id == run_id)
                    .where(ReportDraftSection.attempt == attempt)
                    .where(ReportDraftSection.ordinal == ordinal)
                ).one()
                section_id, name = row.id, row.name
            with section_claim(
                self._engine, section_id, now=self._now, ttl=self._lease_ttl
            ) as claim:
                if claim is None:
                    return False
                try:
                    sentences = self._generate(run_id, attempt, ordinal, name)
                except Exception as error:  # noqa: BLE001 -- any failure costs one attempt
                    self._record_failure(section_id, claim, error)
                    _logger.warning(
                        "driver_section_failed run=%s section=%s error=%s",
                        run_id,
                        name,
                        type(error).__name__,
                    )
                    return True
                self._record_success(section_id, claim, sentences)
                return True
        except Exception as error:  # noqa: BLE001 -- a job must never raise into its loop
            _logger.warning(
                "driver_section_error run=%s ordinal=%d error=%s",
                run_id,
                ordinal,
                type(error).__name__,
            )
            return False

    def _generate(
        self, run_id: UUID, attempt: int, ordinal: int, name: str
    ) -> tuple[Sentence, ...]:
        with Session(self._engine) as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise LookupError(f"ReportRun {run_id} is gone.")
            inputs = load_generation_inputs(session, run)
            written: dict[str, tuple[Sentence, ...]] | None = None
            if ordinal == CLOSING_ORDINAL:
                written = {
                    row.name: sentences_from_json(row.sentences or [])
                    for row in section_rows(session, run_id, attempt)
                    if row.ordinal < CLOSING_ORDINAL and row.status == STATUS_COMPLETE
                }
        return self._generator().generate_section(
            name,
            inputs.payload,
            inputs.style_guide,
            inputs.theme_previous,
            inputs.theme_current,
            written,
        )

    def _record_success(
        self, section_id: UUID, claim: datetime, sentences: tuple[Sentence, ...]
    ) -> None:
        """Write the Section, but only while the row still carries ``claim``: a writer
        whose lease expired and was reclaimed (or whose Section another writer
        completed) changes nothing."""
        with Session(self._engine) as session:
            session.execute(
                update(ReportDraftSection)
                .where(ReportDraftSection.id == section_id)  # type: ignore[arg-type]
                .where(ReportDraftSection.status == STATUS_PENDING)  # type: ignore[arg-type]
                .where(ReportDraftSection.claimed_at == claim)  # type: ignore[arg-type]
                .values(
                    status=STATUS_COMPLETE,
                    sentences=sentences_to_json(sentences),
                    last_error=None,
                    claimed_at=None,
                    claim_expires_at=None,
                )
            )
            session.commit()

    def _record_failure(self, section_id: UUID, claim: datetime, error: Exception) -> None:
        """One failed attempt, applied only while the row still carries ``claim``:
        ``attempts + 1``, ``last_error`` set, ``failed`` once every attempt is spent.
        Otherwise the Section is held off for ``retry_base_delay * 2**(attempts - 1)``
        seconds by turning the claim into a plain expiry (``claimed_at`` cleared,
        ``claim_expires_at`` pushed out) -- so a rate limit cannot burn every attempt
        in milliseconds, and the claim's own release leaves the hold-off in place."""
        message = f"{type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH]
        with Session(self._engine) as session:
            row = session.exec(
                select(ReportDraftSection)
                .where(ReportDraftSection.id == section_id)
                .where(ReportDraftSection.status == STATUS_PENDING)
                .where(ReportDraftSection.claimed_at == claim)
            ).first()
            if row is None:
                return
            attempts = row.attempts + 1
            exhausted = attempts >= self._max_attempts
            hold_off = None
            if not exhausted:
                delay = self._retry_base_delay * 2 ** (attempts - 1)
                hold_off = self._now() + timedelta(seconds=delay)
            session.execute(
                update(ReportDraftSection)
                .where(ReportDraftSection.id == section_id)  # type: ignore[arg-type]
                .where(ReportDraftSection.status == STATUS_PENDING)  # type: ignore[arg-type]
                .where(ReportDraftSection.claimed_at == claim)  # type: ignore[arg-type]
                .values(
                    attempts=attempts,
                    last_error=message,
                    status=STATUS_FAILED if exhausted else STATUS_PENDING,
                    claimed_at=None,
                    claim_expires_at=hold_off,
                )
            )
            session.commit()

    # -- failing a run ----------------------------------------------------------------

    def _fail_exhausted(self, session: Session, run: ReportRun, attempt: int) -> None:
        """Mark the run terminally failed, naming the Section that ran out of attempts."""
        rows = section_rows(session, run.id, attempt)
        culprit = next(
            row
            for row in rows
            if row.status == STATUS_FAILED
            or (row.status == STATUS_PENDING and row.attempts >= self._max_attempts)
        )
        name = SECTION_NAMES[culprit.ordinal - 1]
        self._fail(
            session,
            run,
            f"Section {name!r} failed {culprit.attempts} times: {culprit.last_error}",
        )

    def _fail(self, session: Session, run: ReportRun, reason: str) -> None:
        session.refresh(run)
        if run.failed_at is not None:
            return
        run.failed_at = run.updated_at = self._now()
        run.failure_reason = reason
        session.add(run)
        session.commit()
        _logger.error("report run marked terminally failed: %s", run.id)

    # -- waiting ------------------------------------------------------------------------

    def _pause_until(self, expiries: list[datetime], now: datetime) -> None:
        """Sleep until the earliest live lease expires, but never longer than the idle
        retry: the writer holding it may be another process, which releases the lease
        (success or failure) without telling this one, so the loop looks again soon.
        Wakes early on a ``start`` or ``stop``."""
        seconds = _IDLE_RETRY_SECONDS
        if expiries:
            wait_for = (min(expiries) - now).total_seconds() + _EXPIRY_SLACK_SECONDS
            seconds = min(max(wait_for, _EXPIRY_SLACK_SECONDS), _IDLE_RETRY_SECONDS)
        with self._cond:
            if not self._stopped:
                self._cond.wait(timeout=seconds)

    def _pause(self, loop: _Loop, seconds: float) -> None:
        """Sleep up to ``seconds``, waking early on a ``start`` or ``stop``."""
        with self._cond:
            if not (loop.recheck or self._stopped):
                self._cond.wait(timeout=seconds)
