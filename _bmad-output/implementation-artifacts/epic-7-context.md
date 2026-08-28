# Epic 7 Context: Corpus collection (parallel track — gates nothing in v1)

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic gives Francesco a place to gather his hundreds of existing hand-written reports — today scattered across email, messaging and folders — into one store, as plain text, with each entry marked according to whether the chart behind it is known. The single output that matters is a composition count: how many entries are paired (matched to birth data and month) versus unpaired (prose only). That count is the decision input for whether phase-2 voice conditioning (few-shot exemplar selection) is viable at all, and later whether similarity-based retrieval has enough paired material to work with. The Corpus is treated as the product's real moat — the one advantage a competent developer could not rebuild in a month — but collecting it is slow manual work of unknown size, so v1 deliberately does not block anything on it. This track can start on day one and nothing else in v1 waits on it.

## Stories

- Story 7.1: Add a past report to the Corpus
- Story 7.2: Mark an entry paired or unpaired
- Story 7.3: See how much Corpus I actually have

## Requirements & Constraints

- A past report is added as free text and stored as text, regardless of its original source (email, messaging, a file). No per-source parsing or format handling.
- All Corpus data lives in Postgres. Nothing durable is written to the container filesystem.
- Every entry is marked either paired — matched to birth data and month — or unpaired — prose only.
- A paired entry links to an existing Client and month where one exists. A paired entry whose Client is not in the application stays marked paired with the link left unset; a Client is never invented to satisfy the link.
- The `CORPUS_ENTRY` table joins the Client-deletion cascade: deleting a Client removes every Corpus entry (pairing) that referenced them.
- A composition view shows the total entry count split into paired and unpaired, available at any time without a batch job or a manual query.
- Corpus routes carry the same authentication as every other route (single-principal auth; there is exactly one account).
- Corpus entries contain identifiable client material. **Anonymization position — settled 2026-08-28 (retro item 57):** Corpus content is stored **verbatim**, access is **operator-only** (single-principal auth). No anonymization is applied at ingest — it would break the paired-Client linkage the composition view depends on. **Binding requirement:** any phase-2 use of Corpus content as conditioning / exemplar data MUST anonymize (strip client name, birth date, birth place, and any other direct identifiers) before that content leaves the operator-only boundary. This gates no v1 story; do not build phase-2 consumption here.
- Corpus entries are part of the logical backup export and the restore rehearsal in later epics, so the `CORPUS_ENTRY` schema must be cleanly exportable and reconstructable.

## Technical Decisions

- This capability lives entirely in `shell/http/` (routes plus a small ingest/marking/counts UI) and `shell/adapters/postgres/`. It is governed only by the no-durable-state-on-the-host-filesystem decision. `core/` is not touched by this epic.
- Kept as a separate epic and build track from the review/export/history epic even though both are `shell/http/` + Postgres. Merging them would imply Corpus work is blocked until that epic ships, whereas this runs from day one.
- Data model: `CLIENT ||--o{ CORPUS_ENTRY` for paired entries only. The Client reference and month on an entry are optional — a paired entry can exist with them unset.
- The phase-2 seam is already fixed elsewhere and needs nothing from this epic: exemplars would later enter as an additional argument to the Generator port, changing no other contract. This epic only has to produce the count that decides whether that work is worth planning.
- Logging and telemetry around ingest must stay structured and must not carry Corpus prose or client-identifying content — identifiers only, consistent with the anonymization concern above.

## UX & Interaction Patterns

- Ingest is a paste-in text field; the interaction is source-agnostic, with no upload-per-format flow.
- Paired/unpaired is chosen when the entry is recorded; choosing paired optionally offers linking to an existing Client and month.
- The composition view is always reachable and shows total / paired / unpaired at a glance — it is a live read, not a generated report.
- UI follows the project's server-rendered stack (FastAPI routes, Jinja2 templates, HTMX).

## Cross-Story Dependencies

- Story 7.2's paired-linking depends on the Client record and month concepts from the Client/Natal-Chart epic, and must degrade gracefully when no matching Client exists.
- Story 7.1's `CORPUS_ENTRY` table must be wired into the Client-deletion cascade built in the Client-deletion story of an earlier epic.
- Corpus entries must be included in the logical backup export (review/export/history epic) and in the restore-from-export rehearsal (release-validation epic).
- The FR-24 composition count feeds phase-2 planning, which is out of scope for v1 — no v1 story consumes the count.
- The anonymization position is settled (see Requirements & Constraints, 2026-08-28): verbatim storage now, operator-only access, mandatory anonymization before any phase-2 use. Not a blocker for any story in this epic.
