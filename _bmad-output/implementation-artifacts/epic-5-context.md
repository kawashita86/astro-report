# Epic 5 Context: A report I can trust enough to send without reading it

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Every Claim in a generated Report is checked against the Report Payload before Francesco ever
sees it. Failures regenerate automatically (bounded), and a Report that persistently fails is
surfaced — never silently discarded — with its failing Claims shown against the facts they
contradict. As of the 2026-09-02 correct-course amendment, Francesco also has two human-driven
ways to resolve a persistent failure without a full regeneration: accepting an individual
violation after reviewing it, or hand-correcting the one offending sentence and re-checking only
the Gate. This is the emotional job-to-be-done of the product: send a Report without reading it
first, and not worry about what is in it.

## Stories

- Story 5.1: Define what counts as a Claim, as versioned data
- Story 5.2: Check every Claim against the Payload
- Story 5.3: Make the Gate the only path to an exportable Report
- Story 5.4: Regenerate a failing Report automatically, whole
- Story 5.5: See exactly what failed and what it contradicts
- Story 5.6: Keep the Gate's record so a regression is visible early
- Story 5.7: Accept a Gate violation after review, so a Report can complete despite it (new, 2026-09-02)
- Story 5.8: Correct a violated sentence by hand, and re-check only the Gate (new, 2026-09-02)

## Requirements & Constraints

- A Claim is any sentence containing a token from a closed Italian astronomical vocabulary (ten
  planets, twelve signs, `casa` + ordinal, day-of-month numeral, `retrogrado`, `stazionario`); a
  sentence with no such token is interpretation and is never policed by the Gate. A sentence that
  leans on a fact without naming it is a documented, accepted blind spot — not verifiable against
  a Payload by any mechanism.
- A Claim fails the Gate if it names a planet/sign/house/degree/aspect/date/retrograde condition
  absent from the Payload, or if it contradicts the Payload (wrong date for a named Aspect
  Perfection, wrong house for a Lunation, a false retrograde claim). A closed-vocabulary token
  with an empty citation list is a violation. Any date token appearing anywhere in Section 6 or
  Section 7 of the model's own output is a violation — those dates are code-projected, never
  model-written.
- Claim-level determinism: two generations from the same Payload must never contradict each other
  on a fact (NFR-3). Every Claim in a delivered Report must stay traceable to a stored Payload
  entry for as long as the Report is retained (NFR-4).
- The Gate is the last step before Francesco sees a Report — no path from Generator to export may
  bypass it (NFR-11), and every guardrail must hold with no human review step between generation
  and the Client for the automatic path (NFR-14); the 2026-09-02 amendment adds human-resolved
  paths that are explicitly reviewed by Francesco, not a relaxation of this for the automatic case.
  A Report that has not passed the Gate, been closed by accepted exceptions, or been hand-corrected
  to a genuine pass, cannot be exported.
- Regeneration on Gate failure is automatic and bounded; it always replaces the whole Report, never
  a single Section, and re-runs from the same stored Payload. On exhausting the bound, the Report
  is surfaced with its failing Claims and the Payload entries they contradict or are missing from —
  never silently discarded.
- The Gate outcome (pass/fail, regeneration count, flagged Claims, vocabulary version) is stored
  per Report and must be queryable across Reports so a rising regeneration rate is visible early.
  This is what SM-5 (first-generation pass rate) and SM-7 (Gate leakage, via a monthly hand-sample
  of passed Reports checked against stored Payloads) are computed from.
- A Report closed via accepted violations (Story 5.7) is excluded from SM-5's first-generation pass
  rate (same treatment as every other post-first-attempt outcome) but is eligible for SM-7's
  hand-sample like any other passed Report — confirm both by test, not by redefining either metric.

## Technical Decisions

- `core/gate/vocabulary.it.json` holds the closed vocabulary with its own integer version,
  independent of Payload/Section-composition versions; every Report records which version
  classified it (AD-8).
- `run_gate(draft, payload) -> GateResult` lives in `core/gate/`, is pure (no model call, no I/O),
  and is the only path to export: exactly one export function exists, takes a stored Report ID, and
  reads only Reports whose persisted `GateResult` is `passed` (AD-7, enforced by test). `run_gate()`
  is called unchanged on the automatic path and both new human-resolved paths — the review layer
  sits entirely in `shell/`, never inside the pure Gate. `GateResult`/`StoredGateResult`'s invariant
  ("violations empty iff passed True") is untouched; passed-with-exceptions is recorded on `Report`
  alone, never faked into a Gate result row.
- Generation returns cited structure: each Section is an ordered list of sentences, each carrying
  the Payload entry IDs it rests on (AD-6). `GateViolation` gains a within-section sentence index
  (2026-09-02 amendment) so hand-correction can unambiguously locate the sentence to replace even
  when two sentences share identical text.
- Dated entries in Sections 6/7 are projected by a pure function from the Payload, never written by
  the model (AD-5); a date token from the model there is always a violation.
- `ReportRun` advances forward only through `natal_ready → transits_ready → payload_ready →
  draft_ready → gate_passed → exported`, one stage per poll request (AD-20), each idempotent and
  persisting its output before the next begins (AD-10).
- **AD-10 amendment (2026-09-02):** `gate_passed` is now reached via one of three routes: (1)
  automatic Gate pass; (2) every open violation on the current failing `GateResult` explicitly
  accepted (no draft change, no new Gate check fabricated); or (3) one flagged sentence
  hand-corrected and re-checked by the same pure Gate call, persisting its own
  `ReportDraft`/`StoredGateResult` pair exactly as append-only as an automatic attempt, but counted
  separately from and never bounded by `regeneration_count`. Only route (1) is a "regeneration" in
  the original sense. A `REPORT` row from route (2) records how many violations were accepted so it
  is never indistinguishable from a clean pass. A `REPORT` row is written only once the Gate's
  objections are resolved one way or another — never before; export stays refused until it exists.
- New append-only table (e.g. `gate_violation_review`), mirroring the immutability already enforced
  on `Report`/`ReportDraft`/`StoredGateResult`: one row per accept decision, keyed to the specific
  `StoredGateResult` and violation index reviewed, denormalized (kind/section/sentence/entry_ids)
  for standalone audit.
- `Report` gains two nullable columns: `accepted_violation_count: int = 0` and
  `closing_gate_result_id: UUID | None` — default for every clean pass, populated only via the 5.7
  accept-closure path. `view_report`'s passing-`StoredGateResult` lookup needs a second branch: when
  `accepted_violation_count > 0`, read `closing_gate_result_id` directly instead of requiring
  `passed=True`; the existing clean-pass branch stays unchanged.
- **Flagged risk — resolve by inspecting the actual concurrency/locking discipline in `advance()`,
  not by guessing, before writing the migration:** `ReportDraft`'s unique `(report_run_id, attempt)`
  index and the driver's `attempt=run.regeneration_count` tagging assume only automatic regeneration
  mints a new `ReportDraft` row. Once hand-correction (5.8) also mints one, `attempt` needs a source
  both paths agree on (e.g. a count of existing rows for the run), or they can collide. The
  gate-failure lookup's `regeneration_count`-descending ordering has the same tension — order by
  `created_at` instead.
- Two new HTTP routes mirror the existing `regenerate_report_run` shape: an accept route and a
  hand-correct-and-recheck route, both scoped to one violation at a time, both able to trigger the
  same run-completion write once every open violation on the current failing result is resolved.
- No implication for AD-2, AD-3, AD-9, AD-11, or AD-20: neither new action calls the Generator or
  touches the poll-driven stage engine directly.
- Forward-only Alembic migrations only, no `downgrade()` body (repo policy). Existing tests for
  regeneration, draft view, and gate-passed handling must stay green, unchanged.

## UX & Interaction Patterns

- Gate failure is a destination, not a toast: `/report-runs/{id}/draft` renders a `danger` panel
  headed "Verifica di fondatezza non superata" with one card per violation (kind, Sezione, offending
  sentence as a blockquote, detail, cited entry IDs as mono chips or "nessuna"), each linking to its
  Sezione in the draft below. Primary action is Rigenera (confirms via modal, states it replaces the
  whole Report and increments the regeneration count); secondary is Vedi Payload. Rigenera's copy,
  position and whole-Report behavior are unchanged by this epic's amendment.
- Every unresolved violation card gets a bottom action row (below the cited-entry chips, above the
  "Vai alla Sezione N ↓" link): two ghost buttons, **Accetta** then **Modifica e ricontrolla** —
  styled as tertiary/row-level actions, never competing visually with the page-level Rigenera button.
  - **Accetta**: one click, no confirm modal (unlike Rigenera). In-flight shows an inline spinner and
    disables. On success the card collapses to a one-line resolved strip: kind + Sezione + an
    "Accettata" tag in `warning` tone, pinned above any still-open cards. If it was the last open
    violation, the whole panel is replaced on next render by the normal `gate_passed` state (Vedi
    report) — no separate "all done" interstitial.
  - **Modifica e ricontrolla**: expands inline — the card's blockquote swaps for an editable Textarea
    prefilled with the sentence's exact current text; the button row swaps for **Ricontrolla**
    (primary, submits) and **Annulla** (ghost, discards, no request sent). On a genuine pass the card
    collapses to a resolved strip tagged "Corretta" in `success` tone (never "Accettata"/`warning` —
    this is a real Gate pass, not an exception). A card that still fails re-renders open with updated
    detail/citations. Same last-violation completion rule as Accetta.
  - Resolved strips (any mix of Accettata/Corretta) stack at the top of the panel in resolution
    order, oldest first; open cards keep full detail below, order otherwise unaffected.
- **Passed-with-exceptions badge**: a `warning`-toned badge reading "Superato con N eccezioni"
  (N = `accepted_violation_count`) appears immediately after the Report's title/date everywhere a
  completed Report is named — reading sheet, Report History rows, Home's recent-runs list — stacked
  alongside the row's normal status badge, never replacing it (same pattern as the existing
  superseded-chart warning riding beside "esportato"). A Report with `accepted_violation_count = 0`
  (clean pass, or a Story 5.8 hand-correction reaching a genuine pass) carries no such badge and
  reads identically to any self-passing Report.
- The stage-track row for `gate_passed` shows this same stacked warning badge when closed via
  accepted violations; unmarked on a clean pass or a genuine hand-corrected pass. The **failed**
  stage-track state offers Vedi bozza, Rigenera, Vedi Payload at the page level, plus per-card
  Accetta / Modifica e ricontrolla.
- `DESIGN.md` already defines the `warning` badge variant used here — no new badge component is
  needed, only new usage sites and the panel/card layout changes described above.

## Cross-Story Dependencies

- Story 5.3 (Gate as the only export path) is amended so that a `REPORT` row is written not only on
  an automatic passing `GateResult`, but also once every violation in a failing result is accepted
  (5.7) or a hand-correction brings the Gate to a genuine pass (5.8); export stays refused until
  that row exists either way.
- Story 5.5 (surfacing a persistently failing Report) is amended: alongside seeing the failing
  Claims, Francesco can now, per violation, invoke 5.7 or 5.8 — both additive to Rigenera (5.4),
  never a replacement for it.
- Stories 5.7 and 5.8 both depend on 5.1/5.2 (Claim/vocabulary definition, the pure `run_gate`) and
  5.4/5.5 (the failing-Report surface they attach their actions to). 5.8's re-check calls the exact
  same `run_gate()` as 5.2/5.4, against the same stored Payload.
- 5.8 must carry forward any acceptances already recorded (5.7) against violations byte-for-byte
  unchanged by the edit — Francesco is never asked to re-accept a violation he didn't touch.
- SM-5 and SM-7 (Epic-level success metrics, Story 5.6) must correctly classify Reports closed via
  5.7/5.8: excluded from SM-5's first-generation pass rate, included in SM-7's hand-sample eligibility.
- This epic's Gate-failure panel and stage-track badges are also touched by Epic 9's UI rebuild
  (Story 9.5), which is amended in the same 2026-09-02 correct-course to add the Accetta/Modifica e
  ricontrolla controls and the passed-with-exceptions badge to the shared components.
- The attempt-numbering fix flagged above (`shell/runner/driver.py`,
  `shell/http/routes/report_runs.py`) must be resolved before or alongside implementing 5.8, since
  5.8 is the first path other than automatic regeneration to mint a new `ReportDraft` row.
