# Sprint Change Proposal — 2026-08-28

**Workflow:** Correct Course
**Trigger:** Retrospective action-item bucket **G — "Needs your decision, not code."**
Ten open items across the epic 1–8 retrospectives were parked because they required a
human ruling (scope, policy, or design) before any implementation could proceed. This
proposal records the rulings, the planning-artifact edits already applied, and the
resulting dev-loop handoffs.
**Mode:** Batch.
**Owner:** Francesco (decisions captured 2026-08-28).
**Change scope classification:** **Moderate** — no replan; backlog reorganization only
(one new spec scheduled, tracker statuses updated, three context/spec docs amended). No
architecture change. Routed to the dev loop + Francesco as noted per item.

---

## Section 1 — Issue Summary

Across eight epic retrospectives, the "Action items" triage separated work that the dev
loop could execute directly from items that first needed Francesco to decide something a
retrospective is not entitled to decide on its own: whether a shipped scope gap is
accepted, what the anonymization policy for identifiable client data is, whether a type
should gain a capability, whether a GET route may keep its side effects. Those items were
bucketed as **G** and left `open` with no owner able to move them.

This proposal closes bucket G. Each item below carries: the decision, the rationale, what
was edited now, and what the dev loop picks up.

The ten items (master retro numbering; tracker id in parentheses):

| # | Tracker id | Topic |
|---|---|---|
| 6  | `epic-1-retro-item-6-decide-whether-computationconfig-rulers` | `ComputationConfig`/`Rulers` hashability |
| 11 | `epic-2-retro-item-11-have-chart_wheel_view-compare-the-stored` | Stale-config detection in `chart_wheel_view` |
| 14 | `epic-2-retro-item-14-link-create_client-s-and-correct_client` | Link client create/correct response → chart view |
| 17 | `epic-2-retro-item-17-decide-computationconfig-rulers-hashabil` | Same as 6 + the misleading `Rulers` docstring |
| 45 | `epic-5-retro-item-45-propose-persisting-gatevocabulary-conten` | Persist `GateVocabulary.content_hash` on gate rows |
| 47 | `epic-6-retro-item-47-decide-the-markdown-export-scope-gap-epi` | Markdown export scope gap |
| 49 | `epic-6-retro-item-49-decide-get-with-side-effects-for-get-bac` | GET-with-side-effects (`/backup`, `/export/pdf`) |
| 50 | `epic-6-retro-item-50-give-the-client-facing-export-pdf-human` | Client PDF headings + print CSS |
| 57 | `epic-7-retro-item-57-settle-the-anonymization-position-on-cor` | Corpus anonymization position |
| 65 | `epic-8-retro-item-65-harden-the-outcome-pass-guard-against-pa` | `outcome=="pass"` guard hardening design |

---

## Section 2 — Impact Analysis

**Epic impact:** None re-opened. Epic 6 gains one scheduled follow-up story
(`spec-6-2b-markdown-export.md`); its context doc is annotated. Epic 7's recorded open
question is closed. No epic's acceptance verdict changes.

**Story impact:** One new spec (`spec-6-2b`, `ready-for-dev`). No existing story spec's
intent changes; `spec-7-2` gets a factual amendment (open question → settled ruling).

**Artifact conflicts resolved:**
- `epic-6-context.md` "Both PDF and Markdown must be produced" vs. PDF-only delivery —
  resolved by keeping the requirement and scheduling `spec-6-2b`, with a post-epic
  amendment note added to the context doc.
- `epic-7-context.md` / `spec-7-2` "anonymization is an open question" — resolved by the
  ruling in item 57, applied to both docs.

**Technical impact:** Seven dev-loop follow-ups (items 6/17, 11, 14, 45, 49, 50, 65),
all small, none architectural, none blocking each other except that item 50's
`snake_case → Italian-title` map is a prerequisite for `spec-6-2b`'s headings. No
migration is required by any bucket-G decision (item 45's column is explicitly deferred
to the next Gate-touching change; item 65 adds fields to Markdown release-validation
records, not the DB).

---

## Section 3 — Recommended Approach

**Direct adjustment** — no rollback, no MVP re-scoping. Every item is resolved by a
recorded decision plus, where a decision unblocks code, a restated dev-loop task in
`sprint-status.yaml`. One item (47) is resolved by scheduling a new story rather than
descoping.

Effort: the seven code follow-ups are each well under half a day; `spec-6-2b` is a thin
sibling of the existing PDF export route. Risk: low across the board — the highest-stakes
call is item 57 (a policy that binds future phase-2 work), and it is the conservative
option (store as-is now, hard requirement before any external use).

---

## Section 4 — Detailed Change Proposals

### Item 6 + 17 — `ComputationConfig`/`Rulers` hashability
**Decision:** Do **not** add hashability. `frozen=True` does not make these types
hashable at runtime (`Rulers.traditional`/`modern` are `MappingProxyType`, so
`hash(Rulers(...))` raises `TypeError`), but no consumer needs it — a graph check found
only type-hint uses, nothing dict-keys or caches on a `ComputationConfig`. `content_hash`
is already the identity/cache key that role would want.
**Rationale:** Cheapest resolution; converting the ruler tables to tuple-of-pairs adds
API friction for a capability nothing uses.
**Applied now:** `sprint-status.yaml` — item 6 → `done`; item 17 → `open` with the
residual narrowed to the docstring fix.
**Dev-loop handoff (item 17):** correct the `Rulers` docstring at
`core/types/computation.py:60-68` — state it is deliberately non-hashable and point
readers at `content_hash`. One-line-ish doc change, no behavior.

### Item 11 — stale-config detection in `chart_wheel_view`
**Decision:** **Warn, do not refuse, do not defer.** `chart_wheel_view`
(`shell/http/routes/chart.py:44`) renders stored positions but recomputes aspects at
today's `orbs.natal`. On `stored_chart.computation_config_content_hash !=
request.app.state.computation_config.content_hash`, show a **non-blocking warning banner**
in `chart_wheel.html`.
**Rationale:** The wheel is a verification aid, not a frozen artifact (the Report freezes
its own config hash into `ReportPayload`). Refusing would block a legitimate check after
any `computation.toml` edit; silence is dishonest.
**Applied now:** `sprint-status.yaml` — item 11 action restated, owner → dev loop,
decision recorded.
**Dev-loop handoff:** the hash comparison + banner. No refusal path.

### Item 14 — link client create/correct response → chart view
**Decision:** **Do it.** Link `create_client`'s and `correct_client`'s success response
to `GET /clients/{id}/chart`.
**Rationale:** Trivial, and it directly serves epic 2's stated purpose ("get a natal
chart I can verify"). No reason to carry it as an open question.
**Applied now:** `sprint-status.yaml` — owner → dev loop, decision recorded.
**Dev-loop handoff:** the redirect/link.

### Item 45 — persist `GateVocabulary.content_hash` on gate rows
**Decision:** **Accept the addition; fold it into the next change that legitimately
touches `StoredGateResult` or the Gate write path.** Not a standalone story.
**Rationale:** `content_hash` exists precisely to catch a forgotten `version` bump on a
vocabulary content edit; today `StoredGateResult` persists only `vocabulary_version`
(int), so that failure mode is undetectable after the fact. The fix is one column + one
write-site — cheap insurance — but adding a column now, while the migration chain is
still fragile (retro item 46), argues against a dedicated migration this week.
**Applied now:** `sprint-status.yaml` — item 45 action rewritten as a concrete
opportunistic task, owner → dev loop (opportunistic).
**Dev-loop handoff:** when next in `StoredGateResult` / the Gate write path, add the
`vocabulary_content_hash` column and populate it.

### Item 47 — Markdown export scope gap
**Decision:** **Schedule the Markdown follow-up spec.** The "Both PDF and Markdown"
requirement is **kept, not descoped**.
**Rationale:** Markdown export is a thin transform of the same eight-Section content model
the PDF route already produces; it belongs in the product, just not inside epic 6's
closed delivery.
**Applied now:**
- New: `_bmad-output/implementation-artifacts/spec-6-2b-markdown-export.md`
  (`status: ready-for-dev`) — `GET /report-runs/{run_id}/export/markdown`, same
  structural gate and `ExportRecord` semantics as the PDF route, `format="markdown"`, no
  schema change, no migration.
- `epic-6-context.md` — post-epic amendment note at the top: read every "PDF and
  Markdown" phrasing as PDF-in-epic-6, Markdown-in-`spec-6-2b`.
- `sprint-status.yaml` — item 47 → `ready-for-dev`, pointed at the new spec.
**Dev-loop handoff:** build `spec-6-2b` (after / with item 50's title map).

### Item 49 — GET-with-side-effects
**Decision:** **Accept and document as an accepted deviation.** The `/backup` half is
already done (retro-C item 49: `backup_record` write gated behind `?record=1`). For
`GET /report-runs/{run_id}/export/pdf`, which still advances `run.stage`, writes an
`ExportRecord`, and commits on every hit: keep it, same rationale already ratified for
`/backup` (plain-link download; moving to POST declined).
**Rationale:** An incidental hit on `/export/pdf` writes a harmless extra `ExportRecord`;
`run.stage` advance is monotonic and idempotent. There is no PII-clearing risk here — the
risk that motivated the `/backup` guard (silently clearing the Story 6.6 staleness
warning) has no analogue.
**Applied now:** `sprint-status.yaml` — item 49 action restated as a docstring note,
decision recorded.
**Dev-loop handoff:** add a docstring note to `download_report_pdf`
(`shell/http/routes/report_runs.py`) recording the accepted deviation. Record it in
`docs/decisions/` once retro item 66 (start that index) lands. No behavior change.

### Item 50 — client-facing PDF headings + print CSS
**Decision:** **Do both now** — the shared `snake_case → Italian-title` map and minimal
print CSS in `report_export.html`, as one small change.
**Rationale:** The title map is the reusable part (also improves `report.html` /
`report_draft.html`) and is a prerequisite for `spec-6-2b`'s Markdown headings; the print
CSS is cheap while in that file.
**Applied now:** `sprint-status.yaml` — decision recorded.
**Dev-loop handoff:** build it; do it before or with `spec-6-2b`.

### Item 57 — Corpus anonymization position
**Decision:** **Store Corpus content verbatim. Operator-only access (single-principal
auth). No anonymization at ingest** — it would break the paired-Client linkage the
composition view depends on. **Binding requirement:** any phase-2 use of Corpus content
as conditioning / exemplar data MUST anonymize (strip client name, birth date, birth
place, and any other direct identifiers) before that content leaves the operator-only
boundary. Logging stays identifiers-only, as today.
**Rationale:** Pseudonymizing at ingest would either lose the pairing signal (the whole
point of the Corpus) or require a re-identification mapping table that carries the same
risk as storing verbatim. The exposure today is one operator on an authenticated route;
the real risk surface is phase-2, and that is where the control is mandated.
**Applied now:**
- `epic-7-context.md` — the open-question bullet replaced with the ruling; the
  cross-story-dependency line updated.
- `spec-7-2` — both "open question" references replaced with the settled ruling.
- `sprint-status.yaml` — item 57 → `done`, full ruling recorded in `decision:`.
**Handoff:** none for v1. Phase-2 planning must carry the anonymization requirement as a
gating constraint. Record in `docs/decisions/` once item 66 lands.

### Item 65 — `outcome=="pass"` guard hardening design
**Decision:** **Confirmed the per-record field design.** `restore-rehearsal.md` must
carry `rehearsed_against == "real-postgres"`; `latency.md` must carry `sitting_confirmed
== true`; the guard rejects `outcome == "pass"` when the record's required field is
absent or not the required value. Bespoke field names per record, not one generic field.
Bundle with the item-62 `tests/_release_validation.py` follow-up.
**Rationale:** A generic `external_evidence` field pushes the real check into a per-record
value schema anyway; named fields make each record's missing step obvious at a glance.
**Applied now:** `sprint-status.yaml` — item 65 action restated with the confirmed
design, decision recorded.
**Dev-loop handoff:** implement the guard fields alongside item 62.

---

## Section 5 — Implementation Handoff

**Scope:** Moderate. No PM/Architect involvement.

**Applied by this proposal (no further action):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 10 action-item entries
  updated (`decision:` + `decided_on:` fields; statuses: item 6 → `done`, 47 →
  `ready-for-dev`, 57 → `done`, rest `open` with owner → dev loop).
- `_bmad-output/implementation-artifacts/epic-6-context.md` — post-epic amendment note
  (item 47).
- `_bmad-output/implementation-artifacts/epic-7-context.md` — anonymization ruling
  (item 57).
- `_bmad-output/implementation-artifacts/spec-7-2-mark-an-entry-paired-or-unpaired.md` —
  anonymization ruling (item 57).
- `_bmad-output/implementation-artifacts/spec-6-2b-markdown-export.md` — new spec stub
  (item 47), `ready-for-dev`.

**Routed to the dev loop (small, independent unless noted):**
1. Item 17 — fix the `Rulers` docstring (`core/types/computation.py`).
2. Item 11 — config-hash mismatch warning banner in `chart_wheel_view` / `chart_wheel.html`.
3. Item 14 — link client create/correct success → `GET /clients/{id}/chart`.
4. Item 50 — shared `snake_case → Italian-title` map + print CSS (**do before item 47**).
5. Item 47 — build `spec-6-2b-markdown-export.md` (**after item 50**).
6. Item 49 — accepted-deviation docstring note on `download_report_pdf`.
7. Item 65 — `outcome=="pass"` guard fields, bundled with item 62.
8. Item 45 — opportunistic: `vocabulary_content_hash` column on `StoredGateResult` next
   time that write path is touched.

**Routed to Francesco:**
- Approve `spec-6-2b` (currently `ready-for-dev` as a drafted stub).
- Carry item 57's anonymization requirement into any phase-2 planning.
- Fold items 49 and 57 into `docs/decisions/` when retro item 66 is actioned.

**Success criteria:** bucket G is empty (every item `done` or an `open`/`ready-for-dev`
dev-loop task with a recorded decision and an owner who can move it); `spec-6-2b` builds
green against `tests/test_export_boundary.py`; `epic-7-context.md` and `spec-7-2` no
longer describe anonymization as unresolved.
