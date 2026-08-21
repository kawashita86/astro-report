---
title: 'Story 4.4 — Compute what has changed since last month'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 2
baseline_commit: '137c376b71df2df08bf24adb8129accdca2164fb'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing today tells "still holding" from "newly arising" between two months' `ReportTheme`s (Story 4.3) — without it, "nothing significant has changed" can only be guessed by the model, contradicting Epic 4's premise that continuity is a computed fact, not a judged one.

**Approach:** Add a pure `diff_themes(previous, current) -> ThemeDiff | None` (AD-14) in `core/memory/`, matching each `ThemeAspect`/`StandingRetrograde` across the two Themes by identity and classifying it as new, still-active, tightened or resolved, with a computed `nothing_significant_changed` flag.

## Boundaries & Constraints

**Always:**
- `core/types/memory.py` -- add frozen `AspectChange` (`aspect: ThemeAspect`, `status: str` -- one of `"new"`/`"still_active"`/`"tightened"`/`"resolved"`), `RetrogradeChange` (`retrograde: StandingRetrograde`, `status: str` -- one of `"new"`/`"still_active"`/`"resolved"`), and `ThemeDiff` (`aspect_changes: tuple[AspectChange, ...]`, `retrograde_changes: tuple[RetrogradeChange, ...]`, `nothing_significant_changed: bool`), mirroring the existing dataclasses' style.
- `core/memory/diff.py::diff_themes(previous: ReportTheme | None, current: ReportTheme) -> ThemeDiff | None` -- pure, model-free (AD-1): no DB read, no session, no ReportRun.
- Identity: two `ThemeAspect`s are the same element iff `(transiting_body, natal_point, aspect)` match; two `StandingRetrograde`s iff `body` matches.
- Aspect classification (matched pair present in both): `new` if `previous.orb_exit_at is not None` (checked first -- the previous month's occurrence had already fully separated, so this is a fresh pass, not a continuation, regardless of current's state); else `resolved` if `current.orb_exit_at is not None` (separates within the current month); else `tightened` if `previous.never_perfected and not current.never_perfected` (newly perfects within the current month); else `still_active`. Unmatched: absent from `previous` -> `new`; absent from `current` -> `resolved`.
- Retrograde classification: unmatched-in-`previous` -> `new`; unmatched-in-`current` -> `resolved`; matched -> `still_active`. No `tightened` state for retrogrades.
- `nothing_significant_changed` is `True` iff no `AspectChange`/`RetrogradeChange` has status other than `still_active` (an all-`still_active`-or-empty diff).
- Ordering: `aspect_changes`/`retrograde_changes` list matched-and-`new` entries in `current`'s own `dominant_aspects`/`standing_retrogrades` order, followed by `resolved`-only entries (absent from `current`) in `previous`'s own order.

**Ask First:**
- Scope: this story adds only the pure `diff_themes` function -- no `shell/runner/driver.py` wiring and no DB retrieval of a Client's previous stored `ReportTheme`. Story 4.5 already needs both raw `ReportTheme`s fetched for the Generator port (AD-3) and calls `diff_themes` there once it exists. Confirm this split, since epics.md's Story 4.4 AC ("when a Theme is derived... the comparison is not attempted") reads as if wiring belongs here.
- `ThemeLunation` is excluded from the diff entirely: every current-month Lunation is new by construction (it occurs within that specific month, never carried over), so classifying it would always yield `"new"` with no informational value. Confirm.

**Never:**
- No `shell/runner/driver.py` change, no new AD-10 stage, no new DB table, no Generator/model call, no I/O or clock in `core/memory/diff.py`.
- No special-casing for multiple `ThemeAspect`s sharing the same `(transiting_body, natal_point, aspect)` identity within one `ReportTheme`'s `dominant_aspects` (a rare same-month retrograde-loop re-entry, per `TransitAspectEvent`'s own docs -- `derive_theme` dedupes only by full equality, not by this narrower identity). Accepted as a known, deliberate limitation given how astronomically rare a same-month repeat pass is for a slow body: the dict-based identity match silently keeps one representative entry rather than raising or pairing duplicates. Not an oversight to fix in this story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First month | `previous is None` | `diff_themes` returns `None`; no comparison attempted | N/A |
| New aspect | pair in `current`, absent from `previous` | `AspectChange(status="new")` | N/A |
| Resolved aspect (gone next month) | pair in `previous`, absent from `current` | `AspectChange(status="resolved")` | N/A |
| Resolved aspect (separates this month) | pair in both, `current.orb_exit_at` set | `AspectChange(status="resolved")` | N/A |
| Tightened aspect | pair in both, `previous.never_perfected=True`, `current.never_perfected=False`, `current.orb_exit_at is None` | `AspectChange(status="tightened")` | N/A |
| Fresh pass after prior separation | pair in both, `previous.orb_exit_at` set (already separated last month) | `AspectChange(status="new")`, regardless of `current`'s own state | N/A |
| Still-active aspect | pair in both, neither resolved nor newly-perfected this month | `AspectChange(status="still_active")` | N/A |
| New / resolved / still-active retrograde | body present/absent across `previous`/`current` | matching `RetrogradeChange` status | N/A |
| Nothing significant changed | every matched element `still_active`, no new/resolved entries (including both diffs empty) | `ThemeDiff.nothing_significant_changed is True` | N/A |
| Same pair, deterministic re-run | identical `previous`/`current` passed twice | byte-identical (`==`) `ThemeDiff` both times | N/A |

</frozen-after-approval>

## Code Map

- `core/types/memory.py` -- `ReportTheme`, `ThemeAspect`, `ThemeLunation` to mirror; add `AspectChange`, `RetrogradeChange`, `ThemeDiff` here.
- `core/memory/derive.py:49` -- `_aspect_tightness_key`, the existing precedent for reasoning about `perfected_at`/`orb_exit_at` without a numeric orb-degree.
- `core/types/transits.py:22`, `:76` -- `TransitAspectEvent`/`StandingRetrograde` field docs (`orb_exit_at is None` means still open at month end; `never_perfected` is scoped to the analyzed month, not global history).
- `tests/test_derive_theme.py` -- fixture/helper conventions (`_payload`, `_slow_aspect`, `_COMPUTATION_CONFIG` from `shell/computation.py::load_computation_config()`) to mirror for constructing `ReportTheme` fixtures directly.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/memory.py` -- add `AspectChange`, `RetrogradeChange`, `ThemeDiff` frozen dataclasses -- output shape for the diff.
- [x] `core/memory/diff.py` -- `diff_themes(previous, current) -> ThemeDiff | None` per Boundaries -- the pure comparison itself.
- [x] `tests/test_diff_themes.py` -- new, covers the I/O & Edge-Case Matrix in full, including: a case with two same-identity `ThemeAspect`s within one `ReportTheme` on the `current` side, an equivalent case on the `previous` side, and a case with duplicates on both sides (accepted-limitation behavior, per the amended Never); ordering for `retrograde_changes` (mirroring the existing `aspect_changes` ordering test); `nothing_significant_changed is False` driven solely by a retrograde change; and `nothing_significant_changed is False` driven by a `"tightened"` and by a `"resolved"` aspect status (not only `"new"`).

**Acceptance Criteria:**
- Given two `ReportTheme`s for consecutive months, when `diff_themes` runs, then every `dominant_aspects`/`standing_retrogrades` element across both is classified into exactly one status, and the same pair of inputs always yields a byte-identical `ThemeDiff`.
- Given two consecutive months' Themes that differ in no meaningful element, when compared, then `nothing_significant_changed` is `True`.
- Given `previous is None` (a Client's first month), when `diff_themes` runs, then it returns `None` without attempting a comparison.

## Spec Change Log

- **Finding (review loop 1, intent_gap):** the Identity Boundary's `(transiting_body, natal_point, aspect)` match assumes at most one `ThemeAspect` per key within a single `ReportTheme`, but `derive_theme` (Story 4.3) dedupes only by full equality -- `TransitAspectEvent`'s own docs allow a same-month retrograde-loop re-entry to produce a second, distinct event sharing that narrower identity, which the first implementation's dict-based matching would have silently collapsed to one entry.
  **Amended:** added an explicit `Never` bullet accepting this as a known limitation (human confirmed: "Accept as a documented limitation" over raising or pairwise-matching duplicates) and a task nudge to add a pinning test for the accepted (silent-keep-one) behavior.
  **Known-bad state avoided:** silent, undocumented data loss for an edge case with no test coverage and no stated intent, which could have read as an oversight rather than a deliberate choice on a later re-read of this code.
  **KEEP:** everything else in Intent/Boundaries/Matrix is unchanged and confirmed working -- the classification algorithm, ordering rule, and both prior Ask First scope decisions (no driver wiring, `ThemeLunation` excluded) all held up under review and must survive re-derivation unchanged.

- **Finding (review loop 2, intent_gap):** the Aspect classification rule didn't check whether the *previous* month's occurrence had already separated (`previous.orb_exit_at is not None`) before falling through to `resolved`/`tightened`/`still_active` -- a matched pair whose previous pass had fully separated and is now reappearing (a fresh pass, plausible for a slow body stationing soon after its first orb crossing) read as a continuation instead.
  **Amended:** added a `new`-if-`previous.orb_exit_at is not None` check, evaluated first, ahead of the existing `resolved`/`tightened`/`still_active` checks (human confirmed the one-line fix over documenting it as a further accepted limitation). Added the corresponding I/O Matrix row. Folded in four trivial test-coverage additions the same review round surfaced (retrograde ordering, retrograde-only `nothing_significant_changed=False`, `tightened`/`resolved`-driven `nothing_significant_changed=False`, duplicate-identity on the `previous` side and on both sides) into the task list rather than looping back separately for them.
  **Known-bad state avoided:** a returning aspect misread as an unbroken continuation (`still_active`/`tightened`) when it was in fact a new occurrence following a full separation -- exactly the kind of judged-not-computed inaccuracy this story exists to eliminate.
  **KEEP:** the review-loop-1 amendment (accepted same-month duplicate-identity limitation) and everything else confirmed in loop 1's KEEP note remain unchanged.

## Design Notes

Classification priority, in order: `previous.orb_exit_at is not None` first (a fresh pass following a full prior separation is `new`, never a continuation, regardless of anything about `current`) -- then `current.orb_exit_at is not None` (checked before the tightening check because an aspect can both newly-perfect and separate within the same current month; separating is the more decisive "this is closing" signal, so it takes priority over "tightened") -- then the tightening check -- then `still_active` as the default. Mirrors `_aspect_tightness_key`'s own precedent of reading only `perfected_at`/`orb_exit_at`, no orb-degree, per Story 4.3.

`never_perfected`/`perfected_at` are scoped to the month they were computed in (`core/transits/aspects.py`'s docstring: "within the analyzed month"), not a durable cross-month fact -- so a pair that perfected last month and is merely still holding this month reads as `previous.never_perfected=False`, `current.never_perfected=True` (no *new* crossing this month), correctly falling through to `still_active` rather than misreading it as freshly tightening.

## Verification

**Commands:**
- `uv run pytest tests/test_diff_themes.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Classification: the aspect-diffing decision tree**

- Entry point: the four-branch priority order this whole story exists to get right -- fresh-pass-after-separation before separation before tightening before still-active.
  [`diff.py:64`](../../core/memory/diff.py#L64)

- `diff_themes` itself: returns `None` on a first month, otherwise wires the two element-family diffs into one `ThemeDiff` plus the computed `nothing_significant_changed` flag.
  [`diff.py:122`](../../core/memory/diff.py#L122)

- `_aspect_changes`: matched/new entries in current's order, then resolved-only entries in previous's order -- the ordering guarantee.
  [`diff.py:80`](../../core/memory/diff.py#L80)

**Identity matching and the accepted duplicate-identity limitation**

- `_by_aspect_identity`: a same-identity duplicate within one `ReportTheme` silently collapses to its last value at its first-seen position -- deliberate, not an oversight.
  [`diff.py:48`](../../core/memory/diff.py#L48)

- Retrograde matching mirrors the aspect matching but has no `tightened` state and no re-entry signal, by design.
  [`diff.py:103`](../../core/memory/diff.py#L103)

**Output shape**

- `AspectChange`/`RetrogradeChange`/`ThemeDiff`: the classification output, including the just-added ordering and `ThemeLunation`-exclusion notes on `ThemeDiff`'s own docstring.
  [`memory.py:88`](../../core/types/memory.py#L88)

**Tests: the two amendments this spec went through under review**

- The fresh-pass-after-prior-separation case -- the review-loop-2 finding, now pinned.
  [`test_diff_themes.py:111`](../../tests/test_diff_themes.py#L111)

- All three duplicate-identity pinning tests (current side, previous side, both sides) -- the review-loop-1 finding, now pinned.
  [`test_diff_themes.py:222`](../../tests/test_diff_themes.py#L222)

- Determinism: the same pair of Themes always yields a byte-identical `ThemeDiff`.
  [`test_diff_themes.py:334`](../../tests/test_diff_themes.py#L334)
