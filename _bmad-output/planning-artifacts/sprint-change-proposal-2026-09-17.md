# Sprint Change Proposal — 2026-09-17

**Trigger:** Production behavior review (live report-generation runs on Render), surfaced during a
`bmad-help` conversation with Francesco, root-caused against Epic 5's Groundedness Gate stories.

**Mode:** Incremental — each edit proposal below was reviewed and approved individually.

---

## 1. Issue Summary

A Report whose draft fails the Groundedness Gate with only 1 violation is treated identically, today,
to one that fails with many: `shell/runner/driver.py`'s `except GateFailedError` block always rewinds
`run.stage` to `payload_ready` for another paid Generator call, for every failing check up to
`_MAX_REGENERATIONS` (3) — regardless of violation count. `run.failed_at` is only set once that bound
is *exceeded*, and the entire human-review surface built by Stories 5.7 (Accetta) and 5.8 (Modifica e
ricontrolla) is gated behind `run.failed_at is not None` (`shell/http/routes/report_runs.py:1339`,
`_current_cycle_gate_failure` at `:375`).

Consequence observed in production (Render logs, run `01a0aeb8-0989-7524-b9b8-7c520ce59bb6`,
2026-09-17 08:49–10:07 UTC): a run that failed the Gate with as few as 1 violation still burned
multiple automatic regeneration cycles — each one a paid Gemini call — before Francesco ever had a
chance to see, accept, or hand-correct the flagged sentence. Compounding this, the deployment runs in
`REPORT_RUN_MODE=poll` (the default), so each regeneration attempt only fires on a live browser poll;
with the tab backgrounded, `document.hidden` gates every poll tick (`shell/http/static/shell.js:555`),
producing multi-minute real-world gaps between attempts. (That second issue — polling starving when
the tab is hidden — was addressed separately: Francesco has already switched the Render service to
`REPORT_RUN_MODE=background`, which is out of scope for this proposal.)

Francesco's request: when a failing check names very few violations, skip the automatic regeneration
and route straight to the existing draft-review page, so he can Accetta or Modifica e ricontrolla the
single issue immediately — sparing the wait and the Generator spend a full regeneration cycle costs
for what is often a one-sentence problem.

---

## 2. Impact Analysis

### Epic Impact

- **Epic 5** (Generation & Groundedness Gate) — already `done`. This is a same-shape amendment to its
  frozen intent as the 2026-09-02 correct-course that added Stories 5.7/5.8 — not a reopening of scope,
  a refinement of an already-shipped mechanism's trigger condition.
- No new epic needed. No epic obsoleted. No resequencing — every downstream epic (6–9) only ever
  consumes the `gate_passed` stage as an opaque done-state and is indifferent to which of the three
  existing routes (automatic pass / accepted exceptions / hand-corrected pass) or the new immediate-
  surface trigger reached it.

### Artifact Conflicts

| Artifact | Location | Conflict |
|---|---|---|
| PRD | `prd.md:589-606`, FR-21 | States regeneration always happens first, surfacing only "on persistent failure" (bound exhaustion). Needs a carve-out consequence + amendment note. |
| Architecture | `ARCHITECTURE-SPINE.md:185-201`, AD-10 | Already amended once (2026-09-02) for the 5.7/5.8 routes; needs a further sentence documenting the new immediate-surface trigger and that it leaves `regeneration_count` untouched, same as the reviewed-exception routes. |
| Epics | `epics.md:169` (condensed AD-10 mirror), `:1518-1538` (Story 5.4 AC), `:1540-1565` (Story 5.5 AC) | Story 5.4's AC states regeneration is unconditional up to the bound; Story 5.5's AC gates the review-shown state on "exhausted its regeneration bound" only. Both need broadening. |
| UX | `EXPERIENCE.md`/`DESIGN.md` (Story 9.5) | **No conflict.** The Gate-failure panel, Accetta form, and Modifica e ricontrolla disclosure are already agnostic to *why* `run.failed_at` was set — nothing visual changes, only the timing of when it fires. |
| Deployment / CI / IaC | — | None. `REPORT_RUN_MODE` is unrelated to this change and already handled by Francesco directly. |

### Technical Impact (for implementation handoff)

- New module constant `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION = 2` in `shell/runner/driver.py`, beside
  `_MAX_REGENERATIONS`/`_MAX_STAGE_FAILURES` — a plain, non-runtime-configurable constant, matching
  this file's own established precedent (Story 5.4's Design Notes explicitly reject a runtime-editable
  bound here).
- In the `except GateFailedError` block: before the existing bound-check/rewind logic, branch on
  `len(error.violations) < _MIN_VIOLATIONS_FOR_AUTO_REGENERATION`. If true: set `run.failed_at =
  run.updated_at` and a distinct `run.failure_reason` (e.g. naming "too few violations to warrant
  automatic regeneration") on that same failing check, **without** incrementing
  `run.regeneration_count` and **without** rewinding `run.stage` — mirrors the "never touches
  `regeneration_count`" precedent Story 5.8's hand-correction route already set. The existing
  `store_gate_result(...)` write immediately above this branch is unchanged and still fires first, so
  `_current_cycle_gate_failure`'s existing correlation-window logic (`report_runs.py:333`) needs no
  change — the `StoredGateResult` row and `failed_at` are still written in the same commit.
- Applies on **every** failing check in the run's current cycle, not only the first (per Francesco's
  decision) — a regeneration already in progress that happens to converge to a single remaining
  violation is surfaced immediately rather than spending its next attempt too.
- No changes needed to `report_runs.py`'s routes, `report_draft.html`, `report_run_poll.html`, or
  Stories 5.7/5.8's own code — the review surface they built is reached the same way regardless of
  which condition set `failed_at`.
- Tests: `tests/test_runner_driver.py` — a `GateFailedError` with 1 violation sets `failed_at`
  immediately without rewinding to `payload_ready`, `regeneration_count` unchanged; a `GateFailedError`
  at/above the threshold keeps today's rewind behavior; a boundary case at exactly the threshold value.
  `tests/test_http_report_runs.py` — a run whose `failed_at` was set via this new path still renders
  the Gate-failure panel, Accetta, and Modifica e ricontrolla identically to a bound-exhausted one
  (regression coverage, since the UI logic is unchanged but was never exercised via this trigger).

---

## 3. Recommended Approach

**Option 1 — Direct Adjustment.** Modify Stories 5.4 and 5.5's acceptance criteria plus FR-21 and
AD-10's text; implement as a single new conditional in `driver.py`'s existing except-block. No new
epic, no rollback, no MVP scope change.

- **Effort:** Low — one file's stage-transition logic, fully reusing already-shipped, already-tested UI
  and routes (Stories 5.7/5.8).
- **Risk:** Low — additive branch in a well-isolated except-block; does not touch the automatic-pass,
  accept, or hand-correct paths at all.

Rollback (Option 2) is not viable — there is nothing completed to revert; this is purely additive.
MVP scope review (Option 3) does not apply — this refines FR-21's trigger condition, it does not change
what "an exportable Report" means or reduce/expand the MVP.

---

## 4. Detailed Change Proposals

### PRD — `prd.md:589-606`, FR-21

```diff
 A Report failing the Groundedness Gate is regenerated a bounded number of times; persistent failure is
 surfaced.

 **Consequences (testable):**
 - Regeneration is automatic and bounded.
+- A failing check naming too few violations to warrant spending a regeneration on (a configured
+  ceiling) skips automatic regeneration entirely and is surfaced immediately instead.
 - On persistent failure Francesco is shown the Report, the failing Claims, and the Payload entries they
   contradict — never a silent discard.
 - On persistent failure Francesco may also, per violation and only after reviewing it: **accept** it
   so the Report can complete despite it — visibly flagged wherever the Report is later shown, and
   excluded from SM-5's first-generation pass rate — or **hand-correct** the one flagged sentence and
   re-run the Gate check alone, without a full regeneration.
 - A Report that has not passed the Gate, been closed by accepted exceptions, or been hand-corrected to
   a genuine pass, cannot be exported.

 *(Amended 2026-09-02, correct-course: adds the accept and hand-correct recovery paths alongside
 automatic regeneration.)*
+*(Amended 2026-09-17, correct-course: a low-violation failure is surfaced immediately rather than
+always spending an automatic regeneration on it first — the accept/hand-correct paths above are now
+reachable from either trigger, not only from bound exhaustion.)*
```

### Architecture — `ARCHITECTURE-SPINE.md:185-201`, AD-10

```diff
   never bounded by it. Only the first route is a
   "regeneration" in this rule's original sense; the other two are reviewed, human-closed exceptions,
   and a `REPORT` row produced by the third route records how many violations were accepted so it is
   never indistinguishable from a clean pass. Reaching `exported` happens once; each subsequent export
   writes an `EXPORT_RECORD` row rather than moving the stage.
+  **(Amended 2026-09-17, correct-course):** a `GateFailedError` whose violation count is below a
+  configured ceiling (`_MIN_VIOLATIONS_FOR_AUTO_REGENERATION`, `shell/runner/driver.py`) never rewinds
+  to `payload_ready` at all — `run.failed_at` is set on that same failing check, and `regeneration_count`
+  is left untouched, exactly as the review-closed routes above leave it. This applies on every failing
+  check for the run's current cycle, not only the first — a regeneration in progress that happens to
+  converge to a single remaining violation is surfaced rather than spending its next attempt too.
```

### Epics — `epics.md:169`, condensed AD-10 mirror

Same sentence appended after the existing 2026-09-02 amendment note in that line.

### Epics — `epics.md:1518-1538`, Story 5.4

```diff
 **Acceptance Criteria:**

 **Given** a Report failing the Gate
 **When** regeneration triggers
 **Then** it is automatic and bounded by a configured limit
 **And** the whole Report is regenerated, never a single failing Section
 **And** the regeneration count for the run is incremented

 **Given** a regeneration
 **When** it runs
 **Then** it re-runs from the same stored Payload, so the astronomy cannot change between attempts

 **Given** the bound being reached
 **When** the last attempt still fails
 **Then** the run stops and the Report is surfaced rather than discarded
+
+**Given** a Report failing the Gate whose violation count is below a configured low-violation ceiling
+**When** the failure is evaluated
+**Then** automatic regeneration is skipped for that failure — the run is surfaced for review
+immediately (Story 5.5/5.7/5.8) — and the regeneration count is left unchanged, since none was spent
+**And** this applies to any failing check in the run's current cycle, not only the first
+
+*(Amended 2026-09-17, correct-course.)*
```

### Epics — `epics.md:1540-1565`, Story 5.5

```diff
 **Acceptance Criteria:**

-**Given** a Report that has exhausted its regeneration bound
+**Given** a Report that has exhausted its regeneration bound, or whose current failing check was
+surfaced immediately for having too few violations to warrant regeneration (Story 5.4 amendment)
 **When** Francesco opens it
 **Then** he sees the Report text, each failing Claim, and the Payload entries each Claim contradicts or is missing from

 **Given** such a Report
 **When** it is handled
 **Then** it is never silently discarded

 **Given** such a Report
 **When** export is attempted
 **Then** it is refused, and the reason is stated

-**Given** a Report that has exhausted its regeneration bound and is shown with its failing Claims
+**Given** a Report shown this way — by bound exhaustion or immediate low-violation surfacing — with
+its failing Claims
 **When** Francesco reviews each one
 **Then** he can, per violation, accept it after review (Story 5.7) or correct its sentence and
 re-check the Gate alone (Story 5.8) — both additional to, never a replacement for, Rigenera

-*(Amended 2026-09-02, correct-course.)*
+*(Amended 2026-09-02, correct-course.)*
+*(Amended 2026-09-17, correct-course.)*
```

All five diffs above approved by Francesco as-is on 2026-09-17.

---

## 5. Implementation Handoff

**Scope classification: Minor** — direct implementation by the Developer agent, no backlog
reorganization and no PM/Architect replan needed.

**Route to:** `bmad-agent-dev` (Amelia) via `bmad-build`, following the same precedent Stories 5.7/5.8
themselves were implemented under — spec text and code land together in one story pass.

**Deliverables for that pass:**
1. Apply the five doc diffs above verbatim to `prd.md`, `ARCHITECTURE-SPINE.md`, and `epics.md`
   (2 locations).
2. Implement `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION` and the new branch in
   `shell/runner/driver.py`'s `except GateFailedError` block, per the Technical Impact section above.
3. Add the test coverage listed under Technical Impact.
4. Run `uv run pytest tests/test_runner_driver.py tests/test_http_report_runs.py -q` and
   `uv run ruff check .` clean.

**Success criteria:** a Gate failure with exactly 1 violation, on any attempt in the run's current
cycle, sets `run.failed_at` on that same check (no rewind to `payload_ready`, `regeneration_count`
unchanged) and the draft page immediately shows the Accetta / Modifica e ricontrolla cards for it — no
new Generator call spent. A failure with 2 or more violations behaves exactly as today, unchanged.

---

*Approved by Francesco, 2026-09-17.*
