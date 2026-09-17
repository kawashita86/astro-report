---
title: 'Skip automatic regeneration on low-violation Gate failures'
type: 'feature'
created: '2026-09-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '8f00ed7a4c9945b0390f2f92346626c394871e44'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Gate failure naming as few as 1 violation is treated identically to one with many:
`shell/runner/driver.py`'s `except GateFailedError` block always rewinds `run.stage` to
`payload_ready` for another paid Generator call, up to `_MAX_REGENERATIONS`, before Francesco ever
gets a chance to Accetta or Modifica e ricontrolla the flagged sentence — the review surface is gated
behind `run.failed_at is not None`.

**Approach:** Add a plain module constant `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION = 2` in
`driver.py`. In the existing `except GateFailedError` block, before the bound-check/rewind logic,
branch on `len(error.violations) < _MIN_VIOLATIONS_FOR_AUTO_REGENERATION`: if true, set
`run.failed_at`/`run.failure_reason` on that same failing check immediately — without incrementing
`regeneration_count` or rewinding `run.stage` — reusing Stories 5.7/5.8's already-shipped review UI
and routes untouched. Apply the five approved doc diffs (PRD FR-21, ARCHITECTURE-SPINE AD-10, and
epics.md's AD-10 mirror + Stories 5.4/5.5 ACs) from the approved sprint change proposal.

## Boundaries & Constraints

**Always:**
- `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION` is a plain, non-runtime-configurable module constant,
  matching `_MAX_REGENERATIONS`'s own established precedent in this file.
- The new branch sits inside the existing `except GateFailedError` block, after the existing
  `store_gate_result(...)` call (unchanged, still fires first) and before `run.regeneration_count += 1`.
- Applies on every failing check in the run's current cycle, not only the first attempt.
- Apply all five doc diffs verbatim from
  `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-17.md` §4.

**Ask First:** None — approach and all five diffs were reviewed and approved verbatim by Francesco.

**Never:** Do not make the threshold runtime-configurable. Do not touch
`_current_cycle_gate_failure`, its correlation window, `report_runs.py`'s routes, or Stories
5.7/5.8's own code. Do not touch the automatic-pass, accept, or hand-correct paths.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Below threshold | `GateFailedError` with 1 violation | `run.failed_at` set immediately on that check; `run.stage` not rewound; `regeneration_count` unchanged | N/A |
| At threshold (boundary) | `GateFailedError` with exactly 2 violations | today's rewind-to-`payload_ready` behavior, `regeneration_count` incremented — NOT skipped | N/A |
| Above threshold, bound not exceeded | `GateFailedError` with 3+ violations, count <= `_MAX_REGENERATIONS` | unchanged rewind behavior | N/A |
| Regression: review surface via new trigger | `run.failed_at` set via the new low-violation path | draft view renders Gate-failure panel, Accetta, Modifica e ricontrolla identically to a bound-exhausted run | N/A |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py:188` -- after `_MAX_REGENERATIONS = 3`, add
  `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION = 2` with a Design-Notes-style comment matching this file's
  convention (see `_MAX_REGENERATIONS`'s own comment just above, lines 179-188).
- `shell/runner/driver.py:790-805` -- `advance()`'s docstring already documents the
  `except GateFailedError` branch in prose; extend it with the new low-violation short-circuit
  (`Amended 2026-09-17, correct-course`), matching the file's Story-numbered doc convention.
- `shell/runner/driver.py:906-966` -- the `except GateFailedError` block. New branch goes between the
  `store_gate_result(...)` try/except (ends ~line 942) and `run.regeneration_count += 1` (line 943).
- `shell/http/routes/report_runs.py:344-380` -- `_current_cycle_gate_failure` (read-only reference,
  no change): correlates a `StoredGateResult` to `run.failed_at` via `_GATE_RESULT_CORRELATION_WINDOW`
  (2s). The new branch's `store_gate_result` call and `failed_at` write land in the same commit —
  confirmed no change needed here.
- `tests/test_runner_driver.py:929` -- `_a_violating_generated_draft()` already produces exactly 1
  violation (`"Marte"`, `empty_citation`) — reuse directly for the below-threshold test. Mirror
  `test_gate_passed_exhausting_the_regeneration_bound_marks_the_run_terminally_failed` (line 1230) for
  test shape, and the `_advance`/`_FakeGenerator` helpers (lines 150-213) for driving stages. For the
  at-threshold test, build a 2-violation draft: two Claim sentences citing nothing, e.g. `"Marte"` in
  `energia_generale` and `"Venere"` in `amore` (both closed-vocabulary planet tokens, see
  `core/gate/vocabulary.it.json`).
- `tests/test_http_report_runs.py:1038-1134` -- `_a_bound_exhausted_run()` and
  `test_getting_the_draft_for_a_bound_exhausted_run_shows_gate_violations_and_failure_reason` are the
  template for the new regression test: build a run with `failed_at` set via the new path
  (`regeneration_count=0`, `stage="draft_ready"`), persist a real gate_result via
  `run_gate()`/`store_gate_result()`, assert the draft view renders the same Gate-failure panel,
  Accetta, and Modifica e ricontrolla markup as the bound-exhausted case.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:589-606` (FR-21),
  `_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md:185-207`
  (AD-10), `_bmad-output/planning-artifacts/epics.md:169` (AD-10 mirror), `epics.md:1518-1538` (Story
  5.4), `epics.md:1540-1565` (Story 5.5) -- current file content confirmed to still match the sprint
  change proposal's diff context verbatim (only line numbers drifted slightly).

## Tasks & Acceptance

**Execution:**
- [x] `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md` -- apply FR-21 diff
  verbatim (sprint change proposal §4) -- carve-out consequence + amendment note
- [x] `_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md`
  -- apply AD-10 diff verbatim -- documents the new immediate-surface trigger
- [x] `_bmad-output/planning-artifacts/epics.md` -- apply AD-10 mirror line (~169), Story 5.4 AC
  (~1518-1538), Story 5.5 AC (~1540-1565) diffs verbatim
- [x] `shell/runner/driver.py` -- add `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION = 2` constant, the new
  branch in `except GateFailedError`, and the docstring update -- implements the skip-regeneration
  behavior
- [x] `tests/test_runner_driver.py` -- add: (a) a 1-violation failure sets `failed_at` immediately, no
  rewind, `regeneration_count` unchanged; (b) an at-threshold (2-violation) failure keeps today's
  rewind behavior unchanged (boundary case)
- [x] `tests/test_http_report_runs.py` -- add a regression test: a run whose `failed_at` was set via
  the new low-violation path still renders the Gate-failure panel, Accetta, and Modifica e ricontrolla
  identically to a bound-exhausted one
- [x] Code-review follow-up (documentation/comment staleness + one test-coverage gap, no behavior
  change): `core/errors.py`'s `GateFailedError` docstring, `shell/adapters/postgres/report_run.py`'s
  `regeneration_count` comment, and `shell/http/routes/report_runs.py`'s
  `_GATE_RESULT_CORRELATION_WINDOW` docstring updated to describe the new low-violation branch;
  `tests/test_runner_driver.py` gained a test proving the short-circuit still applies correctly after a
  prior regeneration cycle (`regeneration_count` stays at its already-incremented value)

**Acceptance Criteria:**
- Given a `GateFailedError` with 1 violation on any attempt in the run's current cycle, when
  `advance()` catches it, then `run.failed_at` is set on that same check, `run.stage` is not rewound,
  and `run.regeneration_count` is unchanged.
- Given a `GateFailedError` with violations >= `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION` and the bound
  not yet exceeded, when `advance()` catches it, then today's rewind-and-increment behavior is
  unchanged.
- Given a run whose `failed_at` was set via the new low-violation path, when Francesco opens its
  draft view, then the Gate-failure panel, Accetta, and Modifica e ricontrolla cards render exactly as
  for a bound-exhausted run.
- Given `uv run pytest tests/test_runner_driver.py tests/test_http_report_runs.py -q` and
  `uv run ruff check .`, when run after the change, then both pass clean.

## Spec Change Log

- **Implementation discovery**: six existing `tests/test_runner_driver.py` tests drove the
  rewind/regeneration mechanics using `_a_violating_generated_draft()` (1 violation) as their fixture.
  Under the new branch, a 1-violation `GateFailedError` no longer rewinds, so those six tests would have
  regressed. Fixed by adding a second fixture, `_a_two_violation_generated_draft()` (`"Marte"` in
  `energia_generale`, `"Venere"` in `amore` -- both empty-citation, exactly at
  `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION`), and repointing those six tests at it so they keep exercising
  the pre-existing regeneration behavior unchanged. `_a_violating_generated_draft()` itself is untouched
  and still used both by the new below-threshold test and by
  `test_run_gate_passed_raises_gate_failed_error_on_a_failing_gate_result` (which calls
  `_run_gate_passed` directly, bypassing `advance()`'s except block, so it was never affected). No
  change to this spec's frozen Intent/Boundaries/Matrix was needed -- this was purely fixture upkeep to
  satisfy the Acceptance Criteria's "both pass clean" requirement.
- **Pre-existing, unrelated failure**: `tests/test_http_report_runs.py::test_the_draft_page_offers_modifica_e_ricontrolla_prefilled_with_the_open_violations_sentence`
  fails identically on the untouched `baseline_commit` (verified via `git stash`) -- not caused by this
  change, not fixed by it either (out of this spec's scope).
- **Review round 1** (coordinator-relayed patch-worthy findings, no behavior/scope change): (1)
  `core/errors.py`'s `GateFailedError` class docstring still unconditionally described the pre-change
  always-rewind behavior -- amended to describe the new low-violation immediate-fail branch, mirroring
  `advance()`'s own docstring. (2) `shell/adapters/postgres/report_run.py`'s `regeneration_count` field
  comment claimed it is "incremented on every `GateFailedError`" -- now false; fixed to note the
  low-violation exception. (3) `tests/test_runner_driver.py` gained
  `test_gate_passed_low_violation_short_circuit_applies_after_a_prior_regeneration`: drives one full
  rewind-and-regenerate cycle (2-violation failure, `regeneration_count` reaches 1 the ordinary way),
  then a second `GateFailedError` on that same run comes back with only 1 violation -- proves the
  short-circuit still fires correctly (`failed_at` set, no further rewind) and, the detail singled out
  by name in AD-10's amendment text ("applies on every failing check ... not only the first"), that
  `regeneration_count` stays at 1 rather than bumping to 2. No prior test drove this already-regenerated
  case. (4) `shell/http/routes/report_runs.py`'s `_GATE_RESULT_CORRELATION_WINDOW` docstring extended
  to name the low-violation immediate-fail path as a third terminal-failure trigger landing inside the
  same correlation window, for the same same-`advance()`-call reason as the other two -- constant value,
  function logic and routes untouched. Re-verified `uv run pytest
  tests/test_runner_driver.py tests/test_http_report_runs.py -q` (same single pre-existing, unrelated
  failure noted above) and `uv run ruff check .` (clean) after applying all four.

## Design Notes

The new branch's shape (insert immediately after the existing `store_gate_result(...)` try/except,
before `run.regeneration_count += 1`):

```python
if len(error.violations) < _MIN_VIOLATIONS_FOR_AUTO_REGENERATION:
    run.updated_at = datetime.now(UTC)
    run.failed_at = run.updated_at
    run.failure_reason = (
        f"too few violations ({len(error.violations)}) to warrant automatic "
        f"regeneration: {error}"
    )
    _logger.error(
        "report run marked terminally failed: too few violations to warrant "
        "automatic regeneration: %s",
        run.id,
    )
    session.add(run)
    session.commit()
    return run
```

`run.stage` is deliberately left untouched (it is still whatever it was on entry — `draft_ready`),
exactly mirroring how the bound-exhausted branch leaves it un-rewound.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_driver.py tests/test_http_report_runs.py -q` -- expected: all
  tests pass, including the new coverage
- `uv run ruff check .` -- expected: clean

## Suggested Review Order

**The new short-circuit branch**

- Entry point: the new low-violation branch itself — sets `failed_at` immediately, leaves
  `regeneration_count`/`stage` untouched, falls through to the unchanged rewind logic otherwise.
  [`driver.py:959`](../../shell/runner/driver.py#L959)

- The new threshold constant, deliberately a fixed value (not env-configurable), mirroring
  `_MAX_REGENERATIONS`'s own precedent just above it.
  [`driver.py:197`](../../shell/runner/driver.py#L197)

- `advance()`'s own docstring, amended to describe the new branch before the pre-existing
  rewind/bound-exhaustion prose.
  [`driver.py:800`](../../shell/runner/driver.py#L800)

**Why no other code needed to change**

- `GateFailedError`'s docstring amended to match — confirms the exception's own contract now
  documents both outcomes.
  [`errors.py:165`](../../core/errors.py#L165)

- `regeneration_count`'s field comment amended — confirms the column's invariant ("incremented on
  every regenerating `GateFailedError`") still holds once qualified.
  [`report_run.py:105`](../../shell/adapters/postgres/report_run.py#L105)

- `_GATE_RESULT_CORRELATION_WINDOW`'s docstring extended to name the new path as a third case that
  lands inside the window — the review-surface routes needed zero code changes.
  [`report_runs.py:319`](../../shell/http/routes/report_runs.py#L319)

**Planning docs — the five approved diffs**

- FR-21's new carve-out consequence + amendment note.
  [`prd.md:596`](../planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md#L596)

- AD-10's new paragraph documenting the immediate-surface trigger.
  [`ARCHITECTURE-SPINE.md:208`](../planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md#L208)

- AD-10's condensed mirror line in the epics doc, same amendment appended.
  [`epics.md:169`](../planning-artifacts/epics.md#L169)

- Story 5.4's new AC: the skip-regeneration behavior stated as Given/When/Then.
  [`epics.md:1540`](../planning-artifacts/epics.md#L1540)

- Story 5.5's AC broadened to cover a Report shown via either trigger.
  [`epics.md:1576`](../planning-artifacts/epics.md#L1576)

**Tests**

- Below-threshold: 1 violation short-circuits immediately, no rewind, count unchanged.
  [`test_runner_driver.py:1318`](../../tests/test_runner_driver.py#L1318)

- At-threshold boundary: exactly 2 violations still rewinds and regenerates as before.
  [`test_runner_driver.py:1365`](../../tests/test_runner_driver.py#L1365)

- Applies after a prior regeneration, not only on the first attempt — the detail the architecture
  doc calls out by name.
  [`test_runner_driver.py:1401`](../../tests/test_runner_driver.py#L1401)

- New 2-violation fixture, exactly at the threshold, used to keep six pre-existing tests exercising
  the unchanged rewind mechanics.
  [`test_runner_driver.py:946`](../../tests/test_runner_driver.py#L946)

- Regression: the draft view renders the Gate-failure panel, Accetta, and Modifica e ricontrolla
  identically whether `failed_at` came from this new path or bound exhaustion.
  [`test_http_report_runs.py:1167`](../../tests/test_http_report_runs.py#L1167)

- Fixture for that regression test, mirroring `_a_bound_exhausted_run`'s own shape.
  [`test_http_report_runs.py:1141`](../../tests/test_http_report_runs.py#L1141)
