---
title: 'Retro C: two-write-guard cluster — partial-flush retries and concurrent-drive() IntegrityError races'
type: 'bugfix'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: 'd16cd5c268e48673b92e9a7ddf94156ea653a44c'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Three still-open concurrency gaps in the report pipeline (retro items 23, 26/44, 49).
- **23** — when a two-write stage function (`_run_payload_ready`, `_run_gate_passed`) partially flushes then fails, `with_backoff` retries it on the *same* session whose transaction is now doomed, so every retry dies on `PendingRollbackError`: a transient second-write failure never gets a real retry and the masking error hides the cause. Item 39 added `session.rollback()` to `drive()`'s `except` blocks (the downstream commit is safe) but left the in-`with_backoff`-loop retry unprotected.
- **26 / 44** — `drive()` is called from the start route and the poll route with no row lock; two concurrent calls for one run can both write the same stage row, and the unique-constraint `IntegrityError` (`ReportPayload.report_run_id`; `ReportDraft` on `(report_run_id, attempt)`) is counted as a stage failure toward `_MAX_STAGE_FAILURES` instead of "another request already advanced this stage".
- **49** — `GET /backup` writes a `backup_record` on every hit, so a prefetch/retry silently clears Story 6.6's staleness warning.

**Approach:** In `drive()`'s per-stage loop, run each `with_backoff` attempt inside `session.begin_nested()` (SAVEPOINT), mirroring `shell/adapters/postgres/place_cache.py` — a partial flush rolls back to the savepoint so the next attempt runs on a clean session. Add an `IntegrityError`-aware branch to `drive()`'s per-stage exception handling: roll back, `session.refresh(run)`, and if `run.stage` advanced past the current stage treat it as a completed stage (`break`, no counter change); otherwise fall through to the existing failure path. Give `download_backup` a `record: bool = False` query flag — record + commit only on `?record=1`; the export body is always served. `shell/runner/backoff.py` is not touched (AD-10: one generic retry primitive).

## Boundaries & Constraints

**Always:** Keep `with_backoff` generic — no session/DB awareness in `shell/runner/backoff.py`. Import `IntegrityError` from `sqlalchemy.exc` (as `place_cache.py` / `style_guide.py` do). A benign concurrent-`drive()` `IntegrityError` must not touch `run.stage_failure_count`, `run.regeneration_count`, or `run.failed_at`. `GET /backup` must still return the full JSON export for any request, flagged or not. Existing driver tests `test_gate_passed_pass_path_flush_failure_leaves_run_recoverable`, `test_gate_failed_error_path_survives_a_gate_result_flush_failure`, `test_a_stage_that_fails_once_then_succeeds_still_advances_run_stage_within_one_drive_call` must keep passing unchanged.

**Ask First:** Moving `GET /backup` behind `POST` (declined — minimal GET-hardening chosen). Adding real row locking (`SELECT … FOR UPDATE`) to `drive()`. Changing `_STAGE_BACKOFF_OVERRIDES` attempt counts.

**Never:** No migration, no schema change (the unique constraints already exist). No edit to stage-function bodies (`_run_payload_ready` etc. stay byte-for-byte — the savepoint wraps them from `drive()`). No retry of an `IntegrityError` that is not a concurrent-stage advance. No prefetch/header sniffing. No change to the `/backup` export body or `_BACKUP_MODELS`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Transient second-write failure, then success | `_run_payload_ready` flushes `ReportPayload`, then `store_report_theme` raises a DB error once, then succeeds | attempt 1 rolls back to its savepoint; `with_backoff` attempt 2 runs clean and completes; `run.stage` advances to `payload_ready` in the same call; `stage_failure_count` stays 0 | retry transparent |
| Persistent second-write failure | `store_gate_result` raises on every attempt | each attempt's partial `store_report` flush rolls back to its savepoint; `with_backoff` exhausts; `except Exception` rolls back + `stage_failure_count += 1` + commits; no half-written rows | unchanged from item-39 |
| Concurrent `drive()` loses the `ReportPayload` race | a `ReportPayload` for `run` already exists; `store_report_payload` flush raises `IntegrityError` on `report_run_id` | roll back, `session.refresh(run)`, see `run.stage` past `payload_ready`, return `run` unchanged | INFO log, not `logger.exception` |
| Concurrent `drive()` loses the `ReportDraft` race | a `ReportDraft` for `(run, attempt=N)` already exists; `draft_ready` re-runs at `regeneration_count == N` | same as above (`ix_report_draft_report_run_id_attempt`) | INFO log |
| `IntegrityError` with no stage advance | a `store_*` call raises `IntegrityError` but `run.stage` did not move past the current stage after refresh | fall through to the existing stage-failure path: rollback, `stage_failure_count += 1`, commit (terminal at `_MAX_STAGE_FAILURES`) | real failure |
| Bare `GET /backup` (prefetch / retry / crawler) | request without `?record=1` | full JSON export + `Cache-Control: no-store`; **no** `backup_record` row; staleness warning unaffected | N/A |
| Deliberate `GET /backup?record=1` | operator follows "Back up now" | full export **and** exactly one `backup_record` row committed; staleness warning clears | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py` — `drive()` loop `718-858`: `with_backoff(...)` call `732-744`; `except GateFailedError` `746`; `except Exception` `818-847` (already `session.rollback()` + bookkeeping commit — item 39); per-stage success block `849-855`. `_stage_index()` `256-261`; `_STAGE_SEQUENCE` `103`. Two-write stages: `_run_payload_ready` `376-422` (`store_report_payload` → `store_report_theme`), `_run_gate_passed` `553-626` (`store_report` → `store_gate_result`). `_run_draft_ready` `543-550` (`store_report_draft(attempt=run.regeneration_count)`). Imports `57-95` — add `from sqlalchemy.exc import IntegrityError`.
- `shell/adapters/postgres/place_cache.py:100-107` — the `with session.begin_nested(): … except IntegrityError` SAVEPOINT idiom to mirror.
- `shell/http/routes/style_guide.py:180-195` — route-level `except IntegrityError: session.rollback()` precedent.
- `shell/adapters/postgres/report_payload.py:55` — `report_run_id` `unique=True`. `shell/adapters/postgres/report_draft.py:66-68` — unique `Index("ix_report_draft_report_run_id_attempt", "report_run_id", "attempt", unique=True)`.
- `shell/http/routes/report_runs.py:130-150` `_drive_run`, `153-176` `start_report_run` (POST), `178-192` `poll_report_run` (GET) — the two unlocked `drive()` call sites.
- `shell/http/routes/backup.py:80-114` — `download_backup`; `store_backup_record(session)` + `session.commit()` at `108-109` become conditional on the new `record` flag.
- `shell/adapters/postgres/backup_record.py:58-63` — `store_backup_record` (flush-only). `shell/http/routes/clients.py:618-641` — `_backup_is_stale` (Story 6.6), unchanged.
- `shell/http/templates/client_reports.html:13-17` — `<a href="/backup">Back up now</a>` → `/backup?record=1`.
- `tests/test_runner_driver.py` — fixture `95-105` (`create_engine("sqlite://")`), failure-injection pattern `457-486` / `1198-1245`, `_drive` helper `166-187`. `tests/test_http_backup.py:532-552` — the two `backup_record`-count tests to retarget. `tests/test_place_cache.py:54-70` — duplicate-insert-does-not-raise pattern.

## Tasks & Acceptance

**Execution:**
- [x] `shell/runner/driver.py` — add `from sqlalchemy.exc import IntegrityError`. In `drive()`'s per-stage loop, define a local `_attempt` callable passed to `with_backoff` that (1) runs the stage inside `with session.begin_nested():` (SAVEPOINT), and (2) catches `IntegrityError` *itself* — rolling the savepoint back and **not re-raising into `with_backoff`'s retry** (a unique-constraint conflict never clears on retry, and on `draft_ready` a retry spends another real `generator.generate()` call plus `with_backoff`'s 6 s / 12 s sleeps). Signal a caught `IntegrityError` back to the loop body (e.g. a `nonlocal` flag). After `with_backoff` returns, if that flag is set: `session.rollback()`, `session.refresh(run)`, and if `_stage_index(run.stage) >= index` log at INFO — including the observed `run.stage` — and `break`; otherwise record it as a stage failure (increment `stage_failure_count`, `logger.exception`, terminal at `_MAX_STAGE_FAILURES`, commit `run`) and `break`. A non-`IntegrityError` stage exception still flows through `with_backoff`'s retry and the unchanged `except GateFailedError` / `except Exception` (item-39 rollback) paths. Update `drive()`'s docstring; the `_attempt` comment must note the error handling differs from `place_cache.py` (which swallows the conflict) and that the "next attempt" reasoning does not apply to `gate_passed` (`max_attempts=1`).
- [x] `shell/http/routes/backup.py` — add `record: bool = False` (FastAPI query param) to `download_backup`; call `store_backup_record(session)` + `session.commit()` only when `record` is true; always build and return the export. Docstring: state that only a *non-deliberate* bare `GET /backup` (old bookmark, URL probe, health check) stops recording; a prefetch/crawl/retry of the flagged `?record=1` link still records — the guarantee is that an incidental hit cannot *silently* clear the warning, not that every automated hit is excluded. Note `POST` was declined to keep the plain-link download working.
- [x] `shell/http/templates/client_reports.html` — change the "Back up now" `href` from `/backup` to `/backup?record=1`.
- [x] `tests/test_runner_driver.py` — add: (a) a two-write stage whose second write raises a real DB error (`OperationalError`, not `IntegrityError`) once then succeeds advances `run.stage` within one `drive()` call with `stage_failure_count == 0` — uses a `base_delay_seconds: 0.0` override so the suite adds no real `time.sleep`; (b) a pre-existing `ReportPayload` row makes `drive()` at `payload_ready` treat the `IntegrityError` as a completed stage on the **first** attempt (assert the stage function / `with_backoff` was entered once, no retry sleeps) — `run` returned stage-advanced, `stage_failure_count` / `failed_at` untouched, INFO (not exception) logged; (c) the same for a pre-existing `ReportDraft` `(run, attempt=N)` row at `draft_ready`, asserting `generator.generate()` ran at most once; (d) an `IntegrityError` where `run.stage` did not advance still increments `stage_failure_count`, with no retry.
- [x] `tests/test_http_backup.py` — retarget `test_a_completed_backup_commits_one_backup_record_row` and `test_two_completed_backups_commit_two_backup_record_rows` to `GET /backup?record=1`; add a test that a bare `GET /backup` returns 200 with the full export body, writes **zero** `backup_record` rows, **and** — given a prior `backup_record` plus a newer `Report` — leaves `_backup_is_stale(session)` / the rendered `backup_stale` warning true.

**Acceptance Criteria:**
- Given a two-write stage whose second write fails transiently once, when `drive()` runs, then `with_backoff` retries it successfully within the same call and the run advances with no stage-failure increment.
- Given a `ReportPayload` (or `ReportDraft (run, attempt)`) row already committed by a concurrent `drive()`, when this `drive()` reaches that stage and hits the unique-constraint `IntegrityError`, then the conflict is recognised on the first attempt (no `with_backoff` retry, no extra `generator.generate()` call) and the run is returned at the already-advanced stage without incrementing `stage_failure_count` or marking the run failed.
- Given an `IntegrityError` that is not a concurrent stage advance, when `drive()` handles it, then it is recorded as a stage failure (counter increment, terminal at `_MAX_STAGE_FAILURES`) without being retried.
- Given a `GET /backup` request without `?record=1`, when it completes, then the full export is returned and no `backup_record` row is written; with `?record=1`, exactly one `backup_record` row is committed.
- Given the client-reports page shows the staleness warning, when the user clicks "Back up now", then the request carries `?record=1` and clears the warning.

## Spec Change Log

### Iteration 1 — review loopback (bad_spec)

**Triggering finding (Blind Hunter, medium):** The approved approach caught `IntegrityError` in `drive()`'s `except Exception` block *after* `with_backoff`, so every unique-constraint conflict from a concurrent `drive()` was first retried up to `max_attempts` times. This contradicted the frozen **Never: "No retry of an `IntegrityError` that is not a concurrent-stage advance."** For `draft_ready` (`max_attempts=3`, `base_delay_seconds=6.0`) a benign concurrent race — the exact `ReportDraft` case item 44 tracks — spent three real `generator.generate()` (Gemini) calls and `time.sleep(6)` + `time.sleep(12)` (~18 s of blocked request thread) before the conflict was classified. The old Design Notes wrongly called this "≤3 sub-second retries … an accepted cost".

**Amended (non-frozen only):** Design Notes and Tasks now require `IntegrityError` to be intercepted *inside* the `_attempt` callable (swallow + `nonlocal` flag), so `with_backoff` never retries it; the loop body classifies benign vs genuine after a single attempt. Added: INFO log must include the observed `run.stage`; the `_attempt` comment must not claim a straight mirror of `place_cache.py` (whose handling is inverted) and must note the "next attempt" reasoning is moot for `gate_passed` (`max_attempts=1`); the two `payload_ready` driver tests must use a `base_delay_seconds: 0.0` override (no real `time.sleep` in the suite, matching every other retry test in the file); the bare-`GET /backup` test must also assert `_backup_is_stale` stays true given a prior backup + newer report; `backup.py`'s docstring must not overclaim that `?record=1` excludes every automated hit (a prefetch/crawl/retry of the flagged link still records — the guarantee is only against *silent* clearing by an incidental hit).

**Known-bad state avoided:** wasted paid LLM calls and multi-second stalls on a benign, in-scope concurrency race; a spec whose Design Notes contradicted its own frozen Boundaries.

**KEEP (must survive re-derivation):**
- Savepoint-per-`with_backoff`-attempt via `session.begin_nested()` for item 23 — correct, keep exactly.
- `session.rollback()` *before* `session.refresh(run)`, then `_stage_index(run.stage) >= index` as the benign/genuine discriminator — correct logic, keep.
- `download_backup(record: bool = False)` query flag + `client_reports.html` link `→ /backup?record=1`; export body served unconditionally — keep.
- Do not touch `shell/runner/backoff.py` (AD-10).
- The three protected item-39 driver tests must stay green unchanged.
- The four new driver tests + bare-`GET /backup` test as concepts — keep, adjust per the amendments above.

## Design Notes

**Savepoint per attempt (item 23).** `with_backoff` calls its function up to `max_attempts` times; wrapping the whole `with_backoff` call in one `begin_nested()` would not help (attempt 1's poisoned state still blocks attempt 2). The savepoint must be per attempt, inside the retried callable — and that same callable also intercepts `IntegrityError` (see below):

```python
integrity_conflict = False

def _attempt(stage_fn=stage_fn):
    nonlocal integrity_conflict
    try:
        with session.begin_nested():
            stage_fn(session, run, natal_chart, config, ephemeris_identity,
                     sections_config, generator, vocabulary)
    except IntegrityError:
        # Do NOT let with_backoff retry this (see "IntegrityError" below).
        integrity_conflict = True

with_backoff(_attempt, **backoff_kwargs)
```

For a non-`IntegrityError` failure: a clean exit releases the savepoint (rows stay in the outer transaction for `drive()`'s trailing `session.commit()`); an exception rolls the savepoint back and re-raises, so the next `with_backoff` attempt — and, after exhaustion, `drive()`'s own `except` handlers — get a usable session. `GateFailedError` from `_run_gate_passed` (raised before any write) passes through as a no-op.

**IntegrityError, intercepted before the retry (items 26/44).** Both unique constraints (`ReportPayload.report_run_id`; `ReportDraft` on `(report_run_id, attempt)`) surface the same `sqlalchemy.exc.IntegrityError`. It must be caught **inside `_attempt`, not after `with_backoff`** — a unique-constraint conflict from a concurrent `drive()` never clears on retry, and letting it ride `with_backoff` would spend up to `max_attempts` doomed attempts: for `draft_ready` that is three real `generator.generate()` (Gemini) calls plus `time.sleep(6)` + `time.sleep(12)` before the conflict is even classified. `_attempt` swallows it and returns normally (so `with_backoff` stops) and flags it. The loop body then does `session.rollback()` + `session.refresh(run)` and the `_stage_index(run.stage) >= index` check: advanced → benign concurrent completion, log at INFO (with the observed `run.stage`) and `break`; not advanced → a genuine integrity bug, recorded as a stage failure (`stage_failure_count += 1`, `logger.exception`, terminal at `_MAX_STAGE_FAILURES`) and `break`. `session.rollback()` before `session.refresh(run)` makes the re-read isolation-level-independent (fresh transaction, sees the concurrent commit under READ COMMITTED or REPEATABLE READ alike). `run.stage_failure_count` is not force-reset on the benign path: `session.refresh(run)` already loads the concurrent winner's committed row, whose success path set it to `0`.

**Not mirrored from `place_cache.py`.** `place_cache.store_resolved_place` wraps `begin_nested()` in `try/except IntegrityError: pass` and swallows the conflict in place; here the savepoint shape is the same but `_attempt` surfaces the conflict to the loop body for benign/genuine classification. The `_attempt` comment must not claim a straight mirror.

**Item 49 residual (accepted).** A prefetch of the *flagged* link still records, and a retried deliberate download writes a second harmless `backup_record` row (the staleness check reads only the latest). The retro's bar is "a prefetch/retry cannot *silently* clear the warning" — an explicit click on "Back up now" is not silent. `GET /report-runs/{id}/export/pdf` (also named in item 49) is out of scope: its `export_record` write is a deliberate-export audit trail, not a staleness signal.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_driver.py tests/test_http_backup.py tests/test_http_clients.py -q` — expected: all pass, including the new cases.
- `uv run pytest -q` — expected: full suite green (no regression in the driver, backup, or restore suites).
- `uv run ruff check shell/ tests/` and `uv run ruff format --check shell/ tests/` — expected: clean.

## Suggested Review Order

**Savepoint per attempt + IntegrityError interception (items 23 / 26 / 44)**

- Entry point: the local `_attempt` callable — SAVEPOINT per `with_backoff` attempt, and where a concurrent-`drive()` `IntegrityError` is caught so it is never retried.
  [`driver.py:764`](../../shell/runner/driver.py#L764)
- The one call that used to be a bare `lambda`; now `with_backoff` drives `_attempt`.
  [`driver.py:803`](../../shell/runner/driver.py#L803)
- The `else:` branch — benign concurrent completion (`run.stage` advanced → INFO + `break`, no counter change) vs a genuine integrity bug (recorded as a stage failure, still no retry).
  [`driver.py:905`](../../shell/runner/driver.py#L905)
- `session.rollback()` before `session.refresh(run)` — the re-read runs in a fresh transaction, so it sees the concurrent commit under any isolation level.
  [`driver.py:916`](../../shell/runner/driver.py#L916)
- `drive()` docstring — the two new behaviours stated for the next reader.
  [`driver.py:679`](../../shell/runner/driver.py#L679)

**GET /backup recording gate (item 49)**

- `record: bool = Query(default=False, …)` — the new flag; the export body is still built and returned for every request.
  [`backup.py:85`](../../shell/http/routes/backup.py#L85)
- The write is now conditional: `store_backup_record` + commit only on `?record=1`.
  [`backup.py:133`](../../shell/http/routes/backup.py#L133)
- The only caller that sets the flag — the "Back up now" link in the staleness warning.
  [`client_reports.html:16`](../../shell/http/templates/client_reports.html#L16)
- Adapter docstring reconciled with the new gate.
  [`backup_record.py:1`](../../shell/adapters/postgres/backup_record.py#L1)

**Tests**

- Item 23, transient: two-write stage, second write fails once then succeeds, advances in one `drive()` call.
  [`test_runner_driver.py:1330`](../../tests/test_runner_driver.py#L1330)
- Item 23, exhaustion: second write fails on every attempt, `drive()` still returns cleanly, no half-written rows.
  [`test_runner_driver.py:1553`](../../tests/test_runner_driver.py#L1553)
- Items 26/44: a pre-existing `ReportPayload` / `ReportDraft` row makes the stage a completed stage on the first attempt (no retry, no extra `generator.generate()`).
  [`test_runner_driver.py:1384`](../../tests/test_runner_driver.py#L1384)
- Genuine `IntegrityError` (no stage advance) is recorded as a stage failure; repeated ones reach terminal failure.
  [`test_runner_driver.py:1495`](../../tests/test_runner_driver.py#L1495)
- Item 49: a bare `GET /backup` serves the export, writes nothing, leaves staleness true; `?record=1` records and clears it.
  [`test_http_backup.py:559`](../../tests/test_http_backup.py#L559)
