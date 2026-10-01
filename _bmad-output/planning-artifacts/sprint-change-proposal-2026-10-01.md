# Sprint Change Proposal — 2026-10-01

**Project:** astro-report · **Author:** Developer (correct-course) for Francesco · **Mode:** Batch
**Change scope:** Major (spine amendments AD-9, AD-10, AD-20, new AD-21; SPEC constraints; new epic)
**Status:** Approved by Francesco 2026-10-01 — document edits §4.1–4.5 applied; §4.6 `AGENTS.md` and `.env.example` lines land with Stories 10.4 / 10.2

---

## Section 1: Issue Summary

**Trigger.** Two operator-facing slownesses, raised by Francesco on 2026-10-01 while comparing
astro-report with its sibling project md-report (same stack, same VPS, same Gemini provider):

1. **Report generation is slow.** The `draft_ready` stage asks Gemini for all eight Sections in a
   single structured call. md-report writes one call per Section in parallel, then its closing
   Section last, and feels much faster.
2. **PDF export takes 20–25 s in production.** md-report's PDF takes a couple of seconds.

**Category.** Failed approach requiring a different solution (single-call generation does not meet
the latency the operator needs), plus a technical limitation discovered in production (WeasyPrint
layout cost).

**Evidence.**

| Measurement | Value | Source |
|---|---|---|
| One full-report `gemini-2.5-flash` call, p90 | **118 s** | `docs/release-validation/latency.md` (`real_gen_p90_seconds`) |
| Composed per-Report p90 (single generation, no regeneration) | 119 s of a 180 s budget | same |
| Each Gate-triggered regeneration | +1 full 8-Section call (~118 s), up to 2 (`_MAX_REGENERATIONS`) | `shell/runner/driver.py` |
| PDF render, local, realistic-length text + real 145 KB wheel | **3.5 s** | profiled 2026-10-01 |
| Same, with `display:flex/grid` replaced by block layout | **1.0 s** | profiled 2026-10-01 |
| Same, without `@font-face` / without the wheel | 3.1 s / 2.9 s | profiled 2026-10-01 |
| PDF render, production | 20–25 s | operator report |

The profile is dominated by WeasyPrint's `flex_layout` → `min_content_width` →
`split_first_line`: `report_export.html` places long prose inside ~20 nested flex/grid containers,
and WeasyPrint re-measures every word of every paragraph several times to size them. Production is a
slower vCPU with a single uvicorn worker, which turns 3.5 s into 20–25 s. md-report also stores each
exported PDF (`exported_pdf.pdf_bytes` + `fingerprint`) so a repeat download does not re-render.

**Decisions already made by Francesco (2026-10-01):**

- Gemini runs on a **paid** account with **`gemini-2.5-flash`**, uniform with md-report (which moved
  from `gemini-2.5-pro` to flash via `GEMINI_MODEL` because pro was too slow). The free-tier
  10-requests-per-minute assumption is obsolete.
- **Adopt md-report's architecture wholesale**, integrated with astro-report's existing contracts:
  per-Section parallel generation, Consiglio finale last, per-Section persistence, a background
  driver with leases and a process-wide concurrency cap, per-Section regeneration, and the
  progressive Section-by-Section UI.
- The PDF fix includes md-report's **stored-PDF cache**, not only the layout fix.

---

## Section 2: Impact Analysis

### Checklist status

| # | Item | Status | Note |
|---|---|---|---|
| 1.1 | Triggering story | [x] | No single story; observed in production use after Epics 4–6 and 8-3 (latency measured) |
| 1.2 | Core problem | [x] | Single-call generation and flex-heavy PDF layout |
| 1.3 | Evidence | [x] | Table above |
| 2.1 | Current epic (9, in review) | [x] | Unaffected except 9-5's stage track, superseded for the draft stage by Story 10.6 |
| 2.2 | Epic-level change | [!] | **Add Epic 10** |
| 2.3 | Remaining epics | [x] | 7 and 8 are done; nothing else planned |
| 2.4 | New epics needed | [!] | Epic 10 only |
| 2.5 | Resequencing | [x] | Story 10.1 (PDF) is independent and goes first |
| 3.1 | PRD | [!] | FR-19, FR-21, NFR throughput/latency |
| 3.2 | Architecture | [!] | AD-9, AD-10, AD-20 amended; new AD-21; BUILD-ORDER E5/E8 notes |
| 3.3 | UX | [!] | EXPERIENCE.md *Report Run Lifecycle*, *Polling*, *Loading* |
| 3.4 | Other artifacts | [!] | `AGENTS.md`, `docs/release-validation/gemini-data-terms.md` + its test, `latency.md`, `.env.example`, guard tests |
| 4.1 | Direct adjustment | Viable | Chosen |
| 4.2 | Rollback | Not viable | Nothing to revert; the single-call adapter's validations are reused |
| 4.3 | MVP review | Not needed | Scope is unchanged; only the mechanism changes |

### Epic impact

- **Epics 1–8:** done; no rework. Their contracts (Payload, aliases, Gate, export gate, review
  surfaces) are reused unchanged.
- **Epic 9 (in review):** Story 9-5's stage track still renders the cheap stages
  (`natal_ready → transits_ready → payload_ready`) and `gate_passed`; during `draft_ready` it is
  replaced by the Section rail of Story 10.6.
- **New Epic 10** — *Fast reports: parallel Section generation and instant PDF.*

### Artifact conflicts

| Artifact | Conflict |
|---|---|
| `ARCHITECTURE-SPINE.md` AD-9 | Rationale cites free-tier rate limits as the thing backoff absorbs |
| AD-10 | *"Automatic regeneration under FR-21 replaces the whole Report, never a single failing Section"* — directly contradicted |
| AD-20 | Forbids threads, async tasks and executors; `REPORT_RUN_MODE=poll` is the default |
| `SPEC.md` Constraints | *"no … background worker process. A report run is advanced only by the operator's own polling"*; the Generator *"receives … nothing else"* (Consiglio finale must receive the other seven Sections) |
| PRD FR-21 | Says *the Report* is regenerated |
| `EXPERIENCE.md` | *Report Run Lifecycle* describes poll-driven advance and a single stage-track wait |
| `gemini-data-terms.md` | Records `tier = "free"`; AD-9 requires re-verification on a provider/terms change |
| `AGENTS.md` | No mention of the one permitted thread/executor site |

### Technical impact

- **New table** `report_draft_section` (forward-only Alembic migration). The existing
  `report_draft` row (one assembled JSON draft per attempt) is **kept** as the Gate's and export's
  input, so AD-7, `StoredGateResult`, the review/hand-correct surfaces and `export_report()` are
  untouched.
- **New `Generator` port method** `generate_section(...)`; the existing per-call machinery (short id
  aliases, enum-constrained `entry_ids`, count-pinned day-list schemas, alias-leak / citation /
  no-date-token / day-list-coverage validation, continuity block) is reused per Section.
- **New `shell/runner/` driver**: an in-process `ThreadPoolExecutor` capped by
  `GENERATION_CONCURRENCY` (default 11, max 32 — md-report's values), leases on Section rows, resume
  after restart. Generation threads compute no charts, so the Swiss Ephemeris per-thread pitfall does
  not apply, but the driver's guard test asserts no chart code is reachable from it.
- **Cost:** the Payload is sent once per Section (8×) instead of once. On paid flash this is cheap,
  and Gemini's implicit prefix caching applies if every call shares an identical prefix (system
  instruction + Payload), with the Section-specific instruction placed **last**.
- **Paid tier:** flash's paid Tier-1 limit is far above 9 concurrent requests per Report; backoff
  stays for transient errors only.
- **Deployment:** Coolify single container, always on — the "no idle spin-down" prerequisite of
  AD-20's background mode already holds. No new service, queue or broker.

### Expected outcome

| | Today | After Epic 10 (estimate) |
|---|---|---|
| Draft generation | ~118 s p90 (one 8-Section call) | ~slowest narrative Section + Consiglio finale ≈ **35–60 s** |
| One Gate-triggered regeneration | +~118 s | +one Section (~20–30 s) plus Consiglio finale if affected |
| PDF first export (prod) | 20–25 s | ~4–6 s (scaled from 3.5 s → 1.0 s locally) |
| PDF repeat download | 20–25 s | instant (stored bytes) |

The generation figures are estimates; Story 10.7 measures them and updates `latency.md`.

---

## Section 3: Recommended Approach

**Direct adjustment:** add Epic 10 with seven stories, amend the spine, SPEC, PRD and UX documents,
and keep every existing correctness contract (Payload, aliases, Gate, export gate, review paths).

**Key design choices** (ported from md-report, adapted to astro-report's Gate):

1. **Section rows hold the progress; the assembled draft stays the Gate's input.** Each draft
   attempt gets eight `report_draft_section` rows. When all eight are `complete`, the driver
   assembles them into one `report_draft` row — the same JSON shape as today — and the run moves to
   `gate_passed` exactly as now.
2. **Fan-out, then Consiglio finale.** Sections 1–7 are claimable at once; Section 8 becomes
   claimable only when 1–7 are all `complete`, and receives their sentences (text only, no ids) as
   context. It still cites only Payload ids.
3. **The driver always runs in the background; `REPORT_RUN_MODE` is retired.** md-report's model:
   `start` returns immediately, a per-run loop advances every stage, and draft generation fans out
   into the executor. The poll handler becomes read-only everywhere. On startup, `resume()` restarts
   every incomplete run (the boot-time reconciliation AD-20 explicitly skipped is now included,
   since md-report already has it).
4. **Per-Section regeneration.** A failing Gate check names its Sections (`violation.section`
   already exists). Only those Sections are reset to `pending` in a new attempt; the passing ones are
   copied forward. If any Section 1–7 is regenerated, Consiglio finale is regenerated too, because it
   summarizes them. `_MAX_REGENERATIONS` keeps its meaning — Gate-triggered regeneration cycles per
   run — so SM-5 counts stay comparable. `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION`, accept and
   hand-correct are unchanged.
5. **Per-Section transient failures** retry inside the Section (bounded attempts with
   `last_error`, md-report's `MAX_SECTION_ATTEMPTS`). A Section that exhausts its attempts fails the
   run with the Section named; no partial Report is ever exportable (FR-19 holds).

**Effort:** High overall (10.1 Low, 10.2 Low, 10.3 Medium, 10.4 High, 10.5 Medium, 10.6 Medium,
10.7 Low). **Risk:** Medium — the riskiest parts (driver, leases, resume) are a port of code that
already runs in production in md-report. Main quality risk: Sections written independently may
repeat each other; mitigated by the shared continuity block, the Style Guide's Section territories
and Consiglio finale seeing everything. Story 10.7 includes a side-by-side read of five reports.

**Alternatives rejected:**
- *Parallel calls inside the poll request* (keep AD-20 as written): keeps the request open for the
  whole fan-out, does not survive a redeploy, and gives no progressive UI.
- *Keep one call, switch model/turn thinking off:* helps one call, but keeps whole-report
  regeneration and gives no progressive UI.

---

## Section 4: Detailed Change Proposals

### 4.1 Architecture — `ARCHITECTURE-SPINE.md`

**AD-9 — Rule, last sentence**

OLD:
> Rate limits and transient failures are absorbed by bounded backoff and by run checkpointing (AD-10).

NEW:
> Rate limits and transient failures are absorbed by bounded backoff and by run checkpointing (AD-10).
> **(Amended 2026-10-01, correct-course):** the configured adapter is Gemini on a **paid** account;
> the model is a setting (`GEMINI_MODEL`, default `gemini-2.5-flash`, read only in
> `shell/config.py`), and so is the process-wide cap on concurrent Generator calls
> (`GENERATION_CONCURRENCY`, default 11, max 32). Changing the model is a configuration change;
> changing the provider or the account's terms still requires a recorded data-terms verification.

Rationale: the tier change is a terms change AD-9 already gates on; making the model a setting aligns
with md-report.

**AD-10 — replace the "whole Report" sentence**

OLD:
> **Automatic regeneration under FR-21 replaces the whole Report, never a single failing Section**,
> so a regeneration count means one thing and Sections cannot come from different drafts.

NEW:
> **(Amended 2026-10-01, correct-course):** `draft_ready` is written Section by Section (AD-21).
> Automatic regeneration under FR-21 opens a new draft attempt in which **only the Sections named by
> the failing Gate check** are rewritten, plus Consiglio finale whenever any of Sections 1–7 is
> rewritten; every other Section is copied forward unchanged into the new attempt. Each attempt still
> persists one complete, assembled `ReportDraft` and its own `StoredGateResult`, so a Gate result
> always refers to one coherent draft, and `regeneration_count` still counts Gate-triggered
> regeneration cycles per run.

Rationale: keeps "one Gate result ↔ one draft" auditability while no longer paying for seven
passing Sections.

**AD-20 — superseded**

OLD: title *"A report run advances one stage per poll request, never on a background job"* and its
rule, including the 2026-09-14 `REPORT_RUN_MODE` amendment.

NEW (title and rule replaced; the old text kept below a *Superseded 2026-10-01* marker for history):
> ### AD-20 — A report run is advanced by one in-process driver, never by a request
>
> - **Rule:** the start handler creates the `ReportRun` row, hands its id to the **RunDriver**
>   (`shell/runner/driver.py`) and returns immediately. The driver owns two executors: a small pool
>   of per-run loops, and the **generation executor** capped at `GENERATION_CONCURRENCY`, the
>   process-wide brake across every run. A run's loop calls the same idempotent, one-stage-per-call
>   `advance()` (AD-10) under the same Postgres advisory lock until the run reaches
>   `gate_passed`/`failed_at` or waits on a human (Gate review). During `draft_ready` it submits one
>   job per claimable Section (AD-21). Every HTTP handler — the poll included — is **read-only**
>   with respect to run progress. On startup the driver's `resume()` restarts every run with
>   `failed_at IS NULL` and an incomplete stage; a Section lease left by a dead process expires
>   (`LEASE_TTL`) and is reclaimed. `REPORT_RUN_MODE` is removed. **The driver module is the only
>   place in the codebase allowed to create a thread, executor or async task** — enforced by a guard
>   test with negative tests. Still no queue, broker, cron or second deployable.

Rationale: the parallel fan-out requires work that outlives a request; md-report runs this exact
design in production on the same VPS.

**New AD-21 — A draft is written Section by Section; Consiglio finale last**

> - **Binds:** FR-16, FR-17, FR-19, FR-21, NFR throughput and latency
> - **Prevents:** one slow or failing Section holding the whole Report hostage; regeneration paying
>   for Sections that already passed; a closing Section written blind to the rest of the Report.
> - **Rule:** each draft attempt has one `report_draft_section` row per Section (ordinal, name,
>   status `pending|complete|failed`, sentences JSON, attempts, `last_error`, `claimed_at`,
>   `claim_expires_at`). Status is derived purely in `core/` (`core/draft_state.py`: which Sections
>   are claimable, whether the draft is complete) — there is no in-progress status; a lease marks a
>   Section as being written. Sections 1–7 are claimable together; Section 8 (Consiglio finale)
>   becomes claimable only when 1–7 are `complete`, and its Generator call additionally receives
>   Sections 1–7's sentence texts (no ids). Each call keeps every per-call guarantee of AD-6 and
>   Story 4.5: short id aliases, an `entry_ids` enum, count-pinned day-list schemas, and the
>   alias-leak, citation, no-date-token and day-list-coverage validations. When all eight are
>   `complete`, the driver assembles one `ReportDraft` and the run advances to `gate_passed`.

**BUILD-ORDER.md** — add a note under E5 and E8: *"Superseded in part by Epic 10 (2026-10-01): see
AD-20 (amended) and AD-21."*

### 4.2 SPEC — `_bmad-output/specs/spec-astro-report/SPEC.md`

**Constraints, Generator inputs**

OLD:
> The Generator narrates and never computes: it receives the Report Payload, the Style Guide version
> and the two ReportThemes, and nothing else — no tools, no database handle, no prior Report prose.

NEW:
> The Generator narrates and never computes: it receives the Report Payload, the Style Guide version,
> the two ReportThemes, and the name of the one Section it is writing — and, for Consiglio finale
> only, the sentence texts of this same draft's Sections 1–7 — and nothing else: no tools, no
> database handle, no prior Report's prose.

**Constraints, capacity**

OLD:
> No capacity planning beyond 200 Reports per month; no horizontal scale, multi-region, queue broker
> or background worker process. A report run is advanced only by the operator's own polling of the
> run view (`ARCHITECTURE-SPINE.md` AD-20).

NEW:
> No capacity planning beyond 200 Reports per month; no horizontal scale, multi-region, queue broker
> or separate worker process. A report run is advanced by one in-process driver with a bounded
> generation executor, started by the start request and resumed on boot (`ARCHITECTURE-SPINE.md`
> AD-20, AD-21).

**CAP for run viewing (intent/success, line ~186)** — append to *success*:
> During drafting the view shows each Section's own state (waiting, writing, written, failed) and
> each Section's text as soon as it is written.

### 4.3 PRD — `prds/prd-astro-report-2026-08-14/prd.md`

**FR-21** — first consequence

OLD:
> - Regeneration is automatic and bounded.

NEW:
> - Regeneration is automatic and bounded, and rewrites only the Sections the failing check names
>   (plus Consiglio astrologico finale whenever another Section is rewritten).
>
> *(Amended 2026-10-01, correct-course: per-Section regeneration.)*

**FR-19** — add one consequence:
> - Retries are per Section: a transient failure in one Section never discards Sections already
>   written.

**NFR Cost** — *(found while applying edits)* "Running cost stays at zero" conflicts with the paid
account. Amended: the Generator runs on a paid Gemini account (`gemini-2.5-flash`) by Francesco's
explicit decision; generation is the only usage-priced line item.

**NFR throughput and latency** — append:
> *(2026-10-01)* Generation is parallel per Section (AD-21); the 3-minute p90 is unchanged as the
> budget, and Story 10.7 re-measures it, now including one regeneration cycle.

### 4.4 UX — `ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md`

- **Report Run Lifecycle → Rules:** replace *"Non-blocking start; poll-driven advance"* with
  *"Non-blocking start; driver-driven advance. Polling only reads."* Remove the `poll` /
  `background` mode distinction.
- **New sub-section *Drafting view*** (ported from md-report `_avanzamento.html`, `_rail_riga.html`,
  `_sezione.html`, `_oob.html`): a left **rail** of the eight Sections, each with a dot whose shape
  and colour encode the state plus a screen-reader label (*In attesa*, *In scrittura*, *Scritta*,
  *Da rifare*, *Non riuscita*); the **sheet** on the right shows each Section's prose the moment it
  is written. Each 2 s poll returns only the changed rail rows and Sections as HTMX out-of-band
  swaps. Consiglio finale shows *In attesa delle altre Sezioni* until 1–7 are written. On a
  per-Section regeneration, the rail marks the rewritten Sections *Da rifare → In scrittura*, and
  the passing Sections stay visible.
- **Loading table:** *Report run advancing* → *the stage track for the setup stages, then the
  Section rail during drafting.*
- **Accessibility:** the rail announces each Section state change politely (`aria-live="polite"`
  on the rail's summary line, not on every row).
- Styling follows astro-report's `DESIGN.md` tokens, not md-report's.

### 4.5 Epics — `epics.md` (append)

```
### Epic 10: Fast reports — parallel Section generation and instant PDF

Francesco gets a report on screen in under a minute, sees each Section appear as it is written,
waits only for the Sections the Gate rejected, and downloads the PDF in seconds.
Amends AD-9, AD-10, AD-20; adds AD-21 (sprint-change-proposal-2026-10-01).
```

**Story 10.1 — A PDF in seconds, and instantly the second time** *(independent; do first)*
- `report_export.html`: prose cards (Energia generale, Amore/Lavoro/Denaro/Benessere, day lists,
  Consiglio finale) laid out as blocks; side-by-side layouts use floats or `display: table`;
  flex/grid kept only for small fixed-size rows (icon + heading, placement rows). Visual parity with
  `key-pdf-export.html` checked on a real report.
- New table `exported_pdf` (`report_id`, `fingerprint`, `pdf_bytes`, `created_at`); the fingerprint
  hashes everything the PDF depends on (rendered draft, Client name/birth data, chart id,
  template file hash). The export route serves stored bytes on a fingerprint match, renders and
  stores otherwise. `ExportRecord` and `run.stage` semantics are unchanged (still written on every
  download).
- **AC:** local render of the realistic fixture ≤ 1.2 s (perf test, generous ceiling); a second
  download performs no WeasyPrint call; editing a Section (hand-correct) changes the fingerprint.
- Forward-only migration; checked against real Postgres (`MIGRATION_TEST_DATABASE_URL`).

**Story 10.2 — Paid flash, configured, and the terms re-recorded**
- `shell/config.py`: `GEMINI_MODEL` (default `gemini-2.5-flash`) and `GENERATION_CONCURRENCY`
  (default 11, 1–32, validated at startup), mirroring md-report; `.env.example` updated.
- `GeminiGenerator` takes the model from `Settings`; free-tier comments and the
  10-requests-per-minute rationale removed from `generator.py` and `driver.py`.
- `docs/release-validation/gemini-data-terms.md` re-verified for the paid account
  (`tier = "paid"`, new verification date); `tests/test_data_terms_record.py` updated;
  `GEMINI_DATA_TERMS_VERIFIED_AT` bumped.

**Story 10.3 — Generate one Section at a time**
- `Generator` port gains `generate_section(section, payload, style_guide, theme_previous,
  theme_current, written_sections=None) -> tuple[Sentence, ...]`.
- One-Section response schema (narrative or count-pinned day-list shape), shared aliases, the four
  existing validations scoped to that Section. Prompt order: system instruction + Payload +
  continuity first (identical across the eight calls, for implicit caching), Section instruction
  last.
- Consiglio finale's call adds Sections 1–7's texts.
- `RecordedResponseGenerator` / the local generator are ported to the new method; conformance
  fixtures re-recorded per Section.
- The old whole-report `generate()` is removed once 10.4 lands (no dead path).

**Story 10.4 — Section rows and the driver** *(the core port from md-report)*
- Migration: `report_draft_section` (AD-21's columns; unique `(report_draft_attempt, ordinal)`;
  FK cascade from `report_run`, covered by the Client-deletion cascade tests via
  `tests/_fk.py`).
- `core/draft_state.py` (pure): claimable Sections, Consiglio-last rule, completeness, attempts
  exhausted.
- `shell/runner/lease.py`, `shell/runner/driver.py` (RunDriver: `start`, `resume`, `stop`, the two
  executors), wired into app startup and shutdown; `REPORT_RUN_MODE` and the scheduler removed.
- Assembly of eight complete Sections into one `ReportDraft` row, then the existing `gate_passed`.
- Guard test: no `threading` / `concurrent.futures` / `asyncio.create_task` outside
  `shell/runner/driver.py`, with `test_the_guard_detects_a_*` negative tests.
- **AC:** with a fake generator that sleeps 1 s per Section, a draft completes in ≈ 2 s, not 8 s;
  killing the driver mid-draft and calling `resume()` finishes it without rewriting complete
  Sections; a Section failing `MAX_SECTION_ATTEMPTS` times fails the run, naming the Section.

**Story 10.5 — Regenerate only what the Gate rejected**
- On `GateFailedError` (above the `_MIN_VIOLATIONS_FOR_AUTO_REGENERATION` ceiling and within
  `_MAX_REGENERATIONS`): new attempt; failing Sections plus Consiglio finale (if any of 1–7 failed)
  reset to `pending`; the rest copied forward.
- Accept and hand-correct paths (Stories 5.7/5.8) unchanged; hand-correct also updates that
  Section's row.
- **AC:** a Gate failure in *Amore* alone rewrites Amore and Consiglio finale only; the stored
  `GateResult` of each attempt refers to that attempt's assembled draft.

**Story 10.6 — Watch the Sections being written**
- The run view during `draft_ready` renders the rail + sheet described in §4.4, polling every 2 s
  with HTMX out-of-band swaps of changed rows only (md-report `_oob.html` pattern); the setup stages
  and `gate_passed` keep 9-5's stage track.
- Italian labels, `DESIGN.md` tokens, accessibility floor (Story 9-9) preserved.
- **AC:** the HTTP tests show a Section's text appearing in the poll response as soon as its row is
  complete, while other Sections show *In scrittura*.

**Story 10.7 — Measure it**
- Re-run the 8-3 latency measurement on production with paid flash: draft p90, per-Section p90,
  one-regeneration p90, PDF first/repeat export. Update `docs/release-validation/latency.md` and
  its guard.
- Side-by-side read of five reports (old vs new) for repetition between Sections; any Style Guide
  tweak recorded as a new Style Guide version.

### 4.6 Other artifacts

- **`AGENTS.md`:** under *Conventions that differ from defaults* add: *"`shell/runner/driver.py`
  is the only module that may create a thread, executor or async task (AD-20); a guard test
  enforces it."* Under *Known pitfalls*: *"Generation threads must never compute a chart; if one
  ever does, it must pin the vendored ephemeris path for its own thread."*
- **`sprint-status.yaml`:** add `epic-10: backlog` and stories `10-1` … `10-7: backlog`.
- **`.env.example`:** add `GEMINI_MODEL`, `GENERATION_CONCURRENCY`; remove `REPORT_RUN_MODE`.

---

## Section 5: Implementation Handoff

**Scope classification: Major** — spine amendments and a new epic. Francesco approves this proposal
as both PM and architect (single-operator project); implementation then goes to the Developer.

| Order | Work | Skill | Notes |
|---|---|---|---|
| 0 | Apply the document edits in §4.1–4.6 | Developer, with this proposal | Doc-only commit before code |
| 1 | Story 10.1 (PDF) | `bmad-build` | Independent, ships first, immediate relief |
| 2 | Story 10.2 (paid flash config + terms) | `bmad-build` | Small; unblocks honest backoff tuning |
| 3 | Stories 10.3 → 10.4 → 10.5 | `bmad-build`, one per fresh context | 10.4 is the large port; review with `bmad-code-review` |
| 4 | Story 10.6 (UI) | `bmad-build` | Optionally `bmad-ux` first for the rail's visual spec |
| 5 | Story 10.7 (measure) | `bmad-build` | After deploy |

**Success criteria**

- Production draft generation p90 **≤ 60 s**; the composed per-Report p90 including one
  regeneration stays inside the 180 s budget.
- PDF first export **≤ 6 s** in production; repeat download **< 1 s**.
- Every Gate, alias, citation, day-list and export-gate test still passes unchanged in intent;
  real-Postgres migration checks pass for both new tables.
- No thread or executor outside `shell/runner/driver.py` (guard test green, negatives included).
- A redeploy in the middle of a draft loses no written Section.
