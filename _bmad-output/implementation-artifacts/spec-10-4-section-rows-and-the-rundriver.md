---
title: '10.4 Section rows and the RunDriver'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: '28b4a706f056f37b8cf02b0dc9a9421ba44933c8'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A run only moves when a poll or the 2 s scheduler calls the one-stage `advance()`, and `draft_ready` writes all eight Sections in one blocking ~118 s call, so nothing parallel, resumable or partially saved is possible.

**Approach:** Per AD-20/AD-21, add `report_draft_section` rows, a pure `core/draft_state.py`, leases, and a `RunDriver` (`shell/runner/driver.py`) that loops each run in the background, fans 1–7 out to a `GENERATION_CONCURRENCY`-capped executor, then writes Consiglio finale, assembles one `ReportDraft` and continues to `gate_passed`. Port md-report's `shell/runner/{driver,lease}.py`.

## Boundaries & Constraints

**Always:** Forward-only migration `0025`; table unique on (`report_run_id`, `attempt`, `ordinal`), cascade-deleted with the Client (`delete_client_and_derived`, tests via `tests/_fk.py`). `core/draft_state.py` is pure, fully type-hinted. Stage logic stays in `advance()` (moved to `shell/runner/advance.py`, still one stage per call, under the advisory lock, same `GateFailedError`/failure-count semantics); `draft_ready` is completed by the driver, not by a stage function. A Gate failure still rewinds to `payload_ready` and opens a *new full* attempt (8 fresh rows) — targeted reset is Story 10.5. Every loop thread binds the verified ephemeris path (`bind_verified_ephemeris_path_to_current_thread`) before `advance()`; the generation executor reaches no chart code. `MAX_SECTION_ATTEMPTS` is a constant in `shell/config.py`, not an env var. Logs carry ids only. Every module keeps its why-docstring.

**Ask First:** Any change to `advance()`'s retry/failure/regeneration constants; any new env var.

**Never:** Touch `ReportDraft`'s immutability, Gate, export gate or review routes. No `threading`, `concurrent.futures` or `asyncio.create_task` outside `shell/runner/driver.py`. No queue, cron, second process. Do not build targeted regeneration (10.5) or the progressive UI (10.6).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start | `POST` start | row created, `driver.start(id)`, redirect at once | N/A |
| Fan-out | 8 pending rows | 1–7 claimed together (cap-limited); 8 only after 1–7 complete | N/A |
| Parallel speed | fake generator sleeping 1 s/Section | draft complete in ~2 s | N/A |
| Assembly | 8 complete | one `ReportDraft`, `run.stage=draft_ready`, loop continues to `gate_passed` | N/A |
| Restart | driver stopped mid-draft | `resume()` finishes; complete Sections never rewritten | expired lease reclaimed |
| Transient failure | `generate_section` raises | attempts+1, `last_error` set, retried | N/A |
| Exhausted | `MAX_SECTION_ATTEMPTS` failures | run `failed_at`, reason names the Section; no `Report` row | N/A |
| Lease held | another claim live | claimer returns, changes nothing | N/A |
| Poll | `GET` run | read-only, never advances | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py` -- today `advance()` + stage fns (1098 lines); move to `shell/runner/advance.py` (stage fns, `_STAGE_*`, `_MAX_*`); new `RunDriver(start/resume/stop/wait_idle)` replaces it. Reference: `../md-report/shell/runner/driver.py`.
- `shell/runner/lease.py` (new) -- `section_claim` via atomic conditional UPDATE, `LEASE_TTL`; ref `../md-report/shell/runner/lease.py`.
- `shell/runner/scheduler.py` -- delete; move `generator_for_settings` to new `shell/runner/generators.py` (used by `routes/report_runs.py:510`, `tests/test_gemini_generator.py:1011`).
- `core/draft_state.py` (new) -- `claimable_sections`, `is_draft_complete`, `is_exhausted` over frozen row values.
- `shell/adapters/postgres/report_draft_section.py` + `migrations/versions/0025_report_draft_section.py` (new); cascade in `shell/adapters/postgres/client.py:357`; model after `report_draft.py`.
- `shell/runner/advance.py::_run_draft_ready` -- replaced by open-attempt / assemble helpers called by the driver (`store_report_draft`, `next_report_draft_attempt`).
- `shell/http/app.py:150-172` -- lifespan builds driver (`settings.generation_concurrency`), `resume()` on start, `stop()` before engine dispose; replaces `start/stop_scheduler`.
- `shell/http/routes/report_runs.py:531-633` -- drop `_advance_run`/poll advance and `ReportRunMode`; `start_report_run` and `regenerate_report_run` call `driver.start`.
- `shell/config.py` -- remove `ReportRunMode`/`REPORT_RUN_MODE` (lines 57-130, 358-373, 440+); add `MAX_SECTION_ATTEMPTS`.
- `shell/ports/generator.py`, `shell/adapters/{gemini,local}/generator.py` -- remove whole-report `generate()` (10.3's promise) and its tests.
- `.env.example:69-74`, `AGENTS.md` -- drop `REPORT_RUN_MODE`; note the one permitted thread/executor site.
- Tests to rewrite: `tests/test_runner_driver.py` (2398 lines, `advance` tests → `advance.py`; draft stage → driver), `tests/test_runner_scheduler.py` (delete), `tests/test_http_report_runs.py`, `test_http_app.py`, `test_config.py`; new `test_draft_state.py`, `test_report_draft_section_store.py`, `test_run_driver.py`, `test_report_draft_section_on_postgres.py`, thread-guard test with `test_the_guard_detects_a_*`.

## Tasks & Acceptance

**Execution:**
- [x] migration + `report_draft_section.py` + cascade -- AD-21 columns (ordinal, name, status, sentences, attempts, last_error, claimed_at, claim_expires_at)
- [x] `core/draft_state.py` -- pure claimability/completeness/exhaustion
- [x] `shell/runner/lease.py` -- claim/release
- [x] `shell/runner/advance.py` -- move `advance()`; draft stage handed to driver
- [x] `shell/runner/driver.py` -- `RunDriver`; per-run loop on a fresh `Session`, ephemeris bound per thread
- [x] app lifespan, routes, config, scheduler removal, `generate()` removal
- [x] tests per matrix row; thread-boundary guard + negatives; Postgres migration/engine checks
- [x] `.env.example`, `AGENTS.md`

**Acceptance Criteria:**
- Given a run started with a fake generator, when it finishes, then it reached `gate_passed` with no HTTP request after the start.
- Given two concurrent drivers/loops on one run, when both claim, then no Section is written twice.
- Given `uv run pytest` and (with `MIGRATION_TEST_DATABASE_URL`) the `*_on_postgres` tests, then all pass.

## Spec Change Log

## Design Notes

No in-progress status: a live lease marks a Section being written; `claimable` = `pending`, attempts < max, lease absent/expired, and (ordinal 8 only) 1–7 `complete`. The loop never runs a chart stage inside the generation executor, so the Swiss Ephemeris thread-pinning pitfall applies only to loop threads.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `MIGRATION_TEST_DATABASE_URL=… uv run pytest tests/*_on_postgres.py` -- expected: pass

## Suggested Review Order

**The driver (entry point)**

- RunDriver: per-run loops, capped fan-out, Consiglio finale last, resume.
  [`driver.py:109`](../../shell/runner/driver.py#L109)

- Outcome writes fenced on the claim; failures hold the Section off with a backoff.
  [`driver.py:437`](../../shell/runner/driver.py#L437)
  [`driver.py:459`](../../shell/runner/driver.py#L459)

- Draft step: open rows, claim, fan out, assemble.
  [`driver.py:327`](../../shell/runner/driver.py#L327)

**Pure state and leases**

- Which Sections are claimable, complete or exhausted.
  [`draft_state.py:75`](../../core/draft_state.py#L75)

- Atomic conditional claim yielding a fencing token.
  [`lease.py:42`](../../shell/runner/lease.py#L42)

**Stage machine and assembly**

- `advance()` moved here unchanged; draft assembly into one `ReportDraft`.
  [`advance.py:565`](../../shell/runner/advance.py#L565)

**Schema**

- Table unique on (run, attempt, ordinal); forward-only migration.
  [`report_draft_section.py:47`](../../shell/adapters/postgres/report_draft_section.py#L47)
  [`0025_report_draft_section.py`](../../migrations/versions/0025_report_draft_section.py)

**Wiring and removals**

- Start/regenerate hand runs to the driver; poll is read-only.
  [`report_runs.py:510`](../../shell/http/routes/report_runs.py#L510)

- Scheduler, `REPORT_RUN_MODE` and whole-report `generate()` removed; `MAX_SECTION_ATTEMPTS` constant added.
  [`config.py`](../../shell/config.py)

**Tests**

- Parallel speed, resume, exhaustion, leases, fencing, thread guard.
  [`test_run_driver.py`](../../tests/test_run_driver.py)
  [`test_concurrency_boundary.py`](../../tests/test_concurrency_boundary.py)
