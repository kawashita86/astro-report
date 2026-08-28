# Sprint Change Proposal — 2026-08-28 (UI rebuild + AD-20)

**Workflow:** Correct Course
**Trigger:** A planning refresh on 2026-08-28 produced three items that need to enter the
in-flight backlog without regenerating it: a first operator-UI design contract
(`EXPERIENCE.md` + `DESIGN.md`), architecture invariant **AD-20** (non-blocking report-run
driver), and spec capability **CAP-30** (watch a report run progress).
**Mode:** Batch.
**Owner:** Francesco (decisions captured 2026-08-28).
**Change scope classification:** **Moderate** — backlog reorganization only. One new epic
(Epic 9) plus one story into Epic 3; `epics.md` and `sprint-status.yaml` amended. No PRD
change, no architecture change (AD-20 was already added to the spine this session), no
`core/` change.

---

## Section 1 — Issue Summary

The astro-report v1 backlog (`epics.md`, 8 epics / ~50 stories) is complete — every story
and every retrospective is `done` in `sprint-status.yaml`. The computational product the
PRD specified is built.

Three things changed on 2026-08-28, after that backlog was written:

1. **A UX design contract now exists.** `/bmad-ux` produced
   `_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md`
   and `DESIGN.md` (both `status: final`). The current UI was built ad-hoc from FR
   consequences — 16 standalone full-HTML Jinja templates, **no base layout, no CSS file,
   no design system**, HTMX loaded from a per-template `unpkg` `<script>`. `epics.md` still
   records *"### UX Design Requirements — Not applicable — no UX design contract exists for
   this project."* That statement is now stale.

2. **AD-20 was added to the architecture spine.** The `ReportRun` driver changes from
   "`drive()` called from the start `POST` and re-driven fully on every poll `GET`" to
   non-blocking: the start `POST` returns immediately without driving; each poll `GET`
   advances **at most one** stage; concurrent polls are single-flighted by a Postgres
   transaction-scoped advisory lock on the run id; no worker, queue or cron. Code lands in
   `shell/runner/driver.py` and `shell/http/routes/report_runs.py`.

3. **CAP-30 was added to the spec** — "watch a report run progress" — plus a constraint
   that the operator UI conforms to `EXPERIENCE.md` + `DESIGN.md`, and the "Italian"
   constraint was broadened from report content to the whole UI.

**Evidence:** `EXPERIENCE.md` / `DESIGN.md` frontmatter `status: final`;
`ARCHITECTURE-SPINE.md` AD-20 (committed `afbb87b`); `SPEC.md` CAP-30 + the two new
constraints; `shell/http/templates/*.html` — every file a standalone document, no
`{% extends %}` anywhere; `shell/runner/driver.py` docstring — "`drive()` is called from
both the start POST and the poll GET".

---

## Section 2 — Impact Analysis

### Epic impact

| Epic | Status | Impact |
|---|---|---|
| Epic 1 (private app + guardrails) | done | None. |
| Epic 2 (client + natal chart) | done | Presentation re-skinned by Epic 9 (client list, create/correct/delete forms, chart-wheel frame). FR behavior unchanged. |
| Epic 3 (dated facts + run machinery) | done | **+ Story 3.10** for AD-20 (backend driver change). Story 3.5's HTMX polling view is re-flowed by Epic 9 Story 9.5. |
| Epic 4 (generation) | done | None (no operator surface beyond the Style Guide editor, re-skinned in 9.7). |
| Epic 5 (Gate) | done | Story 5.5's Gate-failure view is re-flowed by Epic 9 Story 9.5. Behavior unchanged. |
| Epic 6 (review / export / history / backup) | done | Presentation re-skinned by Epic 9 (report sheet, payload view, export bar, history list, backup screen, the AD-17 staleness banner made global). Behavior unchanged. |
| Epic 7 (Corpus) | done | Corpus screens re-skinned in 9.7. |
| Epic 8 (release validation) | done | None — independent of the UI. |
| **Epic 9 (operator UI rebuild)** | **new** | Re-implements the presentation layer of Epics 2/3/5/6/7 against `EXPERIENCE.md` + `DESIGN.md`. Touches `shell/http/` only — no `core/`, no FR, no data model. |

No epic is invalidated. No rollback. No dependency breakage: Epic 9 depends on Epics 1–7
being done, which they are.

### Artifact conflicts

- **PRD** — no FR added or changed. The UI rebuild is presentation quality; AD-20 and
  CAP-30 carry no FR (like CAP-27/CAP-29 before them). The one PRD-adjacent drift — "output
  language is Italian" now spans the whole UI, not just report content — is already captured
  in `SPEC.md`. A one-line PRD sync is **offered, not required** (the spec is the build
  contract per `AGENTS.md`).
- **Architecture** — AD-20 already in the spine; `BUILD-ORDER.md` E5 already reworded this
  session. `epics.md` "Additional Requirements" lists AD-1…AD-19 and needs **AD-20
  appended**.
- **UX** — `epics.md` `### UX Design Requirements` ("Not applicable") is **replaced** with a
  real UX-DR catalogue extracted from `EXPERIENCE.md` + `DESIGN.md` (UX-DR1…UX-DR25 below),
  and Epic 9 is added.
- **`sprint-status.yaml`** — gains `epic-9` + stories `9-1`…`9-9` at `backlog`,
  `epic-9-retrospective: optional`, and `3-10-...` at `backlog` under epic-3;
  `last_updated: 2026-08-28`.
- **`AGENTS.md`** — no change. Its `bmad:context` block already names `SPEC.md` as the
  contract, and `SPEC.md` now cites the UX companions.
- **Deployment / CI** — no change. Same Render + Jinja2 + HTMX 2.x stack; the rebuild adds
  one vendored stylesheet and a vendored `htmx.min.js`, replacing a CDN `<script>`.

### Technical impact

- `shell/http/templates/` — all 16 templates rewritten to extend one `base.html`; a new
  `base.html`, a vendored `static/tokens.css` and `static/htmx.min.js`, a `/` route, and
  the component partials (toast region, stage track, confirm modal, banner, empty state).
- `shell/runner/driver.py` — `drive()` → single-stage `advance()`, `pg_try_advisory_xact_lock`.
- `shell/http/routes/report_runs.py` — start route drops the inline `drive()` call.
- `shell/http/app.py` — mount `static/`, add the `/` route.
- Tests — the unauthenticated-route allowlist test still holds (`/` is authenticated);
  a new test that no template ships its own `<html>` skeleton; a test that two overlapping
  advance calls transition a run exactly once.
- **Out of scope:** `report_export.html` (the WeasyPrint PDF template, Georgia serif) — it
  is a client document, not operator chrome, and deliberately does not inherit `DESIGN.md`.

---

## Section 3 — Recommended Approach

**Option 1 — Direct Adjustment (Hybrid: new Epic 9 + one story into Epic 3).**

| Option | Verdict |
|---|---|
| 1. Direct adjustment — add Epic 9 + Story 3.10 within the existing structure | **Selected.** Effort High (a real UI rebuild), risk Low (no `core/` change, no FR change, stack unchanged, `EXPERIENCE.md` / `DESIGN.md` are detailed contracts). Preserves the entire completed backlog and `sprint-status.yaml`. |
| 2. Rollback | Not viable / not needed — nothing to revert; the existing UI works and is being re-skinned. |
| 3. PRD MVP review | Not needed — MVP is delivered. Scope grows by choice, not by constraint. |

**Rationale:** `bmad-create-epics-and-stories` would regenerate `epics.md` from a blank
template and orphan `sprint-status.yaml` (its keys map to the current structure) — losing
the record of ~50 completed stories. Correct-course appends. The UX contract is detailed
enough to decompose cleanly into nine reviewable slices; AD-20 is a self-contained backend
change best expressed as one story beside the run machinery it touches (Epic 3).

**Timeline impact:** net-new work; blocks nothing done, reworks nothing done.

---

## Section 4 — Detailed Change Proposals

### 4A — `epics.md` frontmatter

```
OLD  inputDocuments:
       - '.../prd.md'
       - '.../ARCHITECTURE-SPINE.md'
       - '.../BUILD-ORDER.md'
       - '.../brief-.../addendum.md'

NEW  inputDocuments:
       - '.../prd.md'
       - '.../ARCHITECTURE-SPINE.md'
       - '.../BUILD-ORDER.md'
       - '.../brief-.../addendum.md'
       - '_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
       - '_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
```

### 4B — `epics.md` › Additional Requirements — append after AD-19

```
NEW  - **AD-20 — A report run advances one stage per poll request, never on a background
       job.** The runner exposes a single `advance` function performing at most one stage
       transition (AD-10) and returning. It is invoked only from the poll handler
       `GET report-runs/<run_id>` — never from a thread, task, queue consumer or scheduled
       job. `POST clients/<client_id>/report-runs` creates the `ReportRun` row and returns
       immediately without advancing it. No HTTP response waits on run completion; a single
       stage's own duration (including its one external call and AD-9 backoff) may extend
       that one request, but the response never chains into a second stage. Concurrent polls
       are single-flighted by a Postgres transaction-scoped advisory lock on the run id. A
       run whose tab is closed pauses at its last checkpoint and resumes on the next poll.
```

### 4C — `epics.md` › UX Design Requirements — REPLACE the "Not applicable" block

Replace the current section body (the 2026-08-14 "Not applicable — no UX design contract
exists" note and its provisional UI-surface list) with:

> A UX design contract exists as of **2026-08-28**:
> `ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md` (information architecture, voice,
> component / state / interaction patterns, key flows, WCAG 2.1 AA floor) and `DESIGN.md`
> (visual identity: `#42297A` on white, Inter, light + dark tokens; component specs;
> mockups under `mockups/`). This supersedes the 2026-08-14 "not applicable" ruling. Both
> spines are **binding** (`SPEC.md` constraint). The requirements below are realised by
> **Epic 9**.

Then the catalogue:

| UX-DR | Requirement | Source | Story |
|---|---|---|---|
| UX-DR1 | One `base.html` every rendered page extends; no page ships its own `<html>`/`<head>`. | EXPERIENCE Foundation; DESIGN app-shell | 9.1 |
| UX-DR2 | Design-token stylesheet — `#42297A` 50–950 ramp, semantic colours, Inter 9-role type scale, 4px spacing scale, radius scale, elevation — as CSS custom properties. | DESIGN frontmatter | 9.1 |
| UX-DR3 | Light **and** dark themes — tokens redefined under `prefers-color-scheme` and a manual sidebar toggle; both authored. | DESIGN Colors; EXPERIENCE Foundation | 9.1 |
| UX-DR4 | Vendor HTMX 2.x and the stylesheet in-repo, loaded once from the base layout; remove the per-template `unpkg` `<script>`. | EXPERIENCE anti-patterns | 9.1 |
| UX-DR5 | Persistent 240px sidebar — Home, Clienti, Guida di stile, Corpus, Backup; active state + 3px marker; theme toggle; Esci pinned bottom; collapses to a focus-trapped drawer below 900px. | DESIGN sidebar; EXPERIENCE IA | 9.1 |
| UX-DR6 | Home dashboard at `/` — recent runs with live status badges, global backup-stale banner, quick actions. (`/` currently 404s.) | EXPERIENCE IA (new surface) | 9.2 |
| UX-DR7 | Contextual tab row (Anagrafica / Tema / Report) under a selected Client. | EXPERIENCE IA | 9.3 |
| UX-DR8 | Compact list pattern — 40px rows, hairline dividers, hover, ghost row actions; client-side name filter on the Clienti list. | DESIGN table-row; EXPERIENCE Component Patterns | 9.3 |
| UX-DR9 | Airy form pattern — label-above, 24px field rhythm, helper text below, ~560px measure; birthplace disambiguation as an in-form sub-state. | DESIGN input; EXPERIENCE Component Patterns | 9.4 |
| UX-DR10 | Confirm-modal component — focus-trapped, cancel-focused, consequence named in Italian; **delete Client requires typing the exact name**; supersede is a plain confirm. | EXPERIENCE Component Patterns; SPEC update | 9.4 |
| UX-DR11 | Six-node stage-track component — pending / active / done / failed dots, captions, active-dot pulse (off under reduced motion). | DESIGN stage-track; EXPERIENCE Report Run Lifecycle | 9.5 |
| UX-DR12 | Gate-failure panel — `danger` panel, one card per violation (kind, Sezione, quoted sentence, detail, cited entry IDs as mono chips or "nessuna"), link to the Section, `Rigenera` primary. | EXPERIENCE Report Run Lifecycle | 9.5 |
| UX-DR13 | Report reading sheet — 720px, `body-read`, eight `heading`-weight Section titles, 32px gaps, in-page section nav with scroll-spy. | DESIGN report-sheet | 9.6 |
| UX-DR14 | Payload view — typed disclosure per Section; entry IDs as click-to-copy mono chips. Replaces the recursive `<dl>`/`<ul>` dump. | EXPERIENCE anti-patterns | 9.6 |
| UX-DR15 | Mono-chip component — `sm` radius, `surface-sunken`, click-to-copy with "Copiato" inline feedback; used for every entry ID / hash / `YYYY-MM`. | DESIGN badge-mono | 9.6 |
| UX-DR16 | Toast component — top-right `aria-live` region; success auto-dismiss ~5s; warning / danger persist; max 3, FIFO. | DESIGN toast; EXPERIENCE Component Patterns | 9.8 |
| UX-DR17 | Banner (inline alert) component — info / warning / danger, 3px left border, `-surface` tint; the **backup-stale banner is global** (every screen while stale); config-stale and superseded banners scoped. | DESIGN banner; EXPERIENCE State Patterns | 9.8 |
| UX-DR18 | Skeleton + spinner loaders — skeleton for known-shape region loads; button spinner + disable on submit; `aria-busy`. | DESIGN skeleton; EXPERIENCE State Patterns | 9.8 |
| UX-DR19 | Empty-state component — one per list (Clienti, per-Client Reports, Corpus, Style Guide pre-seed, Home recent-runs); one Italian line + one primary action. | DESIGN empty-state; EXPERIENCE State Patterns | 9.8 |
| UX-DR20 | Inline form-validation pattern — field errors below the field with `aria-describedby` + `danger` border; a form-level summary that takes focus and links to each failed field. | EXPERIENCE Component Patterns / Accessibility Floor | 9.8 |
| UX-DR21 | Style Guide + Corpus screens — readable rendering (raw `<pre>` only for literal code); Corpus entry text clamped to ~6 lines with Expand; composition counts. | EXPERIENCE anti-patterns | 9.7 |
| UX-DR22 | Full Italian UI — every visible string per the `EXPERIENCE.md` label map; `<html lang="it">`; displayed dates `dd/MM/yyyy`, times `HH:mm`; native pickers inherit `lang`; identifiers stay Latin-alphanumeric as mono chips. | EXPERIENCE Foundation / Voice and Tone; SPEC constraint | 9.9 |
| UX-DR23 | Accessibility floor — WCAG 2.1 AA: keyboard for every action incl. modal / drawer; visible focus ring on every interactive element; one `h1` per screen, ordered headings, `nav`/`main` landmarks, skip-to-content; targets ≥ 24px; layout holds at 200% zoom / 400% reflow with wide content scrolling in its own container. | EXPERIENCE Accessibility Floor | 9.9 |
| UX-DR24 | Motion budget — transitions ≤ 150ms; the only ambient motion is the active stage dot and the skeleton sheen, both disabled under `prefers-reduced-motion` (which also disables smooth-scroll and toast slide). | EXPERIENCE Interaction Primitives | 9.9 |
| UX-DR25 | `report_export.html` (WeasyPrint PDF, Georgia serif) is **out of scope** — a client document, not operator chrome; does not inherit `DESIGN.md`. | EXPERIENCE Responsive & Platform | — |

### 4D — `epics.md` › Epic List — add the Epic 9 summary and update the dependency flow

```
NEW entry, after Epic 8:

### Epic 9: Rebuild the operator interface against a real design contract

Francesco works in one styled application — a persistent sidebar, an Italian interface, a
light and a dark theme, forms and a reading view set for the work, and proper feedback
(loaders, toasts, a stage track he can watch) — instead of sixteen unstyled island pages.
**FRs covered:** none directly — realises UX-DR1–UX-DR25 and CAP-30 (with Story 3.10)
**Governed by:** EXPERIENCE.md, DESIGN.md, AD-20; AD-15, AD-17 unchanged
**Notes:** Presentation layer only — `shell/http/` templates, a vendored stylesheet, a
vendored HTMX, one new `/` route. No `core/` change, no FR change, no data-model change.
Depends on Epics 1–7 being done. `report_export.html` is explicitly excluded (client
document, not chrome).
```

```
Dependency flow — REPLACE the diagram with:

Epic 1 → Epic 2 → Epic 3 → Epic 4 → Epic 5 → Epic 6 → Epic 8
                              │                    ↑
                              │   Epic 7 (parallel)─┘
                              └── Story 3.10 (AD-20) ──┐
                                                       ↓
                          Epic 9 (UI rebuild) — needs Epics 1–7 + Story 3.10
```

### 4E — `epics.md` › new Story 3.10, appended to Epic 3 (after Story 3.9)

```
### Story 3.10: Advance a report run without blocking the request

As Francesco,
I want starting a run to return at once and each status poll to move it forward by one step,
So that a slow generation never freezes the screen and I can leave and come back.

**Acceptance Criteria:**

**Given** the runner
**When** it advances a run
**Then** it does so through a single function that performs at most one stage transition and
returns
**And** that function is invoked only from the poll handler `GET /report-runs/{run_id}` —
never from a thread, task, queue consumer or scheduled job

**Given** Francesco starts a run
**When** `POST /clients/{client_id}/report-runs` handles it
**Then** the `ReportRun` row is created and the response returns immediately without running
any stage
**And** the first stage runs on the first poll

**Given** two status polls for the same run arriving together
**When** both call the advance function
**Then** a Postgres transaction-scoped advisory lock on the run id lets exactly one advance
the run; the other returns the current stage without advancing
**And** the lock releases on commit, rollback or a dropped connection

**Given** a single poll landing on `draft_ready`
**When** the Generator call runs inside it
**Then** that one request may take as long as the call plus AD-9 backoff, and the response
still returns after one stage — it never chains into a second

**Given** the process killed mid-stage
**When** the application restarts and the run is polled again
**Then** it resumes at the first incomplete stage and recomputes nothing that already
succeeded (AD-10 unchanged)

**Given** `shell/runner/driver.py` and `shell/http/routes/report_runs.py`
**When** this story lands
**Then** their module docstrings no longer describe driving from the start POST or
re-driving the whole pipeline on every poll

**Governed by:** AD-10, AD-20
```

### 4F — `epics.md` › new Epic 9 section with Stories 9.1–9.9

Full Given/When/Then acceptance criteria for each of the nine stories:

- **9.1 — The application shell.** One `base.html` all pages extend; vendored
  `static/tokens.css` (the `#42297A` ramp, Inter, spacing, radius, elevation as CSS
  variables) and `static/htmx.min.js`; light + dark via `prefers-color-scheme` and a
  sidebar toggle; the 240px sidebar (five areas, active marker, toggle, Esci); skip-to-
  content; `<html lang="it">`. AC: every existing route renders inside the shell; no
  template ships its own `<html>`/`<head>` (asserted by a test); HTMX loads exactly once;
  token contrast meets the DESIGN.md floor; the unauthenticated-route allowlist test still
  passes.
- **9.2 — Home dashboard.** New authenticated `/` route: recent `ReportRun`s with status
  badges, the global backup-stale banner (AD-17), quick actions to Clienti / Guida di
  stile. AC: `/` requires a session; recent runs list by Client + month with current
  stage/terminal status; the banner shows iff the newest Report postdates the last export
  and clears on backup.
- **9.3 — Clienti list and client-scoped tabs.** Compact list (client-side name filter,
  40px rows, superseded badge, ghost row actions); the Anagrafica / Tema / Report tab row
  under a Client. AC: filter is client-side on name with an inline "nessun cliente
  corrisponde" line; a row opens the Client; each tab is its own route; a superseded chart
  is badged on the row and in the Client header.
- **9.4 — Client create / correct / delete, restyled.** Airy forms; birthplace
  disambiguation as an in-form sub-state that preserves typed input; the supersede review
  state; the typed-name delete confirm modal. AC: forms follow the DESIGN.md form spec;
  correction never prefills birthplace; the delete button is disabled until the Client's
  exact name is typed; every destructive/supersede action is a focus-trapped modal naming
  the consequence in Italian, cancel-focused.
- **9.5 — Report run stage view + Gate-failure panel (CAP-30).** The six-node stage track;
  the poll shows the current stage and updates as it advances (reads only — pairs with
  Story 3.10); leave-and-return resumes; the Gate failure renders as a `danger` panel, one
  card per violation with cited entry IDs as mono chips, each linking to its Section,
  `Rigenera` primary. AC: starting a run lands on the stage view immediately; the view
  reflects each advance; a closed-tab run resumes on reopen; a terminally failed run names
  the stage and reason; a Gate failure shows the violation panel and offers `Rigenera`
  (whole-Report, per AD-10). **Realises CAP-30 together with Story 3.10.**
- **9.6 — Report reading sheet + Payload / Draft views restyled.** The 720px `body-read`
  eight-Section sheet with in-page section nav + scroll-spy; the Payload view as typed
  disclosure with click-to-copy mono-chip entry IDs; the export bar with disposition and
  the regeneration-count note. AC: the sheet matches the DESIGN.md report-sheet spec;
  Payload entries are collapsible and their IDs copyable; export and disposition behaviour
  is unchanged from Epic 6.
- **9.7 — Style Guide and Corpus screens restyled.** Style Guide list / edit / view
  rendered readable (an `info` banner on the editor; `<pre>` only for literal code); Corpus
  list with 6-line clamp + Expand and the composition counts. AC: no behaviour change — the
  editor still forks a new version, prior versions still immutable; Corpus entry text is
  clamped with a working Expand.
- **9.8 — Feedback and state primitives.** The cross-cutting components: top-right
  `aria-live` toast region (success auto-dismiss ~5s, warning/danger persist, max 3 FIFO);
  skeleton loaders for known-shape regions; button spinner + disable on submit; per-list
  empty states; inline field errors with `aria-describedby` + a focus-taking form summary;
  the network-retry banner on the poll region. AC: a form submit disables, spins, shows
  inline errors and scrolls to the first; success surfaces a toast (JS) or a dismissible
  banner (no-JS); each list has its empty state; `prefers-reduced-motion` is honoured.
- **9.9 — Italian localisation sweep + accessibility floor.** Every visible string Italian
  per the `EXPERIENCE.md` label map; `dd/MM/yyyy` / `HH:mm`; native pickers via
  `lang="it"`; the WCAG 2.1 AA pass. AC: no English in the rendered UI; a keyboard-only
  pass reaches every action including the modal and the drawer; visible focus ring
  everywhere; one `h1` per screen, `nav`/`main` landmarks, skip link; targets ≥ 24px;
  layout holds at 200% zoom / 400% reflow with wide content scrolling in its own container;
  `report_export.html` is untouched.

### 4G — `sprint-status.yaml`

```
development_status:
  ...
  epic-3:
    + 3-10-advance-a-report-run-without-blocking-the-request: backlog
  ...
  + epic-9: backlog
  + 9-1-the-application-shell: backlog
  + 9-2-home-dashboard: backlog
  + 9-3-clienti-list-and-client-scoped-tabs: backlog
  + 9-4-client-create-correct-delete-restyled: backlog
  + 9-5-report-run-stage-view-and-gate-failure-panel: backlog
  + 9-6-report-reading-sheet-and-payload-views-restyled: backlog
  + 9-7-style-guide-and-corpus-screens-restyled: backlog
  + 9-8-feedback-and-state-primitives: backlog
  + 9-9-italian-localisation-sweep-and-accessibility-floor: backlog
  + epic-9-retrospective: optional
last_updated: 2026-08-28
```

---

## Section 5 — Implementation Handoff

**Scope classification: Moderate** — backlog reorganisation (one new epic, ten new stories,
tracker update). No replan, no architecture change, no PRD change.

| Recipient | Responsibility |
|---|---|
| **Correct-course (this run)** | Apply 4A–4G to `epics.md` and `sprint-status.yaml`; write this proposal; commit to `main`. |
| **Dev loop (`bmad-build`, per story)** | Implement Story 3.10 first (unblocks 9.5), then Epic 9 in story order 9.1 → 9.9. 9.1 is the foundation every other 9.x builds on. |
| **Francesco** | Design review of each rendered screen against `DESIGN.md` and the `mockups/`; sign-off on the Italian copy against the `EXPERIENCE.md` label map. |

**Success criteria:**

- Every route renders inside one styled shell; no standalone-HTML template remains.
- `/` serves a dashboard; the backup-stale banner is global.
- Starting a run returns immediately; the stage view advances one step per poll; two
  overlapping polls advance a run once (Story 3.10 test).
- A keyboard-only and a `prefers-reduced-motion` pass both succeed.
- No English string in the rendered operator UI.
- `uv run pytest` green (per `AGENTS.md`, before any push).

**Offered, not in this proposal:** a one-line PRD sync broadening "output language is
Italian" to name the operator UI — the spec already carries it and is the build contract.

---

## Change log

- 2026-08-28 — proposal created (Correct Course, Batch mode).
- 2026-08-28 — **approved by Francesco.** Applied 4A–4G: `epics.md` (frontmatter, AD-20,
  UX-DR catalogue replacing the "not applicable" block, Epic 9 summary + dependency flow,
  Story 3.10, full Epic 9 with Stories 9.1–9.9) and `sprint-status.yaml` (`epic-9` + `9-1`…
  `9-9` + `3-10` at `backlog`, `epic-9-retrospective: optional`). Committed to `main`.
