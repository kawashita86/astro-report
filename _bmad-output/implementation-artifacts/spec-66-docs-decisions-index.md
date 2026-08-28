---
title: 'docs/decisions/ index for ratified release-gate decisions'
type: 'chore'
created: '2026-08-28'
status: 'done'
route: 'one-shot'
review_loop_iteration: 0
context: []
---

# docs/decisions/ index for ratified release-gate decisions

## Intent

**Problem:** epic-8 retro F9 / action item 66 flagged that the ratified 8.2 / 8.3 / 8.4
release-gate decisions live only as same-day, same-person prose inside their own
`docs/release-validation/` records, with nothing pointing at them — "raised as an explicit
decision rather than absorbed" is satisfied in-file but not discoverable. The
`sprint-change-proposal-2026-08-28.md` additionally routed items 49 (`GET`-with-side-effects)
and 57 (Corpus anonymization) to the same not-yet-existing index.

**Approach:** Add a single `docs/decisions/README.md` — a lightweight index log: intro,
conventions, one index-table row + one prose section per decision (RGD-1..RGD-5), each
linking its source document and ratifying context. No decision is re-litigated; the source
stays authoritative. Add a short back-pointer from each of the three release-validation
records and both affected route docstrings, and close action item 66 in `sprint-status.yaml`.

## Suggested Review Order

**The index**

- Entry point — the five decisions at a glance; check each row's anchor link resolves and the Ratified column matches its source.
  [`README.md:49`](../../docs/decisions/README.md#L49)

- Scope rationale: why 8.2/8.3/8.4 plus items 49/57, why not other bucket-G items, and why Story 8.5 is explicitly excluded.
  [`README.md:1`](../../docs/decisions/README.md#L1)

- Conventions — ID assignment, source-wins-on-conflict, the supersede mechanism, and why RGD-4/5 carry no Story tag.
  [`README.md:27`](../../docs/decisions/README.md#L27)

- RGD-1/2/3 prose — verify each against its cited `docs/release-validation/` record (dates, outcome, the `blocked`-but-ratified nuance in RGD-2).
  [`README.md:59`](../../docs/decisions/README.md#L59)

- RGD-4/5 prose — the two folded-in rulings; check RGD-4's `/backup` description matches `backup.py` (in-memory, `no-store`, not "streamed").
  [`README.md:147`](../../docs/decisions/README.md#L147)

**Back-pointers into the sources**

- One line each tying the record back to its RGD; placed outside the parsed TOML block so the record guards are unaffected.
  [`gemini-data-terms.md:10`](../../docs/release-validation/gemini-data-terms.md#L10)
  [`latency.md:17`](../../docs/release-validation/latency.md#L17)
  [`storage-growth.md:217`](../../docs/release-validation/storage-growth.md#L217)

- Route docstrings: the forward-reference "once retro item 66 lands" is now resolved to "Recorded ... as RGD-4".
  [`report_runs.py:483`](../../shell/http/routes/report_runs.py#L483)
  [`backup.py:127`](../../shell/http/routes/backup.py#L127)

**Tracker**

- Action item 66 → `done` with a decision note; item 49's "record once item 66 lands" resolved.
  [`sprint-status.yaml:710`](../../_bmad-output/implementation-artifacts/sprint-status.yaml#L710)
