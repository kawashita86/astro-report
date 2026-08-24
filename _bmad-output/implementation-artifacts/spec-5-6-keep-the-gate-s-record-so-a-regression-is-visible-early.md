---
title: 'Story 5.6 — Keep the Gate''s record so a regression is visible early'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: '3f379422371d69ca0d8ca8988c693a64cfc45a72'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `run_gate()` computes a full `GateResult` (Story 5.2) on every Gate check, but only a
passing check leaves any trace — `store_report()` writes a `Report` row solely on pass (Story 5.3), and
a failing check's `violations`/`vocabulary_version` vanish once `GateFailedError` is handled (Story
5.4 tracks only `run.regeneration_count`, an in-memory counter, not a queryable history). Francesco has
no stored series to catch a rising regeneration rate or a falling first-generation pass rate before a
client sees a bad Report.

**Approach:** Persist one immutable `gate_result` row per Gate check — pass or fail — recording
`passed`, the `regeneration_count` in force when the check ran, `vocabulary_version`, and every flagged
Claim (`violations`) as JSON, joining the FR-29 Client-deletion cascade. No new query or dashboard code:
per `ARCHITECTURE-SPINE.md`'s Deferred section, SM-5/SM-7 are answered by querying the stored table
directly — this story ships the schema and write path, proven queryable by a test.

## Boundaries & Constraints

**Always:**
- New `shell/adapters/postgres/gate_result.py`: `StoredGateResult` (table `gate_result`) — named
  `Stored*` to avoid colliding with `core/types/gate.py`'s `GateResult` dataclass, mirroring
  `StoredNatalChart`/`StoredReportTheme`'s own naming. Immutable (`before_update` listener raises,
  mirroring `Report`/`ReportDraft`). Fields: `id`, `client_id` (FK), `report_run_id` (FK, indexed,
  **not** unique — many rows per run), `passed: bool`, `regeneration_count: int`,
  `vocabulary_version: int`, `violations` (JSON list, empty when `passed`), `created_at`.
  `store_gate_result(session, *, run, passed, regeneration_count, vocabulary_version, violations)` —
  add()s and flush()es only, never commits, mirroring `store_report()`.
- Write exactly once per Gate check, from `shell/runner/driver.py`:
  - **Pass:** inside `_run_gate_passed`, alongside the existing `store_report(...)` call — safe because
    `with_backoff` calls a stage function once on success, never retries it.
  - **Fail:** inside `drive()`'s `except GateFailedError` block, using `error.violations`,
    `vocabulary.version` (`drive()`'s own parameter — always equals `result.vocabulary_version`, per
    `GateResult`'s docstring), and `run.regeneration_count` read **before** the existing
    `run.regeneration_count += 1` line. Not inside `_run_gate_passed` itself: `with_backoff` retries any
    exception — including a deterministic `GateFailedError` — up to 3 times, so a write there would
    persist duplicate rows for one logical failure.
- `shell/adapters/postgres/client.py`: add `"gate_result"` to `_CLIENT_CASCADE_TABLES` and delete every
  `gate_result` row for the client in `delete_client_and_derived`, in the same tier as `report`/
  `report_draft` (before the `report_run` deletion loop — `gate_result.report_run_id` is itself an FK).
- New migration `migrations/versions/0013_gate_result.py`, revising `0012_bounded_regeneration`,
  mirroring `0011_report.py`'s shape but with a non-unique index on `report_run_id`.
- A test proves first-generation pass rate (`regeneration_count == 0` rows) and a regeneration-count
  series are both directly computable from stored `gate_result` rows — no new production query function.

**Ask First:** None.

**Never:**
- No change to `core/gate/run.py`, `core/types/gate.py`, or `GateFailedError`'s signature — `error.
  violations` and `vocabulary.version` already carry everything needed.
- No dashboard, metrics backend, or query/reporting helper function — `ARCHITECTURE-SPINE.md`'s Deferred
  section states this explicitly; a direct query against `gate_result` is the answer.
- No guard against a retried multi-write stage function poisoning a transaction (epic-4-retro-item-23,
  already open, pre-existing and out of scope here).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Gate passes on the first attempt | `run.regeneration_count == 0`, `run_gate()` returns `passed=True` | One `gate_result` row: `passed=True`, `regeneration_count=0`, `violations=[]` | N/A |
| Gate fails, within the regeneration bound | `run_gate()` returns `passed=False`, pre-check `run.regeneration_count < _MAX_REGENERATIONS` | One `gate_result` row: `passed=False`, `regeneration_count` = pre-increment value, non-empty `violations`; `run.regeneration_count` then increments as today | N/A |
| Gate fails, regeneration bound exhausted | Pre-check `run.regeneration_count == _MAX_REGENERATIONS` | Same one `gate_result` row written before `run.failed_at` is set — the failing check's record is never lost | N/A |
| Client with Gate history deleted | Client has `gate_result` rows spanning a pass and an earlier fail | `delete_client_and_derived` deletes every `gate_result` row for the client before the `report_run` row | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/gate_result.py` (new) -- `StoredGateResult` model + `store_gate_result()` --
  mirrors `report.py`'s shape/immutability guard and `report_draft.py`'s `_json_safe` JSON pattern.
- `shell/runner/driver.py:587-593` (`_run_gate_passed`, pass branch) -- add `store_gate_result(...)`
  next to `store_report(...)`.
- `shell/runner/driver.py:701-735` (`drive()`'s `except GateFailedError` block) -- add
  `store_gate_result(...)` before `run.regeneration_count += 1`.
- `shell/adapters/postgres/client.py:47-49,320-322` (`_CLIENT_CASCADE_TABLES`,
  `delete_client_and_derived`) -- add `gate_result` to both.
- `migrations/versions/0013_gate_result.py` (new) -- `gate_result` table, revises `0012_bounded_regeneration`.
- `core/types/gate.py:52-89` (`GateViolation`/`GateResult`) -- reused as-is, read-only.
- `core/errors.py:146-171` (`GateFailedError`) -- reused as-is, read-only; `error.violations` is enough.
- `tests/test_gate_result_store.py` (new) -- row shape, writes on pass/fail, immutability, cascade join,
  a query proving first-generation pass rate + regeneration-count series are computable.
- `tests/test_runner_driver.py:828,859` (existing pass/fail tests) -- extend to assert exactly one
  `gate_result` row per check, correctly shaped.
- `tests/test_client_store.py:282-309` (cascade-invariant tests) -- add a `"gate_result" in
  _CLIENT_CASCADE_TABLES` regression test mirroring the `report`/`report_theme` ones.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0013_gate_result.py` -- create the `gate_result` table -- schema for AC1.
- [x] `shell/adapters/postgres/gate_result.py` -- `StoredGateResult` + `store_gate_result()` -- the
  persistence path for every Gate outcome.
- [x] `shell/runner/driver.py` -- write a `gate_result` row on both the pass branch and the
  `GateFailedError` branch, each exactly once -- AC1.
- [x] `shell/adapters/postgres/client.py` -- join `gate_result` to the cascade constant and deletion
  function -- AC1's cascade requirement.
- [x] `tests/test_gate_result_store.py` -- cover the I/O matrix, immutability, cascade join, and the
  pass-rate/regeneration-series query proof -- AC1, AC2.
- [x] `tests/test_runner_driver.py` -- extend existing Gate pass/fail tests for the new row -- AC1.
- [x] `tests/test_client_store.py` -- add the cascade-constant regression test -- AC1.

**Acceptance Criteria:**
- Given a Gate check (pass or fail), when it completes, then exactly one immutable `gate_result` row is
  persisted recording `passed`, `regeneration_count`, `vocabulary_version`, and every flagged Claim.
- Given stored `gate_result` rows, when queried directly, then first-generation pass rate
  (`regeneration_count == 0`) and regeneration count as its own series are both computable, with no new
  query function required.
- Given a Client is deleted, when `delete_client_and_derived` runs, then every `gate_result` row for
  that Client is deleted too.

## Spec Change Log

## Design Notes

Why the pass and fail writes live in two different places rather than one: `with_backoff` retries *any*
exception on a stage function, including a deterministic `GateFailedError`, up to 3 times
(`shell/runner/backoff.py`) — writing inside `_run_gate_passed` unconditionally would persist up to 3
duplicate rows for one logical failure. `drive()` already special-cases `GateFailedError` distinctly
from generic stage failure (Story 5.4's own regeneration-counter bookkeeping lives there for the same
reason), so the fail-path write joins that existing precedent instead of adding new per-stage plumbing
to the stage-function registry itself.

AC3 from `epics.md` (stored draft citations + Payload entries available for a monthly hand-sample) needs
no new production code: `ReportDraft`/`ReportPayload` rows are already retained permanently (deleted only
by the Client cascade) with citation structure intact since Story 4.6. If not already covered by an
existing test, add one proving this already-true invariant rather than new guard code — mirrors Story
5.5's own Design Notes for its AC2.

## Verification

**Commands:**
- `uv run pytest tests/test_gate_result_store.py tests/test_runner_driver.py tests/test_client_store.py -q` -- expected: all pass.
- `uv run alembic upgrade head` -- expected: `0013_gate_result` applies cleanly.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Write-path: exactly one row per Gate check, despite retries**

- Why the pass write and the fail write live in two different places -- the load-bearing design decision of this story.
  [`driver.py:547`](../../shell/runner/driver.py#L547)

- The pass write, alongside the existing `store_report(...)` call -- safe because a successful stage function is never retried.
  [`driver.py:600`](../../shell/runner/driver.py#L600)

- The fail write, inside `drive()`'s `except GateFailedError` block, before `regeneration_count` increments -- the only place a failing check is written exactly once despite `with_backoff`'s retries.
  [`driver.py:728`](../../shell/runner/driver.py#L728)

**Schema: a second, non-unique record of every Gate check**

- `StoredGateResult` -- named `Stored*` to avoid colliding with `core/types/gate.py`'s `GateResult` dataclass; `report_run_id` deliberately not unique, unlike `Report`'s.
  [`gate_result.py:43`](../../shell/adapters/postgres/gate_result.py#L43)

- `store_gate_result()` -- `regeneration_count` always comes from the caller, never read off `run` itself, since the fail-path caller must pass the pre-increment value.
  [`gate_result.py:111`](../../shell/adapters/postgres/gate_result.py#L111)

- `gate_result` table, mirroring `0011_report.py`'s shape but with a plain (non-unique) index on `report_run_id`.
  [`0013_gate_result.py:35`](../../migrations/versions/0013_gate_result.py#L35)

**Cascade: gate_result joins Client deletion**

- `_CLIENT_CASCADE_TABLES` gains `gate_result`, and `delete_client_and_derived` deletes every `gate_result` row before the owning `report_run` row.
  [`client.py:48`](../../shell/adapters/postgres/client.py#L48)

**Peripherals**

- AC2 proven directly: first-generation pass rate and regeneration count as a series, computed from stored rows with no new query function.
  [`test_gate_result_store.py:349`](../../tests/test_gate_result_store.py#L349)

- Cascade proven end to end: a Client with both a pass and an earlier fail loses every `gate_result` row.
  [`test_gate_result_store.py:313`](../../tests/test_gate_result_store.py#L313)

- Cascade-constant regression, mirroring the pattern every prior FK-bearing table's own story established.
  [`test_gate_result_store.py:305`](../../tests/test_gate_result_store.py#L305)

- The bound-exhaustion path: every failing check along the way gets its own row, none passed, before `run.failed_at` is set.
  [`test_runner_driver.py:1092`](../../tests/test_runner_driver.py#L1092)
