---
title: '10.5 Regenerate only what the Gate rejected'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: 'a8e2e2acaa88b78ef0895ee9df71fd6a8bac55f8'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Gate rejection (automatic regeneration or Rigenera) opens a *new full* draft attempt of eight fresh `pending` rows, so fixing one bad Section rewrites the whole report (~one more full generation).

**Approach:** The new attempt carries every Section the violations did not name forward as `complete` rows, resets only the named Sections to `pending` (plus Consiglio finale whenever any of 1–7 is reset), and the driver writes just those. Each `StoredGateResult` records the draft attempt it checked.

## Boundaries & Constraints

**Always:** Forward-only migration `0026` adds nullable `gate_result.draft_attempt` (the `ReportDraft.attempt` that check examined; NULL on rows older than this story). The carry-forward source is the latest `ReportDraft` (never section rows), so legacy runs and hand-corrected drafts work. Deciding which ordinals reset is a pure function in `core/draft_state.py`; no violation naming a known Section means a full attempt. `regeneration_count`, `_MAX_REGENERATIONS`, `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION` and the failure/retry semantics are untouched. Carried rows have `attempts=0`; Consiglio finale sees all seven others as `written`. The hand-correct route also writes the corrected attempt's eight `complete` rows.

**Ask First:** Any change to `advance()`'s constants or to `ReportDraft`/`Report` schema.

**Never:** Touch Gate logic, accept path, export gate or `ReportDraft` immutability. No new thread/executor site. No env var. Do not build the progressive UI (10.6). Do not edit applied migrations.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Single Section | Gate failure naming only `amore` | New attempt: `amore` + `consiglio_finale` pending, six others complete (copied) | N/A |
| Closing only | Violations name only `consiglio_finale` | Only ordinal 8 pending | N/A |
| Several | Violations in 2 and 5 | 2, 5, 8 pending | N/A |
| First attempt | No prior `ReportDraft` | All eight pending (as today) | N/A |
| Legacy gate row | Failing result with `draft_attempt` NULL or not the latest draft's | Full attempt, all eight pending | N/A |
| Unknown section | Violation `section` matches no Section name | Full attempt | N/A |
| After hand-correction | Rigenera on a corrected draft | Rows copied from the corrected draft; only still-violating Sections reset | N/A |
| Resume | Attempt rows already exist | `open_draft_attempt` changes nothing | N/A |
| Attribution | Any Gate check | `StoredGateResult.draft_attempt` = attempt of the draft checked | N/A |

</frozen-after-approval>

## Code Map

- `core/draft_state.py` -- add pure `regeneration_ordinals(violation_sections)`: named ordinals, plus `CLOSING_ORDINAL` if any < 8, full range if none resolve.
- `shell/adapters/postgres/report_draft_section.py::open_section_rows` -- gain `carried: Mapping[int, tuple[Sentence, ...]]` (complete rows with sentences; others pending).
- `shell/runner/advance.py::open_draft_attempt` (l.549) -- compute `carried` from latest `ReportDraft` + its failing gate result; `_run_gate_passed` (l.683) and the `GateFailedError` branch (l.938) pass `draft_attempt`.
- `shell/adapters/postgres/gate_result.py` -- `draft_attempt: int | None` column; `store_gate_result(..., draft_attempt=None)`.
- `migrations/versions/0026_gate_result_draft_attempt.py` -- new, forward-only (model on `0025`), `downgrade()` raises.
- `shell/http/routes/report_runs.py:1019-1051` (`correct_gate_violation`) -- write complete rows for the corrected draft; pass `draft_attempt` to `store_gate_result`.
- `shell/runner/driver.py::_draft_step` -- already writes only claimable rows; read-only reference.
- Tests: `tests/test_draft_state.py`, `test_report_draft_section_store.py`, `test_runner_advance.py`, `test_run_driver.py`, `test_gate_result_store.py`, `test_http_report_runs.py`; Postgres check `tests/test_report_draft_section_on_postgres.py` (needs `MIGRATION_TEST_DATABASE_URL`, unset locally).

## Tasks & Acceptance

**Execution:**
- [x] `core/draft_state.py` -- `regeneration_ordinals` -- pure, typed
- [x] `migrations/versions/0026_gate_result_draft_attempt.py` + `gate_result.py` -- column and `store_gate_result` param
- [x] `report_draft_section.py`, `advance.py` -- carry-forward in `open_draft_attempt`; pass `draft_attempt` at both gate writes
- [x] `routes/report_runs.py` -- hand-correct writes rows and `draft_attempt`
- [x] tests per matrix row (driver test: only reset Sections hit the generator; full cycle reaches `gate_passed`), forward-only/migration-chain tests, Postgres check
- [x] `AGENTS.md`/docstrings -- amend 10.4's "new full attempt" wording in `open_draft_attempt` and `advance()`

**Acceptance Criteria:**
- Given a Gate failure in Amore alone, when the run regenerates, then the generator is called only for Amore and Consiglio finale and the run still reaches `gate_passed` or regenerates again with `regeneration_count` counted as before.
- Given the accept and hand-correct paths, when used, then they behave as before and a hand-correction updates that Section's row.
- Given `uv run pytest` and `uv run ruff check . && uv run ruff format --check .`, then all pass.

## Spec Change Log

## Design Notes

Why a `draft_attempt` column rather than inferring from `created_at`: the AC makes the attempt↔result link a stored fact, and it lets regeneration refuse a stale or legacy result (full attempt) instead of resetting the wrong Sections. A plain integer, not an FK, mirrors `ReportDraft`'s `(report_run_id, attempt)` coordinate and needs no cascade ordering.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `MIGRATION_TEST_DATABASE_URL=… uv run pytest tests/*_on_postgres.py` -- expected: pass (run against throwaway Postgres before pushing the migration)

## Suggested Review Order

**The rule (entry point)**

- Pure: which Sections a Gate rejection resets, Consiglio finale included.
  [`draft_state.py:112`](../../core/draft_state.py#L112)

- New attempt copies forward what the Gate did not name; untargetable means full.
  [`advance.py:549`](../../shell/runner/advance.py#L549)
  [`advance.py:590`](../../shell/runner/advance.py#L590)

**Attribution and hand-correction**

- Each Gate result records the draft attempt it checked.
  [`gate_result.py:90`](../../shell/adapters/postgres/gate_result.py#L90)
  [`0026_gate_result_draft_attempt.py`](../../migrations/versions/0026_gate_result_draft_attempt.py)

- Failure path records the newest draft's attempt.
  [`advance.py:999`](../../shell/runner/advance.py#L999)

- Hand-correction stores the corrected attempt's eight complete rows.
  [`report_runs.py:1027`](../../shell/http/routes/report_runs.py#L1027)

**Row opening**

- Carried ordinals open `complete`, the rest `pending`.
  [`report_draft_section.py:115`](../../shell/adapters/postgres/report_draft_section.py#L115)

**Tests**

- Driver: only reset Sections hit the generator.
  [`test_run_driver.py`](../../tests/test_run_driver.py)
  [`test_report_draft_section_store.py`](../../tests/test_report_draft_section_store.py)
  [`test_draft_state.py`](../../tests/test_draft_state.py)
