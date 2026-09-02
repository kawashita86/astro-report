---
name: astro-report
status: final
sources:
  - ../../architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md
updated: 2026-09-02
---

# astro-report — Experience Spine

> Single-surface desktop web console for one operator (ARCHITECTURE-SPINE.md
> AD-15). Server-rendered FastAPI + Jinja2 + HTMX 2.x; no SPA. Visual identity is
> `DESIGN.md`; token references below use `{path.to.token}` and resolve there.
> Both spines win over any mock or import on conflict.

---

## Foundation

- **Form factor.** Desktop web, single browser, single authenticated principal.
  The operator works at a desk during low-frequency, high-consequence sessions
  (recording a client, driving a month's report runs, reviewing prose, exporting,
  backing up). Optimised for 1280–1680px. Tablet ≥768px is supported with the
  sidebar collapsed to a drawer; below 768px is best-effort, not designed.
- **UI system.** No third-party component framework. The delivery layer is
  Jinja2 templates with a **Tailwind utility layer**, HTMX 2.x for partial
  updates and polling, and a small amount of vanilla JS for toasts, the theme
  toggle, modal focus-trapping, and click-to-copy. `DESIGN.md` tokens are
  authored as CSS custom properties consumed by a thin Tailwind config; there is
  no inherited design system to extend.
- **Progressive enhancement.** Every destructive and data-writing action works
  without JavaScript (full-page POST + redirect). JavaScript upgrades: live
  run-stage updates, toasts instead of redirect flash, in-place disclosure,
  the theme toggle, focus management. With JS disabled the app degrades to
  full-page navigation and inline banners — never to a broken state.
- **Language & locale.** The **entire UI is Italian** — chrome, navigation,
  buttons, form labels, helper text, errors, empty states, toasts, stage
  labels — matching the Italian report content. Only the underlying domain
  model keeps its defined names in code / database / configuration (the
  architecture's naming rule); presentation strings are Italian. The document
  is `<html lang="it">`, so native `date` / `time` pickers render in Italian
  format. Every displayed date is `dd/MM/yyyy`, every time `HH:mm` (24-hour),
  every timestamp `dd/MM/yyyy HH:mm`. Month codes stay `YYYY-MM` (they are
  identifiers, shown as mono chips). An Italian label map for every surface is
  in the memlog and applied throughout this spine.
- **The rebuild.** Sixteen standalone unstyled templates become one shell with a
  shared layout, a design-token stylesheet, a persistent sidebar, and the state
  and feedback primitives specified below. Route contracts are unchanged with
  one exception the operator approved and the architecture spine now fixes
  (ARCHITECTURE-SPINE.md **AD-20**): **starting a run no longer blocks** — the
  start `POST` creates the run and returns immediately, and each poll `GET`
  advances **at most one** stage then returns (today the start `POST` drives the
  whole pipeline inline and every poll re-drives it). One stage per poll can
  itself be slow — the `draft_ready` poll holds its connection for the Gemini
  call — but the response never chains stages and the start never waits. No
  background worker, queue or cron: the operator's polling is the drain. The
  stage machine itself (`natal_ready → transits_ready → payload_ready →
  draft_ready → gate_passed → exported`) is unchanged.
- **Non-goals.** No offline / PWA. No multi-user anything — no account menu, no
  roles, no sharing (AD-15). No mobile-first layout. No i18n framework and no
  language switch: the UI is Italian, full stop. English appears only in code,
  not on screen.

---

## Information Architecture

Visual reference: [`mockups/key-home.html`](mockups/key-home.html) (dashboard,
backup-stale banner, run-status badges) and
[`mockups/key-clienti.html`](mockups/key-clienti.html) (compact list + client-side
filter). Mocks illustrate; this spine is the contract.

### Top level (sidebar, in order)

| Area — sidebar label (IT) | Route(s) today | Purpose |
|---|---|---|
| **Home** | *new — `/`* | Landing surface: recent report runs, global backup status, quick actions. Fills the current gap where `/` resolves to nothing. |
| **Clienti** | `/clients`, `/clients/new`, `/clients/{id}/edit`, `/clients/{id}/delete` | The roster. Create, correct, delete. Entry point to everything client-scoped. |
| **Guida di stile** | `/style-guide`, `/style-guide/edit`, `/style-guide/{version}` | Current version + immutable history; the editor that forks a new version. |
| **Corpus** | `/corpus`, `/corpus/new` | Past reports collected as plain text, paired or unpaired; composition counts. |
| **Backup** | `/backup` | The one authenticated logical export to the operator's machine. |

**Esci** is pinned to the sidebar bottom, separated by a hairline. A **theme
toggle** (*Tema chiaro / scuro*) sits just above it.

### Client-scoped (contextual tabs under a selected Client)

```
Clienti
└── {Cliente}                        breadcrumb: Clienti / {nome}
    ├── Anagrafica    /clients/{id}/edit          — birth data, correction flow
    ├── Tema          /clients/{id}/chart         — Kerykeion SVG wheel, verification only
    └── Report        /clients/{id}/reports       — month history + "Nuovo report"
        └── {Run}     /report-runs/{run_id}       breadcrumb: Clienti / {nome} / {mese}
            ├── (stage view — default while running)
            ├── Payload   /report-runs/{run_id}/payload
            ├── Draft     /report-runs/{run_id}/draft      — only when a Gate failure exists
            └── Report    /report-runs/{run_id}/report     — when gate_passed / exported
                └── Export  PDF · Markdown · disposition
```

### Sitemap (full)

```
/                         Home — dashboard
/login                    Sign in (unauthenticated; only allowlisted route besides /healthz)
/clients                  Client list (compact table, search, "New Client")
  /clients/new            Create Client (form; birthplace disambiguation sub-state)
  /clients/{id}/edit      Correct Client (form → review/supersede confirm)
  /clients/{id}/delete    Delete Client (confirm modal; notes superseded chart if any)
  /clients/{id}/chart     Chart wheel (SVG; config-stale banner when applicable)
  /clients/{id}/reports   Report history for the Client + start a run
/report-runs/{id}         Run stage view (live) → resolves to Report or Gate-failure
  /report-runs/{id}/payload    Report Payload, entry by entry (disclosure + mono chips)
  /report-runs/{id}/draft      Cited draft + Gate-failure panel
  /report-runs/{id}/report     Passed Report: 8 sections + export + disposition
  /report-runs/{id}/export/pdf         WeasyPrint download
  /report-runs/{id}/export/markdown    Markdown download
  /report-runs/{id}/export/disposition POST — record send outcome
/style-guide              Current version + history
  /style-guide/edit       Editor (saves a NEW version; info banner)
  /style-guide/{version}  Read-only past version
/corpus                   Composition counts + entries (truncated, expandable)
  /corpus/new             Paste a past report; paired/unpaired; optional client + month
/backup                   Trigger logical export; ?record=1 marks it against staleness
```

Route descriptions above are spec prose; the actual on-screen labels are Italian
per the Voice and Tone map (e.g. the *"New Client"* action is **Nuovo cliente**,
*"start a run"* is **Nuovo report**).

### Wayfinding rules

- The active sidebar item and the breadcrumb always agree.
- A run in progress is reachable from Home and from the Client's **Report** tab;
  both show its live badge. Leaving the run view never cancels the run.
- The **backup-stale** banner is global (top of content column) whenever the
  newest Report postdates the last recorded backup (AD-17), on every screen.

---

## Voice and Tone

All UI copy is **Italian**, terse and factual, addressing the operator with the
formal *tu* dropped in favour of impersonal / imperative phrasing (*"Inserisci…"*,
*"Scegli…"*, *"Nessun cliente."*). The operator is the domain expert: copy states
what happened and what to do — it never explains astrology and never reassures.

- **Domain terms** — the on-screen Italian labels for the model concepts are
  fixed and used consistently (a synonym is a defect, mirroring the
  architecture's naming rule):

  | Model concept (code) | UI label (Italian) |
  |---|---|
  | Client | **Cliente** |
  | NatalChart | **Tema natale** |
  | Report / ReportRun | **Report** |
  | ReportPayload | **Payload** (proper noun, mono-chip glossed on first use: *i dati verificabili del report*) |
  | Draft | **Bozza** |
  | GateResult / the Gate | **Verifica di fondatezza** (short: *Verifica*) |
  | Section | **Sezione** |
  | Claim | **Affermazione** |
  | StyleGuide | **Guida di stile** |
  | Corpus | **Corpus** |
  | ReportTheme | **Tema del report** |

  The four domains stay Italian and lowercase wherever named: `amore`, `lavoro`,
  `denaro`, `benessere`.

- **Errors** — *cosa è successo* + *cosa fare*, one short sentence each, in
  `{colors.danger}`.
  - Field: *"L'ora di nascita è obbligatoria."* / *"Usa il formato AAAA-MM, es. 2026-05."*
  - Form summary (top of form): *"Impossibile creare il cliente. Correggi i 2
    campi segnalati qui sotto."*
  - Geocoder ambiguity is **not** an error: *"Più luoghi corrispondono a
    ‘Springfield’. Scegline uno."*
  - Gate failure is **not** an error toast — it is a first-class result screen
    (see State Patterns).
- **Confirmations** name the irreversible consequence in full:
  - Delete Client: *"Elimina definitivamente {nome} e il suo tema natale"* +
    *", incluso il tema superato conservato da una correzione precedente"* when
    one exists + *". Operazione irreversibile."* The button stays disabled until
    the operator types the Client's exact name into a confirmation field.
  - Supersede chart: *"Applicando questa correzione il tema attuale viene
    superato. Il tema precedente è conservato, contrassegnato come superato e
    resta consultabile — ma i report già generati su di esso potrebbero non
    corrispondere più."* Plain confirm, no typed name.
- **Stage labels** (ReportRun), progress tense: *Calcolo del tema natale ·
  Ricerca dei transiti · Assemblaggio del Payload · Generazione della bozza ·
  Verifica di fondatezza · Pronto per l'esportazione*. Terminal: *Esportato* /
  *Verifica non superata*.
- **Empty states** — one line, no exclamation: *"Nessun cliente."* / *"Nessun
  report per questo cliente."* / *"Nessun report passato è stato ancora
  aggiunto."* / *"Non esiste ancora nessuna versione della guida di stile. La
  generazione è bloccata finché non ne salvi una."*
- **Success** — past tense, minimal: *"Cliente creato."* / *"Salvato come
  versione 7."* / *"Backup scaricato."* / *"Segnato come inviato."*
- **Numbers and identifiers** are shown, never summarised away: regeneration
  count (*"Verifica superata dopo 1 rigenerazione."*), version numbers, entry
  IDs, the ephemeris identity, the `computation.toml` hash.

Brand voice (the *why* behind the product) lives in `DESIGN.md` → Brand & Style.

---

## Component Patterns (behavioral)

Visual specs are in `DESIGN.md` → Components. This section is behavior only.

- **Sidebar nav** — client-side active state from the current path; full-page
  navigation on click (no SPA routing). On < 900px it is a drawer: a header menu
  button opens it, it traps focus, `Esc` and scrim-click close it, the trigger
  regains focus on close.
- **Contextual tabs (Record / Chart / Reports)** — real links, not JS tabs; each
  is its own route. The active tab is derived from the path.
- **Table row** — entire row is a link to the detail route; row-action buttons
  (`{component.button-ghost}`) stop propagation. Keyboard: `↑`/`↓` move a roving
  focus, `Enter` opens, row actions are in the tab order. Hover and focus share
  the `{colors.surface-sunken}` treatment.
- **List filter** — the Client list has a single text field (*"Filtra per
  nome"*) that filters rows **client-side** on name as the operator types; no
  server round-trip, no pagination in v1. Empty result shows an inline
  *"Nessun cliente corrisponde a ‘…’."* line, not the list's empty state.
- **Form submit** — on submit the primary button disables and shows an inline
  spinner; fields lock. Client-side required/pattern checks run first and focus
  the first invalid field. Server validation errors re-render the form with a
  summary at top and per-field messages wired via `aria-describedby`; focus moves
  to the summary. Success (JS): redirect + a `success` toast on the destination.
  Success (no JS): redirect + a dismissible `success` banner.
- **Birthplace disambiguation** — a sub-state of the same form, not a new screen.
  The typed birthplace is preserved in a hidden field; choosing a candidate and
  resubmitting continues. On correction, birthplace is **never** prefilled — the
  field renders empty with the helper *"Retype the birthplace, even to reconfirm
  the same place."* (matches `client_edit.html` behavior).
- **Confirm modal** — opens over the triggering screen, focus-trapped, initial
  focus on the *cancel* button (never on the destructive one). `Esc` and
  scrim-click cancel. The confirm button carries the verb (*Elimina cliente* /
  *Applica correzione*), not *OK*.
  - **Delete Client** requires typing the Client's **exact name** into a
    confirmation field; the `danger` button stays disabled until it matches
    (trimmed, case-sensitive). Label: *"Digita «{nome}» per confermare."*
  - **Supersede chart** is a plain confirm — no typed name — because the prior
    chart is retained (FR-4) and the action is recoverable.
- **Toast** — appended to a top-right `aria-live="polite"` region (`assertive`
  for `danger`). `success` self-dismisses ~5s with a hover-to-pause; `warning` /
  `danger` persist with a close button. Max 3 visible, FIFO; a 4th collapses the
  oldest. Never the sole carrier of information the operator may need later — a
  Gate failure, a stale backup, a superseded chart all also have a persistent
  surface.
- **Stage track** — see *Report Run Lifecycle*. Polls via HTMX `hx-trigger` with
  a **fixed 2s cadence while `hx-trigger` is visible**, pausing when the tab is
  hidden (`htmx:visibilityChange` / `whenVisible`) and stopping on any terminal
  stage. Each poll `GET` advances the run **by at most one stage** and returns
  its new state (ARCHITECTURE-SPINE.md AD-20); it never loops through stages and
  never blocks the start `POST`. One poll — the `draft_ready` one — may hold its
  connection for the Gemini call; the stage track just keeps showing *Verifica di
  fondatezza* / the prior label until it returns. Overlapping polls are
  single-flighted server-side, so a poll that lands mid-advance simply returns
  the current stage.
- **Disclosure (Payload sections, Corpus entries, Style Guide history rows)** —
  collapsed by default beyond the first; `<details>`/`<summary>` semantics so it
  works without JS; state not persisted across loads. Corpus entry text is
  clamped to ~6 lines with an *Expand* control.
- **Mono chip** — click-to-copy; on copy, a 1.5s inline *Copied* swap (not a
  toast). Keyboard-activatable.
- **Chart wheel** — the Kerykeion SVG is rendered server-side and inlined; the
  frame provides a theme-aware background (`{component.panel}`), and the SVG is
  not recolored. Zoom is browser-native. This view is verification-only and never
  reachable from an export path (AD-7).
- **Report sheet section nav** — in-page anchors to the eight Sections with
  scroll-spy; `prefers-reduced-motion` disables smooth scroll.

---

## State Patterns

### Loading

| Situation | Pattern |
|---|---|
| Full page navigation | Browser-native; no app spinner. Server renders fast (no compute on GET except the run driver — see note). |
| A known-shape region loading via HTMX | `{component.skeleton}` matching the final layout. |
| A single indeterminate action (export building, backup packaging) | Inline spinner on the button + disabled; `aria-busy` on the region. |
| Report run advancing | The **stage track**, not a spinner. See *Report Run Lifecycle*. |

### Empty

Every list defines its empty state (`{component.empty-state}`): Clients, per-Client
Reports, Corpus, Style Guide history (only before version 1 exists), Home recent-runs.
Each is one line + one primary action. The Style Guide has a distinct pre-seed
empty state: *"No StyleGuide version exists. Generation is blocked until you save
one."* (generation refuses to run without one — AD-19).

### Error

| Scope | Surface |
|---|---|
| Field | Inline message below the field, `danger`, `aria-describedby`, `danger` border. |
| Form | Summary block at the top listing each failed field as an in-page link; focus moves there. |
| Action (POST failed, 5xx) | `danger` toast (persistent) + the triggering control re-enabled. Body unchanged. |
| Page (404 / wrong state) | A plain page: what's missing + a link back to the parent area. 404 covers "no such run" and "run hasn't reached this stage yet" — copy says so. |
| Network (HTMX request failed) | Non-destructive inline banner in the polled region: *"Connessione persa — nuovo tentativo…"* Polling backs off to 5s, then 15s; a manual *Riprova* appears after the second failure. |
| Session expired | Redirect to `/login` with the attempted path preserved; after sign-in, return there. A `warning` banner on the login screen: *"Sessione scaduta. Accedi per continuare."* |

### Partial / stale (not broken, but qualified)

| Signal | Surface | Persistence |
|---|---|---|
| **Backup stale** (newest Report postdates last backup, AD-17) | Global `warning` banner, top of content column: *"Backup non aggiornato — esistono nuovi report dall'ultimo backup."* + *Esegui backup ora* → `/backup?record=1`. | Every screen, until a backup is recorded. |
| **Config-stale chart** (chart computed under a different `computation.toml`) | `warning` banner scoped to the Chart view; explains positions are shown as stored but aspects are recomputed at current orbs. | The Chart view, until the Client is corrected/recomputed. |
| **Superseded chart** | `warning` badge on the Client, on affected report-history rows, and in the run breadcrumb. | Permanent (the superseded chart is retained, FR-4). |
| **Regenerated report** | `small` note on the Report screen: *"Gate passed after {n} regeneration(s)."* | On the Report. |

### Success

Past-tense toast (JS) or dismissible banner (no JS). Data-writing successes that
change what the operator sees also update the relevant badge/count without a
manual refresh where HTMX already owns the region.

### In progress / long-running

The `ReportRun`. It has its own section below because it is the product's central
interaction and the current implementation's weakest point.

---

## Interaction Primitives

- **Navigation** — full-page links for every route; the sidebar and tabs never
  trap the operator in JS state. Back/forward always work.
- **Selection** — a row opens its detail; there is no multi-select and no bulk
  action in v1 (a month's runs are started one Client at a time).
- **Submission** — one primary action per screen, in the page header or at the
  form's end. Enter submits a single-field form (login); multi-field forms submit
  only from the button.
- **Confirmation** — destructive or supersede actions route through a focus-trapped
  modal that names the consequence; the confirm verb is explicit; cancel is the
  default focus. Non-destructive actions never confirm.
- **Polling** — only the run stage track polls. Fixed 2s while visible, paused when
  the tab is hidden, stopped on terminal stage, backoff on failure.
- **Copy** — every identifier chip is click-to-copy with inline feedback
  (*"Copiato"*, 1.5s).
- **Keyboard shortcuts** — none. No shortcut layer, no `?` panel. `Esc` closing
  an open overlay is standard dialog behavior, not a shortcut. (Considered and
  dropped — nothing depends on it and it isn't worth the rebuild time.)
- **Motion** — transitions ≤150ms, easing standard. The only ambient motion is the
  active stage-track dot pulse and the skeleton sheen; both stop under
  `prefers-reduced-motion`, which also disables smooth-scroll and toast slide.
- **Focus on route change** — after a full-page navigation, focus moves to the
  `h1`; a skip-to-content link precedes the sidebar.

---

## Accessibility Floor

Target **WCAG 2.1 AA**. Single operator, but the work is exacting and often done
tired at month-end — accessibility here is ergonomics.

- **Contrast** — body text ≥ 7:1, secondary text ≥ 4.5:1, non-text UI (borders,
  stage dots, focus ring) ≥ 3:1, in both themes. Values and the ramp are in
  `DESIGN.md` → Colors; `primary-700` on white is 13:1, `link` is 8.5:1.
- **Keyboard** — every action reachable and operable: nav, tabs, table rows and
  their row-actions, modals, drawer, disclosure, copy chips, the theme toggle,
  export buttons. No keyboard trap except the intentional modal/drawer trap,
  which releases on close and restores focus to the trigger.
- **Focus visible** — `{component.focus-visible}` 2px `{colors.focus-ring}` outline
  with 2px offset on every interactive element; never removed.
- **Forms** — every input has a persistent visible `<label>` (already true in the
  current templates); errors associated via `aria-describedby`; the `fieldset` +
  `legend` pattern for the candidate picker and the paired/unpaired choice is
  kept; `autocomplete` and `autofocus` on the login field kept.
- **Live regions** — one polite `aria-live` region for toasts and success
  messages; the stage track announces each stage change politely; Gate failure
  and network errors announce assertively.
- **Structure** — one `h1` per screen, ordered headings, `main` landmark, `nav`
  landmark for the sidebar, `role="alert"` retained for immediate errors.
- **Targets** — interactive targets ≥ 24×24px; table row-actions get padding to
  meet it even though the row is 40px.
- **Motion** — `prefers-reduced-motion` respected everywhere (see Primitives).
- **Reading** — the report sheet holds a 720px measure (~70–80 characters) at
  `{typography.body-read}`; the chart-wheel SVG carries a `<title>`/`<desc>`. A
  parallel text table of the same planetary positions (for non-visual
  verification) is a deferred enhancement — add it if the operator ever needs
  it; not required for v1.
- **Zoom** — layout holds to 200% zoom / 400% reflow without horizontal scroll on
  the content column; wide tables and the payload view scroll inside their own
  container.

Visual contrast values are owned by `DESIGN.md`; this section owns behavior.

---

## Report Run Lifecycle *(invented — product-specific)*

The `ReportRun` is a row advancing forward-only through six persisted stages
(ARCHITECTURE-SPINE.md AD-10). It is the operator's main loop at month-end and the
single interaction the rebuild most needs to fix. Visual reference (both
load-bearing states): [`mockups/key-run-stage.html`](mockups/key-run-stage.html).

### Stages → operator-visible state

| Stage (persisted) | Stage-track node | Operator sees (Italian) | Available actions |
|---|---|---|---|
| *(created)* | — | *Avvio…* skeleton | — |
| `natal_ready` | ● natal done, ○ transits active | *Ricerca dei transiti* | Leave (run continues) |
| `transits_ready` | transits done, payload active | *Assemblaggio del Payload* | — |
| `payload_ready` | payload done, draft active | *Generazione della bozza* | **Vedi Payload** (`/payload`) |
| `draft_ready` | draft done, gate active | *Verifica di fondatezza* | **Vedi Payload** |
| `gate_passed` | all six done, export = success | *Pronto per l'esportazione* — a second badge, *"Superato con N eccezioni"* (`warning`), stacks beside the normal status badge when closed via Story 5.7's accepted-violation path; unmarked (as today) on a clean pass or a Story 5.8 hand-correction that reached a genuine pass | **Vedi report**, Esporta PDF/Markdown |
| `exported` | export node filled | *Esportato il {dd/MM/yyyy HH:mm}* | Ri-esporta (writes an EXPORT_RECORD, stage unchanged), record disposition |
| **failed** (any stage) | failed node in `danger`, prior nodes as-is | Gate-failure panel or error detail | **Vedi bozza** (cited), **Rigenera**, **Vedi Payload**; per unresolved violation card: **Accetta**, **Modifica e ricontrolla** (Stories 5.7/5.8, see *Per-violation review actions* below) |

### Rules

- **Non-blocking start; poll-driven advance** (ARCHITECTURE-SPINE.md AD-20). The
  start `POST` creates the run and returns immediately to the stage view without
  running a stage. From then on, each poll `GET` advances the run by **at most
  one** stage and returns — the operator's own polling is what moves the run
  forward. No background worker, queue or cron. The operator may navigate away or
  start another Client's run; a run whose tab is **closed** pauses at its last
  checkpoint and resumes on the next time that run's view is opened and polled.
- **One slow poll, by design.** The `draft_ready` advance makes the Gemini call
  inside its poll `GET`, so that one request can take 10–40s (plus AD-9 backoff).
  The stage track keeps showing the in-progress label until it returns. Every
  other poll is fast. This is the accepted cost of carrying no run infrastructure.
- **Resumable.** Re-opening a run view shows its true current stage; the next poll
  resumes at the first incomplete stage (AD-10, AD-20). The UI never implies lost
  work.
- **Regeneration replaces the whole Report** (AD-10), never one Section. The
  *Rigenera* action says so: *"La rigenerazione sostituisce l'intero report e
  incrementa il contatore di rigenerazioni."* The count is always shown.
- **Gate failure is a destination, not a toast.** `/draft` renders a
  `{component.panel}` in `danger`: the failure reason, then one card per
  violation — `kind`, the offending Sezione, the sentence as a `blockquote`, the
  detail, and the cited entry IDs as mono chips (or *nessuna*). Each violation
  links to its Sezione in the draft below. Primary action *Rigenera*; secondary
  *Vedi Payload* (to check what the Generator was given). Panel heading:
  *"Verifica di fondatezza non superata"*.
- **Per-violation review actions** (Stories 5.7/5.8, correct-course 2026-09-02).
  Every unresolved card gets its own bottom action row, below the cited-entry
  chips and above the existing *Vai alla Sezione N ↓* link: two `{component.button}`
  `ghost` buttons, **Accetta** then **Modifica e ricontrolla**, sized and styled
  like every other tertiary/row-level action (`DESIGN.md` Button component) —
  never competing visually with the page-level *Rigenera* primary button below
  the panel, which keeps its exact current copy, position and whole-Report
  behavior unchanged.
  - **Accetta**: one click, no confirm modal (unlike Rigenera, which is
    destructive and does confirm) — accepting is reviewed-and-reversible-in-effect
    the moment it's clicked, since the underlying decision is append-only and
    auditable, not a discard. While the request is in flight the button shows an
    inline spinner and disables (existing Feedback-primitives pattern), then the
    card **collapses to a one-line resolved strip**: kind + Sezione + an
    *"Accettata"* tag in `warning` tone (matching the passed-with-exceptions
    badge below), pinned at the top of the panel above any still-open cards. If
    accepting was the last open violation, the whole panel is replaced on the
    next render by the normal `gate_passed` state (Vedi report) — no separate
    "all done" interstitial.
  - **Modifica e ricontrolla**: click **expands inline** — the card's own
    `blockquote` swaps for an editable `{component.input}` `Textarea`, same
    width as the card, prefilled with the sentence's exact current text; the
    button row swaps for **Ricontrolla** (`primary`, submits) and **Annulla**
    (`ghost`, collapses back to the read-only blockquote, discards the edit,
    no request sent). Submitting shows the same inline spinner + disabled state
    as Accetta on both buttons, on the card only — the rest of the panel and
    every other card stay interactive. On response: a card whose sentence now
    passes **collapses to a one-line resolved strip** tagged *"Corretta"* in
    `success` tone (this is a genuine Gate pass on the edited text, not an
    exception — never tagged `warning`/*"Accettata"*); a card that still fails
    re-renders open with its *updated* detail/citations, ready for another edit
    or an Accetta. Same last-violation completion rule as Accetta.
  - **Resolved-strip ordering**: resolved strips (any mix of *Accettata* /
    *Corretta*) stack at the top of the panel in the order they resolved, oldest
    first, so Francesco can scan top-to-bottom to confirm he handled everything
    before the panel disappears; open cards keep full detail below them,
    unaffected in order.
  - **Passed-with-exceptions badge**: a `warning`-toned `{component.badge}`
    reading *"Superato con N eccezioni"* (N = `accepted_violation_count`) sits
    immediately after the Report's title/date wherever a completed Report is
    named — the reading-sheet header (`report.html`), each row of Report
    History, and Home's recent-runs list — **stacked alongside** the row's
    normal status badge, not replacing it: Home already stacks an independent
    `warning` badge next to a status badge this way (a superseded-chart warning
    riding beside *"esportato"*, `key-home.html`'s "Esposito Sara" row), and the
    accepted-exceptions flag is the same kind of independent caveat, not a
    different status. A Report with `accepted_violation_count = 0` (a clean
    pass, or a hand-correction that reached a genuine pass) carries no such
    badge — it reads identically to every Report that passed on its own.
- **Batch context.** Home and the Client's Reports tab list every run with a live
  status badge, so a month-end batch of ~30 is scannable: which passed, which
  failed, which are still running. Failing one Client's run never touches the
  others (independent rows).
- **Month selection.** Starting a run is a single `YYYY-MM` field with a format
  hint (*"Mese del report — AAAA-MM"*) and a pattern check, on the Client's
  **Report** tab (matches the current `POST /clients/{id}/report-runs`
  contract). The field **defaults to the next calendar month** — the product
  forecasts the coming month, so the common case is one keystroke-free submit.
  The operator can type any other `YYYY-MM`.

---

## Key Flows

The single principal is **Francesco** (AD-15 — there is exactly one, structurally;
no second account is ever added). Flows are written as his real sessions.

UI strings the operator sees are Italian; the surrounding narration is spec prose.

### 1. Month-end batch — a Gate failure mid-run

It's the 2nd of November, late. Francesco has 28 recurring Clients to produce
**December** reports for (the product forecasts the coming month). From **Home**
he sees last month's runs all green and no *backup non aggiornato* banner. He
opens **Clienti**, types "Ab" into *Filtra per nome*, clicks **Abbate Chiara →
Report**. The month field already reads `2025-12`; he hits **Nuovo report**. The
stage track appears: tema ✓, transiti ✓, Payload ✓, bozza ✓ — then the **Verifica
node turns red**. He clicks **Vedi bozza**. A `danger` panel headed *"Verifica di
fondatezza non superata"*: one violation — *affermazione chiusa, citazione vuota*
in Sezione 6, the sentence quoted. He reads it, clicks **Rigenera**; the modal
reminds him the whole report is replaced and the count goes to 1. He confirms. The
track resets from *bozza*; this time the Verifica passes. **Climax:** the failure
cost him one Client's regeneration and thirty seconds of reading — not the batch.
Back on **Home**, Abbate now shows a green *esportato* badge beside the 20 he'd
already done, and he picks up the next name.

### 2. New Client — ambiguous birthplace

Francesco adds a first-time Client. **Clienti → Nuovo cliente**. Nome, data di
nascita, ora di nascita (the native pickers show Italian `gg/mm/aaaa` and 24-hour
`hh:mm`), luogo di nascita "Springfield". Submit. The form returns with the same
values and a `fieldset`: *"Più luoghi corrispondono a ‘Springfield’. Scegline
uno."* — five rows with region and country. He picks *Springfield, Illinois, US*,
resubmits. Toast *"Cliente creato."*; he lands on the Client's **Anagrafica** tab.
He clicks **Tema**, eyeballs the wheel against his reference, sees the ascendant
he expected. No *configurazione non aggiornata* banner. Done — ~40 seconds.

### 3. Correcting a birth time — supersede

A Client emails a corrected birth time. Francesco opens the Client →
**Anagrafica**, changes the time from 14:30 to 04:30, leaves *luogo di nascita*
**empty** as instructed (*"Riscrivi il luogo di nascita, anche solo per
riconfermarlo."*), clicks **Rivedi la correzione**. A `warning` review state:
*"Applicando questa correzione il tema attuale viene superato. Il tema precedente
è conservato, contrassegnato come superato e resta consultabile — ma i report già
generati su di esso potrebbero non corrispondere più."* He clicks **Applica
correzione**. The Client now carries a *superato* badge; its one prior Report row
is badged *tema superato* too. **Climax:** the consequence was stated before he
committed, and the old chart is still there to compare — nothing was silently
overwritten.

### 4. Reviewing and exporting a passed Report

Visual reference: [`mockups/key-report-sheet.html`](mockups/key-report-sheet.html).

From a **Report** row Francesco opens a `gate_passed` run → **Vedi report**. The
**report sheet**: 720px, the eight Sezione titles in the left rail, Italian prose
set for reading. A `small` note: *"Verifica superata dopo 1 rigenerazione."* He
reads top to bottom, scroll-spy tracking the rail. Satisfied, he clicks **Esporta
PDF**; the button shows a spinner, the WeasyPrint file downloads. He clicks
**Segna come inviato**; the disposition control collapses to *Inviato* and a
`success` toast confirms. The *backup non aggiornato* banner has now appeared at
the top — a new Report exists since his last backup.

### 5. Revising the Style Guide mid-batch

Halfway through the batch Francesco notices the Generator is overusing a phrase.
**Guida di stile → Modifica**. An `info` banner: *"Il salvataggio crea una nuova
versione — la versione attuale è conservata, mai sovrascritta."* He edits the
textarea, **Salva nuova versione**. *"Salvato come versione 8."* The history list
gains a row. His next **Nuovo report** records *Guida di stile v8* against the
Report; runs already passed are untouched and still cite their own version.

### 6. Backup before closing the laptop

The batch is done. The global `warning` banner reads *"Backup non aggiornato —
esistono nuovi report dall'ultimo backup."* Francesco clicks **Esegui backup
ora**. The **Backup** screen: one button, a note on what the export contains
(clienti, temi natali, report, Payload, esiti della verifica, temi del report,
corpus). He clicks it; the button shows a spinner, an archive downloads to his
machine, and — because the request carried `?record=1` — the staleness banner
clears across the app. **Climax:** the one durability action the system depends on
(AD-17) took a single deliberate click and told him, visibly, that it worked.

---

## Responsive & Platform *(triggered — sidebar collapse + print export)*

- **≥ 1200px** — full shell: 240px sidebar + 32px content padding.
- **900–1199px** — sidebar stays; content padding drops to 16px; list tables allow
  horizontal scroll inside their container.
- **768–899px** — sidebar becomes an off-canvas drawer (header menu button,
  focus-trapped, scrim). Forms and the report sheet already fit. Contextual tabs
  wrap or scroll horizontally.
- **< 768px** — best-effort. Layout stays single-column and usable; not a design
  target (the operator is at a desk).
- **Print / PDF export** — the WeasyPrint export template is a **separate
  document**, not the app in print CSS: Georgia serif, 12pt, 2cm page margin,
  `page-break-inside: avoid` per Section (as it is today). It deliberately does
  **not** inherit `DESIGN.md` — it is a client deliverable, not operator chrome.
  Keep it as-is; the rebuild does not touch it.

---

## Inspiration & Anti-patterns *(triggered)*

**Inspiration.** `matricedeldestino.it` — Inter on white, a strict 4px spacing
scale, an airy centred reading column (~672–896px), restrained radii, subtle
elevation. Borrow the *rhythm and discipline*; not the hue (cooler, graver here —
`#42297A`, not `#6D28D9`) and not the marketing-page airiness on list screens
(those go compact).

**Anti-patterns — what this rebuild exists to remove:**

| Current behavior | Why it's wrong here | Replacement |
|---|---|---|
| Sixteen standalone HTML pages, no shared layout, no nav | The operator has no map and no way between areas | One shell, persistent sidebar, breadcrumb + contextual tabs |
| No `/` route — landing nowhere | First impression is a 404 | Home dashboard: recent runs, backup status, quick actions |
| `ReportRun` driven synchronously inside the POST and re-driven (whole pipeline) on every 2s poll | Start blocks for seconds; every poll re-runs the loop; a slow Generator freezes the screen | Start `POST` returns without driving; each poll advances **one** stage then returns; single-flighted; no worker/queue/cron (ARCHITECTURE-SPINE.md AD-20) |
| Gate failure as raw text + `<ul>` on the draft page | The most consequential result is the least designed | First-class `danger` panel, one card per violation, linked to its Section, *Regenerate* primary |
| Report Payload as an untyped recursive `<dl>`/`<ul>` dump | Unreadable; IDs indistinguishable from prose | Disclosure per Section, entry IDs as mono chips, click-to-copy |
| Corpus list inlines a full `<pre>` of every past report | The index becomes unscannable at any real corpus size | Composition counts + rows with 6-line clamp + Expand |
| Style Guide shown as a `<pre>` | It's structured text read often; `<pre>` is a fallback, not a view | Rendered readable at `body-read`, monospace only where it is literally code |
| Forms redirect on save with no confirmation | The operator can't tell a save from a no-op | `success` toast (JS) / dismissible banner (no JS), past tense, specific |
| Backup-stale warning only on `client_reports.html` | The one durability signal is hidden on a deep screen | Global persistent banner until a backup is recorded |
| HTMX loaded ad hoc from a CDN in one template | Inconsistent, unversioned, offline-fragile | Vendored HTMX 2.x in the shell, loaded once |
