---
title: 'Story 4.8 — Absorb a rate limit without my involvement'
type: 'feature'
created: '2026-08-22'
status: 'done'
review_loop_iteration: 0
baseline_commit: '9c9b399963f2f4e60f5b28eae41b636ae576f5b6'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `drive()`'s `with_backoff` call (Story 3.5) retries every stage — including `draft_ready`'s live Gemini call (Story 4.5) — with the same tiny, generic schedule (3 attempts, ~0.1s/0.2s apart), never sized to the provider's real 10 requests-per-minute ceiling. Worse, when retries within one `drive()` call are exhausted, `drive()` just logs and leaves `run.stage` unchanged — the next poll (every 2s) tries again, forever: no terminal state, nothing ever surfaced to Francesco, and a persistent rate limit turns into an indefinite, ever-hammering silent stall.

**Approach:** Give `draft_ready` its own right-sized `with_backoff` parameters (still the one shared retry primitive, per AD-10) so consecutive Gemini attempts never exceed 10/minute, and add a persisted, cross-poll failure counter on `ReportRun` so that once enough consecutive `with_backoff` exhaustions accumulate, the run is marked terminally failed with a reason instead of retried forever.

## Boundaries & Constraints

**Always:**
- `with_backoff`'s retry algorithm (catch-all exception, exponential doubling, no jitter, re-raise on exhaustion) is untouched (AD-10: one shared retry primitive) — only its delay becomes configurable per call site.
- `draft_ready`'s Gemini attempts never exceed the provider's 10 requests/minute ceiling.
- A stage's successful advance resets its run's failure counter to 0; enough consecutive exhaustions on the current stage instead sets a terminal `failed_at`/`failure_reason` on the row, and a `drive()` call on an already-failed row does nothing further.
- No partial `ReportDraft` can ever exist for a failed run: `store_report_draft` still runs only after a successful `generator.generate()`, unchanged.
- The poll fragment shows the failure reason and stops polling once a run has failed, so Francesco sees why without doing anything.
- No automatic failover to a second `Generator` adapter anywhere — `get_generator()` still constructs exactly one `GeminiGenerator`; changing provider stays a deliberate, separately-gated change (already enforced via `GEMINI_DATA_TERMS_VERIFIED_AT`, Story 4.5) — no new code needed for this bullet.

**Ask First:** none identified — the exact retry-count/delay/failure-threshold constants (see Code Map) are the numbers the 10 RPM ceiling and "bounded, not infinite" pin down without another reading; documented, not gated.

**Never:** No change to `with_backoff`'s retry algorithm itself, or to any other stage's backoff parameters. No new Generator port argument. No retry/failure state surfaced anywhere except the poll fragment.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Transient `draft_ready` failure, then success | Gemini call raises once, then succeeds, within one `drive()` call | Run advances to `draft_ready` normally; `stage_failure_count` stays/resets to 0 | N/A |
| Persistent `draft_ready` failure across many polls | Gemini call always raises; `drive()` called 5 times | 5th call sets `failed_at`/`failure_reason`; run never advances | N/A |
| Polling a failed run | `run.failed_at` is set | `drive()` is a no-op; poll fragment shows the reason, no `hx-trigger` | N/A |
| Draft view for a failed run | `run.failed_at` is set, no `ReportDraft` row exists | `GET /report-runs/{id}/draft` still 404s | 404 |
| A stage other than `draft_ready` fails persistently | e.g. `natal_ready` always raises | Still bounded by the existing default schedule/`_MAX_STAGE_FAILURES`; eventually reaches `failed_at` too | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/backoff.py:28` -- `with_backoff`: add `base_delay_seconds: float = _BASE_DELAY_SECONDS` param, replacing the module constant in the sleep-schedule computation.
- `shell/runner/driver.py:94-101,457-462,465-531` -- `_STAGE_SEQUENCE`/`_STAGE_FUNCTIONS`/`drive()`: add `_STAGE_BACKOFF_OVERRIDES = {"draft_ready": {"max_attempts": 3, "base_delay_seconds": 6.0}}` and `_MAX_STAGE_FAILURES = 5`; `drive()` looks up the override per stage, short-circuits at the top when `run.failed_at is not None`, and on exhaustion increments `run.stage_failure_count`, setting `failed_at`/`failure_reason` at the threshold instead of just logging and breaking.
- `shell/adapters/postgres/report_run.py:52-96` -- `ReportRun`: add `stage_failure_count: int` (default 0), `failed_at: datetime | None`, `failure_reason: str | None`, mirroring `month_start_utc`'s nullable-timestamp pattern.
- `migrations/versions/` -- new `0010_report_run_failure.py` (`down_revision = "0009_report_draft"`), three `op.add_column` calls on `report_run`.
- `shell/http/templates/report_run_poll.html` -- branch on `run.failed_at`: render the reason, omit `hx-trigger`.
- `tests/test_runner_backoff.py` -- add a `base_delay_seconds` schedule test.
- `tests/test_runner_driver.py:416-461` -- extend: 5 consecutive failing `drive()` calls set `failed_at`/`failure_reason`; a `failed_at` run's `drive()` call is a no-op; fail-then-succeed resets `stage_failure_count`.
- `tests/test_http_report_runs.py` -- add: failed-run poll fragment shows the reason with no `hx-trigger`; `/draft` still 404s.

## Tasks & Acceptance

**Execution:**
- [x] `shell/runner/backoff.py` -- add `base_delay_seconds` parameter to `with_backoff`.
- [x] `shell/adapters/postgres/report_run.py` -- add `stage_failure_count`/`failed_at`/`failure_reason` columns to `ReportRun`.
- [x] `migrations/versions/0010_report_run_failure.py` -- new forward-only migration adding the three columns.
- [x] `shell/runner/driver.py` -- `_STAGE_BACKOFF_OVERRIDES`, `_MAX_STAGE_FAILURES`, the `failed_at` short-circuit, and the exhaustion→failure-counter→terminal-failure path in `drive()`.
- [x] `shell/http/templates/report_run_poll.html` -- render `failure_reason` and drop `hx-trigger` once `failed_at` is set.
- [x] `tests/test_runner_backoff.py` -- cover the new `base_delay_seconds` parameter.
- [x] `tests/test_runner_driver.py` -- cover the I/O & Edge-Case Matrix's `draft_ready`-specific rows.
- [x] `tests/test_http_report_runs.py` -- cover the poll-fragment and `/draft` 404 rows.

**Acceptance Criteria:**
- Given a provider rate limit or a transient error, when generation is attempted, then it is retried automatically with backoff bounded to the provider's 10 requests-per-minute ceiling, with no involvement from Francesco.
- Given exactly one configured Generator adapter, when any failure occurs, then there is no automatic failover to another provider, ever.
- Given retries that are exhausted, when the run ends, then the Report is marked failed and surfaced to Francesco with the reason, and no partial Report exists that could be exported.

## Design Notes

- **Per-stage override, not a new default:** only `draft_ready` has a real rate-limited network call (already flagged in driver.py's own Design Notes as "Story 4.8's own deliverable"); the other three stages keep today's fast schedule.
- **A persisted counter, not a longer single `with_backoff` call:** blocking one HTTP request for minutes would contradict `drive()`'s no-blocking-request design (BUILD-ORDER.md E5); spreading the bounded budget across poll-driven `drive()` calls keeps every request cheap.
- **5 consecutive stage failures, not attempts:** each `drive()` call already spends up to 3 Gemini attempts (18s); 5 such failures (~15 real attempts) is a genuinely exhausted run, not a blip.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_backoff.py tests/test_runner_driver.py tests/test_http_report_runs.py tests/test_migration_chain.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Terminal-failure state machine**

- Entry point: the design intent -- per-stage backoff override plus a persisted failure counter that turns exhaustion into a terminal state.
  [`driver.py:113`](../../shell/runner/driver.py#L113)

- `_MAX_STAGE_FAILURES` -- the "how many consecutive exhaustions before giving up" threshold, sized against the backoff schedule above it.
  [`driver.py:123`](../../shell/runner/driver.py#L123)

- `drive()`'s short-circuit: a `failed_at` row is returned untouched, never re-attempted.
  [`driver.py:535`](../../shell/runner/driver.py#L535)

- The except-block: increments the counter, bumps `updated_at` unconditionally, and sets `failed_at`/`failure_reason` at the threshold.
  [`driver.py:563`](../../shell/runner/driver.py#L563)

- Success path resets the counter to 0, so only *consecutive* exhaustions count.
  [`driver.py:585`](../../shell/runner/driver.py#L585)

**Backoff sizing**

- `with_backoff` gains a configurable delay while its retry algorithm stays untouched -- the one change that lets `draft_ready` be sized differently from every other stage.
  [`backoff.py:32`](../../shell/runner/backoff.py#L32)

- The per-stage override itself: 3 attempts, 6s base delay, sized to the provider's 10 requests/minute ceiling.
  [`driver.py:113`](../../shell/runner/driver.py#L113)

**Schema**

- `ReportRun`'s three new columns -- the persisted state the whole mechanism above reads and writes.
  [`report_run.py:104`](../../shell/adapters/postgres/report_run.py#L104)

- The forward-only migration adding them, mirroring the table's existing columns.
  [`0010_report_run_failure.py:33`](../../migrations/versions/0010_report_run_failure.py#L33)

**Surfacing to Francesco**

- The poll fragment: shows the failure reason, drops `hx-trigger` to stop polling, and keeps the Payload link available even on a failed run.
  [`report_run_poll.html:17`](../../shell/http/templates/report_run_poll.html#L17)

**Tests**

- The new backoff-schedule case proving `base_delay_seconds` actually changes the sleep sequence.
  [`test_runner_backoff.py:99`](../../tests/test_runner_backoff.py#L99)

- Persistent-failure-to-terminal-state, the core new behavior.
  [`test_runner_driver.py:807`](../../tests/test_runner_driver.py#L807)

- A failed run is a no-op on `drive()` -- no further Generator calls.
  [`test_runner_driver.py:847`](../../tests/test_runner_driver.py#L847)

- Transient failure still resets the counter on success.
  [`test_runner_driver.py:882`](../../tests/test_runner_driver.py#L882)

- The same terminal-failure path for a non-`draft_ready` stage, proving it isn't special-cased.
  [`test_runner_driver.py:918`](../../tests/test_runner_driver.py#L918)

- The poll fragment's user-facing surfacing, end to end.
  [`test_http_report_runs.py:653`](../../tests/test_http_report_runs.py#L653)

- No partial, exportable Report for a failed run.
  [`test_http_report_runs.py:671`](../../tests/test_http_report_runs.py#L671)
