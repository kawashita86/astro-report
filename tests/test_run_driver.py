"""``RunDriver`` (Story 10.4, AD-20/AD-21): a started run reaches ``gate_passed`` with no
further request; Sections 1-7 are written in parallel under the process-wide cap and
Consiglio finale only after them; failures cost attempts and exhaust into a failed run;
a restart resumes without rewriting a complete Section; two drivers on one run never
write a Section twice.

The driver runs real threads, so these tests use a file-backed SQLite (an in-memory one is
per-connection) copied from a template built once with the real chart stages -- the chart
work is not what is under test, the draft stage is.
"""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, text
from sqlmodel import Session, SQLModel, create_engine, select

import shell.runner.driver as driver_module
from core.draft_state import SECTION_NAMES
from core.types.generation import GeneratedDraft, Sentence
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_draft_section import (
    ReportDraftSection,
    open_section_rows,
    section_rows,
    sentences_to_json,
)
from shell.adapters.postgres.report_run import ReportRun
from shell.runner.driver import RunDriver
from tests.test_runner_advance import (
    _COMPUTATION_CONFIG,
    _EPHEMERIS_IDENTITY,
    _SECTIONS_CONFIG,
    _VOCABULARY,
    _a_generated_draft,
    _a_two_violation_generated_draft,
    _advance,
    _create_client_and_chart,
    _FakeGenerator,
)

_WAIT = 60.0


def _engine_for(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def _wal(dbapi_connection: object, record: object) -> None:
        dbapi_connection.execute("PRAGMA journal_mode=WAL")  # type: ignore[attr-defined]

    return engine


@pytest.fixture(scope="module")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, UUID]:
    """A database holding one Client with a run advanced (really) to ``payload_ready``."""
    path = tmp_path_factory.mktemp("template") / "template.db"
    engine = _engine_for(path)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        client, natal_chart = _create_client_and_chart(session)
        run = ReportRun(client_id=client.id, month="2026-01")
        session.add(run)
        session.commit()
        for _ in range(3):
            _advance(session, run, natal_chart)
        assert run.stage == "payload_ready"
        run_id = run.id
    engine.dispose()
    return path, run_id


@pytest.fixture
def engine(template_db: tuple[Path, UUID], tmp_path: Path) -> Iterator[Engine]:
    copy = tmp_path / "run.db"
    shutil.copy(template_db[0], copy)
    engine = _engine_for(copy)
    yield engine
    engine.dispose()


@pytest.fixture
def run_id(template_db: tuple[Path, UUID]) -> UUID:
    return template_db[1]


@pytest.fixture
def drivers() -> Iterator[list[RunDriver]]:
    created: list[RunDriver] = []
    yield created
    for driver in created:
        driver.stop()


def _driver(
    drivers: list[RunDriver], engine: Engine, generator: object, **overrides: object
) -> RunDriver:
    options: dict[str, object] = {
        "engine": engine,
        "config": _COMPUTATION_CONFIG,
        "ephemeris_identity": _EPHEMERIS_IDENTITY,
        "sections_config": _SECTIONS_CONFIG,
        "vocabulary": _VOCABULARY,
        "generator": lambda: generator,
        "concurrency": 11,
        "retry_base_delay": 0.0,
    }
    options.update(overrides)
    driver = RunDriver(**options)  # type: ignore[arg-type]
    drivers.append(driver)
    return driver


class _Recorder(_FakeGenerator):
    """A fake that is safe to call from many threads and records when each Section
    started and finished, how many ran at once, and what Consiglio finale was shown."""

    def __init__(self, draft: GeneratedDraft | None = None, *, delay: float = 0.0) -> None:
        super().__init__(draft)
        self._lock = threading.Lock()
        self._delay = delay
        self.started: dict[str, float] = {}
        self.finished: dict[str, float] = {}
        self.counts: dict[str, int] = {}
        self.written_seen: dict[str, object] = {}
        self._running = 0
        self.peak = 0
        self.threads: set[str] = set()

    def generate_section(
        self, section, payload, style_guide, theme_previous, theme_current, written_sections=None
    ):
        with self._lock:
            self.counts[section] = self.counts.get(section, 0) + 1
            self.started[section] = time.monotonic()
            self.written_seen[section] = written_sections
            self._running += 1
            self.peak = max(self.peak, self._running)
            self.threads.add(threading.current_thread().name)
        try:
            if self._delay:
                time.sleep(self._delay)
            return super().generate_section(
                section, payload, style_guide, theme_previous, theme_current, written_sections
            )
        finally:
            with self._lock:
                self._running -= 1
                self.finished[section] = time.monotonic()


def _wait_done(driver: RunDriver) -> None:
    assert driver.wait_idle(_WAIT), "the driver did not go idle in time"


def _run(engine: Engine, run_id: UUID) -> ReportRun:
    with Session(engine) as session:
        run = session.get(ReportRun, run_id)
        assert run is not None
        session.expunge(run)
        return run


def _rows(engine: Engine, run_id: UUID, attempt: int = 0) -> list[ReportDraftSection]:
    with Session(engine) as session:
        rows = section_rows(session, run_id, attempt)
        for row in rows:
            session.expunge(row)
        return rows


def _count(engine: Engine, model: type) -> int:
    with Session(engine) as session:
        return len(session.exec(select(model)).all())


# --- the happy path -----------------------------------------------------------------


def test_a_started_run_reaches_gate_passed_with_no_further_request(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    _wait_done(driver)

    run = _run(engine, run_id)
    assert run.stage == "gate_passed"
    assert run.failed_at is None
    assert _count(engine, Report) == 1
    assert _count(engine, ReportDraft) == 1
    rows = _rows(engine, run_id)
    assert [row.status for row in rows] == ["complete"] * 8
    assert all(row.claim_expires_at is None for row in rows)
    assert generator.counts == dict.fromkeys(SECTION_NAMES, 1)


def test_a_run_started_from_scratch_walks_every_stage_in_the_background(
    drivers: list[RunDriver], tmp_path: Path
) -> None:
    """The chart stages run on a loop thread too: from ``stage=None`` all the way through."""
    engine = _engine_for(tmp_path / "fresh.db")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        client, _ = _create_client_and_chart(session)
        run = ReportRun(client_id=client.id, month="2026-01")
        session.add(run)
        session.commit()
        fresh_id = run.id
    driver = _driver(drivers, engine, _Recorder())

    driver.start(fresh_id)
    _wait_done(driver)

    assert _run(engine, fresh_id).stage == "gate_passed"
    engine.dispose()


def test_the_assembled_draft_is_the_eight_sections_verbatim(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    draft = GeneratedDraft(
        energia_generale=(Sentence(text="Un mese intenso.", entry_ids=("id-1", "id-2")),),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(Sentence(text="Respira.", entry_ids=()),),
    )
    driver = _driver(drivers, engine, _Recorder(draft))

    driver.start(run_id)
    _wait_done(driver)

    with Session(engine) as session:
        stored = session.exec(select(ReportDraft)).one()
    assert stored.attempt == 0
    assert stored.draft["energia_generale"] == [
        {"text": "Un mese intenso.", "entry_ids": ["id-1", "id-2"]}
    ]
    assert stored.draft["consiglio_finale"] == [{"text": "Respira.", "entry_ids": []}]
    assert stored.draft["amore"] == []


# --- fan-out and speed --------------------------------------------------------------


def test_sections_one_to_seven_run_together_and_consiglio_finale_only_after_them(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=0.5)
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    _wait_done(driver)

    assert generator.peak == 7
    others = [name for name in SECTION_NAMES if name != "consiglio_finale"]
    assert generator.started["consiglio_finale"] >= max(generator.finished[n] for n in others)
    # ... and was shown exactly the seven written Sections, text only.
    shown = generator.written_seen["consiglio_finale"]
    assert set(shown) == set(others)
    assert all(isinstance(sentences, tuple) for sentences in shown.values())
    assert all(generator.written_seen[name] is None for name in others)


def test_a_draft_of_one_second_sections_is_complete_in_about_two_seconds(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=1.0)
    driver = _driver(drivers, engine, generator)
    started = time.monotonic()

    driver.start(run_id)
    _wait_done(driver)

    # Gate and assembly add a little; eight serial calls would take 8 s.
    assert time.monotonic() - started < 4.5
    assert _run(engine, run_id).stage == "gate_passed"


def test_the_generation_cap_is_the_process_wide_brake(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=0.2)
    driver = _driver(drivers, engine, generator, concurrency=2)

    driver.start(run_id)
    _wait_done(driver)

    assert generator.peak == 2
    assert _run(engine, run_id).stage == "gate_passed"


def test_generation_jobs_run_on_their_own_threads_never_on_a_run_loop(
    drivers: list[RunDriver], engine: Engine, run_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop threads bind the verified ephemeris path before advancing; the
    generation executor reaches no chart code, so it never binds."""
    bound_on: list[str] = []
    real_bind = driver_module.bind_verified_ephemeris_path_to_current_thread

    def _spy() -> None:
        bound_on.append(threading.current_thread().name)
        real_bind()

    monkeypatch.setattr(driver_module, "bind_verified_ephemeris_path_to_current_thread", _spy)
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    _wait_done(driver)

    assert bound_on
    assert all(name.startswith("ar-run") for name in bound_on)
    assert generator.threads
    assert all(name.startswith("ar-generate") for name in generator.threads)


# --- failure ------------------------------------------------------------------------


class _FlakyGenerator(_Recorder):
    """Raises for ``section`` on its first ``failures`` calls, then behaves."""

    def __init__(self, section: str, failures: int) -> None:
        super().__init__()
        self._section = section
        self._failures = failures

    def generate_section(self, section, *args, **kwargs):
        if section == self._section:
            with self._lock:
                self.counts[section] = self.counts.get(section, 0) + 1
                seen = self.counts[section]
            if seen <= self._failures:
                raise RuntimeError("simulated transient failure")
            return getattr(self._draft, section)
        return super().generate_section(section, *args, **kwargs)


def test_a_transient_failure_costs_an_attempt_and_is_retried(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _FlakyGenerator("amore", failures=2)
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    _wait_done(driver)

    assert _run(engine, run_id).stage == "gate_passed"
    amore = next(row for row in _rows(engine, run_id) if row.name == "amore")
    assert amore.status == "complete"
    assert amore.attempts == 2
    assert generator.counts["amore"] == 3
    assert all(row.attempts == 0 for row in _rows(engine, run_id) if row.name != "amore")


def test_a_failed_attempt_records_the_error_and_leaves_the_section_pending(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    release = threading.Event()

    class _FailsThenBlocks(_Recorder):
        def generate_section(self, section, *args, **kwargs):
            if section == "amore":
                with self._lock:
                    self.counts[section] = self.counts.get(section, 0) + 1
                    seen = self.counts[section]
                if seen == 1:
                    raise RuntimeError("boom")
                release.wait(_WAIT)
            return super().generate_section(section, *args, **kwargs)

    driver = _driver(drivers, engine, _FailsThenBlocks())
    driver.start(run_id)
    deadline = time.monotonic() + _WAIT
    amore = None
    while time.monotonic() < deadline:
        amore = next((row for row in _rows(engine, run_id) if row.name == "amore"), None)
        if amore is not None and amore.attempts == 1 and amore.claim_expires_at is not None:
            break
        time.sleep(0.05)
    release.set()
    _wait_done(driver)

    assert amore is not None
    assert amore.attempts == 1
    assert amore.last_error is not None and "boom" in amore.last_error
    assert amore.status == "pending"


def test_a_section_out_of_attempts_fails_the_run_naming_it_and_no_report_is_written(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _FlakyGenerator("lavoro", failures=99)
    driver = _driver(drivers, engine, generator, max_attempts=3)

    driver.start(run_id)
    _wait_done(driver)

    run = _run(engine, run_id)
    assert run.failed_at is not None
    assert run.failure_reason is not None
    assert "lavoro" in run.failure_reason
    assert "simulated transient failure" in run.failure_reason
    assert run.stage == "payload_ready"
    assert _count(engine, Report) == 0
    assert _count(engine, ReportDraft) == 0
    lavoro = next(row for row in _rows(engine, run_id) if row.name == "lavoro")
    assert (lavoro.status, lavoro.attempts) == ("failed", 3)
    assert generator.counts["lavoro"] == 3
    # The healthy Sections were still saved.
    assert [row.status for row in _rows(engine, run_id) if row.name == "amore"] == ["complete"]


def test_consiglio_finale_is_never_written_when_a_section_before_it_failed(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _FlakyGenerator("denaro", failures=99)
    driver = _driver(drivers, engine, generator, max_attempts=2)

    driver.start(run_id)
    _wait_done(driver)

    assert "consiglio_finale" not in generator.counts
    consiglio = next(row for row in _rows(engine, run_id) if row.name == "consiglio_finale")
    assert consiglio.status == "pending" and consiglio.attempts == 0


def test_a_run_with_no_stored_chart_is_failed_not_retried_forever(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    with Session(engine) as session:
        session.execute(text("UPDATE report_run SET stage = 'transits_ready'"))
        session.execute(text("DELETE FROM natal_chart"))
        session.commit()
    driver = _driver(drivers, engine, _Recorder())

    driver.start(run_id)
    _wait_done(driver)

    run = _run(engine, run_id)
    assert run.failed_at is not None
    assert "chart" in (run.failure_reason or "")


# --- restart and leases -----------------------------------------------------------------


def _seed_partial(
    engine: Engine, run_id: UUID, *, complete: tuple[int, ...], lease: dict[int, datetime]
) -> None:
    """Attempt 0 as a dead process left it: the ``complete`` ordinals written, others
    pending, and the given ordinals carrying a lease."""
    with Session(engine) as session:
        open_section_rows(session, run_id, 0)
        session.commit()
        for row in section_rows(session, run_id, 0):
            if row.ordinal in complete:
                row.status = "complete"
                row.sentences = sentences_to_json(getattr(_a_generated_draft(), row.name))
            if row.ordinal in lease:
                row.claimed_at = lease[row.ordinal] - timedelta(minutes=3)
                row.claim_expires_at = lease[row.ordinal]
            session.add(row)
        session.commit()


def test_resume_finishes_a_half_written_draft_without_rewriting_a_complete_section(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    _seed_partial(engine, run_id, complete=(1, 2, 3, 4), lease={})
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)

    driver.resume()
    _wait_done(driver)

    assert _run(engine, run_id).stage == "gate_passed"
    assert set(generator.counts) == set(SECTION_NAMES[4:])
    assert all(count == 1 for count in generator.counts.values())


def test_a_lease_left_by_a_dead_process_expires_and_is_reclaimed(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    soon = datetime.now(UTC) + timedelta(seconds=1.5)
    already = datetime.now(UTC) - timedelta(seconds=5)
    _seed_partial(engine, run_id, complete=(1, 2, 3), lease={5: soon, 6: already})
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)
    started = time.monotonic()

    driver.resume()
    _wait_done(driver)

    assert _run(engine, run_id).stage == "gate_passed"
    # Section 5's live lease was respected, then reclaimed once it ran out.
    assert generator.counts["benessere"] == 1
    assert generator.counts["giorni_favorevoli"] == 1
    assert time.monotonic() - started >= 1.0


def test_resume_skips_finished_and_failed_runs(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    with Session(engine) as session:
        session.execute(
            text("UPDATE report_run SET failed_at = :now, failure_reason = 'x'"),
            {"now": datetime.now(UTC)},
        )
        session.commit()
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)

    driver.resume()
    _wait_done(driver)

    assert generator.counts == {}
    assert _count(engine, ReportDraftSection) == 0


def test_stop_drops_work_and_loses_nothing_the_next_driver_resumes_it(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    gate = threading.Event()

    class _Blocking(_Recorder):
        def generate_section(self, section, *args, **kwargs):
            if section == "benessere":
                gate.wait(_WAIT)
            return super().generate_section(section, *args, **kwargs)

    first = _driver(drivers, engine, _Blocking())
    first.start(run_id)
    deadline = time.monotonic() + _WAIT
    while time.monotonic() < deadline:
        rows = _rows(engine, run_id)
        if sum(row.status == "complete" for row in rows) >= 6:
            break
        time.sleep(0.05)
    first.stop()
    gate.set()
    done_before = {row.name for row in _rows(engine, run_id) if row.status == "complete"}

    second_generator = _Recorder()
    second = _driver(drivers, engine, second_generator, lease_ttl=timedelta(seconds=1))
    second.resume()
    _wait_done(second)

    assert _run(engine, run_id).stage == "gate_passed"
    assert not (set(second_generator.counts) & (done_before - {"benessere"}))


# --- concurrency -------------------------------------------------------------------------


def test_two_drivers_on_one_run_never_write_a_section_twice(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=0.3)
    first = _driver(drivers, engine, generator)
    second = _driver(drivers, engine, generator)

    first.start(run_id)
    second.start(run_id)
    _wait_done(first)
    _wait_done(second)

    assert generator.counts == dict.fromkeys(SECTION_NAMES, 1)
    assert _run(engine, run_id).stage == "gate_passed"
    assert _count(engine, ReportDraft) == 1
    assert _count(engine, Report) == 1


def test_starting_a_run_that_is_already_being_driven_changes_nothing(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=0.3)
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    driver.start(run_id)
    driver.start(run_id)
    _wait_done(driver)

    assert generator.counts == dict.fromkeys(SECTION_NAMES, 1)


def test_start_returns_at_once_and_a_stopped_driver_ignores_it(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    generator = _Recorder(delay=0.5)
    driver = _driver(drivers, engine, generator)
    began = time.monotonic()

    driver.start(run_id)

    assert time.monotonic() - began < 0.4
    driver.stop()
    driver.start(run_id)
    assert not driver.is_driving(run_id)


# --- the Gate ----------------------------------------------------------------------------


def test_a_gate_failure_opens_a_new_full_attempt_of_eight_fresh_rows(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    class _ViolatesOnce(_Recorder):
        def generate_section(self, section, *args, **kwargs):
            draft = (
                _a_two_violation_generated_draft()
                if self.counts.get("amore", 0) == 0
                else _a_generated_draft()
            )
            self._draft = draft
            return super().generate_section(section, *args, **kwargs)

    generator = _ViolatesOnce()
    driver = _driver(drivers, engine, generator)

    driver.start(run_id)
    _wait_done(driver)

    run = _run(engine, run_id)
    assert run.stage == "gate_passed"
    assert run.regeneration_count == 1
    assert _count(engine, ReportDraft) == 2
    assert len(_rows(engine, run_id, 0)) == 8
    assert len(_rows(engine, run_id, 1)) == 8
    assert {row.status for row in _rows(engine, run_id, 1)} == {"complete"}
    with Session(engine) as session:
        results = session.exec(select(StoredGateResult).order_by(StoredGateResult.created_at)).all()
    assert [result.passed for result in results] == [False, True]


def test_a_regenerate_rewind_is_picked_up_by_a_new_start(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    """The route rewinds a failed run to ``payload_ready`` and calls ``start``: the
    same driver that finished it before drives it again, into a fresh attempt."""
    generator = _Recorder()
    driver = _driver(drivers, engine, generator)
    driver.start(run_id)
    _wait_done(driver)
    with Session(engine) as session:
        session.execute(text("UPDATE report_run SET stage = 'payload_ready'"))
        session.commit()

    driver.start(run_id)
    _wait_done(driver)

    assert _count(engine, ReportDraft) == 2
    assert len(_rows(engine, run_id, 1)) == 8
    assert generator.counts == dict.fromkeys(SECTION_NAMES, 2)


# --- retry hold-off and write fencing ----------------------------------------------------


def test_a_failed_attempt_holds_the_section_off_so_failures_are_spaced_by_the_delay(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    """A rate limit must not burn every attempt in milliseconds: after a failure the
    Section is not claimable until ``retry_base_delay * 2**(attempts - 1)`` has passed."""
    stamps: list[float] = []

    class _Stamps(_FlakyGenerator):
        def generate_section(self, section, *args, **kwargs):
            if section == "amore":
                stamps.append(time.monotonic())
            return super().generate_section(section, *args, **kwargs)

    driver = _driver(drivers, engine, _Stamps("amore", failures=2), retry_base_delay=0.5)

    driver.start(run_id)
    _wait_done(driver)

    assert len(stamps) == 3
    assert stamps[1] - stamps[0] >= 0.5
    assert stamps[2] - stamps[1] >= 1.0
    assert _run(engine, run_id).stage == "gate_passed"


def _claimed_pending_row(engine: Engine, run_id: UUID) -> tuple[UUID, datetime]:
    token = datetime.now(UTC)
    with Session(engine) as session:
        open_section_rows(session, run_id, 0)
        session.commit()
        row = section_rows(session, run_id, 0)[1]
        row.claimed_at = token
        row.claim_expires_at = token + timedelta(minutes=3)
        session.add(row)
        session.commit()
        return row.id, token


def test_a_stale_writer_whose_claim_was_taken_over_is_ignored(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    driver = _driver(drivers, engine, _Recorder())
    section_id, stale = _claimed_pending_row(engine, run_id)
    # Another writer reclaimed the Section after our lease expired.
    newer = stale + timedelta(minutes=5)
    with Session(engine) as session:
        row = session.get(ReportDraftSection, section_id)
        row.claimed_at = newer
        session.add(row)
        session.commit()

    driver._record_success(section_id, stale, (Sentence(text="Vecchia.", entry_ids=()),))
    driver._record_failure(section_id, stale, RuntimeError("late"))

    row = next(r for r in _rows(engine, run_id) if r.id == section_id)
    assert row.status == "pending" and row.sentences is None
    assert row.attempts == 0 and row.last_error is None
    assert row.claimed_at == newer


def test_the_current_claim_holder_is_applied(
    drivers: list[RunDriver], engine: Engine, run_id: UUID
) -> None:
    driver = _driver(drivers, engine, _Recorder())
    section_id, token = _claimed_pending_row(engine, run_id)

    driver._record_success(section_id, token, (Sentence(text="Nuova.", entry_ids=()),))

    row = next(r for r in _rows(engine, run_id) if r.id == section_id)
    assert row.status == "complete" and row.sentences == [{"text": "Nuova.", "entry_ids": []}]
    assert row.claimed_at is None and row.claim_expires_at is None
