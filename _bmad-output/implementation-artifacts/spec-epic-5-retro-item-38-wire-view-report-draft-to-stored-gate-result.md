---
title: 'epic-5-retro-item-38 — Wire view_report_draft to the persisted StoredGateResult'
type: 'bugfix'
created: '2026-08-25'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'f79f4065c049fb6953973be2033ff84a43b6d860'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `view_report_draft` (`shell/http/routes/report_runs.py`) recomputes `run_gate()` against
`request.app.state.gate_vocabulary` -- the *currently loaded* vocabulary -- whenever `run.failed_at`
is set. Its own docstring names the gap: this can differ from what actually caused the failure "until
Story 5.6 persists the vocabulary version per run." Story 5.6 then built exactly that
(`StoredGateResult`, `shell/adapters/postgres/gate_result.py`), but never wired this route to read it.
A vocabulary edit landing between a run's terminal failure and Francesco opening its draft can show a
different violation set than what actually failed -- or none at all, misleadingly implying the report
is now clean.

**Approach:** Replace the live `run_gate(...)` call with a read of the latest `StoredGateResult` row
for `run_id`, ordered by `regeneration_count` descending -- mirroring `_run_gate_passed`'s existing
`ReportDraft.attempt.desc()` pattern. `regeneration_count` strictly increases across a run's writes by
construction, so the highest value is always the last check. No row found (a generic, non-Gate
terminal failure never wrote one; Story 5.5's own test covers this) -> empty violations, unchanged
from today.

## Boundaries & Constraints

**Always:**
- `run.failed_at is not None` still gates the branch exactly as today; a passing run's context is
  byte-for-byte unchanged.
- Query `StoredGateResult` by `report_run_id == run_id`, order by `regeneration_count` descending,
  take the first row. No row -> `violations = []`; `run` is still added to context so
  `failure_reason` renders.
- `StoredGateResult.violations` (`list[dict[str, Any]]`) needs no reshaping -- Jinja2's
  attribute-then-item lookup renders a dict the same as the `GateViolation` dataclass the template was
  written against, so `report_draft.html` is untouched.
- Drop the now-unused `run_gate` import from `shell/http/routes/report_runs.py`.

**Ask First:** None.

**Never:**
- No change to `core/gate/run.py`, `StoredGateResult`, `store_gate_result()`, or
  `shell/runner/driver.py` -- only what the view route reads changes.
- No change to `report_draft.html` or any new persistence/column.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Bound-exhausted run, `StoredGateResult` row(s) exist | `run.failed_at` set, one or more `gate_result` rows for `run_id` | 200; violations from the highest-`regeneration_count` row, not recomputed | N/A |
| Generic terminal failure, no `StoredGateResult` row | `run.failed_at` set, zero `gate_result` rows for `run_id` | 200; `failure_reason` shown, no violations list (unchanged) | N/A |
| Passing run | `run.failed_at` is `None` | 200; unchanged | N/A |
| Multiple rows + live vocabulary has since diverged | Rows at `regeneration_count` 0, 1, 2; `gate_vocabulary` reloaded/edited since | The `regeneration_count == 2` row's violations are shown, unaffected by the live vocabulary | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py:31,207-217,249-252` -- `view_report_draft`'s Gate branch: drop the
  `run_gate` import and call, add the `StoredGateResult` query.
- `shell/adapters/postgres/gate_result.py` -- `StoredGateResult`, read-only reuse.
- `shell/runner/driver.py:575-579` (`_run_gate_passed`) -- precedent for the `.desc()`-by-business-field
  ordering to mirror.
- `tests/test_http_report_runs.py:768-915` -- Story 5.5's four draft-view tests. The bound-exhausted
  test (line 787) stores no `StoredGateResult` row today -- update it to `store_gate_result(...)` real
  computed violations (via `run_gate()` + `load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)`, mirroring
  `tests/test_runner_driver.py:60,68`) before asserting. The generic-failure (line 837) and passing-run
  (line 887) tests already match the new behavior unchanged.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/report_runs.py` -- replace `run_gate(...)` with the `StoredGateResult` query
  (latest by `regeneration_count` descending, default `[]`); drop the `run_gate` import; update the
  docstring's Gate paragraph to describe the read, not the recomputation.
- [x] `tests/test_http_report_runs.py` -- update the bound-exhausted test to seed a `StoredGateResult`
  row; add one test covering multiple rows plus a diverged live vocabulary (I/O matrix row 4).

**Acceptance Criteria:**
- Given a bound-exhausted run with a persisted `StoredGateResult` row, when Francesco opens its draft
  view, then the shown violations are read from that row, not recomputed against the live vocabulary.
- Given a bound-exhausted run with no `StoredGateResult` row, when Francesco opens its draft view, then
  `failure_reason` still renders and no violations list is shown.
- Given more than one `StoredGateResult` row for a run, when the draft view renders, then the row with
  the highest `regeneration_count` is the one shown.

## Verification

**Commands:**
- `uv run pytest tests/test_http_report_runs.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**The read itself -- StoredGateResult replaces live recomputation**

- Entry point: the Gate branch no longer calls `run_gate()`; it queries the persisted row that actually recorded the failure.
  [`report_runs.py:250`](../../shell/http/routes/report_runs.py#L250)

- `.where(passed.is_(False))` added during review: makes explicit that this must always be the failing check, not merely "whatever has the highest `regeneration_count` today."
  [`report_runs.py:253`](../../shell/http/routes/report_runs.py#L253)

- Docstring rewritten to describe the read and the drift it closes, replacing the old recomputation rationale.
  [`report_runs.py:207-217`](../../shell/http/routes/report_runs.py#L207-L217)

**Tests -- proving the fix, not just the happy path**

- Updated to seed a real `StoredGateResult` row (via `run_gate()` + `load_gate_vocabulary()`) instead of relying on live recomputation.
  [`test_http_report_runs.py:792`](../../tests/test_http_report_runs.py#L792)

- New: proves ordering by `regeneration_count` (rows inserted out of order, so insertion/`uuid7` order can't coincidentally pass), cross-run isolation, and immunity to a diverged live vocabulary.
  [`test_http_report_runs.py:856`](../../tests/test_http_report_runs.py#L856)

- Docstring corrected: the empty-violations case here comes from no `StoredGateResult` row existing, not from a Gate recompute (the route no longer recomputes at all).
  [`test_http_report_runs.py:977`](../../tests/test_http_report_runs.py#L977)
