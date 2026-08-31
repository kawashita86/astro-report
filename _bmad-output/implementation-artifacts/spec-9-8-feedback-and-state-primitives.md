---
title: 'Feedback and state primitives — toasts, loaders, empty states, inline errors'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'd1e71e3fccbf039c01e3e31351bc640035ba54f4'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** No toast, spinner, skeleton, or per-field validation primitive exists anywhere yet. Three client-mutation routes (create/correct/delete) still return bare fragments outside the app shell entirely — explicitly deferred here by Story 9.4 ("Story 9.8 consolidates"). `client_reports.html`'s empty state is a plain unstyled English paragraph. The stage-track poll retries forever at a fixed 2s with no backoff or manual retry, though Story 9.5 documented that gap for this story too.

**Approach:** One shared `[data-flash]` banner in `base.html`, promoted to a toast by new `shell.js` JS — delivered via a cookie+middleware for the redirect-based writes (corpus, style guide, report-run actions) and via direct template context for the three client responses (now real templates, not bare fragments). Add submit-button lock+spinner and per-field validation to the client forms (fields already carry attributable errors today, just collapsed into one message). Add `.skeleton`/`.spinner` CSS primitives. Consolidate list empty-states behind one `_empty_state.html` macro, bringing `client_reports.html` up to it. Extend the existing stage-track poll-error banner with 5s/15s backoff and a manual "Riprova" trigger, client-side only — AD-20's server semantics are untouched.

## Boundaries & Constraints

**Always:**
- No route status code, redirect target, or existing context key changes anywhere — only new context keys (`flash`, `field_errors`, empty-state vars) are added.
- Existing wording is preserved verbatim (`Client {id} created.` / `corrected.` / `deleted.` stay English, matching Story 9.4's deferral of that translation to Story 9.9). New copy this story introduces where no prior wording exists (corpus/style-guide/report-run flash messages, "Riprova", the `client_reports.html` empty state) is Italian, matching its screen.
- Reuse `tokens.css` components verbatim (`.banner*`, `.btn*`, `.field--invalid`/`.field__error`, `.list-empty`); new CSS is one appended `PROVISIONAL — Story 9.8` block. Extend the existing `prefers-reduced-motion` block (tokens.css:491-504) to also kill the new shimmer/spin/toast-slide animations.
- Form-lock never sets the native `disabled` attribute on a field whose value must reach the server in that same submission (it would silently drop it) — lock is `pointer-events:none` + `aria-disabled` on `.field`s; only the submit `<button>` is actually `disabled`.
- `RedirectResponse` is a `Response` subclass — `set_flash()` calls it directly, no new response type.

**Ask First:** None — decisions below are made; raise deviations at review.

**Never:**
- No global/`base.html` backup-stale banner (UX-DR17's "global" wording) — wide, untested blast radius across every screen for zero ACs in this story; it stays local to the screens that already render it.
- No restyle of `corpus_new.html`, or of anything in `client_reports.html` beyond its one empty-state paragraph — Story 9.9's Italian/audit sweep owns the rest.
- No skeleton wired to a live region — no template has a genuinely unknown-content HTMX load (the one HTMX region, stage-track, always renders real computed content, first load included); `.skeleton` ships as a primitive only, not consumed here.
- No change to AD-20's server-side `advance`/advisory-lock semantics, and no change to `report_run_poll.html`'s existing `every 2s` cadence — backoff is purely a client-side gate on when that already-present trigger is allowed to fire next.
- No session framework, no `itsdangerous`/`SessionMiddleware` dependency — one small cookie plus one ASGI middleware.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Client create/correct/delete succeeds | POST succeeds | `200`, extends `base.html`, same wording + chart link as today, now inside a toast (JS) / dismissible banner (no-JS) | N/A |
| Redirect-based write succeeds (corpus/style-guide/report-run) | POST → `303` | flash cookie set on the redirect response; the destination `GET` shows it as toast/banner; `FlashClearMiddleware` deletes the cookie on that response | N/A |
| 4th toast queued | 3 toasts already visible | oldest is dismissed (FIFO), new one shown; success auto-dismisses ~5s (hover pauses), warning/danger persist with a close control | N/A |
| Field-level create/correct validation | missing/invalid `name`, `birth_date`, `birth_time`, or `birthplace` | that field gets `.field--invalid` + `.field__error` + `aria-describedby`; the existing `.banner--danger` summary lists a link per failed field and takes focus | chart-computation failure (not field-attributable) stays a form-level-only message, unchanged |
| Poll fails once, then twice | `htmx:responseError`/`sendError` on `#run-status` | banner shown; next auto-poll gated 5s, then 15s; `Riprova` appears from the 2nd failure and fires an immediate retry on click | N/A |
| Poll recovers | next poll returns 2xx | banner and `Riprova` hidden, failure count reset to 0 (existing success-hide behavior, now also resets backoff state) | N/A |
| List surface is empty | Clienti / Client Reports / Corpus / Style Guide history / dashboard recent-runs | shared `_empty_state.html` macro: one Italian line + one primary action | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/flash.py` (new) — `set_flash(response, kind, message)` sets a `flash` cookie (JSON); `_flash_context_processor(request)` reads+parses it (try/except on bad JSON → `None`) for Jinja context; `FlashClearMiddleware` deletes the cookie on the outgoing response whenever the request carried one.
- `shell/http/app.py` — `application.add_middleware(FlashClearMiddleware)` (app.py:146 area, alongside `AuthMiddleware`).
- `shell/http/routes/{clients,chart,corpus,home,report_runs,style_guide}.py` — each module's own `Jinja2Templates(directory=_TEMPLATES_DIR)` (clients.py:69, chart.py:41, corpus.py:42, home.py:43, report_runs.py:70, style_guide.py:46) gains `context_processors=[_flash_context_processor]`.
- `shell/http/routes/corpus.py:237`, `style_guide.py:166`, `report_runs.py:324,401,748` — call `set_flash(response, "success", "<italian message>")` on the `RedirectResponse` before returning (entry added / new version saved / report avviato / rigenerazione avviata / esito di invio registrato).
- `shell/http/routes/clients.py:138` (`_render_form`), `:154` (`_render_edit_form`) — new `field_errors: dict[str, str] | None = None` param, passed through to the template context.
- `shell/http/routes/clients.py:283-359` (create) and mirrored `:433-558` (correct) — the missing-fields (289/450), name-length (298/461), `birth_date` (307/472), `birth_time` (317/484), `PlaceResolutionError`+candidate-decode (339-342/515-524) sites each pass a `field_errors={"<field>": "..."}` alongside `error`; the chart-computation site (358/558) stays `error`-only.
- `shell/http/routes/clients.py:378-384` (create success), `:597-603` (correct success), `:677` (delete success) — replace the bare `Response(...)` with `_templates.TemplateResponse(request, "client_action_result.html", {"flash": {"kind": "success", "message": "<unchanged wording>"}, "chart_href": ..., "heading": "Clienti"}, status_code=200)`.
- `shell/http/templates/base.html` — one shared flash block right after `page_header`: `<p class="banner banner--{{ flash.kind }}" role="{{ 'alert' if flash.kind != 'success' else 'status' }}" data-flash data-flash-kind="{{ flash.kind }}" tabindex="-1">{{ flash.message }}<button type="button" class="banner__dismiss" aria-label="Chiudi">×</button></p>` guarded by `{% if flash %}`.
- `shell/http/templates/client_action_result.html` (new) — extends `base.html`; renders the optional `chart_href` link and a "Back to Clienti" link; flash comes from context automatically via the `base.html` block.
- `shell/http/templates/client_new.html`, `client_edit.html` — add `data-submit-lock` to the `<form>`; each `.field` gets conditional `field--invalid`/`.field__error`/`aria-describedby` from `field_errors`; the existing `.banner--danger` summary adds one `<a href="#{field}">` per failed field.
- `shell/http/templates/_empty_state.html` (new) — `{% macro empty_state(message, href, label) %}` rendering the existing `.list-empty` markup.
- `shell/http/templates/client_list.html:61-64`, `home.html:39-42`, `corpus_list.html:46-49`, `style_guide_list.html:41` — swap the ad hoc empty-state paragraph for the macro (copy unchanged, already Italian).
- `shell/http/templates/client_reports.html:26` — swap `<p>No Reports yet for this Client.</p>` for the macro with new Italian copy + a primary action (e.g. "Avvia un report" → the client's report-run start form).
- `shell/http/templates/report_run_poll.html:9-13` (add `poll-retry from:body` to `hx-trigger`), `:27-29` (add `<button type="button" class="btn btn--secondary" data-poll-retry hidden>Riprova</button>` beside `[data-poll-error]`).
- `shell/http/static/tokens.css` — append `PROVISIONAL — Story 9.8` block: `.toast-region`, `.toast` (+ kind variants reusing `.banner`'s kind palette), `.toast__close`, `.skeleton` (+ shimmer `@keyframes`), `.spinner` (+ spin `@keyframes`), `.banner__dismiss`; extend the reduced-motion block at 491-504.
- `shell/http/static/shell.js` — job 11 (toast queue: `showToast`, FIFO cap 3, success auto-dismiss ~5s + hover-pause, warning/danger persist + close); job 12 (`[data-flash]` → toast promotion on load, generic `.banner__dismiss` click handler); job 13 (`[data-submit-lock]` forms: disable+spin the submit button, lock other fields via `pointer-events`, `aria-busy`); extend job 6 (poll, 481-532) with failure-count/backoff state and the `[data-poll-retry]` click handler. Docstring "Ten jobs" → "Thirteen jobs".
- `tests/test_http_shell.py`, `test_http_clients.py`, `test_http_client_deletion.py`, `test_http_corpus.py`, `test_http_style_guide.py`, `test_http_report_runs.py`, `test_stage_view.py` — see Tasks.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/flash.py` — `set_flash`, `_flash_context_processor`, `FlashClearMiddleware` — new module, unit-testable in isolation.
- [x] `shell/http/app.py` — register `FlashClearMiddleware`.
- [x] Six route modules — add `context_processors=[_flash_context_processor]` to each `Jinja2Templates(...)`.
- [x] `corpus.py`, `style_guide.py`, `report_runs.py` (5 redirect sites) — `set_flash(...)` before each `RedirectResponse`.
- [x] `clients.py` — `field_errors` param on `_render_form`/`_render_edit_form`; wire it at the 5 attributable failure sites in `create_client` and the mirrored 5 in `correct_client`.
- [x] `clients.py` + new `client_action_result.html` — replace the 3 bare `Response(...)` successes with the styled template render.
- [x] `base.html` — shared flash block.
- [x] `client_new.html`, `client_edit.html` — `data-submit-lock`, per-field error markup, summary links.
- [x] `_empty_state.html` — new macro; wire into `client_list.html`, `home.html`, `corpus_list.html`, `style_guide_list.html`, `client_reports.html`.
- [x] `report_run_poll.html` — `poll-retry` trigger + `Riprova` button.
- [x] `tokens.css` — `PROVISIONAL — Story 9.8` block + reduced-motion extension.
- [x] `shell.js` — jobs 11-13 + job 6 extension; docstring update.
- [x] Tests — flash cookie set+cleared across a redirect round-trip (one route is enough to prove the mechanism; assert `Set-Cookie` on the `303` and its absence on the following `200`); the three client successes extend `base.html` and keep their exact wording/links/status codes; field-level errors render `aria-describedby` + `field--invalid` for each of the 4 fields and the chart-computation case stays form-level-only; `client_reports.html` empty state is Italian with an action link; `report_run_poll.html` carries `data-poll-retry` and the extended `hx-trigger`; `.skeleton`/`.spinner`/`.toast` classes exist in `tokens.css` and are covered by the reduced-motion block.

**Acceptance Criteria:**
- Given `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, when done, then all pass.
- Given any of the 8 write actions this story touches (client create/correct/delete, corpus add, style-guide save, report-run start/regenerate/disposition), when it succeeds, then a toast appears with JS and a dismissible banner without, at the same status code and destination as before.
- Given the create/correct client form, when a field-specific validation error occurs, then that field is marked invalid with a description and the summary links to it; when a non-field error occurs, then the existing single-message banner is unchanged.
- Given the stage-track view, when a poll fails once then again, then the backoff and `Riprova` button behave as specified, and AD-20's advance/lock semantics are provably untouched (existing Story 3.10/9.5 tests still pass unmodified).
- Given every existing route's status-code/404/redirect-target test, when done, then it still passes unchanged.

## Spec Change Log

## Design Notes

**Why the client success responses become real templates.** `create_client`/`correct_client`/`delete_client` return bare `Response(...)` today — not a redirect, deliberately (epic-2-retro-item-14: a 303 to the chart SVG would be followed and lose the outcome). That constraint stands; only the *body* changes, from a raw string to a `TemplateResponse` carrying the same wording, same status code, same link — now inside `base.html`'s chrome so the flash block (and everything else the shell provides) applies uniformly instead of needing a fourth, bespoke delivery path.

**Why `_empty_state.html` is a macro, not an `{% include %}`.** The existing shared-partial precedent (`_client_tabs.html`) is an include because its inputs (`client`, `active_tab`) are already ambient in every including route's context. Empty-state text/action varies per call site with no shared ambient variable, so a parameterized macro avoids adding a context key to five unrelated routes just to satisfy an include contract.

## Verification

**Commands:**
- `uv run pytest` — expected: full suite green, including the new/amended tests above.
- `uv run ruff check .` && `uv run ruff format --check .` — expected: clean.

**Manual checks:**
- Create, correct, and delete a Client with JS on: confirm a toast appears (auto-dismiss for success) and the destination page is styled; repeat with JS off and confirm the same information as a dismissible banner.
- Trigger a field-specific validation error (e.g. blank `name`) on `/clients/new`: confirm the field is marked invalid, the summary takes focus and its link jumps to the field.
- Start a report run, then (e.g. via devtools offline toggle) fail two consecutive polls: confirm the banner, the 5s/15s gap, and that `Riprova` appears and works; confirm recovery clears both.
- Load `/clients/{id}/reports` for a Client with none: confirm the new Italian empty state and its action link.
- Zoom to 200% / toggle `prefers-reduced-motion`: confirm the toast/skeleton/spinner animations are disabled but the elements remain functional.

## Suggested Review Order

**The flash mechanism (the one new piece of infrastructure)**
- `shell/http/flash.py` — cookie set/parse/clear and the middleware's clear-on-any-response behavior.
- `shell/http/templates/base.html` — the single shared flash block every page now carries.

**The three client success pages (closing Story 9.4's deferral)**
- `shell/http/routes/clients.py` create/correct/delete success returns, and `client_action_result.html`.

**Field-level validation**
- `create_client`/`correct_client`'s 5 mirrored failure sites and `client_new.html`/`client_edit.html`'s per-field markup.

**Poll backoff**
- `shell.js`'s extended job 6 and `report_run_poll.html`'s new `Riprova` button — confirm no change reaches `report_runs.py`/AD-20.

## Suggested Review Order

**The flash mechanism**

- Entry point — cookie set/read/clear, with the explicit reasoning for why the context processor returns `{}` rather than `{"flash": None}`.
  [`flash.py:58`](../../shell/http/flash.py#L58)

- The clear-on-any-response middleware, including the 401-short-circuit case a Blind Hunter review initially (wrongly) flagged — verified correct via a standalone Starlette ordering test.
  [`flash.py:129`](../../shell/http/flash.py#L129)

- The one shared banner every page now renders from, promoted to a toast by `shell.js`.
  [`base.html:102`](../../shell/http/templates/base.html#L102)

- The toast region every page carries, populated by the flash promotion and the toast queue below.
  [`base.html:111`](../../shell/http/templates/base.html#L111)

**The three client success pages (closing Story 9.4's deferral)**

- The bare-fragment→template swap for create: same wording/status/chart-link, now inside `base.html`'s chrome.
  [`clients.py:410`](../../shell/http/routes/clients.py#L410)

- The `<h1>` this template needed to hold the app's "one h1 per screen" floor — added after review.
  [`client_action_result.html:16`](../../shell/http/templates/client_action_result.html#L16)

**Field-level validation**

- Bracket access on `field_errors`, not dot-access — closes a dict-method-collision risk (`items`/`get`/`keys`/`values`) a review caught.
  [`client_new.html:22`](../../shell/http/templates/client_new.html#L22)

- `aria-invalid` added alongside `aria-describedby` — the actual ARIA signal assistive tech expects on an invalid field.
  [`client_new.html:30`](../../shell/http/templates/client_new.html#L30)

**Poll backoff (client-side only, AD-20 untouched)**

- The backoff state and the gate on the existing `every 2s` trigger — vetoes early ticks, never changes the trigger itself.
  [`shell.js:525`](../../shell/http/static/shell.js#L525)

- Where a failure increments the gate and reveals `Riprova` from the 2nd failure on.
  [`shell.js:597`](../../shell/http/static/shell.js#L597)

- The extended trigger and the manual-retry button it answers to.
  [`report_run_poll.html:11`](../../shell/http/templates/report_run_poll.html#L11)

**Toast queue and empty-state consolidation**

- FIFO-capped queue, success auto-dismiss + hover-pause, warning/danger persist-until-closed.
  [`shell.js:890`](../../shell/http/static/shell.js#L890)

- The parameterized macro five list screens now share, instead of five copies of the same markup.
  [`_empty_state.html:18`](../../shell/http/templates/_empty_state.html#L18)

**Design-token hygiene (post-review fixes)**

- Toast/dismiss hover and shadow now reuse existing semantic tokens (`--surface-sunken`, `--elevation-overlay`) instead of hardcoded, non-dark-theme-aware `rgba(...)`.
  [`tokens.css:1628`](../../shell/http/static/tokens.css#L1628)

**Tests**

- Proves the flash cookie round-trip end-to-end through one real route, not just the unit-level `flash.py` tests.
  [`test_http_corpus.py:141`](../../tests/test_http_corpus.py#L141)

- Closes the review-found gap: proves the client success pages now actually extend `base.html`, not just that the wording matches.
  [`test_http_clients.py:324`](../../tests/test_http_clients.py#L324)
