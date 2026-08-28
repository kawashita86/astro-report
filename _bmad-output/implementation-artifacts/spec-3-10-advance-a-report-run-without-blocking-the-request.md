---
title: 'Advance a report run without blocking the request'
type: 'refactor'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
baseline_commit: 'abcd0deaee8892410894fcdce3cfb7c344d120a7'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `drive()` (`shell/runner/driver.py`) loops through every registered stage in one
call and is invoked from both `POST /clients/{client_id}/report-runs` and every
`GET /report-runs/{run_id}` poll. A run that reaches `draft_ready` therefore blocks the starting
request (and any poll) on the whole remaining pipeline — the Generator call plus its backoff, then
the Gate — so the screen freezes and closing the tab can abandon work mid-pipeline. AD-20 requires
the opposite: start returns instantly, each poll moves the run forward exactly one stage.

**Approach:** Replace `drive()` with `advance()` — same per-stage machinery, but it performs **at
most one** stage transition per call and returns. `advance()` is called **only** from the poll
handler; the start route just creates the `ReportRun` row and redirects. Concurrent polls for the
same run are single-flighted by a Postgres transaction-scoped advisory lock on the run id: the poll
that gets the lock advances one stage; the other returns the current stage untouched.

## Boundaries & Constraints

**Always:**
- `shell/runner/driver.py` exposes `advance(session, run, *, natal_chart, natal_chart_id, config,
  ephemeris_identity, sections_config, generator, vocabulary) -> ReportRun` (renamed from `drive`,
  same signature; `__all__ = ["advance"]`). It executes the **single** next stage after
  `run.stage` — its existing per-stage body run once, not in a loop: `with_backoff` +
  `begin_nested()` SAVEPOINT + the unique-constraint `IntegrityError` classification + the
  `except GateFailedError` regeneration path + the generic `except Exception` terminal-failure path,
  all unchanged in behavior. Every place the old loop did `break` or `continue` to the next
  iteration, `advance()` `return run`s instead. A successful transition commits and returns.
- One-stage guarantee: if `run.stage` is `draft_ready` before the call, `advance()` runs
  `gate_passed` and returns — it never also runs a later stage. If `run.stage` is `None`,
  `advance()` runs `natal_ready` only.
- No stage to run (`run.stage` is `gate_passed`, or the next stage name has no entry in
  `_STAGE_FUNCTIONS`, e.g. `exported`) → `advance()` returns `run` unchanged, no commit.
- A run with `failed_at` set still short-circuits first, returns unchanged, acquires no lock.
- Advisory lock: new `shell/runner/advisory_lock.py::try_acquire_advance_lock(session, run_id: UUID)
  -> bool`. When `session.get_bind().dialect.name == "postgresql"`, runs
  `SELECT pg_try_advisory_xact_lock(:ns, hashtext(:key))` with a fixed module-level int4 namespace
  constant and `:key = str(run_id)`; returns the boolean. On any other dialect (SQLite in tests)
  returns `True` without touching the DB — there is no cross-connection concurrency there to guard.
  `advance()` calls it immediately after the `failed_at` check; on `False` it does
  `session.rollback()`, `session.refresh(run)`, logs at INFO with `run.id`, and returns `run`
  without running any stage. The lock is transaction-scoped: Postgres releases it on `advance()`'s
  own `commit()` / `rollback()`, or if the connection drops — no explicit unlock.
- `POST /clients/{client_id}/report-runs` (`start_report_run`): create the `ReportRun` row, commit,
  redirect to `/report-runs/{run.id}`. It does **not** call `advance()` / `drive()` / any runner
  function. `_drive_run` is renamed `_advance_run`, calls `advance()`, and is used only by
  `poll_report_run`.
- Module docstrings of `shell/runner/driver.py` and `shell/http/routes/report_runs.py` are
  rewritten so neither describes driving from the start POST or re-driving the whole pipeline on
  every poll; they describe AD-20 (one stage per poll, poll-only, advisory-locked). Stale `drive()`
  prose references in `shell/runner/backoff.py`, `shell/adapters/postgres/report_run.py`,
  `shell/http/app.py`, and the `shell/adapters/postgres/*` adapter docstrings are updated to
  `advance()` and to "on the next poll" wording — mechanical, no behavior change.

**Ask First:** None identified.

**Never:**
- No background task, thread, `asyncio` task, queue consumer, or scheduled job — AD-20 forbids all
  of them; the browser's poll cadence remains the only drain.
- No change to AD-10 stage semantics, ordering, `_STAGE_SEQUENCE`, `_STAGE_FUNCTIONS`, the
  `with_backoff` overrides, `stage_failure_count` / `regeneration_count` / `_MAX_*` bookkeeping, or
  any stage function body. Resume-after-interruption still works because each stage still persists
  before the next begins.
- Do not remove the concurrent-`drive()` `IntegrityError` classification — it stays as
  defense-in-depth (SQLite has no advisory lock; a future non-poll caller).
- No schema change, no migration — `ReportRun` is untouched.
- No `docs/decisions/` entry — AD-20 is an architecture-spine decision, already recorded there and
  in `sprint-change-proposal-2026-08-28-ui-rebuild.md`, not a release-gate decision.
- No change to `core/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start a run | `POST /clients/{id}/report-runs`, valid month | Row created, `stage` is `None`, `month_start_utc`/`transit_events` `NULL`; 303 to poll view; no stage ran | N/A |
| First poll | `run.stage is None` | `natal_ready` runs; returns at `natal_ready`; response returns | N/A |
| Poll lands on `draft_ready` | `run.stage == "draft_ready"` | `gate_passed` runs (one `generator`-free Gate call); returns at `gate_passed` or, on `GateFailedError`, rewound to `payload_ready`; never chains to a second stage | GateFailedError handled exactly as today |
| Poll on a completed run | `run.stage == "gate_passed"` | No stage runs; `run` returned unchanged; no commit | N/A |
| Concurrent polls, same run (Postgres) | Two poll requests call `advance()` together | One acquires `pg_try_advisory_xact_lock`, advances one stage, commits (lock releases); the other gets `False`, refreshes, returns the current stage without advancing | N/A |
| Poll on a terminally failed run | `run.failed_at` set | Returns unchanged before acquiring any lock | N/A |
| Process killed mid-stage | Row committed at stage N, app restarts, run polled | Next poll resumes at stage N+1, recomputes nothing already persisted (AD-10) | N/A |
| Stage exhausts `with_backoff` | Always-failing stage | `run.stage` unchanged, `stage_failure_count += 1`, terminal at `_MAX_STAGE_FAILURES` — as today, but per poll not per loop | Logged with `run.id`; no exception escapes `advance()` |
| Non-Postgres backend | SQLite test session | `try_acquire_advance_lock` returns `True` without a DB call; `advance()` proceeds | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py` -- `drive:643` (rename to `advance`, delloop: run one stage), the
  `for index, stage_name in enumerate(_STAGE_SEQUENCE)` loop body `749-973` (becomes a single
  computed `next_index = _stage_index(run.stage) + 1`; `break`→`return run`; success tail `965-973`
  commits + `return run`), `_stage_index:257`, module docstring `1-46` (rewrite lines `4-13` about
  "called from both the start POST and the poll GET"), `__all__:97`.
- `shell/runner/advisory_lock.py` (new) -- `try_acquire_advance_lock`, the namespace int4 constant.
  Mirror `shell/runner/month.py` / `backoff.py` as a one-concern runner module.
- `shell/runner/backoff.py` -- docstring `40` (`drive()` -> `advance()`), module docstring line `1`.
- `shell/http/routes/report_runs.py` -- module docstring `1-16` (rewrite), imports `57`
  (`drive`->`advance`), `_drive_run:205` (rename `_advance_run`, call `advance`),
  `start_report_run:227` (drop the `_drive_run(...)` call at `247`), `poll_report_run:252` (call
  `_advance_run`).
- `shell/http/app.py` -- `234`, `241`, and the `_drive_run` / "first consumer" prose in the
  `sections_config` / `gate_vocabulary` doc-comments (`_drive_run` -> `_advance_run`).
- `shell/adapters/postgres/report_run.py` -- module docstring `1-16` (`drive()` -> `advance()`,
  "from either the start route or the poll route, resumes" -> "on the next poll, resumes"), field
  comments referencing `drive()`.
- `shell/adapters/postgres/{gate_result,report,report_draft,report_payload,report_theme,client}.py`
  -- prose `drive()` references in docstrings -> `advance()` (mechanical).
- `tests/test_runner_driver.py` -- `_drive:167` becomes a **drain** helper (loop `advance()` until
  `run.stage` stops changing, `run.failed_at` is set, or a call makes no progress; bounded
  iteration cap), so the full-pipeline tests and the three external importers keep working. New
  `_advance()` (single call) for the one-call tests. `engine:96` / `session:104` fixtures reused.
  Retro-C concurrent-`IntegrityError` tests (`1311-1650`) switch to `_advance` single calls.
- `tests/test_http_report_runs.py` -- `fake_drive:136` -> `fake_advance` (one transition per call),
  `monkeypatch.setattr(report_runs_module, "advance", ...)`; happy-path tests `284-355` reworked
  for start-does-not-advance + one-stage-per-poll; `engine`/`app_instance`/`client` fixtures
  `107-125` reused; the stage-parametrized tests near `1380` still valid.
- `tests/test_runner_advisory_lock.py` (new) -- SQLite no-op returns `True`; SQL shape asserted; a
  real-Postgres two-connection single-flight test gated on an env var, skipping when unset (mirror
  `tests/test_migration_chain_on_postgres.py:33-49`).
- `tests/test_latency_record.py:316` -- `from shell.runner.driver import drive` -> `import advance`
  plus a local drain loop (or switch to `tests.test_runner_driver._drive` like `test_restore.py` /
  `test_storage_growth_record.py`, which need no change once `_drive` drains).

## Tasks & Acceptance

**Execution:**
- [x] `shell/runner/advisory_lock.py` -- new `try_acquire_advance_lock(session, run_id)` per
  Boundaries: Postgres `pg_try_advisory_xact_lock(:ns, hashtext(:key))`, `True` no-op elsewhere.
- [x] `shell/runner/driver.py` -- rename `drive` -> `advance`; collapse the stage loop to a single
  computed next-stage step; acquire the advance lock right after the `failed_at` short-circuit and
  return early on `False`; rewrite the module docstring for AD-20; keep every `except` / savepoint
  / counter path byte-for-byte in behavior.
- [x] `shell/http/routes/report_runs.py` -- rewrite module docstring; `import advance`; rename
  `_drive_run` -> `_advance_run` calling `advance`; remove the advance call from `start_report_run`
  (create + commit + redirect only); `poll_report_run` calls `_advance_run`.
- [x] `shell/runner/backoff.py`, `shell/http/app.py`, `shell/adapters/postgres/report_run.py`,
  `shell/adapters/postgres/{gate_result,report,report_draft,report_payload,report_theme,client}.py`
  -- update stale `drive()` / "start route or poll route" prose to `advance()` / "on the next
  poll". Prose only.
- [x] `tests/test_runner_driver.py` -- make `_drive` a bounded drain over `advance()`; add
  `_advance` single-call helper; move the backoff-exhaustion, `GateFailedError`-rewind,
  `natal_chart_id`-assignment, and retro-C concurrent-`IntegrityError` tests to `_advance` so each
  asserts exactly one transition; add tests: (a) `advance()` moves `run.stage` forward by exactly
  one `_STAGE_SEQUENCE` position per call and the `_FakeGenerator` is untouched until the call that
  lands on `draft_ready`; (b) a call entering at `draft_ready` calls the Generator once and returns
  at `draft_ready` — never at `gate_passed` — in that same call; (c) a run polled after a simulated
  mid-run kill (`run.stage` set to an intermediate value, stored columns present) resumes at the
  next stage and recomputes nothing; (d) with `try_acquire_advance_lock` patched to `False`,
  `advance()` returns the current stage, runs no stage function, and does not commit a stage change.
- [x] `tests/test_http_report_runs.py` -- `fake_drive` -> `fake_advance` (one transition per call);
  rework the happy-path tests so `POST` leaves `stage is None` and successive polls each advance one
  stage; add: start route creates the row without advancing (no stage columns set); the poll route
  invokes `advance` exactly once per request.
- [x] `tests/test_runner_advisory_lock.py` -- new: SQLite path returns `True` with no query; the
  emitted SQL contains `pg_try_advisory_xact_lock`; real-Postgres gated test opens two connections,
  both call `advance()` on one run, asserts exactly one advances and the other returns the
  unchanged stage, and that the lock is gone after the winner commits.
- [x] `tests/test_latency_record.py` -- update its direct `drive` import to `advance` + drain (or
  reuse `_drive`).

**Acceptance Criteria:**
- Given the runner, when it advances a run, then it does so through a single `advance()` that
  performs at most one stage transition and returns, and that function is invoked only from
  `poll_report_run` — no thread, task, queue consumer, or scheduled job calls it.
- Given `POST /clients/{client_id}/report-runs`, when it handles a start, then the `ReportRun` row
  is created and the response returns immediately with no stage run; the first stage runs on the
  first poll.
- Given two status polls for one run arriving together on Postgres, when both call `advance()`,
  then the transaction-scoped advisory lock lets exactly one advance the run while the other returns
  the current stage without advancing, and the lock is released on the winner's commit/rollback or a
  dropped connection.
- Given a poll landing on `draft_ready`, when the Gate runs inside it, then the response still
  returns after that one stage and never chains into a second.
- Given the process killed mid-stage, when the app restarts and the run is polled again, then it
  resumes at the first incomplete stage and recomputes nothing already succeeded.
- Given `shell/runner/driver.py` and `shell/http/routes/report_runs.py`, when this story lands, then
  their module docstrings no longer describe driving from the start POST or re-driving the whole
  pipeline on every poll.

## Design Notes

**Why the advisory lock and not a row lock.** `SELECT ... FOR UPDATE` on the `ReportRun` row would
serialize polls too, but the losing poll would then block until the winner commits — for a
`draft_ready` poll that is the full Generator + backoff wait, reintroducing exactly the freeze
AD-20 removes. `pg_try_advisory_xact_lock` is non-blocking: the loser returns `False` at once and
renders the current stage. Transaction-scoped (`_xact_`) means no `pg_advisory_unlock` to leak on
an error path — the `commit()` `advance()` already does releases it.

**Why `advance()` keeps all of `drive()`'s exception machinery.** The retro-C SAVEPOINT-per-attempt
work, the `IntegrityError` benign-vs-genuine split, the Story 5.4 regeneration rewind, and the
Story 4.8 terminal-failure counter are all per-stage already — the old loop just repeated them.
Running the body once per call changes *when* they run (one poll each), never *what* they do. The
`IntegrityError` path stays because the SQLite test backend has no advisory lock and a future
non-poll caller could reappear.

**Why `_drive` stays as a drain helper in the tests.** `tests/test_restore.py`,
`tests/test_storage_growth_record.py`, and `tests/test_latency_record.py` import it as an
end-to-end "run to completion" harness. A `_drive` that loops `advance()` to a fixed point keeps
them working with no change; only single-transition assertions move to the new `_advance` helper.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_driver.py tests/test_http_report_runs.py
  tests/test_runner_advisory_lock.py tests/test_runner_backoff.py tests/test_report_run_store.py
  tests/test_restore.py tests/test_storage_growth_record.py tests/test_latency_record.py -q`
  -- expected: all pass.
- `uv run ruff check shell/runner/ shell/http/routes/report_runs.py` -- expected: no findings.
- `uv run pytest -q` -- expected: full suite green (no lingering `drive` reference).
- `MIGRATION_TEST_DATABASE_URL=... uv run pytest tests/test_runner_advisory_lock.py -q` -- expected:
  the real-Postgres single-flight test runs and passes (skips cleanly without the env var).

## Suggested Review Order

**The one-stage-per-call driver (design intent)**

- Entry point: module docstring states AD-20 — one stage per poll, poll-only, advisory-locked, no background task.
  [`driver.py:1`](../../shell/runner/driver.py#L1)
- `advance()` — the old stage loop collapsed to a single computed next-stage step; every `break` is now `return run`.
  [`driver.py:652`](../../shell/runner/driver.py#L652)
- Next stage resolved from the in-memory row *before* the lock, so a completed/stageless poll takes no lock (mirrors the `failed_at` fast-path).
  [`driver.py:784`](../../shell/runner/driver.py#L784)
- Lock-loser path: roll back, refresh so the caller renders the fresh stage, return without running a stage.
  [`driver.py:797`](../../shell/runner/driver.py#L797)
- Success tail: `natal_chart_id` set on the `natal_ready` transition, commit, return — no loop continuation.
  [`driver.py:1016`](../../shell/runner/driver.py#L1016)

**The advisory lock**

- `try_acquire_advance_lock` — non-blocking `pg_try_advisory_xact_lock` on Postgres; a no-op `True` (no query) on SQLite.
  [`advisory_lock.py:48`](../../shell/runner/advisory_lock.py#L48)
- Why a transaction-scoped advisory lock, not `SELECT ... FOR UPDATE` (which would re-introduce the freeze).
  [`advisory_lock.py:1`](../../shell/runner/advisory_lock.py#L1)
- Fixed int4 namespace so run locks never collide with any other advisory-lock user.
  [`advisory_lock.py:45`](../../shell/runner/advisory_lock.py#L45)

**HTTP routes: start returns instantly, poll drives**

- Module docstring rewritten: start only creates the row + redirects; every stage runs from the poll.
  [`report_runs.py:1`](../../shell/http/routes/report_runs.py#L1)
- `start_report_run` — no runner call; validates client/month/chart, creates the row, commits, redirects.
  [`report_runs.py:234`](../../shell/http/routes/report_runs.py#L234)
- `_advance_run` — the single `advance()` call site, used only by `poll_report_run`.
  [`report_runs.py:210`](../../shell/http/routes/report_runs.py#L210)
- `poll_report_run` calls `_advance_run` once per request, then renders.
  [`report_runs.py:263`](../../shell/http/routes/report_runs.py#L263)

**Tests**

- `advance()` moves the run forward exactly one stage per call.
  [`test_runner_driver.py:1959`](../../tests/test_runner_driver.py#L1959)
- Winning path invokes the lock with `run.id`; `failed_at` fast-path invokes it never.
  [`test_runner_driver.py:2116`](../../tests/test_runner_driver.py#L2116)
- Process-killed-mid-run resumes at the next stage, recomputes nothing.
  [`test_runner_driver.py:600`](../../tests/test_runner_driver.py#L600)
- `_drive` is now a bounded drain over `advance()`; `_advance` is the single-call helper.
  [`test_runner_driver.py:199`](../../tests/test_runner_driver.py#L199)
- Advisory lock: SQLite no-op issues no query; Postgres SQL shape; `False` when not granted; real two-connection single-flight (env-gated).
  [`test_runner_advisory_lock.py:26`](../../tests/test_runner_advisory_lock.py#L26)
- `fake_advance` (one transition per call); start route never calls `advance`; each poll invokes it exactly once.
  [`test_http_report_runs.py:138`](../../tests/test_http_report_runs.py#L138)
