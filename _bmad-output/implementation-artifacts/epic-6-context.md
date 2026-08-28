# Epic 6 Context: Review, export and history — the forty-reports-in-an-afternoon loop

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

> **Post-epic amendment (2026-08-28, retro item 47).** Epic 6 shipped PDF export
> only; Markdown export was deferred at planning time (`deferred-work.md:525`). The
> "Both PDF and Markdown" requirement below is **kept, not descoped** — it is
> tracked as a follow-up story with its own spec:
> `_bmad-output/implementation-artifacts/spec-6-2b-markdown-export.md`. Read every
> "PDF and Markdown" / "both formats" phrasing below as: PDF in epic 6, Markdown in
> the spec-6-2b follow-up.

## Goal

This epic is Francesco's remaining involvement with a Report once it exists: read it next to the facts that produced it, export a clean client-facing file, record how it went out, and browse what was produced before. It is also where the durability guarantee becomes something Francesco actually holds, rather than something that depends on a hosting provider's restore window. Together these close the loop that has to survive being repeated forty times in one afternoon — every interaction in this epic is budgeted against that repetition, not against a single careful use.

## Stories

- Story 6.1: Read a Report with its facts one click away
- Story 6.2: Export a passed Report to PDF and Markdown
- Story 6.3: Record how the report went out, in one interaction
- Story 6.4: Browse everything I have produced for a Client
- Story 6.5: Take a backup I actually hold
- Story 6.6: Be told when my backup is out of date

## Requirements & Constraints

- **Review**: a Report displays all eight Sections in fixed order, with the Gate result (including regeneration count) visible, and the underlying Payload view reachable in one interaction without leaving the Report. This must still hold for Reports generated months earlier.
- **Export**: only a Report whose stored Gate result is `passed` can be exported; export is refused otherwise. Both PDF and Markdown must be produced. The exported file contains only the eight Sections and the Client's name — no chart wheel, no Payload, no Gate result, no run identifier, no internal metadata. The first export moves the run to `exported` exactly once; every later export of the same Report writes an additional export record rather than re-advancing the run's stage.
- **Send disposition**: at export, Francesco records in exactly one interaction whether the Report was sent as generated or edited before sending. Nothing heavier than a single choice is acceptable — this is the measurement source for the unedited-send-rate success metric, and it has to survive being done forty times without being abandoned partway through. The elapsed time from Client selection to export is captured alongside it, feeding the per-Report time-budget metric.
- **Report History**: Reports are listed per Client, ordered by month. Any prior Report reopens with its Payload and Gate result intact — including a Report whose Natal Chart has since been superseded by a correction, which must still be readable and clearly marked as belonging to the superseded chart.
- **Backup**: one authenticated route produces a complete logical export (Clients, Natal Charts, Reports, Report Payloads, Gate results, Themes, Corpus entries) that downloads to Francesco's own machine, complete enough to reconstruct application state — not a partial dump. The route carries the same authentication as every other route.
- **Staleness warning**: the UI shows a visible warning whenever the newest Report postdates the last recorded export, and the warning clears once a fresh backup completes. The last-export timestamp is stored in Postgres, not on the container filesystem — durable state does not live on the compute host's filesystem.
- **Traceability**: every Claim in a delivered Report must remain traceable to its stored Payload entry for as long as the Report is retained — this is what makes the Payload-alongside-Report view and History reopen non-negotiable, not cosmetic.
- **Latency/throughput budget**: the whole per-Report cycle (including review and export) is budgeted under 3 minutes at p90 for generation-through-screen, and the system must sustain forty Reports in one working session and 100–200 per month — review and export interactions must not become the bottleneck.
- **Time budget**: total Francesco involvement per Report (select Client, generate, review, export) stays under 15 minutes; this is what the single-click send-disposition and one-click Payload access are protecting.
- **Data durability**: Clients, Natal Charts, Reports and Report Payloads must survive host restarts and redeploys. A lost Natal Chart is recoverable by recomputation; a lost Report Payload is not recoverable and permanently breaks traceability — this is the sharpest edge the backup feature exists to blunt.

## Technical Decisions

- **The Gate is pure and is the only path to export.** `run_gate` is a pure function in `core/gate/` — no model calls, no I/O. Exactly one export function exists in the codebase; it takes a stored Report ID and reads only Reports whose persisted Gate result is `passed`. There is no function anywhere that takes a draft directly and produces an exportable artifact — export always goes through the persisted, already-verified Report.
- **Durability is an operator action, not a platform promise.** The hosting provider's free-plan point-in-time restore (a roughly 6-hour window, no scheduled backups) does not satisfy the durability requirement, so it is not relied on. The backup route and staleness warning are the actual mechanism; restoring from an export is expected to be exercised before release, not merely assumed to work.
- **A report run is a checkpointed row that only moves forward.** Reaching the `exported` stage happens once per Report; every subsequent export of the same Report writes a separate export record rather than moving the run's stage again. This is what makes repeated exports of the same Report safe and auditable.
- **Data model touchpoints**: `REPORT` has a one-to-one `GATE_RESULT` (pass/fail, regeneration count, flagged Claims, vocabulary version) and a one-to-many `EXPORT_RECORD` (send disposition, elapsed time). Deleting a Client cascades to remove every row referencing it, including these — both tables must participate in that cascade correctly.
- **Where this lives in the codebase**: this capability area sits in `shell/http/` (routes, review/history UI) and `shell/adapters/weasyprint` (PDF rendering). Core stays untouched by this epic beyond reading the already-computed Gate result and Payload.
- **Logging discipline applies here too**: any logging touching report review/export must stay structured and must never carry Client birth data, names, or Report prose — identifiers only.

## Cross-Story Dependencies

- Story 6.1's Payload-alongside-Report view depends on the Payload view already built for FR-15 (an earlier epic) — this epic reuses it rather than rebuilding it.
- Story 6.2's export gate depends on the Gate result already being persisted per Report (from the Groundedness Gate epic) — export reads that stored result, it does not recompute it.
- Story 6.3's send-disposition and elapsed-time recording feed reporting needs outside this epic (the unedited-send-rate and per-Report-time success metrics) and must join the same Client-deletion cascade as the Gate result table.
- Story 6.4's Report History is also what the month-over-month non-repetition feature (a different epic) draws on — History is shared infrastructure, not exclusive to review/export.
- Story 6.6's staleness warning depends on Story 6.5's backup route existing and recording a last-export timestamp; the warning has no signal to check against until the backup route is in place.
