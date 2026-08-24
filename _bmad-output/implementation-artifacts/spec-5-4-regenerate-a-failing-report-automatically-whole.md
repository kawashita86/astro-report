---
title: 'Story 5.4 — Regenerate a failing Report automatically, whole'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'b54712cd88a05a6f36726f5f7faa5bc33478846f'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `_run_gate_passed` (Story 5.3) raises `GateFailedError` on a failing Gate result, and
`drive()`'s generic stage-failure bookkeeping just retries the *same* already-persisted `ReportDraft`
forever (`run_gate()` is pure, so it fails identically every time) until 5 pointless consecutive
failures mark the run terminally failed — no new draft is ever generated, so "regeneration" does not
actually happen today.

**Approach:** On a `GateFailedError`, `drive()` rewinds `run.stage` to `payload_ready` so the next
`drive()` call re-runs `draft_ready` and calls the Generator again for a genuinely new whole
`GeneratedDraft`, from the same stored Payload. A new `run.regeneration_count` tracks attempts across
this cycle — distinct from the generic `stage_failure_count`, which a successful `draft_ready` would
otherwise reset to 0 every cycle, hiding a persistent Gate problem. Reaching a fixed bound stops the
loop via the same terminal-failure fields (`failed_at`/`failure_reason`) Story 4.8 established, with
`run.stage` left at `draft_ready` so the final draft stays reachable. `ReportDraft` becomes
append-only-per-attempt (uniqueness loosened from `report_run_id` alone to `(report_run_id, attempt)`)
since a second draft for the same run is no longer a bug once regeneration is real.

## Boundaries & Constraints

**Always:**
- `_run_draft_ready` tags each persisted `ReportDraft` with `attempt=run.regeneration_count` (`0` for
  the first, never-regenerated draft).
- `_run_gate_passed` reads back the *latest* `ReportDraft` for `run` (highest `attempt`), never `.one()`
  — more than one row is now expected.
- On `GateFailedError` inside `drive()`'s stage loop: increment `run.regeneration_count`; while it is
  `<= _MAX_REGENERATIONS`, set `run.stage = "payload_ready"` (so `draft_ready` re-runs next call) and
  commit — `stage_failure_count` is left untouched.
- Once `run.regeneration_count` exceeds `_MAX_REGENERATIONS`: set `failed_at`/`failure_reason` (naming
  "regeneration bound exhausted"), leave `run.stage` at `draft_ready`, commit — mirrors Story 4.8's
  terminal-failure shape exactly (same fields, same poll-fragment display), just a different trigger.
- Any exception from `_run_gate_passed` other than `GateFailedError` keeps today's unmodified generic
  `stage_failure_count`/`_MAX_STAGE_FAILURES` path.
- `view_report_draft` (`shell/http/routes/report_runs.py`) orders by `attempt` descending so Francesco
  always sees the latest attempt, never an arbitrary one.
- New Alembic migration `0012_bounded_regeneration.py` (forward-only, mirrors
  `0010_report_run_failure.py`): adds `report_run.regeneration_count`; adds `report_draft.attempt`,
  drops the old unique index on `report_run_id` alone, adds a unique index on `(report_run_id, attempt)`.

**Ask First:** None.

**Never:**
- No change to `_run_gate_passed`'s own exception-raising behavior, or to `run_gate()`/`GateFailedError`
  themselves.
- No UI for failing Claims or Payload contradictions — Story 5.5.
- No `GATE_RESULT` audit table, no persisted violations list — Story 5.6.
- `_MAX_REGENERATIONS`, like `_MAX_STAGE_FAILURES`, is a plain module constant in `driver.py`, not a
  new runtime-editable setting.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First Gate failure | `draft_ready` run, violating draft | `run.stage == "payload_ready"`, `regeneration_count == 1`; a 2nd `ReportDraft` (`attempt=1`) is persisted on the next `drive()` call | N/A |
| Regeneration then pass | A Gate failure followed by a clean regenerated draft | `run.stage == "gate_passed"`, one `Report` row, `regeneration_count` reflects attempts used | N/A |
| Bound exhausted | Generator always returns the same violating draft, `_MAX_REGENERATIONS` regenerations all fail | `run.stage == "draft_ready"`, `failed_at` set, `failure_reason` names regeneration exhaustion | Terminal; `drive()` short-circuits thereafter |
| Same Payload across attempts | Two regeneration attempts | Both `ReportDraft` rows reference the same, unchanged `ReportPayload` row | N/A |
| Reading the draft mid-regeneration | `GET /report-runs/{id}/draft` after one failed attempt | Renders the latest (`attempt`-highest) `ReportDraft` | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py:120-130` -- add `_MAX_REGENERATIONS` constant near `_MAX_STAGE_FAILURES`.
- `shell/runner/driver.py:460-514` (`_run_draft_ready`) -- pass `attempt=run.regeneration_count` to
  `store_report_draft`.
- `shell/runner/driver.py:516-564` (`_run_gate_passed`) -- change the `ReportDraft` query from `.one()`
  to latest-by-`attempt`.
- `shell/runner/driver.py:643-676` (`drive()`'s except block) -- split into `except GateFailedError`
  (new regeneration path) before `except Exception` (existing path, unchanged).
- `shell/adapters/postgres/report_run.py:104` -- add `regeneration_count: int = Field(default=0)`,
  mirroring `stage_failure_count`.
- `shell/adapters/postgres/report_draft.py:33-65` -- add `attempt: int`; change `report_run_id` from
  `unique=True` to a plain index; add a composite unique constraint on `(report_run_id, attempt)`.
- `shell/adapters/postgres/report_draft.py:105-132` (`store_report_draft`) -- new `attempt: int` kwarg.
- `shell/http/routes/report_runs.py:200-202` (`view_report_draft`) -- order the `ReportDraft` query by
  `attempt` descending.
- `migrations/versions/0012_bounded_regeneration.py` (new) -- mirror `0010_report_run_failure.py`'s
  forward-only shape; also drops/recreates `report_draft`'s unique index (mirror
  `0009_report_draft.py`'s `ix_report_draft_report_run_id`).
- `tests/test_runner_driver.py:859-920,1022-1057` -- rewrite both existing gate-fail tests: a single
  failure no longer leaves `run.stage` at `draft_ready`, and 5 consecutive `drive()` calls no longer
  means 5 identical checks of one unchanging draft.
- `tests/test_report_draft_store.py:177` (`test_a_second_report_draft_for_the_same_report_run_id_...`)
  -- rewrite: a second draft at the *same* `attempt` still raises; a second draft at a *different*
  `attempt` for the same run now succeeds.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0012_bounded_regeneration.py` (new) -- add `regeneration_count`/`attempt`
  columns and swap `report_draft`'s unique index -- schema support for bounded whole-Report
  regeneration.
- [x] `shell/adapters/postgres/report_run.py` -- add `regeneration_count` field -- tracks regenerations
  distinct from `stage_failure_count`.
- [x] `shell/adapters/postgres/report_draft.py` -- add `attempt` field, composite unique constraint,
  `store_report_draft(attempt=...)` -- allow more than one draft per run.
- [x] `shell/runner/driver.py` -- `_MAX_REGENERATIONS`, `_run_draft_ready` attempt tagging,
  `_run_gate_passed` latest-draft read, `drive()`'s `GateFailedError`-specific except branch -- the
  regeneration loop itself.
- [x] `shell/http/routes/report_runs.py` -- `view_report_draft` orders by `attempt` descending -- always
  shows the latest attempt.
- [x] `tests/test_runner_driver.py` -- rewrite the two gate-fail tests; add a bound-exhausted test and a
  regenerate-then-pass test (I/O matrix rows 1-3).
- [x] `tests/test_report_draft_store.py` -- update the uniqueness test for the composite constraint; add
  multi-attempt coverage (I/O matrix rows 1, 4).
- [x] `tests/test_http_report_runs.py` -- extend `view_report_draft` coverage for "shows latest attempt"
  (I/O matrix row 5).

**Acceptance Criteria:**
- Given a Report failing the Gate, when regeneration triggers, then it is automatic, bounded by
  `_MAX_REGENERATIONS`, regenerates the whole Report via a fresh Generator call, and increments
  `run.regeneration_count`.
- Given a regeneration, when it runs, then it reuses the same stored `ReportPayload` row — the
  astronomy does not change between attempts.
- Given the bound reached and the last attempt still failing, then the run stops (`failed_at` set) and
  the last draft remains reachable rather than discarded.

## Design Notes

Why `run.stage` rewinds to `payload_ready` rather than a dedicated "regenerating" pseudo-stage:
`_stage_index`'s skip-by-index logic already re-runs exactly the stages after `completed_index` --
rewinding to `payload_ready` reuses that machinery for free (`draft_ready` re-runs, `gate_passed`
re-runs, nothing earlier does) rather than inventing a second state machine.

Why `regeneration_count` can't reuse `stage_failure_count`: `drive()` resets `stage_failure_count` to 0
on every successful stage advance (`driver.py:679`), and a regeneration's `draft_ready` re-run succeeds
by definition once the Generator returns anything -- wiping out any accumulated Gate-failure signal
before `gate_passed` even runs again. A separate counter is the only way the bound is real.

`_MAX_REGENERATIONS = 3`: no planning artifact states a number (FR-21/AD-10 only require "bounded");
chosen to mirror `with_backoff`'s own default `max_attempts=3`. Flag during review if a different bound
is wanted.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_driver.py tests/test_report_draft_store.py tests/test_http_report_runs.py tests/test_migration_chain.py -q` -- expected: all pass.
- `uv run alembic upgrade head` (against a local/test DB) -- expected: `0012_bounded_regeneration` applies cleanly.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**The regeneration loop itself**

- Entry point: on `GateFailedError`, rewinds to `payload_ready` while bounded, else marks terminally failed with `run.stage` left at `draft_ready`.
  [`driver.py:701`](../../shell/runner/driver.py#L701)

- The bound: a plain module constant, deliberately not planning-artifact-derived or runtime-configurable.
  [`driver.py:141`](../../shell/runner/driver.py#L141)

- `GateFailedError`'s docstring now describes the real post-5.4 handling, not the superseded Story 5.3 behavior.
  [`errors.py:146`](../../core/errors.py#L146)

**Draft persistence becomes append-only-per-attempt**

- Each regeneration is tagged with the run's own failure count, never overwriting a prior attempt.
  [`driver.py:531`](../../shell/runner/driver.py#L531)

- `gate_passed` always re-derives the *latest* draft -- never `.one()` -- since more than one row is now expected.
  [`driver.py:572`](../../shell/runner/driver.py#L572)

- Uniqueness loosened from "one per run" to "one per (run, attempt)"; a plain `Index`, not a `UniqueConstraint`, to match the migration's actual object type exactly.
  [`report_draft.py:66`](../../shell/adapters/postgres/report_draft.py#L66)

- New `attempt` column, defaulted for the first, never-regenerated draft.
  [`report_draft.py:80`](../../shell/adapters/postgres/report_draft.py#L80)

**A counter that can't be confused with the generic one**

- Why a shared counter with `stage_failure_count` doesn't work: a successful `draft_ready` re-run would silently reset it.
  [`report_run.py:126`](../../shell/adapters/postgres/report_run.py#L126)

**Always showing the current attempt**

- Francesco's draft view orders by attempt descending, never an arbitrary row.
  [`report_runs.py:208`](../../shell/http/routes/report_runs.py#L208)

**Schema**

- Forward-only migration: new columns on `report_run`/`report_draft`, plus the composite unique index swap.
  [`0012_bounded_regeneration.py:36`](../../migrations/versions/0012_bounded_regeneration.py#L36)

**Peripherals**

- Bound-exhaustion coverage: the Generator returns the same violating draft forever; the run stops rather than looping silently.
  [`test_runner_driver.py:1008`](../../tests/test_runner_driver.py#L1008)

- Regenerate-then-pass coverage: proves the same Payload row is reused, never recomputed, across attempts.
  [`test_runner_driver.py:960`](../../tests/test_runner_driver.py#L960)

- Uniqueness coverage: same attempt still conflicts; a different attempt for the same run no longer does.
  [`test_report_draft_store.py:212`](../../tests/test_report_draft_store.py#L212)

- Latest-attempt rendering, proven at the HTTP layer.
  [`test_http_report_runs.py:597`](../../tests/test_http_report_runs.py#L597)
