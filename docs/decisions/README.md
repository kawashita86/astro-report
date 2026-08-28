# Ratified decisions index

Decisions that were **raised, ruled on, and ratified** rather than absorbed
silently into code or a spec — release-gate calls plus two adjacent policy /
accepted-deviation rulings routed here by name. Each decision already lives, in
full, in a source document: a `docs/release-validation/` record, a route
docstring, or an epic-context doc. This index is the discoverable pointer to
those rulings — one row per decision, one prose section giving the context, the
ruling, who ratified it and when, and links to the source and its ratifying
context.

- **Started** per epic-8 retrospective F9 / Action item 8 (tracker id
  `epic-8-retro-item-66`), which asked for a `docs/decisions/` index over the
  three ratified 8.2 / 8.3 / 8.4 release-gate decisions.
- **Items 49 and 57** (`GET`-with-side-effects, Corpus anonymization) are folded
  in here because `sprint-change-proposal-2026-08-28.md` routed them here by
  name — its §4 carries the rulings, its §5 the "fold into `docs/decisions/`"
  handoff. No other bucket-G item from that proposal was routed here.
- **Item 53** (backup-file operator handling — encryption at rest, retention,
  rotation) is a ratified bucket-H policy decision; its source doc is
  `docs/operations/backup-handling.md` and it is indexed here as **RGD-6**.
- **Not covered:** Story 8.5 (`docs/release-validation/restore-rehearsal.md`)
  has **no** ratified decision yet — its `outcome = "pass"` still outruns the
  evidence (epic-8 retro F5 / F6; tracker item 59). It joins this index only
  once the real operator rehearsal is run and ratified.
- **As of** 2026-08-28. A new `RGD-n` is added here by whoever ratifies the
  decision (or lands the change that records it); IDs are assigned in the order
  rows are added and are stable thereafter.

## Conventions

- **ID** — `RGD-<n>` (Ratified Gate/policy Decision), assigned in the order
  decisions are added here. Stable once assigned.
- **This index does not restate the reasoning.** The linked source is
  authoritative; if the two ever disagree, the source wins and this row is
  stale.
- **Superseding a decision** — do not delete the row. Prefix its Decision cell
  with **`Superseded by RGD-<n>`**, add the same note at the top of its prose
  section, and leave the rest intact.
- **RGD-4, RGD-5 and RGD-6 have no `docs/release-validation/` record** — their
  source is a route docstring, a context doc, or an operations runbook
  (`docs/operations/backup-handling.md` for RGD-6) — so they carry no
  `(Story 8.x)` heading tag and cite no TOML machine block, unlike
  RGD-1 / RGD-2 / RGD-3.
- A `docs/release-validation/` record whose `outcome` is still `blocked` can
  still carry a ratified sub-decision (see RGD-2) — the row records the ratified
  part and says what remains open.
- **Commit reference** — epic-8 retro F9 also wanted each ratified decision tied
  to a commit / PR. The commit that first recorded a decision here is that tie;
  add it to the row's prose "Links" block once it exists.

## Index

| ID | Decision | Ratified | Source |
|----|----------|----------|--------|
| [RGD-1](#rgd-1--gemini-data-terms-re-verification-is-a-benign-change-story-82) | Gemini data-terms re-verification: the 2026-03-23 revision is a benign change; `pass` | Francesco, 2026-08-27 | `docs/release-validation/gemini-data-terms.md` |
| [RGD-2](#rgd-2--regeneration-cost-is-a-recorded-known-limitation-the-latency-budget-is-not-revised-story-83) | Regeneration cost is a recorded known limitation; latency budget not revised | Francesco, 2026-08-27 | `docs/release-validation/latency.md` |
| [RGD-3](#rgd-3--storage-growth-50-ceiling-policy-story-84) | Storage-growth policy: move Neon to paid tier at 50% of the free-plan ceiling; no Payload pruning | Francesco, 2026-08-27 | `docs/release-validation/storage-growth.md` |
| [RGD-4](#rgd-4--get-with-side-effects-on-the-export-and-backup-routes-is-accepted) | `GET` with side effects on `/export/pdf`, `/export/markdown`, `/backup` is accepted | Francesco, 2026-08-28 | `shell/http/routes/report_runs.py`, `shell/http/routes/backup.py` |
| [RGD-5](#rgd-5--corpus-content-is-stored-verbatim-anonymization-is-a-phase-2-boundary-requirement) | Corpus stored verbatim, operator-only; anonymization mandatory before any phase-2 use | Francesco, 2026-08-28 | `_bmad-output/implementation-artifacts/epic-7-context.md` |
| [RGD-6](#rgd-6--backup-file-operator-handling-fde-only-monthly-rotation-keep-all) | `GET /backup` file: full-disk-encrypted machine only (no per-file encryption); monthly rotation; keep every backup | Francesco, 2026-08-28 | `docs/operations/backup-handling.md` |

---

## RGD-1 — Gemini data-terms re-verification is a benign change (Story 8.2)

**Context.** The zero-cost design (AD-9, PRD §6.2, NFR-17) depends on Google
applying its Paid-Services data terms — no training on submitted content, no
human review of submitted content — to the Gemini API free tier for the EEA, via
the EEA/CH/UK jurisdictional carve-out. The published terms had advanced to
"Effective March 23, 2026" since the 2026-01-15 planning reading, and a new
Paid-Services safety-logging clause (limited-retention abuse-detection logging)
had appeared.

**Decision.** Neither change touches PRD §6.2's two guarantees: limited-retention
abuse-detection logging is not model training and not human annotation. The
re-verification outcome is **`pass`** — the currently published terms preserve
both guarantees, hosting (Render `frankfurt`) and storage (Neon
`Europe/Frankfurt`) are in the EU/EEA, and the release may proceed. If a later
re-check finds guarantee (a) or (b) materially weakened for the EEA free tier,
set `outcome = "blocked"` and re-open the story — do not write `pass` over a
regression.

**Ratified.** Francesco, 2026-08-27 (`ratified_on` in the record's machine
block).

**Links.**
- Source: [`docs/release-validation/gemini-data-terms.md`](../release-validation/gemini-data-terms.md) — clause-by-clause comparison, verbatim quotes, `terms_snapshot` Wayback capture, re-verification trigger.
- Ratifying context: Story 8.2; PRD §6.2, NFR-17, AD-9. Retrospective note: [`epic-8-retro-2026-08-27.md`](../../_bmad-output/implementation-artifacts/epic-8-retro-2026-08-27.md) ("8.2 data terms — built as specced").

## RGD-2 — Regeneration cost is a recorded known limitation; the latency budget is not revised (Story 8.3)

**Context.** NFR-5 puts one Report at under 3 minutes at p90 and counts "any
bounded regeneration" toward that budget. The Story 8.3 measurement composed a
per-Report p90 of 119 s (1 s local pipeline + 118 s p90 of a live
`gemini-2.5-flash` n=10 sample) — within the 180 s budget, but a
**single-generation-call** figure. The same live sample found 8/10 drafts passed
citation / date-token validation on the first try, so a real Report has a ~20 %
chance of a second ~100 s generation call, landing at ~220–250 s, over budget.

**Decision.** Record the regeneration exposure as a known limitation in
`latency.md` and re-measure against real post-launch traffic
(`ExportRecord.elapsed_seconds` as a loose upper bound once traffic exists)
rather than revise the 3-minute budget number. The epic context carries the
matching carve-out: a run needing citation- or Gate-driven regeneration may
exceed the budget, and that case is a recorded known limitation, not a blocker.
No `epics.md` / PRD budget number changed — the budget-revision rule was
correctly a no-op.

**Ratified.** Francesco, 2026-08-27 (`ratified_on` in the record's machine
block). **Still open on the record itself:** `latency.md` currently carries
`outcome = "blocked"` / `sitting_confirmed = false` — the AC-4 human half
(Francesco's forty-report one-sitting produce → review → export) has not yet
happened (tracker item 61 — the AC-4 human sitting; guard hardening is tracker
item 65). That is a separate outstanding step; the regeneration-scope decision
recorded here is settled independently of it.

**Links.**
- Source: [`docs/release-validation/latency.md`](../release-validation/latency.md) — "Known limitation — regeneration is not in the composed p90" and "Re-measure against real post-launch traffic".
- Ratifying context: Story 8.3 AC; PRD Assumptions Index items 3 and 4 (`RESOLVED 2026-08-27`); `epics.md` NFR-5 / NFR-10. Retrospective finding: [`epic-8-retro-2026-08-27.md`](../../_bmad-output/implementation-artifacts/epic-8-retro-2026-08-27.md) F3.

## RGD-3 — Storage-growth 50%-ceiling policy (Story 8.4)

**Context.** Report Payloads are stored permanently (NFR-9 — a lost Payload
permanently breaks its Report's traceability guarantee) on Neon's 0.5 GB free
plan. The PRD carries no storage budget. Story 8.4 measured a real persisted
`report_payload` row (`payload_p90_bytes = 64259` over `sample_n = 12`,
canonical-JSON byte length) and projected growth at 200 Reports/month against
the 0.5 GB ceiling: half the ceiling is dated `half_ceiling_reached_on =
2027-09-26` on the payload-only machine block (~13 months after the
`checked = 2026-08-27` date) and ~10 months out on the realistic
full-per-Report footprint. Both land inside any reasonable planning horizon, so
Story 8.4 AC-3 ("raised as an explicit decision rather than absorbed") fires.

**Decision** (`policy_decision = "raised"`): *When Neon storage crosses 50 % of
the 0.5 GB free-plan ceiling, move the Neon project to its paid tier and
renegotiate the €0/month target (NFR-7) as an explicit, recorded cost decision.
Do not prune, archive, TTL, or export-and-delete Report Payloads — NFR-9 makes
Payload loss unacceptable and the traceability guarantee has no expiry.* The
trigger is the **Neon dashboard storage gauge** (checked monthly, or a Neon
usage alert at ~40–50 %), not the projected dates. Designing any
storage-reclamation mechanism is explicitly out of scope — raising the decision
is the deliverable. Outcome **`pass`**; release may proceed.

**Ratified.** Francesco, 2026-08-27 (`ratified_on` / `policy_ratified_on` in the
record's machine block). Open sub-item: the entry paid-plan monthly price to
attach at ratification is Francesco's to confirm from Neon's pricing page.

**Links.**
- Source: [`docs/release-validation/storage-growth.md`](../release-validation/storage-growth.md) — "Storage-growth policy (decision)", the full-footprint projection, and the re-measure trigger.
- Ratifying context: Story 8.4 AC-3; NFR-9, NFR-5 / NFR-7; README "Running cost" table. Retrospective finding: [`epic-8-retro-2026-08-27.md`](../../_bmad-output/implementation-artifacts/epic-8-retro-2026-08-27.md) F4 (disclosed measurement-basis limitation, deferred separately).

## RGD-4 — `GET` with side effects on the export and backup routes is accepted

**Context.** Three `GET` routes mutate and commit on every hit:
`GET /report-runs/{run_id}/export/pdf` and its `download_report_markdown`
sibling each write an `ExportRecord` row and, on the first successful export,
advance `run.stage` to `"exported"`; `GET /backup` serves the operator backup
(built fully in memory, `Cache-Control: no-store`) and, on `?record=1`, writes a
`backup_record` row. A `GET` that mutates is normally a smell — an incidental
hit from a browser prefetch or a crawler triggers the side effect.

**Decision.** Accept it, as a documented deviation rather than a bug.

- **`/backup`** — the `backup_record` write (which Story 6.6's staleness warning
  reads) is gated behind `?record=1` (retro-C item 49), so a bare
  `GET /backup` cannot silently clear the warning. Moving the download itself to
  `POST` was declined — it is a plain-link download.
- **`/export/pdf` and `/export/markdown`** — kept on `GET` on the same
  rationale, with **no** `?record=1`-style guard: an incidental hit only writes
  a harmless extra `ExportRecord`, and the `run.stage` advance is monotonic and
  idempotent, so there is no analogue here of the staleness-warning-clearing
  risk that motivated gating `/backup`'s record write.

**Ratified.** Francesco, 2026-08-28 (`sprint-change-proposal-2026-08-28.md` §4,
item 49; the `/backup` half was ratified earlier under retro-C item 49).

**Links.**
- Source: [`shell/http/routes/report_runs.py`](../../shell/http/routes/report_runs.py) — `download_report_pdf` docstring, "Accepted GET-with-side-effects deviation (epic-6-retro-item-49)"; [`shell/http/routes/backup.py`](../../shell/http/routes/backup.py) — `download_backup` docstring and the `?record=1` gate.
- Ratifying context: [`sprint-change-proposal-2026-08-28.md`](../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-28.md) §4 item 49; retrospective items `epic-6-retro-item-49` and retro-C item 49.

## RGD-5 — Corpus content is stored verbatim; anonymization is a phase-2 boundary requirement

**Context.** Corpus entries contain identifiable client material (name, birth
date, birth place). The question was whether to anonymize or pseudonymize at
ingest. Anonymizing at ingest would break the paired-Client linkage the
composition view depends on — the whole point of the Corpus — or require a
re-identification mapping table carrying the same risk as verbatim storage.

**Decision.** Store Corpus content **verbatim**. Access is **operator-only**
(single-principal auth; there is exactly one account). **No anonymization at
ingest.** Logging and telemetry around ingest stay identifiers-only — no Corpus
prose, no client-identifying content. **Binding requirement:** any phase-2 use
of Corpus content as conditioning / exemplar data MUST anonymize (strip client
name, birth date, birth place, and any other direct identifiers) before that
content leaves the operator-only boundary. This gates no v1 story; phase-2
consumption is not built here.

**Ratified.** Francesco, 2026-08-28.

**Links.**
- Source: [`_bmad-output/implementation-artifacts/epic-7-context.md`](../../_bmad-output/implementation-artifacts/epic-7-context.md) — Requirements & Constraints ("Anonymization position — settled 2026-08-28"); [`spec-7-2-mark-an-entry-paired-or-unpaired.md`](../../_bmad-output/implementation-artifacts/spec-7-2-mark-an-entry-paired-or-unpaired.md).
- Ratifying context: [`sprint-change-proposal-2026-08-28.md`](../../_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-28.md) §4 item 57; retrospective item `epic-7-retro-item-57`.

## RGD-6 — backup-file operator handling: FDE-only, monthly rotation, keep all

**Context.** `GET /backup` (`shell/http/routes/backup.py`, Story 6.5) serves a
full unencrypted plaintext JSON dump of every durability-relevant table —
every Client's name, birth date, and birth place included. It is the
application's real durability mechanism (AD-17: Neon's free plan has no
scheduled backups). No policy governed the downloaded file once it left the
route (epic-6 retro / tracker item `epic-6-retro-item-53`).

**Decision.**

- **Encryption at rest — full-disk encryption only, no per-file encryption.**
  Backup files are kept only on a full-disk-encrypted personal machine
  (FileVault / LUKS). The plaintext JSON must never come to rest on a
  non-FDE volume (USB stick, sync folder, consumer cloud drive). No
  `age`/`gpg` wrapping. Accepted residual: anyone with the machine unlocked
  can read every Client's PII — accepted under the single-operator model.
  Per-file encryption becomes mandatory if a second person needs a copy or a
  backup must leave the FDE machine.
- **Retention / rotation — monthly, keep every backup.** Take a fresh backup
  monthly via the reports page "Back up now" link (`GET /backup?record=1`, so
  Story 6.6 staleness tracking sees it). Do not delete old backups. Story 6.6's
  in-app staleness warning is the cadence reminder.
- **Decommission.** Destroy the FDE key before the disk leaves the operator's
  control.

**Ratified.** Francesco, 2026-08-28.

**Links.**
- Source: [`docs/operations/backup-handling.md`](../operations/backup-handling.md) — full policy, rationale, decommission step.
- Ratifying context: retrospective item `epic-6-retro-item-53`. Related: **RGD-4** (the `GET`-with-side-effects deviation on the same route) and **RGD-5** (Corpus PII position).
