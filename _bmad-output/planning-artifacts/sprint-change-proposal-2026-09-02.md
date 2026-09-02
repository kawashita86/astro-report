---
title: "Sprint Change Proposal: astro-report"
status: approved
created: 2026-09-02
trigger: "Accept a Gate violation after review, or hand-correct a sentence and re-check the Gate alone"
---

# Sprint Change Proposal — astro-report

**Date:** 2026-09-02
**Prepared by:** Amelia (Developer agent), via `/bmad-correct-course`
**Mode:** Incremental (full batch of interlocking edits reviewed and approved in one pass — see §6)

---

## 1. Issue Summary

**Problem statement.** The "Verifica di fondatezza" (Groundedness Gate) stage of a report run —
the second-to-last of the six-node stage track (Story 9.5) — today offers exactly one recovery
action when a generated draft fails the Gate: **Rigenera**, which discards the whole draft and pays
for a brand-new Generator call. Francesco can see each violation (kind, Sezione, the offending
sentence, the detail, the cited Payload entries) but cannot act on any single one of them. Two
capabilities are missing:

1. **Accept a violation after review** — when Francesco judges a flagged sentence to be fine despite
   the Gate's objection, there is no way to let the Report complete; his only option is to keep
   re-rolling the whole draft and hope the Generator avoids that phrasing.
2. **Hand-correct a violated sentence and re-check only the Gate** — when the fix is an obvious
   one-sentence wording change, there is no way to make it without discarding the other seven
   Sections and spending another paid Generator call.

**How this was discovered.** Francesco described both gaps directly against the current report-run
review flow: "if some validation rules are broken by the ai prompt generation, the page shows the
issues that affect the report... I would like to allow the user... to accept a violation... and to
manually change the text... and then resubmit only the validation." The current Rigenera button and
its existing behavior are to remain exactly as they are.

**Evidence.**
- `shell/http/templates/report_draft.html:7-31` — the Gate-failure panel renders one card per
  violation with no action beyond the page-level Rigenera form.
- `shell/http/routes/report_runs.py:374-423` (`regenerate_report_run`) — the only recovery route
  today; rewinds the whole run to `payload_ready` for a full new Generator call.
- `core/types/gate.py:73-90` (`GateResult`) — `violations` is empty **iff** `passed` is `True`; there
  is no vocabulary today for "passed despite N violations."
- `shell/adapters/postgres/{report,report_draft,gate_result}.py` — `Report`, `ReportDraft`,
  `StoredGateResult` are all unconditionally immutable (`before_update` listeners that raise);
  nothing in the current schema can record a per-violation review decision without a new table.
- `ARCHITECTURE-SPINE.md:196-197` (AD-10) — *"Regeneration under FR-21 replaces the whole Report,
  never a single failing Section"* — directly precludes ask (b) as originally worded; the amendment
  below narrows this sentence to the *automatic* path only.
- `epics.md:1508-1528` (Story 5.4 AC) — *"the whole Report is regenerated, never a single failing
  Section"* — same conflict, same story family.

**Issue category (checklist 1.2):** new requirement — an operator override plus a cheaper
single-sentence fix path — not a misunderstanding of existing scope and not a technical limitation
discovered mid-implementation.

---

## 2. Impact Analysis

### Epic impact

- **Epic 5 — "A report I can trust enough to send without reading it"** (binds AD-5/6/7/8, FR-20/21/22):
  gains two new stories (5.7, 5.8) and amended ACs on Stories 5.3 and 5.5. Story 5.4 (automatic
  regeneration) is unaffected — Rigenera keeps its exact current behavior.
- **Epic 9 — UI rebuild** (Story 9.5): the Gate-failure panel gains two new per-violation actions and
  a new "passed with N accepted exceptions" display state, wherever a Report is shown.
- No epic is invalidated, resequenced, or removed.

### Artifact conflicts

- **PRD:** FR-21 gains two sentences naming the new recovery actions (§4.3 below) — additive, no
  existing FR text removed. **SM-5** ("share of Reports passing on *first generation*") already
  excludes both new paths by its own existing wording; no metric-definition change needed, only a
  test confirming it. **SM-7**'s hand-sample explicitly gains passed-with-exceptions Reports as
  eligible sample members (Story 5.7 AC) since a human-overridden Report is exactly the kind worth
  double-checking for Gate leakage.
- **Architecture (`ARCHITECTURE-SPINE.md`):** **AD-10** needs a textual amendment — not a new AD —
  narrowing its "replaces the whole Report" sentence to the automatic path and naming the two new,
  narrower recovery routes. The invariant AD-10 protects (append-only, checkpointed, idempotent
  stages; Sections never mixed across drafts) is preserved for Rigenera and extended, not weakened,
  for the new paths: both new writes are append-only, mirroring every existing table in this
  subsystem. `epics.md:169`'s AD-10 restatement needs the matching amendment so the two copies don't
  drift. **AD-1** (purity), **AD-6** (cited structure), **AD-7** (the Gate is pure and the only path
  to export) are all unaffected in substance: `core/gate/run.py::run_gate()` is called exactly as
  before, unchanged, on both new paths; the human-review layer sits entirely in `shell/`, above the
  pure Gate, never inside it. `core/types/gate.py`'s `GateResult`/`StoredGateResult` invariant
  ("violations empty iff passed True") is **not touched** — the new "passed-with-exceptions" state is
  recorded on `Report` alone, never faked into a Gate-result row.
- **UX (`EXPERIENCE.md`/`DESIGN.md`):** real changes needed, not cosmetic — the Report Run Lifecycle
  table and "Regeneration replaces the whole Report" rule need the same narrowing the architecture
  amendment describes, plus two new per-violation controls and a new status-badge state. `DESIGN.md`
  already defines a generic `warning` badge variant that covers the new "accepted exception" flag
  without a new component.
- **Spec / computation contract:** none. The Report Payload, Domain Profiles, and the Generator's
  input contract (AD-3) are untouched — both new actions operate entirely after generation, never
  before or during it.

### Technical impact (for the implementing developer — informational, not prescriptive)

This extends the existing append-only Gate-outcome subsystem with one new table and two new routes,
not a new subsystem:

- **New table** (e.g. `gate_violation_review`), append-only like every sibling table: one row per
  accept decision, keyed to the specific `StoredGateResult` and violation index it was reviewed
  against, denormalized enough (kind/section/sentence/entry_ids) to stand alone for audit.
- **`Report`** gains two nullable columns: `accepted_violation_count: int = 0` and
  `closing_gate_result_id: UUID | None` — `0`/`None` for every existing and future clean pass
  (zero behavior change for the default case), populated only when a run completes via Story 5.7's
  accept-closure path.
- **`view_report`**'s passing-`StoredGateResult` lookup needs a second branch: when
  `accepted_violation_count > 0`, read `closing_gate_result_id` directly instead of requiring a
  `passed=True` row — additive; the existing clean-pass branch and its `RuntimeError` guard stay
  byte-for-byte unchanged.
- **`core/types/gate.py`'s `GateViolation`** gains one additive field — a within-section sentence
  index — so a correction route can unambiguously locate which `Sentence` to replace even if two
  sentences share identical text. `core/gate/run.py` already iterates sentences by position to build
  each violation, so surfacing that index is near-free and touches no pass/fail logic.
- **Flagged, not resolved — the one real risk in this change:** `ReportDraft`'s unique
  `(report_run_id, attempt)` index and `_run_draft_ready`'s `attempt=run.regeneration_count` tagging
  (`shell/runner/driver.py:559`) assume only automatic regeneration ever mints a new `ReportDraft`
  row. Once hand-correction (Story 5.8) also mints one, `attempt` needs a source both paths agree on
  (e.g. a count of existing rows for the run) rather than `run.regeneration_count` alone, or the two
  paths can collide on the same attempt number. The same tension applies to
  `_current_cycle_gate_failure`'s `regeneration_count`-descending ordering
  (`shell/http/routes/report_runs.py:130`) — recommend ordering by `created_at` there instead. Both
  are flagged for the developer to resolve by inspection of the actual concurrency/locking discipline
  already in `advance()`, not dictated here.
- Two new HTTP routes, mirroring the existing `regenerate_report_run` shape (`report_runs.py:374`):
  an accept route and a hand-correct-and-recheck route, both scoped to one violation at a time (per
  the "per violation" granularity chosen), both able to trigger the same run-completion write once
  every open violation on the current failing result is resolved one way or another.
- Tests needing new coverage (found, not fixed, by this proposal): the accept-closure path, the
  hand-correction path (including the carry-forward-of-prior-acceptances case), the
  attempt-numbering fix above, and `view_report`'s new branch.

No AD-2 (ephemeris identity), AD-3 (Generator's only channel), AD-9 (single Generator adapter),
AD-11 (no durable host-filesystem state), or AD-20 (poll-driven advance) implication anywhere in
this change — neither new action calls the Generator or touches the poll-driven stage engine
directly; both are new, narrower completion paths alongside it.

---

## 3. Recommended Approach

**Selected: Option 1 — Direct Adjustment.** Add two new stories to Epic 5 and amend three existing
stories (5.3, 5.5, 9.5) plus one PRD FR and one architecture decision (both copies), all additive.
No rollback, no MVP re-scoping.

**Rationale:**
- **Effort: Medium.** One new table, two new routes, one flagged-but-not-trivial attempt-numbering
  fix, plus UX component work — more than a single-field addition, but entirely within Epic 5/9's
  existing boundaries; no new port, no new epic, no change to the Generator contract.
- **Risk: Low-Medium.** Every new write is append-only, mirroring the immutability pattern already
  enforced on every sibling table (`Report`, `ReportDraft`, `StoredGateResult`) — nothing existing is
  ever mutated. The one real risk (attempt-number collision between Rigenera and hand-correction) is
  explicitly flagged above rather than silently assumed away.
- **Rollback (Option 2) is not viable:** there is nothing to roll back — the gap has existed since
  Story 9.5 shipped the Gate-failure panel, and no later story depends on it staying accept/correct-free.
- **MVP review (Option 3) is not warranted:** this doesn't touch a Non-Goal, doesn't change SM-5's
  definition (it already excludes both new paths), and only adds an eligibility note to SM-7's
  existing hand-sample.

---

## 4. Detailed Change Proposals

### 4.1 Architecture — `ARCHITECTURE-SPINE.md`, AD-10

**OLD:**
> **Rule:** a `ReportRun` row advances forward only, through `natal_ready → transits_ready →
> payload_ready → draft_ready → gate_passed → exported`. Each stage persists its output before the
> next begins — including the cited draft structure, which SM-7's hand sampling needs. Re-driving a
> run resumes at the first incomplete stage; **AD-20 fixes what invokes that advance and when — the
> poll request, one stage at a time, never a background job.** Every stage function is idempotent on
> its input.
> **Regeneration under FR-21 replaces the whole Report, never a single failing Section**, so a
> regeneration count means one thing and Sections cannot come from different drafts. Reaching
> `exported` happens once; each subsequent export writes an `EXPORT_RECORD` row rather than moving the
> stage.

**NEW:**
> **Rule:** a `ReportRun` row advances forward only, through `natal_ready → transits_ready →
> payload_ready → draft_ready → gate_passed → exported`. Each stage persists its output before the
> next begins — including the cited draft structure, which SM-7's hand sampling needs. Re-driving a
> run resumes at the first incomplete stage; **AD-20 fixes what invokes that advance and when — the
> poll request, one stage at a time, never a background job.** Every stage function is idempotent on
> its input.
> **Automatic regeneration under FR-21 replaces the whole Report, never a single failing Section**,
> so a regeneration count means one thing and Sections cannot come from different drafts. **(Amended
> 2026-09-02, correct-course, Story 5.7/5.8):** `gate_passed` is now reached by one of three routes,
> not one — an automatic Gate pass; every open violation on the current failing `GateResult`
> explicitly accepted after review (no draft change, no new Gate check); or one flagged sentence
> hand-corrected and re-checked by the same pure, model-free Gate call, which persists its own
> `ReportDraft`/`StoredGateResult` pair exactly as append-only as an automatic attempt, but counted
> separately from `regeneration_count` and never bounded by it. Only the first route is a
> "regeneration" in this rule's original sense; the other two are reviewed, human-closed exceptions,
> and a `REPORT` row produced by the third route records how many violations were accepted so it is
> never indistinguishable from a clean pass. Reaching `exported` happens once; each subsequent export
> writes an `EXPORT_RECORD` row rather than moving the stage.

**Rationale:** narrows the "replaces the whole Report" sentence to the automatic path it always
described and names the two new, narrower recovery routes alongside it. No new AD.

### 4.2 Architecture mirror — `epics.md:169` (AD-10 restatement)

**OLD:**
> **Regeneration under FR-21 replaces the whole Report, never a single failing Section.**

**NEW:**
> **Automatic regeneration under FR-21 replaces the whole Report, never a single failing Section.**
> *(Amended 2026-09-02: `gate_passed` can also be reached by an accepted-violation closure or a
> hand-corrected sentence re-check — Stories 5.7/5.8 — neither of which is a "regeneration" or
> touches `regeneration_count`.)*

### 4.3 PRD — `prd.md`, FR-21

**OLD:**
> FR-21: A Report failing the Groundedness Gate is regenerated a bounded number of times
> automatically. On persistent failure Francesco is shown the Report, the failing Claims, and the
> Payload entries they contradict — never a silent discard. A Report that has not passed the Gate
> cannot be exported.

**NEW:**
> FR-21: A Report failing the Groundedness Gate is regenerated a bounded number of times
> automatically. On persistent failure Francesco is shown the Report, the failing Claims, and the
> Payload entries they contradict — never a silent discard. On persistent failure Francesco may also,
> per violation and only after reviewing it: **accept** it so the Report can complete despite it —
> visibly flagged wherever the Report is later shown, and excluded from SM-5's first-generation pass
> rate — or **hand-correct** the one flagged sentence and re-run the Gate check alone, without a full
> regeneration. A Report that has not passed the Gate, been closed by accepted exceptions, or been
> hand-corrected to a genuine pass, cannot be exported.
>
> *(Amended 2026-09-02, correct-course: adds the accept and hand-correct recovery paths alongside
> automatic regeneration.)*

### 4.4 Epic 5 — new Story 5.7: *Accept a Gate violation after review, so a Report can complete despite it*

As Francesco,
I want to explicitly accept a specific Gate violation after reading it,
So that a Report I judge to be fine despite the Gate's objection isn't stuck forever behind a check I disagree with.

**Acceptance Criteria:**

**Given** a run whose current Gate failure is showing its violation cards
**When** Francesco accepts one
**Then** that decision is recorded against the specific `StoredGateResult` and violation it was
reviewed on, append-only — never silently reversible, mirroring every other Gate-adjacent table's
immutability

**Given** every violation in the current failing `GateResult` has been accepted
**When** the last one is accepted
**Then** a `REPORT` row is written immediately, recording how many violations were accepted and
which failing `GateResult` it was closed against, and the run advances to `gate_passed` — no new
Gate check is fabricated to justify it

**Given** a Report written this way
**When** it is shown anywhere — the reading sheet, Report History, Home's status badges, exports
**Then** it is visibly and permanently flagged as passed with N accepted exceptions, never rendered
identically to a clean pass

**Given** SM-5's first-generation pass rate
**When** it is computed
**Then** a Report closed this way is excluded, exactly as every other post-first-attempt outcome
already is — confirmed by a test, not a metric-definition change

**Given** SM-7's periodic hand-sample of passed Reports
**When** it is drawn
**Then** a Report closed via accepted violations is eligible for that sample like any other passed
Report

*(New 2026-09-02, correct-course.)*

### 4.5 Epic 5 — new Story 5.8: *Correct a violated sentence by hand, and re-check only the Gate*

As Francesco,
I want to reword the one sentence a violation names and see immediately whether that fixes it,
So that a wording problem doesn't cost a full paid regeneration and doesn't put the other seven Sections at risk of coming from a different draft.

**Acceptance Criteria:**

**Given** a violation card naming one sentence in one Section
**When** Francesco edits that sentence's text and resubmits
**Then** only that sentence changes — every other sentence in every other Section, and that
sentence's own citations, carry over unchanged from the draft that failed

**Given** the edited sentence
**When** it is resubmitted
**Then** the Groundedness Gate runs again — pure, no model call — against the same stored Payload,
and a new immutable `ReportDraft`/`StoredGateResult` pair is persisted for this attempt, mirroring
how an automatic regeneration is persisted, but this correction never increments
`regeneration_count` and is never bounded by it

**Given** the recheck comes back with zero violations
**When** it is evaluated
**Then** a `REPORT` row is written exactly as a normal Gate pass would be — no accepted-exception
flag, since the Gate genuinely passed the corrected text

**Given** the recheck still finds violations, some already accepted before this edit and
byte-for-byte unchanged by it
**When** the new result is evaluated
**Then** those acceptances carry forward automatically — Francesco is never asked to re-accept a
violation he didn't touch

**Given** violations remain after carrying acceptances forward
**When** the draft view re-renders
**Then** it shows exactly the remaining, unresolved violation cards, each still offering Accept and
hand-correct

*(New 2026-09-02, correct-course.)*

### 4.6 Epic 5 — amend Story 5.3, `epics.md:1479-1506`

**Insert** after the existing "Given a passing `GateResult`... the `REPORT` row is written" block:

> **Given** every violation in a run's current failing `GateResult` has been accepted, or a
> hand-corrected sentence brings the Gate to a genuine pass (Story 5.7/5.8)
> **When** that resolution completes
> **Then** the `REPORT` row is written the same way — a Report still exists only once the Gate's
> objections are resolved, one way or another, never before
> **And** export is still refused for any run whose Report row does not yet exist
>
> *(Amended 2026-09-02, correct-course: the original "only on a passing GateResult" is the automatic
> case; Story 5.7/5.8 add the two human-resolved paths that also satisfy it.)*

### 4.7 Epic 5 — amend Story 5.5, `epics.md:1530-1548`

**Insert** new AC block:

> **Given** a Report that has exhausted its regeneration bound and is shown with its failing Claims
> **When** Francesco reviews each one
> **Then** he can, per violation, accept it after review (Story 5.7) or correct its sentence and
> re-check the Gate alone (Story 5.8) — both additional to, never a replacement for, Rigenera
>
> *(Amended 2026-09-02, correct-course.)*

### 4.8 Epic 9 — amend Story 9.5, `epics.md:2067-2071`

**OLD:**
> **Given** a run that failed the Gate
> **When** the draft view renders
> **Then** a `danger` panel headed "Verifica di fondatezza non superata" shows one card per
> violation — kind, the Sezione, the offending sentence as a blockquote, the detail, and the cited
> entry IDs as mono chips (or "nessuna")
> **And** each violation card links to its Sezione in the draft below
> **And** the primary action is Rigenera, which replaces the whole Report and increments the
> regeneration count (AD-10)

**NEW:**
> **Given** a run that failed the Gate
> **When** the draft view renders
> **Then** a `danger` panel headed "Verifica di fondatezza non superata" shows one card per
> violation — kind, the Sezione, the offending sentence as a blockquote, the detail, and the cited
> entry IDs as mono chips (or "nessuna")
> **And** each violation card links to its Sezione in the draft below
> **And** the primary action is Rigenera, which replaces the whole Report and increments the
> regeneration count (AD-10)
> **And** each violation card also offers **Accetta** (Story 5.7) and **Modifica e ricontrolla** — an
> inline textarea prefilled with the sentence (Story 5.8) — both acting on that one violation alone,
> distinct from Rigenera
>
> **Given** a Report completed via one or more accepted violations
> **When** Francesco views it anywhere — stage track, reading sheet, Report History
> **Then** it is visibly marked as passed with N accepted exceptions, never shown identically to a
> clean pass
>
> *(Amended 2026-09-02, correct-course: adds Story 5.7/5.8's actions to the existing Gate-failure
> panel.)*

---

## 5. Implementation Handoff

**Scope classification: Moderate.** New domain concept (accepted exception), one new append-only
table, two new routes, one flagged-but-unresolved attempt-numbering fix in `shell/runner/driver.py`,
plus real UX work (`EXPERIENCE.md`/`DESIGN.md`) — more than a single-file additive change, but fully
within Epic 5/9's existing boundaries; no epic restructuring, no PRD scope change, no MVP re-plan.

**Route to:** Product Owner first (backlog reorganization — slot Stories 5.7/5.8 into Epic 5,
re-number/re-check any downstream story references, update `sprint-status.yaml`), then Developer
agent (`bmad-build` / Amelia) for implementation.

**Deliverables for the Product Owner:**
1. Add Stories 5.7 and 5.8 to Epic 5 in `epics.md` (§4.4/§4.5 above, verbatim).
2. Apply the amendments in §4.1, §4.2, §4.3, §4.6, §4.7, §4.8 to `ARCHITECTURE-SPINE.md`, `epics.md`
   (two locations), and `prd.md` respectively.
3. Update `sprint-status.yaml` to reflect the two new Epic 5 stories (status: backlog).
4. Flag `EXPERIENCE.md`'s Report Run Lifecycle table/Rules and `DESIGN.md`'s badge usage for a UX
   pass (Sally) before or alongside implementation — not strictly blocking, since `DESIGN.md`'s
   existing `warning` badge variant already covers the new state, but the Rules prose and the
   violation-card layout need real updates.

**Deliverables for the Developer agent:**
1. Implement per §2's Technical Impact notes: the new review table, `Report`'s two new nullable
   columns, `view_report`'s new branch, `GateViolation`'s new sentence-index field, and the two new
   routes. Resolve the flagged attempt-numbering tension (`shell/runner/driver.py:559`,
   `shell/http/routes/report_runs.py:130`) by inspection — not by guessing — before writing the
   migration.
2. Forward-only Alembic migration(s), no `downgrade()` body (repo policy).
3. New tests per §2's list; existing tests for `regenerate_report_run`, `view_report_draft`,
   `_run_gate_passed` must stay green unchanged — nothing in this change touches their existing
   behavior.
4. Update `report_draft.html` (and `report.html`/Home's status badges) for the two new per-violation
   actions and the accepted-exceptions flag, per the UX pass.
5. Run `uv run pytest` locally before pushing (repo policy: work lands directly on `main`, no PR).

**Success criteria:** a violation card offers Accetta and Modifica e ricontrolla alongside the
unchanged Rigenera; accepting every open violation completes the run without a new Generator call;
hand-correcting a sentence re-checks the Gate alone and, on a genuine pass, completes the run
identically to today's automatic pass; every new write is append-only (no `before_update` guard is
ever triggered); `uv run pytest` is green.

---

## 6. Approval

**Approved by Francesco, 2026-09-02** — full batch of edits in §4 approved as drafted, no changes
requested.
