---
title: 'Story 9.2 amendment — sign-in redirect and clickable dashboard rows'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 1
route: 'one-shot'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-31.md'
---

## Intent

**Problem:** Story 9.2's own acceptance criteria said an unauthenticated request is "redirected to sign-in like every other guarded route" — but `AuthMiddleware` returned a bare empty-body 401 to every unauthenticated request, browser included, confirmed by an existing test asserting exactly that. Francesco hit a blank page instead of the sign-in screen unless he already knew to type `/login`. Separately, the dashboard's recent-run rows were plain text with no way to open the run they named.

**Approach:** Redirect unauthenticated browser navigations (GET/HEAD, `Accept: text/html`, no `HX-Request`) to `/login?next=<path>`, preserving the uniform 401 for every other caller shape (HTMX polls, JSON-shaped requests, any non-GET/HEAD method — a redirect can't carry a POST body forward). `POST /login` now redirects to a sanitized `next` on success instead of returning plain text. Dashboard rows became links to the run's Report (if a passed `Report` row exists) or its stage view otherwise.

## Suggested Review Order

**The redirect and its guard**

- Entry point — where the 401-vs-redirect decision is made.
  [`auth.py:234`](../../shell/http/auth.py#L234)

- `_wants_html_navigation` — the three-part guard (method, HX-Request, Accept) deciding *how* a denial is presented, never *whether* it happens.
  [`auth.py:194`](../../shell/http/auth.py#L194)

- `safe_next_path` — the open-redirect/header-injection guard on the attacker-controlled `next` value.
  [`auth.py:158`](../../shell/http/auth.py#L158)

**Completing the sign-in loop**

- `/login` GET/POST now read, sanitize, and honor `next` — replacing the old plain-text "Signed in." response nothing ever consumed.
  [`app.py:174`](../../shell/http/app.py#L174)

**Dashboard rows as links**

- `home_dashboard` now checks actual `Report` row existence (matching `view_report`'s own gate) rather than re-deriving readiness from `stage`/`failed_at`.
  [`home.py:90`](../../shell/http/routes/home.py#L90)

**Tests**

- The redirect, its method/HTMX/Accept exclusions, and `safe_next_path`'s adversarial cases (off-site, backslash, tab, CRLF, self-redirect, length cap).
  [`test_auth.py:247`](../../tests/test_auth.py#L247)

- The sign-in flow's redirect-carrying-cookie tests, updated for the 303 (previously asserted a bare 200).
  [`test_http_app.py:255`](../../tests/test_http_app.py#L255)

- Dashboard row links, keyed on `Report` row existence rather than stage.
  [`test_http_home.py:247`](../../tests/test_http_home.py#L247)

## Spec Change Log

- review-loop 1 (blind-hunter): `safe_next_path` also rejected a tab character (the same off-site-redirect bypass class as `//` and `\`, since browsers strip embedded tabs before resolving a URL) and a self-redirect to `/login`, and gained a length cap. The redirect was scoped to `GET`/`HEAD` only — a redirect can't carry a POST body forward, so a guarded `POST` (which also looks like a browser navigation) kept the bare 401 instead of silently dropping the user's action. `home_dashboard`'s "is this run's Report viewable" check was changed from a `stage`/`failed_at` heuristic to an actual `Report`-row-existence query, matching `view_report`'s own source of truth. The dashboard link gained an `aria-label` distinguishing "apri il report" from "apri l'avanzamento," and `.dash-run__client` gained a visible underline (it was a `<span>` before this story; nothing signalled the new `<a>` was clickable). The two POST `/login` failure branches that reject before parsing the body (oversized body, invalid UTF-8) were documented as unable to recover `next` by design, rather than left unexplained.
