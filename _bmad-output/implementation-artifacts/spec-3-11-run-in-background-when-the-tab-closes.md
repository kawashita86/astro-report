---
title: 'Run in background when the tab closes'
type: 'feature'
created: '2026-09-14'
status: 'done'
review_loop_iteration: 2
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
baseline_commit: 'c1c9d9a4b8b1f6148d649988fc283b443deca3c3'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `advance()` (`shell/runner/driver.py`) only ever runs from the poll GET (AD-20,
Story 3.10) — a run pauses at its last checkpoint the moment Francesco closes the tab, and only
resumes once he reopens it and polls again. Francesco asked for a second, deployment-wide mode
where a run keeps advancing unattended, without changing how the stage-track view looks or
behaves — met by a correct-course amendment to AD-20 (`ARCHITECTURE-SPINE.md`, 2026-09-14).

**Approach:** Add a `REPORT_RUN_MODE` setting (`poll` | `background`, default `poll`). In
`background` mode, an in-process asyncio scheduler task — started at app startup, stopped at
shutdown — ticks the same `advance()`, under the same advisory lock, for every incomplete
`ReportRun`; the poll handler becomes read-only in that mode. `poll` mode stays exactly what
Story 3.10 shipped.

## Boundaries & Constraints

**Always:**
- `shell/config.py` -- new `ReportRunMode` `StrEnum` (`POLL = "poll"`, `BACKGROUND = "background"`);
  `Settings.report_run_mode: ReportRunMode = ReportRunMode.POLL` (a **default at the dataclass
  level**, not just in the reader -- 14 test files construct `Settings(...)` directly without this
  field and must keep working unmodified). New `_read_report_run_mode(environ)` follows the
  existing `(value, error)` shape but, uniquely among this file's readers, is **optional**: unset
  or blank -> `(ReportRunMode.POLL, None)`; set to `"poll"`/`"background"` -> that value; anything
  else -> an error naming the permitted values, folded into `load_settings()`'s existing
  `problems` collection exactly like every other reader. Add `report_run_mode` to `__repr__` (not
  secret, no redaction) and to `__all__`.
- `shell/runner/scheduler.py` (new, one-concern runner module, mirrors `advisory_lock.py`) --
  `generator_for_settings(settings) -> Generator` (the `Environment.LOCAL` ->
  `RecordedResponseGenerator()` / else `GeminiGenerator(settings.gemini_api_key)` branch, moved
  here from `report_runs.py::get_generator` so both call sites share one decision);
  `_run_pending_report_runs(engine, *, config, ephemeris_identity, sections_config, vocabulary,
  settings) -> None` (sync): one `Session`, one query --
  `select(ReportRun).where(ReportRun.failed_at.is_(None)).where(or_(ReportRun.stage.is_(None),
  ReportRun.stage != "gate_passed"))` (`or_` needed because SQL `NULL != 'gate_passed'` is not
  `TRUE` -- a run that never had a first poll, `stage IS NULL`, must still be picked up) -- then,
  for each row, loads its `Client` + current stored chart, deserializes the chart, and calls the
  same `advance()` Story 3.10 uses, one `Session` shared across the whole tick; `_scheduler_loop(application)`
  (async): `while True: await asyncio.to_thread(_run_pending_report_runs, ...); await
  asyncio.sleep(_TICK_INTERVAL_SECONDS)`, `_TICK_INTERVAL_SECONDS = 2.0` (mirrors
  `report_run_poll.html`'s existing `hx-trigger="every 2s"` so background progress reads the same
  speed as watching the tab); `start_scheduler(application)` (sync, called before `yield`) sets
  `application.state.scheduler_task` to a new `asyncio.create_task(_scheduler_loop(application))`
  when `settings.report_run_mode is ReportRunMode.BACKGROUND`, else `None`; `async def
  stop_scheduler(application)` (called after `yield`, before `engine.dispose()`) is a no-op when
  the task is `None`, else cancels it and awaits it inside `contextlib.suppress(asyncio.CancelledError)`.
- Per-run isolation: each row's client/chart lookup + `advance()` call is wrapped in its own
  `try/except Exception`; on failure, `_logger.exception(...)` then `session.rollback()`, and the
  loop continues to the next row -- one bad run must never abort the tick or leave the shared
  session unusable for the rest of it.
- Unrecoverable per-run lookup failure (review-loop 1): when the row's `Client` or its current
  stored chart is missing -- the two checks that raise `RuntimeError` before `advance()` is ever
  called -- catch that specific failure separately from a generic `advance()` exception and mark
  the run terminally failed in the same transaction: `run.failed_at = datetime.now(UTC)`,
  `run.failure_reason` naming which lookup failed, `session.add(run)`, `session.commit()` (no
  `session.rollback()` in this branch -- the point is to persist the terminal state, mirroring
  `shell/runner/driver.py`'s own terminal-failure shape). Never silently retried forever the way
  the generic per-row `except` above would otherwise retry it every tick. An exception raised by
  `advance()` itself still falls through to the generic per-row `except Exception` above unchanged
  -- `advance()` already has its own internal terminal-failure handling for stage errors; this
  addition is scoped to the pre-`advance()` lookup only.
- Outer-loop isolation: `_scheduler_loop`'s `await asyncio.to_thread(...)` call is itself wrapped in
  `try/except Exception: _logger.exception(...)` before the `asyncio.sleep` -- the task must never
  die silently, since a dead task means `background` mode silently reverts to no progress at all.
- `shell/http/app.py::_lifespan` -- call `start_scheduler(application)` right after `yield` is
  reached is wrong; call it **before** `yield` (mirrors where `application.state.engine` is already
  set, in `create_app`, not in `_lifespan`), and `await stop_scheduler(application)` **before**
  `application.state.engine.dispose()` after `yield` -- the scheduler must be fully stopped before
  the engine it uses is disposed. Rewrite the docstring to describe both engine disposal and
  scheduler stop/start.
- `shell/http/routes/report_runs.py::poll_report_run` -- call `_advance_run(...)` only when
  `request.app.state.settings.report_run_mode is ReportRunMode.POLL`; in `background` mode `run`
  (already loaded via `session.get` earlier in the handler) is rendered as-is, with no `advance()`
  call from the poll at all. `get_generator` becomes a one-line delegate to
  `generator_for_settings(request.app.state.settings)`. Import `ReportRunMode` alongside the
  existing `Environment` import.

**Ask First:** None identified.

**Never:**
- No new dependency (no APScheduler, no Celery/RQ, no queue library) -- a plain `asyncio.Task` on
  the existing event loop is the whole mechanism.
- No queue, broker, or second deployable; no worker-process split.
- No change to AD-10 stage semantics, `_STAGE_SEQUENCE`, `_STAGE_FUNCTIONS`, `advance()`'s own body,
  the advisory lock, or any stage function -- the scheduler is purely a new *caller* of the
  existing `advance()`.
- No boot-time reconciliation pass after a restart/redeploy -- an explicitly accepted gap.
- No app-level enforcement or detection of the Render no-spin-down prerequisite.
- No `AGENTS.md` edit -- explicit follow-up for a future `bmad-project-context` refresh, not this
  story.
- No change to the JS poll-retry backoff (`shell/http/static/shell.js`) -- independent, already
  shipped.
- No schema or migration change -- `ReportRun` is untouched.
- Do not touch any of the 14 test files that construct `Settings(...)` directly -- the new field's
  dataclass-level default must make that unnecessary.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `REPORT_RUN_MODE` unset | absent from environ | `Settings.report_run_mode == ReportRunMode.POLL` | N/A |
| `REPORT_RUN_MODE=poll` / `=background` | explicit, valid | matching `ReportRunMode` member | N/A |
| `REPORT_RUN_MODE=bogus` | invalid value | `load_settings` raises `ConfigError` naming `poll`/`background` | non-zero exit |
| Poll in `background` mode | `GET /report-runs/{id}`, mode=background | `run` rendered from its current DB state; `advance`/`_advance_run` never called | N/A |
| Scheduler tick, run never polled | `stage IS NULL`, mode=background | included by the `or_(...)` predicate, advanced | N/A |
| Scheduler tick, run terminally failed | `failed_at` set | excluded from the query, untouched | N/A |
| Scheduler tick, run at `gate_passed`/`exported` | `stage == "gate_passed"` | excluded from the query (or a no-op `advance()` for `exported`, which has no registered stage function) | N/A |
| Scheduler tick, one run's `advance()` call itself raises | mode=background | that row's exception is logged, session rolled back, remaining rows in the same tick still process; `run.failed_at` is untouched by this generic path (`advance()` owns its own terminal-failure handling) | `_logger.exception`, no crash |
| Scheduler tick, one run's client or stored chart is missing (review-loop 1) | mode=background | that row is marked terminally failed in the same transaction (`failed_at`/`failure_reason` set, committed) instead of retried; remaining rows in the same tick still process | `_logger.exception`, no crash, no infinite retry |
| App shutdown, mode=background | server stopping | scheduler task cancelled and awaited before `engine.dispose()` | N/A |
| App built without entering the lifespan | `TestClient(create_app(...))`, no `with` | scheduler never starts (existing suite, only `test_http_app.py` enters the lifespan) | N/A |

</frozen-after-approval>

## Code Map

- `shell/config.py` -- new `ReportRunMode` `StrEnum` (near `Environment:40`); `Settings` dataclass
  `environment:82`-`gemini_data_terms_verified_at:88` gains `report_run_mode: ReportRunMode =
  ReportRunMode.POLL` after `88`; `__repr__:90-98` gains a field; new `_read_report_run_mode`
  mirroring `_read_environment:166-180`'s shape but optional; `load_settings:311-368` wires it into
  `problems`/the final `Settings(...)` call; `__all__:29` gains `ReportRunMode`.
- `shell/runner/scheduler.py` (new) -- `generator_for_settings`, `_run_pending_report_runs`,
  `_scheduler_loop`, `start_scheduler`, `stop_scheduler`, `_TICK_INTERVAL_SECONDS`. Imports
  `advance` from `shell.runner.driver` (mirrors `report_runs.py`'s own import), `ReportRun` from
  `shell.adapters.postgres.report_run`, `current_chart_for_client`/`deserialize_natal_chart`/
  `Client` from `shell.adapters.postgres.client`, `GeminiGenerator`/`RecordedResponseGenerator`
  from their adapter modules, `Environment`/`ReportRunMode`/`Settings` from `shell.config`, `or_`
  from `sqlalchemy`. **Review-loop 1:** `_run_pending_report_runs` calls `generator_for_settings`
  once per tick (before the `for run in runs` loop), not once per run; its client/chart lookup
  branch, on `RuntimeError`, sets `run.failed_at`/`run.failure_reason` and commits (see Boundaries'
  new "Unrecoverable per-run lookup failure" bullet) instead of only logging+rolling back; the
  module docstring's `asyncio.to_thread` claim is corrected to say Starlette/FastAPI dispatches sync
  route handlers through AnyIO's worker thread pool, a separate pool from asyncio's default
  executor -- not "the same threadpool", just an analogous off-loop-thread pattern.
- `shell/http/app.py` -- imports `start_scheduler`/`stop_scheduler` from `shell.runner.scheduler`;
  `_lifespan:98-110` gains the start/stop calls per Boundaries; docstring rewrite.
- `shell/http/routes/report_runs.py` -- `from shell.config import Environment` (`68`) ->
  `Environment, ReportRunMode`; `get_generator:279-298` body -> one-line delegate; `poll_report_run`
  `376` (`_advance_run(...)` call) gated on `report_run_mode is ReportRunMode.POLL`; module
  docstring `1-21` note that `background` mode exists and behaves per AD-20's amendment.
  **Review-loop 1:** `get_generator` (and `poll_report_run`'s `generator: Generator =
  Depends(get_generator)` parameter) is restructured so a real `Generator` is constructed only when
  `report_run_mode is ReportRunMode.POLL` -- e.g. change the parameter to take `request: Request`
  directly and call `generator_for_settings(request.app.state.settings)` only inside the
  `if ... is ReportRunMode.POLL:` branch, since a background-mode poll never uses the generator it
  would otherwise construct on every single request for the deployment's whole lifetime.
- `shell/runner/driver.py` (review-loop 1) -- module docstring's "Why one stage per call, from the
  poll GET only, with no background task or queue" section and `advance()`'s own docstring
  ("Called only from `poll_report_run` ... never from ... an `asyncio` task ... or a scheduled
  job") both predate this story and now contradict `shell/runner/scheduler.py`. Amend both to
  acknowledge the `background`-mode caller (AD-20's amendment, Story 3.11), mirroring the
  `report_runs.py` module docstring's own update above -- prose only, no behavior change.
- `.env.example` (review-loop 1) -- add a documented, optional `REPORT_RUN_MODE` entry (the file's
  header currently reads "All seven are required" -- update it to reflect the new optional eighth
  variable) explaining `poll`/`background` and that it defaults to `poll` when unset. Do **not**
  add or change any `REPORT_RUN_MODE` entry in `render.yaml` or `compose.yaml` -- setting it to
  `background` anywhere live is a deployment decision for Francesco to make separately, not part of
  this story.
- `tests/test_config.py` -- reuse `VALID_ENVIRONMENT`/`environment_without`/`environment_with`
  (existing helpers) for the new matrix rows: unset -> `POLL` default, explicit `poll`/`background`,
  invalid value -> `ConfigError`. **Review-loop 1:**
  `test_report_run_mode_invalid_value_aborts_and_names_permitted_values` also asserts the invalid
  raw value itself (`"bogus"`) appears in the error message, not only the permitted values.
- `tests/test_runner_scheduler.py` (new) -- mirrors `tests/test_runner_advisory_lock.py`'s
  self-contained in-memory SQLite setup (`create_engine("sqlite://")`,
  `SQLModel.metadata.create_all`) plus `tests/test_runner_driver.py::_create_client_and_chart` for
  fixture rows; monkeypatches `shell.runner.scheduler.advance` to a recording fake (this file does
  not re-test stage behavior, only selection/dispatch/isolation) to assert: `NULL`-stage and
  mid-pipeline rows are picked up, `failed_at`/`gate_passed` rows are not, and one row's fake
  raising does not stop the rest of the tick. **Review-loop 1:** add a test for a `ReportRun` whose
  `client_id` references no `Client` row at all (distinct from the existing "chart superseded, no
  current chart" test) asserting it is marked `failed_at` and does not stop the rest of the tick;
  add a test asserting the missing-chart case also now sets `failed_at`/`failure_reason` rather
  than only being skipped; add a test asserting `_scheduler_loop` itself survives an exception from
  `_run_pending_report_runs` on one iteration and calls it again on the next (e.g. monkeypatch
  `_run_pending_report_runs` to raise once then succeed, drive the loop for two iterations with
  `asyncio.sleep` patched to return immediately, assert it was called twice and the task is still
  alive).
- `tests/test_http_app.py` -- new tests, alongside the existing `test_dispose_is_called_once...`
  pair, asserting `application.state.scheduler_task` is created only under
  `report_run_mode=ReportRunMode.BACKGROUND` and only once the lifespan is entered (`with
  TestClient(...)`), and is cancelled by the time the `with` block exits.
- `tests/test_http_report_runs.py` -- new test using `dataclasses.replace(LOCAL,
  report_run_mode=ReportRunMode.BACKGROUND)` for a background-mode `app_instance`, asserting a poll
  never calls the patched `advance` and still renders the run's current stage.

## Tasks & Acceptance

**Execution:**
- [x] `shell/config.py` -- add `ReportRunMode`, the `report_run_mode` field (dataclass-level
  default), `_read_report_run_mode`, wire into `load_settings`/`__repr__`/`__all__` per Boundaries.
- [x] `shell/runner/scheduler.py` -- new module: `generator_for_settings`,
  `_run_pending_report_runs` (`or_`-based NULL-safe query, per-run try/except+rollback),
  `_scheduler_loop` (outer try/except, `asyncio.sleep(_TICK_INTERVAL_SECONDS)`), `start_scheduler`,
  `stop_scheduler`.
- [x] `shell/http/app.py` -- wire `start_scheduler`/`stop_scheduler` into `_lifespan` in the correct
  order relative to `yield` and `engine.dispose()`; rewrite the docstring.
- [x] `shell/http/routes/report_runs.py` -- gate `poll_report_run`'s `_advance_run` call on
  `ReportRunMode.POLL`; delegate `get_generator` to `generator_for_settings`; update imports and
  module docstring.
- [x] `tests/test_config.py` -- add the `REPORT_RUN_MODE` matrix rows (default, both valid values,
  invalid value).
- [x] `tests/test_runner_scheduler.py` -- new: selection predicate (including `NULL` stage),
  exclusion of `failed_at`/`gate_passed` rows, per-row failure isolation within one tick.
- [x] `tests/test_http_app.py` -- scheduler task created/cancelled per Boundaries, gated on both
  `report_run_mode` and lifespan entry.
- [x] `tests/test_http_report_runs.py` -- background-mode poll never calls `advance`, still renders.
- [x] `shell/runner/scheduler.py` (review-loop 1) -- mark `failed_at`/`failure_reason` on a
  missing-client/missing-chart lookup failure instead of only logging+rolling back; hoist
  `generator_for_settings` out of the per-run loop to once per tick; correct the module docstring's
  `asyncio.to_thread`/AnyIO claim.
- [x] `shell/http/routes/report_runs.py` (review-loop 1) -- restructure `get_generator`/
  `poll_report_run` so a real `Generator` is constructed only in `poll` mode.
- [x] `shell/runner/driver.py` (review-loop 1) -- amend the module and `advance()` docstrings to
  acknowledge the `background`-mode scheduler caller.
- [x] `.env.example` (review-loop 1) -- document the optional `REPORT_RUN_MODE` variable; update
  the "all seven required" header line.
- [x] `tests/test_runner_scheduler.py` (review-loop 1) -- missing-`Client` row test, missing-chart
  row now asserted `failed_at`, and an `_scheduler_loop` survives-one-bad-tick test.
- [x] `tests/test_config.py` (review-loop 1) -- invalid-value test also asserts the raw value
  appears in the error message.

**Acceptance Criteria:**
- Given `REPORT_RUN_MODE` unset or `poll`, when the app runs, then every existing Story 3.10 test
  and behavior is unchanged, including the 14 test files constructing `Settings(...)` without this
  field.
- Given `REPORT_RUN_MODE=background`, when the app starts, then an in-process scheduler task begins
  ticking `advance()` for every `ReportRun` with `failed_at IS NULL` and `stage` not `"gate_passed"`
  (including a `NULL`-stage row), without any poll request occurring.
- Given `REPORT_RUN_MODE=background`, when `GET /report-runs/{id}` is polled, then the response
  renders the run's current state without itself calling `advance()`.
- Given the app shuts down while `REPORT_RUN_MODE=background`, when shutdown runs, then the
  scheduler task is cancelled and awaited before the engine is disposed.
- Given one `ReportRun` in a scheduler tick raises during its lookup or `advance()` call, when the
  tick continues, then every other eligible run in that same tick is still processed.
- Given a `ReportRun` whose `Client` or stored chart is missing (review-loop 1), when the scheduler
  ticks it, then the run is marked terminally failed (`failed_at`/`failure_reason` set and
  committed) instead of being retried on every future tick.

## Spec Change Log

- **Review-loop 1** (Blind Hunter finding, merged from two related findings): in `background` mode,
  a `ReportRun` whose `Client` or stored chart is missing was caught by the generic per-row
  `except`, logged, and silently retried every tick forever -- never reaching a terminal state,
  unlike `poll` mode's visible 404. Root cause was inside `<frozen-after-approval>` (the "Per-run
  isolation" Boundaries bullet never specified terminal handling for this case), so this routed as
  an intent gap; resolved by Francesco (2026-09-14): mark the run `failed_at` immediately on this
  specific lookup failure, mirroring `shell/runner/driver.py`'s own terminal-failure shape, rather
  than retrying forever or merely rate-limiting the log noise. **KEEP:** the generic per-row
  `except Exception` around the whole lookup+`advance()` body stays exactly as it was for every
  other failure mode (including an exception raised by `advance()` itself) -- this amendment adds a
  more specific `except` for the two `RuntimeError`s the lookup itself raises, it does not replace
  the general one. Six smaller findings from the same review (docstring accuracy in
  `shell/runner/driver.py` and `shell/runner/scheduler.py`, `.env.example` documentation, two
  missing test cases, one weak assertion, and constructing a `Generator` on every poll even when
  unused in `background` mode) were classified `patch` and folded into the same Code Map/Tasks
  updates above rather than looped back separately. Three findings (multi-worker/multi-replica
  scheduling, `_TICK_INTERVAL_SECONDS`/`shell.js` drift, no idle-tick backoff) were classified
  `reject` -- respectively out of scope under AD-20's explicit single-process constraint, not
  meaningfully fixable without disproportionate churn, and not a real problem at this project's
  documented scale (≤200 reports/month).

- **Review-loop 2** (Blind Hunter, fresh pass over the review-loop-1 diff): no `intent_gap`/`bad_spec`
  this round -- every root cause was outside `<frozen-after-approval>`, so nothing looped back to
  Francesco. `patch` (applied directly): the new `failed_at` branch in `_run_pending_report_runs`
  now also sets `run.updated_at`, matching every terminal-failure path in
  `shell/runner/driver.py`; `generator_for_settings` is now called only when the tick's query
  actually returned at least one run, not unconditionally every 2s; that branch's `_logger.exception`
  became `_logger.error` (an anticipated, handled condition, not an unexpected one -- mirrors
  `driver.py`'s own `.error`-vs-`.exception` convention); the "never both callers at once" docstring
  claims in `driver.py` were softened to "made safe by the advisory lock, not ruled out
  structurally" (a rolling deploy or a live `REPORT_RUN_MODE` change can genuinely overlap two
  callers); the Design Notes' "ordinary SQLAlchemy usage" framing now acknowledges the
  `expire_on_commit` re-fetch cost of sharing one `Session` across a tick. `defer` (recorded in
  `deferred-work.md`, not this story's problem): `poll_report_run`'s unconditional missing-`Client`
  `RuntimeError` predates this story and 500s regardless of `REPORT_RUN_MODE`; no external
  scheduler health/readiness signal beyond a log line. `reject`: no DB index for the new query and
  no batching/`LIMIT` (both would require a migration, which the frozen Never list forbids, for a
  non-problem at this project's ≤200-reports-per-month scale); a systemic-outage circuit breaker
  beyond the existing per-run `with_backoff`/`_MAX_STAGE_FAILURES` (Story 4.8, unchanged); shutdown
  blocking on an in-flight tick (`asyncio.to_thread` can't be cancelled mid-flight -- the same
  accepted-risk class as the restart-loses-only-the-timer gap AD-20's amendment already names); and
  `.env.example`'s `REPORT_RUN_MODE=poll` being an active line (consistent with every other
  variable's presentation in that file; the prose comment above it already states it's optional).
  The last three `reject`s and the shutdown-blocking point are additionally acknowledged in
  `shell/runner/scheduler.py`'s own Design Notes docstring so they're on the record as
  consciously-accepted, not overlooked.

## Design Notes

**Why a plain `asyncio.Task`, not a library.** AD-20's amendment explicitly rules out a queue or a
second deployable; a bare task on the app's own event loop, ticking synchronous work off the loop
via `asyncio.to_thread` -- the same *off-loop-thread* idea Starlette/FastAPI already applies to
every sync route handler here (via AnyIO's own worker thread pool, a separate pool from
`asyncio.to_thread`'s default executor -- not literally the same pool) -- needs no new dependency
and matches "one process, one new scheduler loop."

**Why the tick is 2.0s.** `report_run_poll.html`'s `hx-trigger="every 2s"` is the cadence an
operator already experiences while watching; reusing that number (rather than inventing a new one)
is what makes the UX addendum's "renders identically... as if they had kept polling" true in
practice, not just in the two code paths' end states.

**Why one `Session` per tick, not one per run.** `advance()` already commits per stage transition;
reusing one `Session` sequentially across a tick's runs is ordinary SQLAlchemy usage, and a
`session.rollback()` inside each run's `except` block returns it to a clean state for the next run
-- a fresh `Session` per run would cost a new connection for no isolation benefit `rollback()`
doesn't already provide.

**Why `generator_for_settings` moves out of `report_runs.py`.** The `Environment.LOCAL` branch
guards real Gemini spend; duplicating it into the scheduler risks the two call sites drifting (one
patched to add a variant, the other forgotten). One function, two callers.

**Why one `Generator` per tick, not one per run (review-loop 1).** `generator_for_settings` was
originally called inside the per-run loop; a tick with N pending runs built N separate Generator
instances every 2 seconds for no benefit -- `advance()` only reads from it, it carries no per-run
state, so one instance per tick (like the one `Session` per tick) is exactly as correct and cheaper.

## Verification

**Commands:**
- `uv run pytest tests/test_config.py tests/test_runner_scheduler.py tests/test_http_app.py
  tests/test_http_report_runs.py tests/test_runner_driver.py tests/test_runner_advisory_lock.py -q`
  -- expected: all pass.
- `uv run ruff check shell/config.py shell/runner/scheduler.py shell/http/app.py
  shell/http/routes/report_runs.py shell/runner/driver.py` -- expected: no findings.
- `uv run pytest -q` -- expected: full suite green, no `Settings(...)` call site broken by the new
  field.

**Manual checks (if no CLI):**
- `.env.example` renders the new `REPORT_RUN_MODE` entry as optional/defaulted, not as one of the
  "all required" variables the file's header line describes.

## Suggested Review Order

**The scheduler itself (design intent)**

- Entry point: module docstring states why a plain `asyncio.Task`, one `Session`/`Generator` per
  tick, and the two accepted-risk tradeoffs (systemic-outage load, shutdown blocking on an
  in-flight tick).
  [`scheduler.py:1`](../../shell/runner/scheduler.py#L1)
- `_run_pending_report_runs` -- the NULL-safe query, the per-run try/except isolation, and the
  more specific missing-Client/chart except that marks a run terminally failed instead of retrying
  it forever.
  [`scheduler.py:98`](../../shell/runner/scheduler.py#L98)
- `_scheduler_loop` -- the outer try/except that keeps the task alive across a bad tick, then
  sleeps `_TICK_INTERVAL_SECONDS`.
  [`scheduler.py:201`](../../shell/runner/scheduler.py#L201)
- `start_scheduler`/`stop_scheduler` -- gated on `ReportRunMode.BACKGROUND`; cancel-and-await
  ordering that must finish before the engine is disposed.
  [`scheduler.py:227`](../../shell/runner/scheduler.py#L227)

**The mode switch (config)**

- `ReportRunMode` -- the two-value enum the whole feature branches on.
  [`config.py:54`](../../shell/config.py#L54)
- `report_run_mode` -- the one field in `Settings` with a dataclass-level default, so 14 existing
  test files never needed to change.
  [`config.py:115`](../../shell/config.py#L115)
- `_read_report_run_mode` -- the only optional reader in this file; unset/blank means `poll`,
  never a missing-variable error.
  [`config.py:339`](../../shell/config.py#L339)

**Wiring: where each mode actually takes effect**

- `_lifespan` -- `start_scheduler` before `yield`, `stop_scheduler` awaited before
  `engine.dispose()`.
  [`app.py:100`](../../shell/http/app.py#L100)
- `poll_report_run` -- the one `if ... is ReportRunMode.POLL:` branch that makes `background` mode
  read-only, and only builds a real `Generator` inside it.
  [`report_runs.py:367`](../../shell/http/routes/report_runs.py#L367)
- `get_generator` -- now a plain function called directly, not a `Depends(...)` FastAPI dependency
  resolved on every request.
  [`report_runs.py:285`](../../shell/http/routes/report_runs.py#L285)
- `advance()`'s docstring -- the second caller acknowledged, and why "never both at once" became
  "made safe by the advisory lock."
  [`driver.py:675`](../../shell/runner/driver.py#L675)

**Peripherals**

- `_read_report_run_mode`'s only unmocked env-var reader test: unset defaults to `poll`.
  [`test_config.py:297`](../../tests/test_config.py#L297)
- Invalid value aborts and names both permitted values plus the offending one.
  [`test_config.py:321`](../../tests/test_config.py#L321)
- A `NULL`-stage row (never polled once) is still picked up by the scheduler's query.
  [`test_runner_scheduler.py:130`](../../tests/test_runner_scheduler.py#L130)
- Missing chart -> terminally failed, not retried forever.
  [`test_runner_scheduler.py:225`](../../tests/test_runner_scheduler.py#L225)
- Missing `Client` row entirely -> same terminal treatment, isolated from the rest of the tick.
  [`test_runner_scheduler.py:271`](../../tests/test_runner_scheduler.py#L271)
- The outer loop survives one bad tick and ticks again.
  [`test_runner_scheduler.py:322`](../../tests/test_runner_scheduler.py#L322)
- Scheduler task exists only once the lifespan is entered, only in `background` mode.
  [`test_http_app.py:167`](../../tests/test_http_app.py#L167)
- Task cancelled and awaited before the engine is disposed.
  [`test_http_app.py:182`](../../tests/test_http_app.py#L182)
- A `background`-mode poll never calls `advance`, still renders the run's current stage.
  [`test_http_report_runs.py:440`](../../tests/test_http_report_runs.py#L440)
- The new, optional, defaulted env var documented for operators.
  [`.env.example:56`](../../.env.example#L56)
