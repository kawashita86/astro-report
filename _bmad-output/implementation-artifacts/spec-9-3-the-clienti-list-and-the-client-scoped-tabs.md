---
title: 'Story 9.3 — The Clienti list and the client-scoped tabs'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
baseline_commit: '5573871a06f4ff52b3cea2318125e2f014d8a051'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** There is no `GET /clients` screen at all — Story 9.2's dashboard and
the sidebar already link to `/clients`, which 404s today — and the three
client-scoped screens (`/clients/{id}/edit`, `/clients/{id}/chart`,
`/clients/{id}/reports`) each render a bare English `<h1>` with no breadcrumb and
no way to move between them. A month-end batch of thirty clients is not
navigable.

**Approach:** Add the `GET /clients` roster: a compact 1120px table (40px rows,
hairline dividers, hover, ghost row-actions, a "tema superato" badge on any
client with a superseded chart) with a client-side name filter that never hits
the server. Add one shared contextual-tab partial — breadcrumb `Clienti / {nome}`
plus real-link tabs Anagrafica / Tema / Report with the active tab derived from
the path — and include it in the page header of the three client-scoped
templates so the breadcrumb and the active sidebar item always agree. Presentation
only: no route contract, query result, or model changes; full-Italian body copy
of the three screens stays for Story 9.9, but every new surface here is Italian
from the start.

## Boundaries & Constraints

**Always:**
- `GET /clients` is authenticated by default (not added to
  `shell.http.auth.ALLOWLIST`); an anonymous request is the uniform `401` with an
  empty body.
- The list reuses `shell.adapters.postgres.client.list_clients(session)` verbatim
  for ordering (name, then id). No new query shape, no pagination.
- Every template still extends `base.html` (or `_bare.html`); no second `<html>`;
  `<html lang="it">` preserved. New chrome copy is Italian per the EXPERIENCE.md
  label map (`Cliente`/`Clienti`, `Tema natale`→tab label **Tema**,
  `Report`, `Anagrafica`, `Nuovo cliente`, `Filtra per nome`).
- Progressive enhancement: with JS disabled the roster shows the full list and
  every row link and row-action link works; the filter field simply does nothing.
  JS only adds live filtering, the match count, and the inline no-match line.
- A11y floor: one `h1` per screen; the tab row is a `<nav>` landmark with an
  `aria-label`; the active tab carries `aria-current="page"`; the filter field
  has a visible `<label>` or `aria-label`; interactive targets ≥ 24×24px; a
  visible focus ring on every control.
- Date/time rendering is `dd/MM/yyyy` and `HH:mm`, formatted in the route (the
  `shell/http/routes/home.py` precedent), not with a new Jinja filter.
- New CSS is appended to `static/tokens.css` as a clearly-commented
  **PROVISIONAL — Story 9.3** block using semantic tokens only; contrast holds in
  both themes (≥ 3:1 non-text, ≥ 4.5:1 text). Story 9.8 consolidates it; do not
  build on the exact class names elsewhere.

**Ask First:**
- Showing anything in the list's "Nascita" column beyond `birth_date` and
  `birth_time` — no birthplace name is stored on `Client` (only lat/lon/zone), so
  the mockup's "· Napoli" is not backable. Default: date · time only.
- Restructuring or translating the *body* of `client_edit.html` /
  `chart_wheel.html` / `client_reports.html` beyond adding the shared page
  header — that is Story 9.9.

**Never:**
- No change to `core/`; no change to any route's request/response contract,
  status codes, redirects, or persisted data.
- No new `GET /clients` filtering, sorting, or paging on the server; no query
  string params.
- No SPA/JS tab routing — tabs are plain `<a>` full-page links.
- No custom date widget; no new client-list model method or adapter function.
- `report_export.html` stays untouched.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Roster with clients | Authenticated `GET /clients`, N `Client` rows | `200`; compact table, one row per client in (name, id) order; each row's name cell links to `/clients/{id}/edit`; Nascita cell shows `dd/MM/yyyy` · `HH:mm`; row-action links to `/clients/{id}/reports`, `/clients/{id}/chart`, `/clients/{id}/edit`; extends `base.html` (one `<html>`, `lang="it"`, sidebar present, `Clienti` nav `is-active`) | N/A |
| Client with a superseded chart | ≥1 `StoredNatalChart` with `superseded_at` set for a client | That client's Tema cell shows the `tema superato` badge; a client with only a current chart shows `corrente` and no badge | N/A |
| Empty roster | Authenticated `GET /clients`, zero `Client` rows | `200`; the list empty state — exactly `Nessun cliente.` on one line — plus the `Nuovo cliente` primary action; no table body rows | N/A |
| Client-side filter typing | JS enabled, roster rendered, operator types a name fragment | Rows whose `data-name` does not contain the fragment (case-insensitive) are hidden with no network request; the count region updates to `{shown} di {total}` | N/A |
| Filter matches nothing | JS enabled, fragment matches no row | The table is hidden and an inline line `Nessun cliente corrisponde a "{fragment}".` is shown — not the list empty state | N/A |
| Filter cleared | JS enabled, operator clears the field | All rows shown again, count back to `{total} di {total}`, no-match line hidden | N/A |
| No-JS roster | JS disabled, `GET /clients` | Full list renders; filter field present but inert; every row/action link navigates | N/A |
| Client-scoped screen render | Authenticated `GET` of `/clients/{id}/edit`, `/clients/{id}/chart`, or `/clients/{id}/reports` | Page header shows breadcrumb `Clienti / {nome}` (`Clienti` links to `/clients`) and a tab `<nav>` with Anagrafica / Tema / Report as real links; exactly one tab has `aria-current="page"` matching the route; sidebar `Clienti` item is also `is-active` (they agree); still one `<html>`, one `h1` | 404 unchanged for an unknown id / missing chart |
| Anonymous `GET /clients` | No session cookie | `401`, empty body; `ALLOWLIST` still exactly `{"/healthz", "/login"}` | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/clients.py` — add `@router.get("/clients", include_in_schema=False)`
  `list_clients_view(request, session)`. Smallest sibling shape to mirror:
  `list_client_reports` (l.623) — `session.exec(...)`, build plain view dicts,
  `_templates.TemplateResponse(request, "client_list.html", {...})`. Import
  `list_clients` from `shell.adapters.postgres.client` (already re-exported in its
  `__all__`, l.42). Compute superseded set once:
  `session.exec(select(StoredNatalChart.client_id).where(StoredNatalChart.superseded_at.is_not(None)).distinct()).all()`
  → `set`. `StoredNatalChart` is already imported here (l.51). Build rows
  `{"id", "name", "birth_date": c.birth_date.strftime("%d/%m/%Y"),
  "birth_time": c.birth_time.strftime("%H:%M"), "has_superseded_chart": c.id in superseded}`.
  `_has_superseded_chart` (l.193) is the per-row predicate already in this module —
  the batch query above is its set-valued form; do not call it in a loop.
- `shell/http/routes/clients.py` — `_render_edit_form` (l.153) currently takes
  `client_id` only; thread the fetched `client` object through it (both
  `client_edit_form` l.337 and `correct_client` l.360 already do
  `session.get(Client, client_id)`), and add `"active_tab": "anagrafica"` to its
  context dict so `client_edit.html` can include the tab partial.
- `shell/http/routes/clients.py` — `list_client_reports` (l.623): its
  `TemplateResponse` context (l.681) already passes `client`; add
  `"active_tab": "report"`.
- `shell/http/routes/chart.py` — `chart_wheel_view` (l.44): its context (l.84)
  already passes `client`; add `"active_tab": "tema"`.
- `shell/http/templates/base.html` — the layout. `{% block page_header %}` (l.97)
  is where the shared partial goes. Sidebar already marks `Clienti` active for any
  `path.startswith("/clients")` (l.49) — no sidebar change.
- `shell/http/templates/_client_tabs.html` — **new.** Given `client` and
  `active_tab` ∈ {`anagrafica`,`tema`,`report`}: a `.breadcrumb` (`<a href="/clients">Clienti</a>
  / {{ client.name }}`), then `<nav class="client-tabs" aria-label="Sezioni del cliente">`
  with three `<a>` (Anagrafica→`/clients/{{ client.id }}/edit`,
  Tema→`/clients/{{ client.id }}/chart`, Report→`/clients/{{ client.id }}/reports`);
  the one matching `active_tab` gets `class="is-active" aria-current="page"`.
- `shell/http/templates/client_list.html` — **new.** `{% extends "base.html" %}`.
  `page_header` block: `.breadcrumb` = `Clienti`; `<div class="page-header">` with
  `<h1>Clienti</h1>` + `.page-header__action` `Nuovo cliente` → `/clients/new`
  (reuse the classes Story 9.2 added). `content`: a `.list-filter` with
  `<input data-client-filter aria-label="Filtra per nome" placeholder="Filtra per nome">`
  and `<span data-client-count aria-live="polite">`; then, when `clients` is
  non-empty, `.list-panel` wrapping a `<table>` (thead Nome/Nascita/Tema/Azioni;
  one `<tr data-client-row data-name="{{ row.name|lower }}">` per row: name cell
  `<a href="/clients/{{ row.id }}/edit">`, Nascita `{{ row.birth_date }} · {{ row.birth_time }}`,
  Tema `corrente` or `<span class="row-badge">tema superato</span>`, Azioni a
  `.row-actions` group of ghost `<a>` Report/Tema/Correggi), plus a hidden
  `<p data-client-empty hidden>` for the no-match line; when `clients` is empty,
  a `.list-empty` block `Nessun cliente.` + the `Nuovo cliente` action.
  Reference: `_bmad-output/.../mockups/key-clienti.html` (illustrative;
  EXPERIENCE.md label map + this Matrix win on conflict).
- `shell/http/templates/client_edit.html`, `chart_wheel.html`,
  `client_reports.html` — add `{% block page_header %}{% include "_client_tabs.html" %}{% endblock %}`;
  keep each existing `<h1>` in `{% block content %}` (its English body copy is
  Story 9.9). `client_edit.html`'s warning/candidate sub-states are unchanged.
- `shell/http/static/shell.js` — append a third IIFE section (the file's own
  docstring lists two jobs; extend it): if `document.querySelector("[data-client-filter]")`,
  wire `input` → for each `[data-client-row]` toggle `hidden` on
  `row.dataset.name.indexOf(value.toLowerCase()) === -1`; update
  `[data-client-count]` to `{shown} di {total}`; when `shown === 0 && value`,
  hide `[data-client-table]`/show `[data-client-empty]` with the fragment text,
  else the inverse. No animation (matches the file's reduced-motion note).
- `shell/http/static/tokens.css` — append **PROVISIONAL — Story 9.3** block after
  the Story 9.2 block (ends l.676): `.breadcrumb`, `.client-tabs` + `.client-tabs a`
  + `.client-tabs a.is-active`, `.list-filter` + input, `.list-panel` + `table`/
  `th`/`td` compact rules (40px rows via `td { height: 40px }`, hairline
  `border-bottom`, `tbody tr:hover td` → `--surface-sunken`), `.row-badge` (reuse
  `--warning-surface`/`--warning` like the mockup badge), `.row-actions a` (ghost:
  transparent, `--ink-secondary`, hover `--surface-sunken`), `.list-empty`,
  `.filter-empty`/`[data-client-empty]`. Comment as Story 9.8 fodder.
- `shell/http/app.py` — no change; `/clients` is a new path on the already-registered
  `clients_router`.
- `tests/test_http_clients.py` — new `GET /clients` section (see Tasks). Fixtures
  `authenticated_client` / `db_session` / row builders already used across this file.
- `tests/test_http_shell.py` — `_MIGRATED_ROUTES` (l.66): add `"/clients"` (it
  renders on an empty DB). `exactly_one_html` / `_SIDEBAR_LABELS` helpers already
  here.
- `tests/test_http_client_tabs.py` — **new**; the tab-row / breadcrumb / active-tab
  agreement across the three client-scoped routes.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/clients.py` — add `GET /clients` → `client_list.html`:
  `list_clients(session)` for order, one batched `distinct` query for the
  superseded-chart client-id set, view rows with pre-formatted `dd/MM/yyyy` /
  `HH:mm`. Thread `client` + `"active_tab": "anagrafica"` through
  `_render_edit_form`; add `"active_tab": "report"` to `list_client_reports`'s
  context.
- [x] `shell/http/routes/chart.py` — add `"active_tab": "tema"` to
  `chart_wheel_view`'s `TemplateResponse` context.
- [x] `shell/http/templates/_client_tabs.html` — new shared partial: breadcrumb
  `Clienti / {nome}` + the three real-link tabs; active tab from `active_tab`
  with `aria-current="page"`.
- [x] `shell/http/templates/client_list.html` — new: page header (breadcrumb,
  `h1`, `Nuovo cliente`), the filter field + `aria-live` count, the compact
  table (or the `Nessun cliente.` empty state), the hidden no-match line.
- [x] `shell/http/templates/client_edit.html`, `chart_wheel.html`,
  `client_reports.html` — add the `page_header` block including
  `_client_tabs.html`; leave the content bodies otherwise as-is.
- [x] `shell/http/static/shell.js` — add the client-side list-filter enhancement
  (guarded on `[data-client-filter]`); update the file docstring to name the
  third job.
- [x] `shell/http/static/tokens.css` — append the PROVISIONAL Story 9.3 component
  block (breadcrumb, tabs, list filter, compact table, row badge, row actions,
  empty/no-match), semantic tokens only, both-theme contrast.
- [x] `tests/test_http_clients.py` — new section covering every `GET /clients`
  I/O Matrix row: authenticated roster (row order, edit link, `dd/MM/yyyy` ·
  `HH:mm`, action links, `base.html` markers, `Clienti` nav `is-active`); the
  `tema superato` badge appears only for a client with a superseded chart;
  empty-roster path renders exactly `Nessun cliente.` + `Nuovo cliente` and no
  `data-client-row`; the filter markup hooks (`data-client-filter`,
  `data-client-row` + `data-name`, `data-client-count`, `data-client-empty`) are
  present; anonymous `GET /clients` is `401` with an empty body and `ALLOWLIST`
  is unchanged. Add one assertion that `shell.js` wires `data-client-filter`.
- [x] `tests/test_http_client_tabs.py` — new: for each of `/clients/{id}/edit`,
  `/clients/{id}/chart`, `/clients/{id}/reports` — the breadcrumb `Clienti /
  {name}` with `Clienti` linking `/clients`, the three tab links to the right
  routes, exactly one tab marked `aria-current="page"` and it matches the route,
  and the sidebar `Clienti` item also `is-active`.
- [x] `tests/test_http_shell.py` — add `"/clients"` to `_MIGRATED_ROUTES`.

**Acceptance Criteria:**
- Given an authenticated session and no `Client` rows, when `GET /clients` is
  handled, then the response is `200`, contains the one-line `Nessun cliente.`
  empty state and a `Nuovo cliente` action, extends `base.html` (one `<html>`,
  `lang="it"`), and no table row is rendered.
- Given several `Client` rows, when `GET /clients` renders, then rows appear in
  `list_clients` order, each name cell links to `/clients/{id}/edit`, each row
  exposes `data-name` for client-side filtering, and any client with a superseded
  `StoredNatalChart` shows the `tema superato` badge while the others show
  `corrente`.
- Given the roster with JS, when the operator types a fragment that matches no
  client, then no network request is made, the table is hidden, and the inline
  line `Nessun cliente corrisponde a "{fragment}".` is shown instead of the list
  empty state; clearing the field restores every row.
- Given any of `/clients/{id}/edit`, `/clients/{id}/chart`,
  `/clients/{id}/reports`, when it renders for a known client, then its page
  header carries the breadcrumb `Clienti / {nome}` and the Anagrafica / Tema /
  Report tab links, exactly the tab for that route has `aria-current="page"`, and
  the sidebar `Clienti` item is simultaneously `is-active` — breadcrumb and
  sidebar agree.
- Given an unauthenticated `GET /clients`, when it is handled, then it is a `401`
  with an empty body and `shell.http.auth.ALLOWLIST` is still exactly
  `{"/healthz", "/login"}`.
- Given the full suite, when the story is done, then `uv run pytest`,
  `uv run ruff check .` and `uv run ruff format --check .` are all green,
  including the new `tests/test_http_client_tabs.py` and the amended
  `tests/test_http_clients.py` / `tests/test_http_shell.py`.

## Design Notes

**Birthplace is not stored.** `Client` keeps only `latitude`, `longitude`,
`iana_zone` — no place name (see `shell/adapters/postgres/client.py`'s `Client`
model). The `key-clienti.html` mock's "16/02/1986 · 04:30 · Napoli" cannot be
reproduced faithfully; the Nascita column shows date · time only. This is flagged
in *Ask First*.

**Active tab passed from the route, not sniffed in the template.** Each of the
three handlers already loads the `Client` and knows which screen it is; passing a
literal `active_tab` string keeps the partial dumb and the assertion in
`test_http_client_tabs.py` trivial. Deriving it from `request.url.path` in Jinja
would re-encode the route→tab mapping in a template conditional.

**Whole-row click is a JS enhancement, not the markup contract.** The name cell
is a real `<a>` (works with no JS); making the whole `<tr>` clickable is left to
Story 9.8's shared table-row component — nesting a block-level `<a>` around
`<td>`s with their own `<a>` row-actions is invalid HTML, and the AC only asks
for compact rows + ghost actions + the row linking to the detail route, which the
name-cell link satisfies.

**Filtering is name-only and case-insensitive** against a pre-lowercased
`data-name` attribute, matching EXPERIENCE.md ("filters rows client-side on name
as the operator types; no server round-trip, no pagination in v1").

## Verification

**Commands:**
- `uv run pytest tests/test_http_clients.py tests/test_http_client_tabs.py tests/test_http_shell.py`
  — expected: green, including the new `GET /clients` and tab-row cases.
- `uv run pytest` — expected: full suite green (no existing test asserted
  `/clients` 404s, so nothing else needs amending).
- `uv run ruff check .` — expected: clean (new module code carries
  `from __future__ import annotations`).
- `uv run ruff format --check .` — expected: clean.
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -n "<html" shell/http/templates/client_list.html shell/http/templates/_client_tabs.html`
  — expected: no matches (both extend / are included into `base.html`).
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -rn "unpkg\|cdnjs\|jsdelivr\|htmx.org" shell/http/templates/client_list.html`
  — expected: no matches.

**Manual checks:**
- Run the app, sign in, open `/clients`: the sidebar shows `Clienti` active, rows
  are ~40px with hairline dividers and a hover tint, a client corrected at least
  once shows `tema superato`. Type in the filter — rows narrow with no network
  request; type nonsense — the no-match line replaces the table. Compare against
  `mockups/key-clienti.html` and the DESIGN.md list density (1120px, 40px rows).
- Open a client's Anagrafica, then click Tema, then Report: the breadcrumb reads
  `Clienti / {nome}` throughout, the active tab tracks the route, and `Clienti`
  stays active in the sidebar. Toggle the theme — tab, breadcrumb and badge
  contrast hold in both.

## Suggested Review Order

**The roster route (design entry point)**

- Start here: the new `GET /clients` — reuses `list_clients` for order, one batched `distinct` for the superseded set, view rows with pre-formatted dates.
  [`clients.py:223`](../../shell/http/routes/clients.py#L223)

- The roster template: page header + breadcrumb, the client-side filter row (now inside `{% if clients %}`), the compact table, the `Nessun cliente.` empty state.
  [`client_list.html:1`](../../shell/http/templates/client_list.html#L1)

**The shared contextual-tab header**

- One partial, three consumers: breadcrumb `Clienti / {nome}` + real-link tabs; the active one from the literal `active_tab`, never path-sniffed.
  [`_client_tabs.html:1`](../../shell/http/templates/_client_tabs.html#L1)

- `_render_edit_form` now threads the loaded `client` (was `client_id`) so Anagrafica can render the partial; all 12 call sites in `correct_client` follow.
  [`clients.py:154`](../../shell/http/routes/clients.py#L154)

- Report tab wiring: `list_client_reports` gains `"active_tab": "report"`.
  [`clients.py:727`](../../shell/http/routes/clients.py#L727)

- Tema tab wiring: `chart_wheel_view` gains `"active_tab": "tema"`.
  [`chart.py:84`](../../shell/http/routes/chart.py#L84)

- The three client-scoped templates each include the partial in their `page_header` block; bodies untouched (English copy is Story 9.9).
  [`client_edit.html:3`](../../shell/http/templates/client_edit.html#L3)

**Progressive-enhancement filter + provisional styling**

- Client-side, name-only filter; runs once on load too (bfcache/back-nav), swaps the table for an SR-announced no-match line, no network.
  [`shell.js:179`](../../shell/http/static/shell.js#L179)

- PROVISIONAL Story 9.3 CSS block (breadcrumb, tabs, filter, compact table, row badge, ghost actions, empty states); colour tokens only; Story 9.8 consolidates.
  [`tokens.css:678`](../../shell/http/static/tokens.css#L678)

**Tests**

- New parametrized tab-header coverage across the three client-scoped routes: breadcrumb, three tab targets, single `aria-current`, sidebar agreement.
  [`test_http_client_tabs.py:1`](../../tests/test_http_client_tabs.py#L1)

- New `GET /clients` roster section: order, links, date format, superseded badge, empty state, filter hooks, anonymous 401.
  [`test_http_clients.py:1041`](../../tests/test_http_clients.py#L1041)

- `/clients` added to the shared shell-conformance route set.
  [`test_http_shell.py:69`](../../tests/test_http_shell.py#L69)
