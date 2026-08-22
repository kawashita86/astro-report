# Epic 5 Context: A report I can trust enough to send without reading it

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Every Claim in a generated Report is checked against the Report Payload before Francesco ever sees
it in an exportable state. Failures regenerate the whole Report automatically, bounded, and never a
single Section; persistent failure is surfaced with the specific Claims and the Payload entries they
contradict, never silently discarded. This is the emotional core of the product: send a report
without reading it first, and not worry about what is in it. The Gate outcome is stored and queryable
so a regression in generation or Style Guide quality shows up as a trend before a client ever sees a
bad Report.

## Stories

- Story 5.1: Define what counts as a Claim, as versioned data
- Story 5.2: Check every Claim against the Payload
- Story 5.3: Make the Gate the only path to an exportable Report
- Story 5.4: Regenerate a failing Report automatically, whole
- Story 5.5: See exactly what failed and what it contradicts
- Story 5.6: Keep the Gate's record so a regression is visible early

## Requirements & Constraints

- A Claim is verified only against facts present in the Report Payload: named planet, sign, house,
  degree, aspect, date, or retrograde condition. A Claim naming or contradicting something not in the
  Payload fails — wrong date for an Aspect Perfection, wrong house for a Lunation, a body called
  retrograde that isn't.
- A sentence that leans on a fact without naming it is not policed — this limit is real and must stay
  documented, not papered over; it is unverifiable against a Payload by any mechanism.
- Interpretive statements asserting no astronomical fact are never Claims and never fail the Gate;
  they are governed by the Style Guide instead.
- A sentence containing a closed-vocabulary token with an empty citation list is a violation.
- A date token appearing anywhere in the two dated-list Sections (Sections 6 and 7) of the model's own
  output is a violation — those dates are projected by code, and the model may not write them.
- Regeneration on Gate failure is automatic, bounded by a configured limit, and always whole-Report —
  never a single failing Section, so Sections never come from different drafts. The regeneration count
  is tracked per run.
- When the bound is reached and the Report still fails, the run stops and the Report is surfaced
  rather than discarded; Francesco sees the Report text, each failing Claim, and the Payload entries
  each Claim contradicts or is missing from. Export is refused with the reason stated.
- A Report row is written only on a Gate pass — never before. It records the Style Guide version, the
  Payload schema version, and the Gate vocabulary version that produced it.
- Exactly one export function exists anywhere in the codebase; it takes a stored Report ID and reads
  only Reports whose persisted Gate result is `passed`. No function accepts a draft and produces an
  exportable artifact. A test must assert this so a second export path cannot be added quietly.
- Every Gate outcome is stored: pass/fail, regeneration count, every Claim flagged, and the vocabulary
  version that classified it. This must support querying first-generation pass rate and regeneration
  count as reportable series (these are the product's early-warning signal for a Generator or Style
  Guide regression, and the counterbalancing signal that a rising pass rate isn't just the Gate being
  loosened).
- Stored draft citations and Payload entries must remain available so a monthly hand sample of passed
  Reports can be checked against their Payloads — this is the only measure of the Gate's false-negative
  rate (Gate leakage); the Gate's pass rate alone is blind to it.
- The Gate itself is a pure function of a draft and a Payload — calls no model, performs no I/O, and
  running it twice on the same inputs gives an identical result.
- Report prose may vary between generations (wording must vary, or recurring clients get visibly
  repetitive text); Claims may not — two generations from the same Payload must never contradict each
  other on a fact.
- Traceability: every Claim in every delivered Report must remain traceable to a stored Payload entry
  for as long as the Report is retained.
- Reports ship unedited — every guardrail here must hold with no human review step between generation
  and the client, because none exists.

## Technical Decisions

- `run_gate(draft, payload) -> GateResult` lives in `core/gate/`, is pure, calls no model, performs no
  I/O. It is the only path to export: exactly one export function exists, takes a stored Report ID, and
  reads only Reports whose persisted `GateResult` is `passed`.
- Claim classification is a versioned closed vocabulary, not a heuristic or model judgment: a sentence
  is a Claim if and only if it contains a token from `core/gate/vocabulary.it.json` — the ten planets,
  the twelve signs, `casa` with an ordinal, a day-of-month numeral, `retrogrado`, `stazionario`. The
  vocabulary carries its own integer version, independent of the Payload and Section-composition
  versions; every Report records which version classified it. Revising the vocabulary bumps that
  version.
- The Generator returns cited structure, not prose: each Section is an ordered list of sentences, each
  carrying the Payload entry IDs it rests on. This citation structure — not reconstructed-by-guessing
  prose — is what the Gate checks and what Gate leakage sampling relies on. Rendering into continuous
  prose happens later in the shell; citations are retained against the stored draft rather than
  discarded at render time.
- Dated day-lists (Sections 6 and 7) are rendered by code from the Payload via a pure function, never
  written by the model — the Generator emits no date token there at all, so a misfiled day is
  structurally impossible rather than something the Gate must catch.
- Payload entry IDs are content-derived (stable hash of a canonical field tuple, never sequential/
  time/random-derived), so a citation means the same entry across generations of the same Payload.
- A report run is a checkpointed `ReportRun` row advancing only forward through fixed stages, relevant
  ones here: `draft_ready → gate_passed → exported`. The Gate runs before the Report is shown to
  Francesco in any exportable state; the run advances to `gate_passed` only on a passing `GateResult`.
  Reaching `exported` happens once; later exports write an `EXPORT_RECORD` row instead of moving the
  stage.
- Data model: `REPORT` is produced only on Gate pass; `REPORT ||--|| GATE_RESULT` records passes and
  regenerations. Both `REPORT` and `GATE_RESULT` join the Client deletion cascade.

## Cross-Story Dependencies

- Consumes the cited draft structure produced by Epic 4's Generator (Story 4.5, "Generate eight
  Sections as cited structure"; Story 4.6 persists the cited draft at `draft_ready`) — the Gate cannot
  run without that citation structure.
- Consumes the Report Payload assembled in Epic 3 (Payload assembly and entry IDs) as the source of
  truth the Gate checks Claims against.
- Gates Epic 6 (Review, export, history): the single export function reads only Reports whose stored
  `GateResult` is `passed`; Story 6.1's displayed Gate result (including regeneration count) and
  Story 6.2's export refusal both depend on the Gate's stored outcome from this epic.
- Within the epic: Story 5.1's versioned vocabulary is a prerequisite for Story 5.2's check; Story 5.3
  (Gate as sole export path) depends on 5.2 producing a `GateResult`; Story 5.4 (bounded regeneration)
  and Story 5.5 (surfacing persistent failure) both depend on 5.2–5.3 existing; Story 5.6 (stored Gate
  record) depends on every prior story's outcomes being available to persist and query.
