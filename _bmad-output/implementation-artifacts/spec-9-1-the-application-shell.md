---
title: 'Story 9.1 — The application shell: one styled layout every page extends'
type: 'refactor'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd26deee5f58079b7d24c358a6ff6f7a376652a70'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/mockups/'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The operator UI is sixteen standalone full-HTML templates, each shipping its own
`<!doctype>/<html lang="en">/<head>` skeleton, one of them pulling HTMX from a CDN, none sharing
styling, navigation, or a theme. There is no shell for the rest of Epic 9 to extend.

**Approach:** Introduce one `base.html` that carries the `<html lang="it">` document, a vendored
`static/tokens.css` (the DESIGN.md token set as CSS custom properties, light + dark) and a vendored
`static/htmx.min.js` loaded exactly once, a persistent 240px sidebar with the five Italian nav areas
+ theme toggle + Esci, a skip-to-content link, and `nav`/`main` landmarks. Every operator template
becomes `{% extends "base.html" %}` + blocks, dropping its own skeleton and keeping its existing body
content and copy verbatim. A `/static` mount is added and allowlisted by path prefix so pre-auth
`/login` still loads its stylesheet. No route contract, `core/` code, FR behaviour, or on-screen copy
changes; the Italian-copy sweep and the full a11y audit are Stories 9.9, feedback primitives are 9.8,
the `/` dashboard is 9.2.

## Boundaries & Constraints

**Always:**
- Exactly one `base.html`; after this story no operator template contains `<!doctype>`, `<html>`, or
  `<head>`. `_bare.html` (a no-op layout: `{% block content %}{% endblock %}`) is the one permitted
  second layout, used only so an HTMX fragment response emits no document skeleton.
- `<html lang="it">` on every rendered operator page. The five nav labels, the theme-toggle label,
  and `Esci` are Italian from the start (**Home, Clienti, Guida di stile, Corpus, Backup**, `Tema
  chiaro / scuro`, `Esci`) per EXPERIENCE.md — this is chrome, not screen copy.
- `static/tokens.css` defines a CSS custom property for every token in DESIGN.md's frontmatter
  `colors:` map (light values on `:root`, `-dark` values under both `@media (prefers-color-scheme:
  dark)` and `:root[data-theme="dark"]`), plus the nine-role type scale, the 4px spacing scale, and
  the radius + elevation scales. Transcribe DESIGN.md values exactly; do not invent hexes.
- HTMX is vendored (`static/htmx.min.js`, the 2.0.4 build matching today's `htmx.org@2.0.4` pin),
  loaded once from `base.html`'s `<head>`. No `unpkg`/CDN `<script>` remains in any template.
- `AuthMiddleware` still rejects every non-allowlisted route anonymously with an empty-body 401.
  `ALLOWLIST` stays exactly `{"/healthz", "/login"}`. Static assets are reachable anonymously via a
  new, separately-declared `ALLOWLIST_PREFIXES = ("/static/",)` (prefix requires the trailing slash
  and a following path segment — the bare `/static` mount path stays 401).
- Every migrated template keeps its current element structure, ids, `role="alert"`, form field
  names, links, and English text nodes so the existing `tests/test_http_*.py` substring assertions
  still pass.
- `report_run_poll.html` keeps its dual-mode behaviour: full-page request → `base.html`; `HX-Request`
  → `_bare.html` (fragment only, no `<html>`, no htmx `<script>`).
- New/edited Python modules open with a prose "why" docstring, are fully type-hinted, and start with
  `from __future__ import annotations`. Any new syntactic-guard test ships a negative
  `test_..._detects_...` counterpart (repo convention).
- Theme choice is applied pre-paint (inline `<head>` snippet reading `localStorage`) to avoid a
  flash; the toggle handler and the <900px drawer (focus-trapped, Esc-closes, focus restored to the
  trigger) live in `static/shell.js`. All shell transitions are disabled under
  `prefers-reduced-motion`.

**Ask First:**
- The **Home** nav item links to `/`, which 404s until Story 9.2. If a visible dead link is
  unacceptable as an interim, HALT and agree an alternative (e.g. Home → `/clients` until 9.2).
- Replacing (vs. deleting) `tests/test_http_chart_wheel.py::test_chart_wheel_template_is_byte_identical_when_config_is_not_stale`
  — the frozen byte-for-byte snapshot is genuinely obsoleted by the shell. Plan is to rewrite it as
  semantic assertions; confirm before deleting any assertion it uniquely carries.
- Any change to a `core/` module, a route path/signature, an HTTP status, or a data model — none is
  expected; HALT if one seems required.

**Never:**
- No new route or dashboard content (`/` stays unregistered — Story 9.2). No changes to
  `report_export.html` (the WeasyPrint client document: keeps its standalone `<html>`, Georgia serif,
  no `{% extends %}`, does not link `tokens.css`).
- No Italian translation of screen body copy, form labels, errors, or empty states (Story 9.9). No
  toasts, skeletons, spinners, or inline-validation components (Story 9.8). No restyling of a
  screen's inner content beyond what extending `base.html` mechanically requires.
- No Tailwind, no build step, no npm, no bundler, no SPA framework, no web components. Vendored files
  are committed assets, not fetched.
- No shared-`Jinja2Templates`-instance refactor of the six route modules (out of scope; each finds
  `base.html` in the existing templates dir already).
- Do not load any external font/CSS/JS at runtime; `tokens.css` uses a system Inter fallback stack.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Authenticated GET of a migrated operator route | valid session cookie | 200; exactly one `<html`; `lang="it"`; skip-link before `<nav>`; `<nav>` + `<main>` landmarks; sidebar shows the 5 areas + theme toggle + Esci; `tokens.css` and `htmx.min.js` each linked once | N/A |
| HTMX poll of a running run | `GET /report-runs/{id}`, header `HX-Request: true` | fragment only — no `<html>`, no `<head>`, no htmx `<script>`; still contains the stage text | N/A |
| Full-page load of the run stage view | `GET /report-runs/{id}`, no HX header | full shell via `base.html`; exactly one `<html>` | N/A |
| Anonymous GET of a static asset | no session, `GET /static/tokens.css` (and `/static/htmx.min.js`) | 200 with the file bytes; auth bypassed via the `/static/` prefix | unknown `/static/nope.css` → 404, not 401 |
| Anonymous GET of the bare mount path / a non-static unknown path | no session, `GET /static` or `GET /nope` | 401, empty body (prefix match needs `/static/` + a segment) | uniform empty-body 401 |
| Login page render | `GET /login`, no session | 200; extends `base.html`; sidebar/nav chrome suppressed; `tokens.css` still linked so the page is styled pre-auth; exactly one `<html>` | N/A |
| Dark theme | `prefers-color-scheme: dark`, or `data-theme="dark"` on `<html>` via the toggle | dark token values apply; toggle writes the choice to `localStorage` and it is re-applied pre-paint on next load | `localStorage` throwing/absent → silently fall back to `prefers-color-scheme` |
| Viewport < 900px | narrow viewport | sidebar leaves the flow; a header control opens a focus-trapped drawer; Esc / scrim closes it and returns focus to the trigger | N/A |
| `prefers-reduced-motion` set | reduced-motion user | drawer slide and theme transition disabled | N/A |
| `report_export.html` rendered for WeasyPrint | export route renders it to a string | unchanged — its own `<html>`, no `{% extends %}`, no `tokens.css` link | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/app.py` — `create_app()` (l.102) builds the app; `Jinja2Templates(directory=_TEMPLATES_DIR)` at l.145; `_TEMPLATES_DIR` at l.64. **Add** `from fastapi.staticfiles import StaticFiles` and `application.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")` after the routers (l.143). `_STATIC_DIR = Path(__file__).resolve().parent / "static"`.
- `shell/http/auth.py` — `ALLOWLIST` frozenset (l.44); `AuthMiddleware.dispatch` (l.147) normalizes trailing slash (l.156) then checks `ALLOWLIST` membership (l.157). **Add** `ALLOWLIST_PREFIXES: tuple[str, ...] = ("/static/",)`, extend the l.157 guard with `or request.url.path.startswith(ALLOWLIST_PREFIXES)`, add `ALLOWLIST_PREFIXES` to `__all__` (l.30).
- `shell/http/routes/{clients,corpus,style_guide,chart,report_runs}.py` — each builds its own `Jinja2Templates` on `_TEMPLATES_DIR = .../templates` (chart.py:40, clients.py:67, corpus.py:41, report_runs.py:68, style_guide.py:45). No code change needed — `{% extends "base.html" %}` resolves against the same dir. `report_runs.py:279` renders `report_run_poll.html`; `report_runs.py:497` renders `report_export.html` via `get_template().render()` for WeasyPrint (leave untouched).
- `shell/http/templates/*.html` — 16 templates. **Migrate 15** (see task list) to extend `base.html`. **Exclude** `report_export.html`.
- `shell/http/templates/report_run_poll.html` — current dual-mode guard `{% if not request.headers.get("hx-request") %}` wraps a hand-rolled skeleton incl. `<script src="https://unpkg.com/htmx.org@2.0.4">` (l.9). Convert to `{% extends "_bare.html" if request.headers.get("hx-request") else "base.html" %}`.
- `tests/test_auth.py` — `test_the_allowlist_holds_exactly_healthz_and_login` (l.170), `test_every_route_is_authenticated_unless_allowlisted` (l.174, walks `app.routes`). Expected to stay green (`ALLOWLIST` unchanged; bare `/static` → 401). Add prefix coverage in the new shell test, not here.
- `tests/test_http_chart_wheel.py:360` — `test_chart_wheel_template_is_byte_identical_when_config_is_not_stale`: frozen full-markup snapshot incl. `<html lang="en">`. **Rewrite** as semantic assertions.
- `tests/test_http_report_runs.py:414` — `test_an_htmx_poll_request_gets_a_fragment_without_the_full_page_shell`: asserts `<html` in full page, absent in fragment. Must stay green after the conditional-extends conversion (no edit expected; verify).
- `tests/test_http_*.py` — ~10 files of route tests asserting on rendered-body substrings (field names, `role="alert"`, English titles). Preserve those tokens; run the whole suite.
- `_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md` — frontmatter `colors:` / `typography:` / `spacing:` / `rounded:` / `components:` maps are the token source of truth; `## Colors`/`## Typography`/`## Layout & Spacing` prose carries the contrast floors and the shell dimensions.
- `.../mockups/key-home.html`, `key-clienti.html`, `color-themes-1.html` — visual reference for the shell, sidebar states, and light/dark; illustrative only, the spine wins on conflict.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/static/tokens.css` — create. Transcribe DESIGN.md frontmatter: every `colors:` key as `--<key>` on `:root` (light); the `-dark` keys redefined under `@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]) }` and under `:root[data-theme="dark"]`. Add `--font-<role>` size/line-height/weight vars for the nine type roles, `--space-<step>` for the 4px scale, `--radius-<step>`, and the two elevation shadows. Include a minimal reset + `body` background/color from tokens + a system Inter fallback stack. No `@import`, no external font.
- [x] `shell/http/static/htmx.min.js` — vendor the htmx 2.0.4 minified build (same version as the removed `htmx.org@2.0.4` CDN pin). Committed file.
- [x] `shell/http/static/shell.js` — first-party, no deps: (1) theme toggle — flip `data-theme` on `<html>`, persist to `localStorage`, wrapped in try/catch; (2) <900px drawer — open/close from the header control, focus-trap while open, close on Esc and scrim click, restore focus to the trigger. Guard all animation behind `prefers-reduced-motion`.
- [x] `shell/http/templates/base.html` — create. `<!doctype html>` + `<html lang="it">`; `<head>` with charset, viewport, `robots noindex,nofollow`, `<title>{% block title %}astro-report{% endblock %}`, `<link rel="stylesheet" href="/static/tokens.css">`, the pre-paint theme `<script>` (inline), `<script src="/static/htmx.min.js" defer></script>`. `<body>`: skip-to-content link → `{% block sidebar %}` (default: `<nav>` with the 5 areas, active-item marker keyed off `request.url.path`, theme toggle, `Esci` pinned bottom; a <900px header control) → `<main id="main-content">{% block page_header %}{% endblock %}{% block content %}{% endblock %}</main>` → `<script src="/static/shell.js" defer></script>`. Login suppresses the sidebar by overriding `{% block sidebar %}{% endblock %}`.
- [x] `shell/http/templates/_bare.html` — create: exactly `{% block content %}{% endblock %}` (+ trailing newline). Fragment layout for HTMX responses.
- [x] `shell/http/templates/report_run_poll.html` — convert to `{% extends "_bare.html" if request.headers.get("hx-request") else "base.html" %}`; move the `#run-status` div into `{% block content %}`; move `<h1>` into `page_header`/`content`; delete the unpkg `<script>` and the hand-rolled skeleton.
- [x] `shell/http/templates/login.html` — extend `base.html`; override `{% block sidebar %}{% endblock %}`; move the form + error banner into `{% block content %}`; keep field names, `error` handling, and text.
- [x] `shell/http/templates/{client_new,client_edit,client_delete,client_reports}.html` — extend `base.html`; body into `{% block content %}`; `<h1>` into `page_header` or `content`; keep all field names, `role="alert"`, `candidates`/`fieldset` logic, links, and copy verbatim.
- [x] `shell/http/templates/{corpus_list,corpus_new}.html` — same migration.
- [x] `shell/http/templates/{style_guide_list,style_guide_edit,style_guide_view}.html` — same migration.
- [x] `shell/http/templates/{report,report_draft,report_payload,chart_wheel}.html` — same migration; `chart_wheel.html` keeps `{{ svg | safe }}` and the `config_stale` block and its ids unchanged.
- [x] `shell/http/app.py` — import `StaticFiles`; add `_STATIC_DIR`; `application.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")` after the router includes.
- [x] `shell/http/auth.py` — add `ALLOWLIST_PREFIXES: tuple[str, ...] = ("/static/",)` next to `ALLOWLIST`; in `dispatch`, bypass when `request.url.path.startswith(ALLOWLIST_PREFIXES)`; export it in `__all__`; update the module docstring's allowlist sentence.
- [x] `tests/test_http_chart_wheel.py` — rewrite `test_chart_wheel_template_is_byte_identical_when_config_is_not_stale` as: renders via the route with `config_stale` false → 200, `'role="alert"'` and `"config-stale-warning"` absent, `"<svg" ` present, exactly one `<html`, `lang="it"`. Keep the stale-path sibling test's behaviour.
- [x] `tests/test_http_shell.py` — create. Cover the I/O Matrix rows: one-`<html>` + landmarks + skip link + sidebar labels + `lang="it"` across a parametrized set of migrated routes (authenticated); the HTMX-fragment vs full-page split for `report_run_poll`; `login` renders through `base.html` with no sidebar nav; `htmx.min.js` referenced exactly once and no `unpkg`/`cdn` substring anywhere; `/static/tokens.css` + `/static/htmx.min.js` reachable with no session; bare `/static` and `/nope` still 401 empty-body anonymously; every DESIGN.md `colors:` key (light + `-dark`) present as a `--` custom property in `tokens.css`; `report_export.html` source has no `{% extends %}` and keeps its own `<html>`. Ship negatives: `test_the_one_html_guard_detects_a_second_html_element`, `test_the_htmx_once_guard_detects_a_duplicate_or_cdn_script`.

**Acceptance Criteria:**
- Given the migrated templates, when each operator route is fetched with a valid session, then the response has exactly one `<html>` element, `lang="it"`, a skip-to-content link preceding a `<nav>`, a `<main>`, and the sidebar (Home / Clienti / Guida di stile / Corpus / Backup, a theme toggle, Esci) with an active-item marker matching the path.
- Given `base.html`, when any page loads, then `/static/tokens.css` is linked once and `/static/htmx.min.js` is the only htmx `<script>`; no template references `unpkg` or any CDN.
- Given `tokens.css`, when the viewer's OS is dark or `data-theme="dark"` is set, then dark token values apply, and contrast meets the DESIGN.md floor in both themes (body ≥ 7:1, secondary ≥ 4.5:1, non-text UI ≥ 3:1) — verified by Francesco against DESIGN.md.
- Given `AuthMiddleware`, when an anonymous request hits `/static/tokens.css`, then it is served 200; when it hits `/static` or any non-allowlisted path, then it is 401 with an empty body, and `ALLOWLIST` is still exactly `{"/healthz", "/login"}`.
- Given the existing route set, when the shell is in place, then every route still renders, `tests/test_auth.py` and every `tests/test_http_*.py` pass, and `/` is still unregistered (404 authenticated, 401 anonymous).
- Given `report_export.html`, when a PDF is exported, then its output is unchanged — standalone `<html>`, Georgia serif, no `tokens.css`.
- Given a viewport below 900px, when the header drawer control is used, then the sidebar opens as a focus-trapped drawer that closes on Esc and restores focus to the trigger; under `prefers-reduced-motion` no shell animation runs.

## Spec Change Log

## Design Notes

**Why `_bare.html` instead of a conditional block for the fragment path.** `{% extends %}` must be
the first tag in a template and cannot be wrapped in `{% if %}`, but its argument *can* be an
expression. `{% extends "_bare.html" if request.headers.get("hx-request") else "base.html" %}` keeps
one real shell (`base.html`) while letting an HX poll return just `{% block content %}`. `_bare.html`
is a layout, not a per-template skeleton, so it does not violate the "one base.html / no own
skeleton" rule — and `tests/test_http_report_runs.py:414` still sees `<html>` only on the full page.

**Pre-paint theme snippet** (inline in `<head>`, before the stylesheet paints):
```html
<script>try{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t;}catch(e){}</script>
```
Everything else (the toggle click handler, the drawer) is in `static/shell.js`, `defer`-loaded.

**tokens.css theme structure** — define light on bare `:root`; redefine dark under
`@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){…} }` and again under
`:root[data-theme="dark"]{…}` so an explicit toggle wins in both directions. Never give a token its
only definition inside a media/attribute block.

**Login through the same base** — `base.html` wraps the sidebar in `{% block sidebar %}`; `login.html`
overrides it empty and adds a body/main modifier class for the centred, no-nav layout. One base, no
second document skeleton.

## Verification

**Commands:**
- `uv run pytest` — expected: full suite green, including the new `tests/test_http_shell.py` and the
  rewritten chart-wheel test.
- `uv run ruff check .` — expected: clean (new modules have `from __future__ import annotations`).
- `uv run ruff format --check .` — expected: clean.
- `grep -rn "unpkg\|cdn\|htmx.org" shell/http/templates/` — expected: no matches.
- `grep -rn "<html" shell/http/templates/` — expected: only `base.html` and `report_export.html`.

**Manual checks:**
- Run the app; sign in; open each screen and confirm the sidebar, active-item marker, and styling
  against `DESIGN.md` / `mockups/`. Toggle the theme and reload — the choice persists with no flash.
- Narrow the window below 900px — the sidebar becomes a drawer, keyboard-operable, Esc closes it.
- Export a PDF and confirm it is byte-unchanged from before this story.

## Suggested Review Order

**The shell layout (design intent)**

- Entry point: the one layout every operator page now extends — `<html lang="it">`, head assets, skip link, sidebar block, `<main>` landmark.
  [`base.html:9`](../../shell/http/templates/base.html#L9)
- Active-nav marker derived from `request.url.path` — no per-page wiring; `{% block sidebar %}` is what `login.html` overrides away.
  [`base.html:32`](../../shell/http/templates/base.html#L32)
- Pre-paint theme snippet runs before the stylesheet and only honours a validated `light`/`dark` value.
  [`base.html:20`](../../shell/http/templates/base.html#L20)
- The no-op fragment layout so an HTMX response emits no document skeleton.
  [`_bare.html:1`](../../shell/http/templates/_bare.html#L1)

**The auth boundary (highest risk)**

- Static assets bypass `AuthMiddleware` via a separately-declared prefix tuple — `ALLOWLIST` itself is untouched.
  [`auth.py:54`](../../shell/http/auth.py#L54)
- The dispatch check: exact-match allowlist OR `/static/`-prefix; the bare `/static` mount path still 401s.
  [`auth.py:168`](../../shell/http/auth.py#L168)
- The `/static` mount, added after the routers.
  [`app.py:152`](../../shell/http/app.py#L152)

**Vendored assets**

- Design tokens: light on bare `:root`, dark re-bound under `@media` and `:root[data-theme="dark"]`; base `h1/h2/h3` type roles; `.auth-view` login column; the <900px drawer and the reduced-motion kill switch.
  [`tokens.css:21`](../../shell/http/static/tokens.css#L21)
- Shell JS: theme toggle (localStorage in try/catch) + focus-trapped drawer; `matchMedia("(min-width: 900px)")` releases the trap when the viewport widens.
  [`shell.js:160`](../../shell/http/static/shell.js#L160)

**Template migration (mechanical, one shape ×15)**

- Dual-mode conversion: full page → `base.html`, `HX-Request` → `_bare.html`; the unpkg `<script>` is gone.
  [`report_run_poll.html:1`](../../shell/http/templates/report_run_poll.html#L1)
- `login.html` extends the same base, blanks the sidebar + header, adds `auth-view`; fields/ids/copy verbatim.
  [`login.html:1`](../../shell/http/templates/login.html#L1)
- Representative migration: skeleton dropped, body into `{% block content %}`, `config-stale` block + ids kept.
  [`chart_wheel.html:1`](../../shell/http/templates/chart_wheel.html#L1)
- Largest template diff — the recursive `render_value` macro lifted to child top level (renders green under two existing route tests).
  [`report_payload.html:1`](../../shell/http/templates/report_payload.html#L1)

**Tests (supporting)**

- New shell suite: I/O-matrix coverage — singular shell + landmarks, fragment/full-page split, static reachability vs. the bare mount, traversal guard, token completeness, htmx version pin, two negative guards.
  [`test_http_shell.py:146`](../../tests/test_http_shell.py#L146)
- The frozen byte-identical chart-wheel snapshot, rewritten as semantic assertions (shell obsoleted the snapshot).
  [`test_http_chart_wheel.py:358`](../../tests/test_http_chart_wheel.py#L358)
