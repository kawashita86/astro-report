---
title: 'Story 9.2 — A home dashboard instead of a 404'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'f1be5738848d0ec4ceec1ac8db505e152341a803'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/mockups/key-home.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `/` resolves to nothing — an authenticated request 404s, so opening
the app lands nowhere and there is no surface that shows which report runs are in
flight or whether the backup is behind. Story 9.1 shipped the shell with a "Home"
nav item that points at this dead route.

**Approach:** Add one authenticated `GET /` route (a new `shell/http/routes/home.py`
router, mirroring `backup.py`) rendering a `home.html` that extends `base.html`:
the recent `ReportRun`s across every Client — newest first, capped — each row
carrying the Client name, the month as a mono chip, an Italian status badge for
its current stage or terminal state, and the last-updated timestamp; the global
backup-stale `warning` banner (AD-17) at the top of the content column with an
"Esegui backup ora" link; and quick-action links to Clienti and the Guida di
stile. No `core/` change, no data-model change, no new behaviour — the run state
and the staleness rule already exist and are only surfaced here.

## Boundaries & Constraints

**Always:**
- `GET /` is authenticated by default. `ALLOWLIST` stays exactly
  `{"/healthz", "/login"}` and `ALLOWLIST_PREFIXES` stays `("/static/",)` — `/` is
  **not** added to either. An anonymous `GET /` stays an empty-body `401`
  (unchanged; this is what "redirected to sign-in like every other guarded route"
  means in this codebase — every guarded route returns the uniform empty-body
  401, there is no redirect-to-login anywhere today).
- `home.html` does `{% extends "base.html" %}`; exactly one `<html>`, `lang="it"`
  inherited from the base. Exactly one `<h1>` ("Home"). The page primary action
  ("Nuovo cliente" → `/clients/new`) goes in `{% block page_header %}`; the run
  list and banner go in `{% block content %}`.
- Every visible string is Italian from the start (this is new UI, not a Story 9.1
  mechanical migration). Domain labels are fixed per EXPERIENCE.md: **Cliente**,
  **Report**, **Guida di stile**, **Backup**. Timestamps render `dd/MM/yyyy HH:mm`;
  the `YYYY-MM` month renders as a mono chip, Latin-alphanumeric.
- Backup-stale banner copy is exactly:
  `Backup non aggiornato — esistono nuovi report dall'ultimo backup.` with a link
  labelled `Esegui backup ora` to `/backup?record=1`. Banner is a
  `warning`-styled region with `role="alert"`; shown iff `backup_is_stale` is
  true; absent otherwise; absent again after a `GET /backup?record=1`.
- Recent-runs list: `select(ReportRun, Client)` joined on `ReportRun.client_id ==
  Client.id`, ordered `ReportRun.updated_at` desc (tie-break `ReportRun.id` desc),
  `.limit(_RECENT_LIMIT)` with `_RECENT_LIMIT = 20` as a named module constant.
  Empty result → the one-line empty state `Nessun report avviato.` with the quick
  actions still shown.
- Status badge text is a fixed total map over `(run.failed_at, run.stage)`:
  `failed_at` set → `Verifica non superata` (`danger` variant), with
  `run.failure_reason` as the element `title`; `stage == "exported"` → `Esportato`
  (`success`); `stage == "gate_passed"` → `Pronto per l'esportazione` (`running`);
  `"draft_ready"` → `Verifica di fondatezza` (`running`); `"payload_ready"` →
  `Generazione della bozza` (`running`); `"transits_ready"` → `Assemblaggio del
  Payload` (`running`); `"natal_ready"` → `Ricerca dei transiti` (`running`);
  `stage is None` → `In coda` (neutral). Keep this map local to `home.py` (a
  module-level dict or a small helper) — Story 9.5 owns the full stage track and
  may generalise it later.
- The staleness predicate currently lives as the private
  `shell/http/routes/clients.py::_backup_is_stale`. Promote the body to
  `shell/adapters/postgres/backup_record.py` as
  `backup_is_stale(session) -> bool` (add it to `__all__`); leave
  `clients.py::_backup_is_stale` as a one-line delegate keeping its name and
  docstring so `tests/test_http_backup.py`'s existing import stays valid.
- New Python modules open with a prose "why" docstring, are fully type-hinted,
  and start with `from __future__ import annotations`. `home.py` mirrors the
  `_TEMPLATES_DIR` / `_templates = Jinja2Templates(...)` pattern the other five
  route modules use; it is registered in `create_app()` with an
  `include_router` call alongside the others.

**Ask First:**
- The mockup (`key-home.html`) also shows three summary cards ("Report di
  dicembre 21/28", "Clienti 28", "Guida di stile v8"). These are **excluded** —
  the AC only calls for the recent-runs list, and "Report di <month>" needs a
  forecast-month selection rule that is not specified. Confirm exclusion, or
  renegotiate scope to include them.
- The mockup shows a secondary `warning` "tema superato" badge on rows whose
  chart was later superseded. **Excluded** here (adds a `StoredNatalChart`
  lookup; not in the AC). Confirm, or pull it in.
- Any change to a `core/` module, a route path/signature other than adding `GET
  /`, an HTTP status, or a data model — none is expected; HALT if one seems
  required.

**Never:**
- No `/` entry in `ALLOWLIST` / `ALLOWLIST_PREFIXES`; no redirect-to-login
  mechanism (the app has none — do not invent one for this story).
- No change to `report_export.html`, to any `core/` code, to the `ReportRun` /
  `Report` / `BackupRecord` schemas, or to the run driver.
- No new toast / skeleton / loader component (Story 9.8); no HTMX polling on the
  dashboard (the badges are point-in-time on page load — Story 9.5 owns live
  polling). No client-side JS specific to this page.
- No translation or restyle of the existing `client_reports.html` banner or any
  other already-shipped screen (Stories 9.3 / 9.9). No shared banner partial yet.
- No Tailwind / build step / npm / SPA. Any CSS this page needs is a small
  provisional block appended to the vendored `static/tokens.css`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Authenticated `GET /`, runs exist | valid session; ≥1 `ReportRun` | 200; extends `base.html`; exactly one `<html`, `lang="it"`; `<h1>Home</h1>`; one row per recent run (newest-updated first, ≤20) with Client name, month as a mono chip, the mapped Italian status badge, updated `dd/MM/yyyy HH:mm`; quick-action links to `/clients` and `/style-guide`; "Nuovo cliente" action → `/clients/new` | N/A |
| Authenticated `GET /`, no runs | valid session; zero `ReportRun` | 200; one-line empty state `Nessun report avviato.`; quick actions still rendered; no run table | N/A |
| Backup is stale | ≥1 `Report` and (no `backup_record`, or newest `Report.created_at` > latest `backup_record.created_at`) | `warning` banner with `role="alert"` at the top of the content column: `Backup non aggiornato — esistono nuovi report dall'ultimo backup.` + `Esegui backup ora` → `/backup?record=1` | N/A |
| Backup not stale | no `Report` at all, or latest `backup_record.created_at` ≥ newest `Report.created_at` | no banner in the response | N/A |
| Banner clears after a recorded backup | stale, then `GET /backup?record=1`, then reload `/` | banner absent on the reload | N/A |
| Terminal-failed run | `run.failed_at` is set | badge reads `Verifica non superata`, `danger` variant, `title="{run.failure_reason}"` | N/A |
| Not-yet-advanced run | `run.stage is None` | badge reads `In coda`, neutral variant | N/A |
| Anonymous `GET /` | no / invalid session cookie | `401`, empty body; `/` never appears in `ALLOWLIST` | uniform empty-body 401 (middleware, ahead of routing) |

</frozen-after-approval>

## Code Map

- `shell/http/app.py` — `create_app()` (l.110) builds the app; router imports at
  l.122–127, `include_router` calls at l.146–151, `/static` mount l.152, the
  inline `/healthz` + `/login` routes l.156–226. **Add** `from
  shell.http.routes.home import router as home_router` to the deferred import
  block and `application.include_router(home_router)` alongside the others. No
  other change here.
- `shell/http/routes/home.py` — **new.** Smallest existing sibling to copy is
  `shell/http/routes/backup.py` (imports `get_session` from `shell.http.app`,
  `router = APIRouter()`, `__all__ = ["router"]`, `@router.get("/", ...
  include_in_schema=False)`). Add the `_TEMPLATES_DIR` /
  `_templates = Jinja2Templates(...)` pair as in `corpus.py:41-42`. Query
  `ReportRun` + `Client`, compute `backup_is_stale(session)`, render `home.html`.
- `shell/http/routes/clients.py` — `_backup_is_stale` (l.603–624) is the staleness
  logic to promote; call sites at l.692 (and its docstring l.652–656). After the
  move, l.603 becomes a one-line delegate. `list_client_reports` (l.627) is the
  reference for the `select(Report, ReportRun).join(...)` + `session.exec(...).all()`
  shape and for how `backup_stale` is passed into a `TemplateResponse` context.
- `shell/adapters/postgres/backup_record.py` — has `latest_backup_record`
  (l.48), `store_backup_record` (l.60), `__all__` (l.33). **Add**
  `backup_is_stale(session)` here: reads `Report.created_at`
  (`from shell.adapters.postgres.report import Report`; no import cycle —
  `report.py` does not import this module) and `latest_backup_record`. Logic
  verbatim from `clients.py::_backup_is_stale`: no `Report` → `False`; else no
  `backup_record` → `True`; else `newest_report_created_at > latest_backup.created_at`.
- `shell/adapters/postgres/report_run.py` — `ReportRun` model. Fields used:
  `client_id`, `month` (str `YYYY-MM`), `stage` (`str | None`), `failed_at`
  (`datetime | None`), `failure_reason` (`str | None`), `updated_at` (datetime).
  Stage sequence is `natal_ready → transits_ready → payload_ready → draft_ready →
  gate_passed → exported` (`shell/runner/driver.py::_STAGE_SEQUENCE`, l.113).
- `shell/adapters/postgres/client.py` — `Client` model; `Client.name` (l.84) is a
  single `str` (no split name fields).
- `shell/http/templates/base.html` — the layout to extend. Blocks: `title`,
  `page_header`, `content`. It already marks the "Home" nav item active when
  `request.url.path == "/"` (l.43–46) — no sidebar change needed.
- `shell/http/templates/home.html` — **new.** `{% extends "base.html" %}`,
  `{% block title %}Home — astro-report{% endblock %}`, `page_header` with the
  `<h1>` + "Nuovo cliente" link, `content` with the banner (conditional),
  the run list (or empty state), and the two quick-action links.
- `shell/http/static/tokens.css` — has the `--warning` / `--warning-surface`
  colour tokens (l.49-50, +dark) but **no** component classes. **Append** a small
  provisional block: a `warning` banner rule, a `.status-badge` + four variants
  (neutral / running / success / danger) keyed to existing semantic tokens, and a
  compact list/row layout for the dashboard. Mark it "provisional — Story 9.8
  consolidates".
- `_bmad-output/.../mockups/key-home.html` — visual reference (layout, badge
  phrasing, banner). Illustrative; the AC + EXPERIENCE.md label map win on conflict.
- `_bmad-output/.../EXPERIENCE.md` — `## Information Architecture` (Home row, the
  global-banner rule), `## Voice and Tone` (stage labels, empty-state style, the
  exact backup-stale copy), `## State Patterns` → Partial / stale (banner spec).
- `tests/test_http_shell.py` — `test_slash_is_still_unregistered_for_an_authenticated_caller`
  (l.329) asserts authenticated `/` is 404 — **rewrite** to expect 200 +
  dashboard markers. Its anonymous sibling `test_slash_is_401_empty_body_for_an_anonymous_caller`
  (l.337) stays green unchanged.
- `tests/test_http_app.py` — `test_authenticated_requests_still_get_fastapis_own_404_for_unknown_paths`
  (parametrize includes `"/"`) — **drop `"/"`** from the list. The anonymous
  `test_anonymous_requests_to_anything_outside_the_allowlist_are_uniformly_401`
  keeps `"/"` (still 401, unchanged). `test_a_session_from_signing_in_authenticates_later_requests`
  ends with `assert client.get("/").status_code == 404` — **change** to `== 200`
  (a signed-in session still proves it reaches routing).
- `tests/test_auth.py` — `test_every_route_is_authenticated_unless_allowlisted`
  (l.174) walks `app.routes`; `/` will be walked and must 401 anonymously — it
  will, since `/` is not allowlisted. No edit expected; verify it stays green.
- `tests/test_http_backup.py` — imports `from shell.http.routes.clients import
  _backup_is_stale` (l.43) and asserts on it (l.597–635). The one-line delegate
  keeps this green; verify.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/backup_record.py` — add `backup_is_stale(session:
  Session) -> bool` (logic verbatim from `clients.py::_backup_is_stale`), import
  `Report`, add the name to `__all__`.
- [x] `shell/http/routes/clients.py` — replace `_backup_is_stale`'s body with a
  one-line delegate to `backup_record.backup_is_stale`; keep the name, signature
  and docstring. Update the docstring reference at l.652–656 if it names the old
  location.
- [x] `shell/http/routes/home.py` — new router: `GET /` (authenticated by
  default, `include_in_schema=False`). Query recent `ReportRun` + `Client`
  (join, `updated_at` desc, `id` desc tie-break, `limit(_RECENT_LIMIT=20)`);
  build one view row per run `{client_name, month, badge_text, badge_variant,
  failure_reason, updated_at}` via the fixed `(failed_at, stage)` → label map;
  compute `backup_is_stale`; render `home.html` with `runs`, `backup_stale`.
- [x] `shell/http/app.py` — import `home_router` in the deferred block; add
  `application.include_router(home_router)`.
- [x] `shell/http/templates/home.html` — new; `{% extends "base.html" %}`.
  `page_header`: `<h1>Home</h1>` + "Nuovo cliente" link to `/clients/new`.
  `content`: the conditional backup-stale `warning` banner (`role="alert"`, exact
  Italian copy, `Esegui backup ora` → `/backup?record=1`); the recent-runs list
  (Client name, month mono chip, `.status-badge` with variant class, updated
  timestamp `dd/MM/yyyy HH:mm`) or the `Nessun report avviato.` empty state; the
  two quick-action links (`Vai a Clienti` → `/clients`, `Apri la guida di stile`
  → `/style-guide`).
- [x] `shell/http/static/tokens.css` — append a provisional component block:
  `warning` banner, `.status-badge` + neutral/running/success/danger variants
  (semantic tokens only, contrast ≥ 3:1 non-text / ≥ 4.5:1 text in both themes),
  compact dashboard list layout. Comment it as Story 9.8 consolidation fodder.
- [x] `tests/test_http_home.py` — new. Cover every I/O & Edge-Case Matrix row:
  authenticated dashboard with runs (markup markers, ordering, cap, badge text
  for each `(failed_at, stage)` case, month mono chip, timestamp format);
  empty-state path; banner shown when stale / absent when not / absent after
  `GET /backup?record=1`; anonymous `GET /` is `401` empty body; the response
  extends `base.html` (one `<html`, `lang="it"`, sidebar present, "Home" nav
  active). Use the `authenticated_client` / DB-session fixtures the other
  `tests/test_http_*.py` files use.
- [x] `tests/test_http_shell.py` — rewrite
  `test_slash_is_still_unregistered_for_an_authenticated_caller`: authenticated
  `GET /` → 200, body has `<h1>Home</h1>` and one `<html`. Leave the anonymous
  sibling untouched.
- [x] `tests/test_http_app.py` — drop `"/"` from
  `test_authenticated_requests_still_get_fastapis_own_404_for_unknown_paths`'s
  parametrize list; change the trailing `client.get("/")` assertion in
  `test_a_session_from_signing_in_authenticates_later_requests` from `404` to
  `200`. Leave the anonymous-401 parametrized test (which keeps `"/"`) as is.

**Acceptance Criteria:**
- Given an authenticated session, when `GET /` is handled, then a dashboard
  renders (200, not 404) listing recent `ReportRun`s newest-first and capped at
  20, each with its Client name, its month as a mono chip, an Italian status
  badge reflecting `run.stage` or its terminal state, and a `dd/MM/yyyy HH:mm`
  updated time.
- Given no `ReportRun` rows, when `GET /` renders, then the run area shows exactly
  `Nessun report avviato.` and the quick actions are still present.
- Given the newest `Report` postdates the last recorded backup (or no backup was
  ever recorded), when `GET /` renders, then a `warning` `role="alert"` banner
  with the text `Backup non aggiornato — esistono nuovi report dall'ultimo
  backup.` and an `Esegui backup ora` link to `/backup?record=1` appears at the
  top of the content column; and after a `GET /backup?record=1` the next `GET /`
  renders without it.
- Given the dashboard, when it renders, then it links to `/clients` and to
  `/style-guide` as quick actions and to `/clients/new` as the page primary
  action.
- Given an unauthenticated request to `GET /`, when it is handled, then it is a
  `401` with an empty body — the same response every non-allowlisted route
  gives — and `ALLOWLIST` is still exactly `{"/healthz", "/login"}`.
- Given the full suite, when the story is done, then `uv run pytest`,
  `uv run ruff check .` and `uv run ruff format --check .` are all green,
  including the new `tests/test_http_home.py` and the amended shell/app tests.

## Design Notes

**Why a new route module rather than an inline route in `app.py`.** `/healthz`
and `/login` are inline because they take no DB session and no template beyond
`login.html`. The dashboard needs `Depends(get_session)`, a join query and a
template context — that is the shape every other `shell/http/routes/*.py` module
already has. `home.py` copied from `backup.py` keeps `app.py` a factory, not a
handler bag.

**Why the staleness predicate moves to the adapter layer.** It is now read by two
screens (client reports, and this dashboard), and EXPERIENCE.md makes the banner a
global concern. Importing a `_`-private function across route modules is the
smell the codebase already calls out (see `corpus.py`'s note about not importing
`report_runs.py`). `backup_record.py` already owns `latest_backup_record` /
`store_backup_record`, so the predicate belongs beside them. The `clients.py`
delegate is kept only so the existing `tests/test_http_backup.py` import needs no
churn.

**The banner is dashboard-scoped for now, not truly global.** EXPERIENCE.md wants
it on every screen; doing that needs either every route to pass the flag or a
shared Jinja context, and Story 9.1 explicitly ruled a shared-`Jinja2Templates`
refactor out of scope. This story puts it on the dashboard (where the AC requires
it) and leaves it on `client_reports.html` (Story 6.6). A shared partial + global
wiring is later-story work (9.3 / 9.8).

**Status badge is a total map, computed server-side.** No `None`/unknown gap: the
`(failed_at, stage)` pair covers every persisted state. `failed_at` wins over
`stage` (a run can be failed at any stage). The label wording tracks
EXPERIENCE.md's "what happens next" framing — a run whose last *completed* stage
is `transits_ready` is shown as `Assemblaggio del Payload`, matching the mockup.

## Verification

**Commands:**
- `uv run pytest` — expected: full suite green, including new `tests/test_http_home.py`
  and the amended `tests/test_http_shell.py` / `tests/test_http_app.py`.
- `uv run pytest tests/test_auth.py tests/test_http_backup.py` — expected: green
  unchanged (the `_backup_is_stale` delegate and the un-allowlisted `/`).
- `uv run ruff check .` — expected: clean (new modules carry
  `from __future__ import annotations`).
- `uv run ruff format --check .` — expected: clean.
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -rn "unpkg\|cdn\|htmx.org" shell/http/templates/home.html`
  — expected: no matches.
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -n "<html" shell/http/templates/home.html`
  — expected: no matches (it extends `base.html`).

**Manual checks:**
- Run the app, sign in, open `/`: the sidebar shows Home active, the run list
  matches recent runs, the backup banner state matches whether a fresh Report is
  un-backed-up. Follow "Esegui backup ora", then reload `/` — the banner is gone.
- Compare against `mockups/key-home.html` and the DESIGN.md dashboard dimensions
  (~1120px). Toggle the theme — badge and banner contrast hold in both.

## Suggested Review Order

**The new route (design intent)**

- Entry point — the `GET /` handler: one join for recent runs across every Client, a badge per run, the backup-stale flag, then `home.html`.
  [`home.py:86`](../../shell/http/routes/home.py#L86)
- The fixed Italian status-badge map (`stage` → text + variant) with `failed_at` winning and a neutral `.get` fallback so an unmapped stage never 500s the landing page.
  [`home.py:71`](../../shell/http/routes/home.py#L71)
- The route is authenticated by default — registered like every other router, never added to `ALLOWLIST`, so anonymous `GET /` stays the uniform empty-body 401.
  [`app.py:153`](../../shell/http/app.py#L153)

**The backup-stale predicate, promoted to the adapter layer**

- `backup_is_stale` moved here beside `latest_backup_record` — now read by both the dashboard and the Client-reports page instead of a `_`-private cross-module import.
  [`backup_record.py:66`](../../shell/adapters/postgres/backup_record.py#L66)
- `clients.py` keeps the old name as a one-line delegate so `tests/test_http_backup.py`'s existing import is untouched.
  [`clients.py:620`](../../shell/http/routes/clients.py#L620)

**The dashboard template and its styling**

- Extends `base.html`; conditional `warning` banner, the recent-runs list under a real `<h2>`, a one-line empty state with an onward link, and the quick actions.
  [`home.html:1`](../../shell/http/templates/home.html#L1)
- Provisional component block (banner / badges / list) — semantic tokens only, `flex-wrap` and ≥24px targets for the 200%-zoom and touch-target floors; Story 9.8 consolidates.
  [`tokens.css:486`](../../shell/http/static/tokens.css#L486)

**Auth-boundary tests updated for a now-registered `/`**

- `/` authenticated now serves the dashboard (was a routing 404); the anonymous-401 sibling is untouched.
  [`test_http_shell.py:329`](../../tests/test_http_shell.py#L329)
- `/` dropped from the authenticated-404 parametrize list; the sign-in test now proves routing is reached via a 200.
  [`test_http_app.py:229`](../../tests/test_http_app.py#L229)
- The valid-cookie checkpoint test: past auth, `/` is a 200.
  [`test_auth.py:231`](../../tests/test_auth.py#L231)

**Coverage (peripherals)**

- Full I/O-matrix walk for the dashboard: shell markers, links, empty state, row content, ordering, cap, the parametrized badge map, terminal failure, and the banner shown/absent/cleared.
  [`test_http_home.py:1`](../../tests/test_http_home.py#L1)
- The unmapped-stage regression guard: an unknown `stage` degrades to the neutral badge with a 200, never a 500.
  [`test_http_home.py:355`](../../tests/test_http_home.py#L355)
- Direct unit coverage for the promoted `backup_is_stale` (no Report; Report + no backup; backup ahead; Report ahead).
  [`test_backup_record_store.py:1`](../../tests/test_backup_record_store.py#L1)
