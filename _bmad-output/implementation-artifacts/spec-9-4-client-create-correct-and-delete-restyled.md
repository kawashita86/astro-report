---
title: 'Story 9.4 — Client create, correct and delete: restyled, with a real delete guard'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
baseline_commit: '23cd07191d6019d7c67da85382209f8f91ac82af'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The three client-mutation screens — new (`/clients/new`),
correct (`/clients/{id}/edit`), delete (`/clients/{id}/delete`) — still render
bare, unstyled full-width forms. There is no visible way to reach the delete
route (only URL typing), the delete confirm is a single "Confirm delete"
button with no guard, and the supersede confirm is an unstyled English
paragraph. Entering birth data is cramped and deleting a client is one
mis-click.

**Approach:** Restyle all three to the DESIGN.md form pattern (≤560px measure,
label-above-input, ~24px field rhythm, helper text below) and the candidate
picker to the `fieldset` radio pattern. Add a real delete guard: an "Elimina
cliente" trigger on the Anagrafica screen that (JS) opens a focus-trapped
confirm modal whose `danger` button stays disabled until Francesco types the
Client's exact name, and (no-JS) navigates to the existing confirm page, now
restyled. Translate the two destructive-confirm surfaces (delete, supersede)
to their verbatim EXPERIENCE.md Italian. Presentation plus one client-side
guard only: no route contract, query, or model changes.

## Boundaries & Constraints

**Always:**
- Presentation and one client-side guard only. Every route's request/response
  contract, status codes, redirects, and persisted data are unchanged.
  `POST /clients/{id}/delete` stays gated **solely** by `confirmed=1`; the
  typed-name match only enables/disables the submit button in the browser and
  is never checked server-side. `POST /clients/{id}/edit` keeps its
  resolve → compute → `confirmed=1` two-step.
- Progressive enhancement holds: the create and correction forms full-page
  POST; `GET /clients/{id}/delete` renders a functional confirm page and its
  submit deletes; the supersede warning is a server-rendered sub-state. JS
  only adds the delete modal, its focus trap, and the typed-name gate. Never a
  broken state without JS.
- All three templates keep `{% extends "base.html" %}` — one `<html lang="it">`,
  one `<h1>` per screen. `client_edit.html` keeps its
  `{% include "_client_tabs.html" %}` page header with the Anagrafica tab
  `aria-current="page"`; the sidebar `Clienti` item stays `is-active`.
- Native `date` / `time` inputs are kept as-is — no custom date widget.
- New destructive-confirm copy is Italian, verbatim from EXPERIENCE.md "Voice
  and Tone → Confirmations":
  - Delete: `Elimina definitivamente {nome} e il suo tema natale` +
    `, incluso il tema superato conservato da una correzione precedente` when a
    superseded chart exists + `. Operazione irreversibile.`
  - Delete guard label: `Digita «{nome}» per confermare.`
  - Supersede: `Applicando questa correzione il tema attuale viene superato. Il
    tema precedente è conservato, contrassegnato come superato e resta
    consultabile — ma i report già generati su di esso potrebbero non
    corrispondere più.`
  - Confirm buttons carry the verb — `Elimina cliente` / `Applica correzione`,
    never "OK"; cancel is `Annulla`.
- Form pattern per DESIGN.md density split: ≤560px measure, `<label>` above
  input, ~24px between fields, helper text below in `small`. The candidate
  picker is a `fieldset`/`legend` radio group with full-width option rows; the
  selected row gets a `primary-50` fill and a `primary-700` left marker.
- a11y floor: the modal traps focus, takes initial focus on `Annulla` (never
  the destructive button), and restores focus to its trigger on close; `Esc`
  and scrim-click cancel. Every control keyboard-operable with a visible focus
  ring (global `*:focus-visible`, never removed); interactive targets
  ≥ 24×24px. A form-level error summary carries `role="alert"` and takes focus.
- New CSS is a single appended `PROVISIONAL — Story 9.4` block in
  `shell/http/static/tokens.css`, semantic tokens only, contrast holding in
  both themes (≥ 3:1 non-text, ≥ 4.5:1 secondary, ≥ 7:1 body). New JS is one
  added IIFE section in `shell/http/static/shell.js`, no dependency, no
  scripted animation (reduced-motion parity). Story 9.8 consolidates both — do
  not build on these class names elsewhere.

**Ask First:**
- Translating the create/correction **field labels** (Name / Birth date /
  Birth time / Birthplace) and the success-fragment copy
  (`Client {id} created.` / `… corrected.`). Default: leave English, restyle
  only — matches the Story 9.3 precedent that deferred body copy to Story 9.9.
  Making them Italian now widens the test delta.
- Giving the **supersede** confirm a modal treatment (DESIGN.md lists it under
  the modal component). Default: keep it as the restyled server-rendered
  warning sub-state (already a no-JS-native plain two-step confirm); modal-ize
  in Story 9.8.
- Placing the "Elimina cliente" entry point anywhere other than the Anagrafica
  (`/clients/{id}/edit`) screen.

**Never:**
- No change to `core/`. No new route, no query-string parameter, no change to
  `create_client_with_chart` / `correct_client_and_chart` /
  `delete_client_and_derived` signatures, no change to
  `shell.http.auth.ALLOWLIST` (stays exactly `{"/healthz", "/login"}`).
- No server-side enforcement of the typed name. No SPA. No HTMX for the modal
  — vanilla JS, matching `shell.js`.
- No custom date/time widget. No new dependency, no CDN `<script>`/`<link>`.
- `report_export.html` stays untouched.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| New-client form render | Authenticated `GET /clients/new` | `200`; `.form-view` (≤560px), each field a `<label>` above its input with helper text below, native `date`/`time` kept, `.btn--primary` submit; extends `base.html` (one `<html lang="it">`, one `<h1>`, `Clienti` nav `is-active`) | N/A |
| Ambiguous birthplace sub-state | Create or correct POST, geocoder returns a candidate list | `200`; the same form re-rendered with a `.candidate-picker` `fieldset`/`legend` radio group, the typed birthplace preserved in a hidden field; nothing persisted | N/A |
| Correction form render | Authenticated `GET /clients/{id}/edit` for a known client | `200`; correction form in the `.form-view`/`.field` pattern; birthplace field empty with the "retype it, even to reconfirm" helper; Anagrafica tab `aria-current="page"`; breadcrumb `Clienti / {nome}` | `404` for an unknown id |
| Delete trigger, JS | Anagrafica screen, JS enabled, operator activates "Elimina cliente" | A focus-trapped modal opens over the screen, initial focus on `Annulla`; body is the Italian consequence naming the client (plus the superseded-chart clause when one exists); the `danger` "Elimina cliente" submit is disabled | N/A |
| Delete guard typing | Modal open, operator types into `Digita «{nome}» per confermare` | The submit is enabled only while the trimmed value exactly equals the client name (case-sensitive); any mismatch re-disables it | N/A |
| Delete modal dismissed | `Esc`, scrim-click, or `Annulla` | Modal closes, focus returns to the trigger, nothing deleted, no request made | N/A |
| Delete, no JS | JS disabled, operator follows the "Elimina cliente" link | `GET /clients/{id}/delete` renders the restyled confirm page (`.panel--danger`, Italian consequence with `{nome}` and the superseded clause when applicable); submitting posts `confirmed=1` and deletes — route contract unchanged | `404` unknown id; `422` oversized / non-UTF-8 body |
| Supersede confirm | Correction POST without `confirmed=1`, resolve + compute succeed | `200`; a styled `.panel--warning` sub-state carrying the exact EXPERIENCE.md Italian supersede sentence, `Applica correzione` (`confirmed=1`) + `Annulla`; nothing persisted until resubmitted | N/A |
| Anonymous | No session cookie, any of `/clients/new`, `/clients/{id}/edit`, `/clients/{id}/delete` | `401`, empty body; `ALLOWLIST` unchanged | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/clients.py` — presentation-context only.
  - `_render_delete_form` (l.180) takes `client_id` today; add a `client_name:
    str` parameter (or pass the whole `client`) and include it in the context
    dict so `client_delete.html` can render `{nome}`. Both callers
    (`client_delete_form` l.573, `delete_client` l.590) already hold `client`.
  - `_render_form` (l.138) / `_render_edit_form` (l.154) unchanged — the
    correction path already passes `client`. No handler logic, no status code,
    no new field.
- `shell/http/templates/client_new.html` — rewrap the form: `<div class="form-view">`
  wrapper (≤560px), each field a `<div class="field">` with `<label>` then the
  input then an optional `<p class="field__help">`; `role="alert"` form-error
  banner (`.banner--danger`) that is focusable (`tabindex="-1"`); the candidate
  branch becomes `<fieldset class="candidate-picker"><legend>…</legend>` with
  one `<label>` row per candidate; submit is `<button class="btn btn--primary">`.
  Keep English field labels and the `action="/clients"` / field `name=`s.
- `shell/http/templates/client_edit.html` — same `.form-view`/`.field` restyle
  for the correction form (the `else` branch, l.27-74); keep the birthplace
  helper (l.70). Restyle the `warning` branch (l.10-26) as
  `<div class="panel panel--warning">` with the verbatim Italian supersede
  sentence, an `Applica correzione` `.btn--danger` submit (keeps every hidden
  field incl. `confirmed=1`) and an `Annulla` `.btn--secondary` link back to
  `/clients/{{ client_id }}/edit`. Add, at the end of `content`: an
  `<a class="btn btn--danger-ghost" href="/clients/{{ client_id }}/delete"
  data-delete-client>Elimina cliente</a>` and an inline
  `<div class="modal-scrim" data-delete-modal hidden>` → `<div class="modal"
  role="dialog" aria-modal="true" aria-labelledby="…">` containing the Italian
  consequence (with a `{% if <superseded> %}` clause — thread a
  `has_superseded_chart` bool into `_render_edit_form`'s context, computed via
  the existing `_has_superseded_chart(session, client_id)` l.196), a
  `<form method="post" action="/clients/{{ client_id }}/delete">` with
  `<input type="hidden" name="confirmed" value="1">`, a labelled
  `<input data-delete-confirm>` (`Digita «{{ client.name }}» per confermare.`),
  `Annulla` (`data-delete-cancel`, `.btn--secondary`) and
  `<button data-delete-submit class="btn btn--danger" disabled>Elimina cliente</button>`.
  Put the exact name on `data-client-name="{{ client.name }}"`.
- `shell/http/templates/client_delete.html` — restyle as the no-JS fallback:
  `.form-view` + `<div class="panel panel--danger">`, the Italian consequence
  using `{{ client_name }}` and the `{% if has_superseded_chart %}` clause,
  `<button class="btn btn--danger">Elimina cliente</button>`; keep
  `action="/clients/{{ client_id }}/delete"` and the `confirmed=1` hidden
  input. Optionally include `_client_tabs.html`-style breadcrumb `Clienti / {nome}`
  (no tab row).
- `shell/http/templates/base.html` — no change; the modal markup lives inline
  in `client_edit.html`, `shell.js` is already loaded at l.102.
- `shell/http/static/shell.js` — add section **4. Delete-confirm modal**,
  guarded on `document.querySelector("[data-delete-modal]")`. Intercept the
  `[data-delete-client]` click (`preventDefault`), open the modal, trap focus
  (generalise the drawer's existing `FOCUSABLE` + `onKeydown` trap into a small
  `trapFocus(container, onEscape)` helper, or mirror it minimally), initial
  focus on `[data-delete-cancel]`; `Esc` / scrim-click / `[data-delete-cancel]`
  close and restore focus to the trigger. Wire `[data-delete-confirm]` `input`
  → `[data-delete-submit].disabled = value.trim() !== modal.dataset.clientName`.
  Update the file docstring ("Four jobs …"). No animation.
- `shell/http/static/tokens.css` — append the `PROVISIONAL — Story 9.4` block
  after the Story 9.3 block (ends l.869): `.form-view` (`max-width:560px`),
  `.field` (`margin-bottom:var(--space-lg)`), `.field label` (label role type,
  block), `.field input`/`.field select` (`--border-strong` 1px, `sm` radius,
  focus `--primary-500` + ring), `.field__help` (`small`/`--ink-secondary`),
  `.field--invalid`/`.field__error` (`--danger`), `.candidate-picker` fieldset
  + `label` rows + selected (`label:has(input:checked)` → `--primary-50` fill +
  `inset 3px 0 0 var(--primary-700)`; degrade gracefully without `:has`),
  `.btn` + `.btn--primary`/`.btn--secondary`/`.btn--danger`/`.btn--danger-ghost`
  (38px min-height, `md` radius, label text; `:disabled` → `--ink-disabled` on
  `--surface-sunken`, no border), `.banner--danger` (mirror `.banner--warning`
  l.538 with `--danger*`), `.panel`/`.panel--warning`/`.panel--danger` (`lg`
  radius, `xl` padding, `-surface` tint + 3px left border), `.modal-scrim`
  (fixed inset, `rgba(20,18,33,.45)`, grid-centre, `z-index` above the drawer's
  50) + `.modal` (`--surface-raised`, `lg` radius, `--elevation-overlay`,
  `width:min(480px,100%)`). Reuse `--elevation-overlay` (l.144). Comment as
  Story 9.8 fodder.
- `tests/test_http_client_correction.py` — the assertion at l.420
  (`"supersede" in response.text.lower()`) and any sibling English-copy checks
  in the unconfirmed-correction section move to the new Italian supersede
  string. Add: the correction form renders `.form-view` + at least one `.field`
  with a `<label>` before its `<input>` and a `.btn--primary`; the Anagrafica
  screen renders `[data-delete-client]` and a hidden `[data-delete-modal]`
  whose `data-client-name` equals the seeded client's exact name and whose
  `[data-delete-submit]` is `disabled`. Contract tests (l.353-402, max-length,
  404, confirmed-correction success) stay green untouched.
- `tests/test_http_client_deletion.py` — l.176-177 (`"Client"`, `"chart"`),
  l.191 and l.219 (`"superseded"`) move to the Italian strings
  (`Cliente` still substring-matches; assert `tema natale` / `tema superato`).
  Add: `GET /clients/{id}/delete` renders the seeded client's `{nome}` and a
  `.btn--danger`, still posts `confirmed=1` to the same route; add
  `test_shell_js_wires_the_delete_confirm_guard` asserting `shell.js` reads
  `[data-delete-confirm]` / toggles `[data-delete-submit]`. Every
  status-code / `confirmed`-gate / malformed-body test (l.155-162, l.198-251,
  l.259+) stays green unchanged.
- `tests/test_http_clients.py` — in the `/clients/new` area (the form-served
  test at l.275 and the ambiguous-birthplace test at l.399): add that the
  form renders `.form-view` + `.field` (label-above) and `.btn--primary`, and
  that the candidate sub-state renders `.candidate-picker`.
- `tests/test_http_shell.py` — no change. `/clients/new` is already in
  `_MIGRATED_ROUTES` (l.68); `/clients/{id}/edit` and `/clients/{id}/delete`
  stay covered by their own suites (they need a seeded client).

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/clients.py` — thread the client name (and a
  `has_superseded_chart` bool) into `_render_delete_form` and
  `_render_edit_form` context dicts. No handler logic, status code, redirect,
  or persisted-data change.
- [x] `shell/http/templates/client_new.html` — restyle to the
  `.form-view`/`.field` pattern; candidate branch → `.candidate-picker`
  fieldset; `.btn--primary` submit; `.banner--danger` focusable form-error
  summary. English field labels and all `name=`/`action` unchanged.
- [x] `shell/http/templates/client_edit.html` — restyle the correction form to
  the same pattern; restyle the supersede warning as `.panel--warning` with
  the verbatim Italian sentence + `Applica correzione`/`Annulla`; add the
  `[data-delete-client]` trigger and the inline focus-trap delete modal
  (Italian consequence, superseded clause, typed-name field, disabled
  `.btn--danger` submit, `data-client-name`).
- [x] `shell/http/templates/client_delete.html` — restyle as the no-JS confirm
  fallback: `.panel--danger`, Italian consequence with `{{ client_name }}` and
  the superseded clause, `.btn--danger` submit; route/`confirmed=1` unchanged.
- [x] `shell/http/static/shell.js` — add the delete-confirm-modal IIFE section
  (open on `[data-delete-client]`, focus-trap with cancel-focused, `Esc`/scrim
  cancel, restore focus, typed-name enable/disable of `[data-delete-submit]`);
  update the docstring to four jobs. No scripted animation.
- [x] `shell/http/static/tokens.css` — append the `PROVISIONAL — Story 9.4`
  block (form-view, field, candidate-picker, btn variants, banner--danger,
  panel + panel--warning/danger, modal-scrim + modal), semantic tokens only,
  both-theme contrast, reduced-motion safe.
- [x] `tests/test_http_client_correction.py` — update the supersede-copy
  assertion(s) to Italian; add form-structure + delete-trigger/modal-markup
  assertions on the Anagrafica screen.
- [x] `tests/test_http_client_deletion.py` — update the English consequence
  assertions to the Italian strings; add `{nome}` + `.btn--danger` render
  assertions and a `shell.js` delete-guard wiring test; leave every contract
  test unchanged.
- [x] `tests/test_http_clients.py` — add `.form-view`/`.field`/`.btn--primary`
  and `.candidate-picker` assertions in the `/clients/new` section.

**Acceptance Criteria:**
- Given `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`,
  when the story is done, then all are green, including the amended
  `test_http_client_correction.py`, `test_http_client_deletion.py` and
  `test_http_clients.py`.
- Given any of `/clients/new`, `/clients/{id}/edit`, `/clients/{id}/delete`,
  when rendered for an authenticated caller, then the response has exactly one
  `<html lang="it">`, exactly one `<h1>`, the sidebar `Clienti` item
  `is-active`, and (edit only) the Anagrafica tab `aria-current="page"`.
- Given the route contracts, when the story is done, then
  `shell.http.auth.ALLOWLIST` is still exactly `{"/healthz", "/login"}`, and
  every pre-existing status-code, `404`, malformed-body, and `confirmed=1`-gate
  test in the correction and deletion suites passes unchanged except the
  destructive-confirm copy assertions, which now match the Italian strings.
- Given `prefers-reduced-motion`, when the delete modal opens, then no scripted
  or CSS transition runs.

## Spec Change Log

_Empty — no review loopback yet._

## Design Notes

**The typed-name gate is browser-only by design.** The route contract is
frozen and the guard is friction against a careless click, not an
authorization boundary — the server still requires `confirmed=1` and nothing
else. A server-side name check would change the contract and break the
deletion suite's gate tests.

**Delete confirm is both a modal and a page.** Progressive enhancement is
mandatory and `GET /clients/{id}/delete` already exists with a fixed contract,
so it stays as the no-JS path (restyled). JS upgrades the "Elimina cliente"
trigger to open the inline modal instead of navigating. The modal's form
targets the same route with the same `confirmed=1` body.

**Supersede stays a server sub-state.** The existing resolve → review → confirm
two-step already satisfies the AC ("a plain confirm … states that the prior
chart is kept, marked superseded, and stays consultable"); Story 9.4 only
restyles and translates it. Modal-ising it is an *Ask First* deferred to 9.8.

**Reuse the drawer's focus trap.** `shell.js` already implements a focus trap
(`FOCUSABLE`, `onKeydown`, restore-focus) for the off-canvas drawer. Generalise
it into one helper the modal and the drawer share rather than a second copy.

**Candidate-picker selected state** uses `label:has(input:checked)`; a browser
without `:has` simply shows the radio without the fill/marker — acceptable
progressive degradation, the radio itself is unaffected.

## Verification

**Commands:**
- `uv run pytest tests/test_http_client_correction.py tests/test_http_client_deletion.py tests/test_http_clients.py tests/test_http_shell.py`
  — expected: green, including the new form-structure and delete-guard cases.
- `uv run pytest` — expected: full suite green.
- `uv run ruff check .` — expected: clean.
- `uv run ruff format --check .` — expected: unchanged from baseline. NOTE
  (build-time finding): the pinned ruff 0.16.3 already reports ~72 files
  repo-wide as needing reformat at the untouched baseline commit
  `23cd071` — a pre-existing repo condition, not caused by this story.
  New lines added here were conformed to 0.16.3; the only remaining flags in
  touched files (`clients.py:380`, `test_http_client_deletion.py:138`,
  `test_http_clients.py:233`) are pre-existing lines this story never edited.
  A repo-wide reformat is deliberately out of scope. `.venv/bin/python -m
  pytest` is the working suite runner here (`uv run pytest` collects nothing
  in this environment — an `uv run` wrapper quirk).
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -n "<html" shell/http/templates/client_new.html shell/http/templates/client_edit.html shell/http/templates/client_delete.html`
  — expected: no matches (all extend `base.html`).
- `TOKENSAVE_DISABLE_GREP_HOOK=1 grep -rn "unpkg\|cdnjs\|jsdelivr\|htmx.org" shell/http/templates/client_new.html shell/http/templates/client_edit.html shell/http/templates/client_delete.html`
  — expected: no matches.

**Manual checks:**
- Run the app, sign in, open `/clients/{id}/edit`: the form is ≤560px with
  labels above inputs and ~24px rhythm; the native date/time pickers still show
  `gg/mm/aaaa` / 24h. Click "Elimina cliente" — a modal opens over the screen,
  focus lands on `Annulla`, the `danger` button is disabled. Type the client's
  name exactly — the button enables; change one character — it disables again.
  Press `Esc` — the modal closes and focus is back on the trigger.
- Disable JavaScript, click "Elimina cliente" — the confirm page loads,
  names the client in Italian, and its submit still deletes.
- Trigger a correction with a changed birthplace — the styled Italian
  `panel--warning` supersede sub-state renders; confirm — the chart is
  superseded and the regeneration/behaviour is unchanged.
- Toggle the theme on each screen — field borders, the panel tints, the modal
  surface and the focus ring all hold contrast in both themes.

## Suggested Review Order

**The delete guard (the story's headline behaviour)**

- Entry point — the delete affordance and the inline confirm modal: a real link (no-JS) upgraded to a focus-trapped `alertdialog`.
  [`client_edit.html:91`](../../shell/http/templates/client_edit.html#L91)

- The typed-name gate and the modal lifecycle: open closes the drawer + inerts the background, close resets the field and re-disables the submit, both sides of the name compare are trimmed.
  [`shell.js:247`](../../shell/http/static/shell.js#L247)

- The background-inert helper — everything except the scrim leaves the a11y tree / tab order while the modal is open.
  [`shell.js:295`](../../shell/http/static/shell.js#L295)

- The no-JS fallback: the restyled `GET /clients/{id}/delete` page, same route and `confirmed=1` body, `danger` panel naming the client and the retained superseded chart.
  [`client_delete.html:15`](../../shell/http/templates/client_delete.html#L15)

- Route context only — `has_superseded_chart` threaded to the edit template (drives the modal's superseded clause), `client_name` threaded to the delete template. No handler logic, status code, or persisted-data change.
  [`clients.py:158`](../../shell/http/routes/clients.py#L158)

**The form restyle**

- The DESIGN.md form pattern — `.form-view` (≤560px), label-above `.field`s, helper below; English field labels stay for Story 9.9.
  [`client_new.html:12`](../../shell/http/templates/client_new.html#L12)

- The correction form on the same pattern, plus the supersede sub-state restyled as a `.panel--warning` with the verbatim EXPERIENCE.md Italian sentence and `Applica correzione` / `Annulla`.
  [`client_edit.html:14`](../../shell/http/templates/client_edit.html#L14)

- The birthplace candidate picker — `fieldset`/`legend` radio group, selected row gets a `primary-50` fill + `primary-700` marker (`:has`, degrading gracefully).
  [`client_edit.html:61`](../../shell/http/templates/client_edit.html#L61)

- Focus moves to the form-level `role="alert"` error summary on a 422 re-render.
  [`shell.js:412`](../../shell/http/static/shell.js#L412)

**Provisional styling (Story 9.8 consolidates)**

- The appended `PROVISIONAL — Story 9.4` block — form-view, field, candidate-picker, four button variants, danger banner, warning/danger panels, and the focus-trapped modal; semantic tokens only, no transition, `place-items: safe center` + `max-height` so a tall modal stays reachable.
  [`tokens.css:872`](../../shell/http/static/tokens.css#L872)

**Tests**

- The restyled form + delete-guard markup on the Anagrafica screen (`.form-view`, label-before-input, `data-delete-*` hooks, disabled submit).
  [`test_http_client_correction.py:419`](../../tests/test_http_client_correction.py#L419)

- The modal names the retained superseded chart when one exists (I/O-Matrix "Delete trigger, JS").
  [`test_http_client_correction.py:451`](../../tests/test_http_client_correction.py#L451)

- The no-JS confirm page: Italian consequence with the client name, `.btn--danger`, unchanged route + `confirmed=1`.
  [`test_http_client_deletion.py:169`](../../tests/test_http_client_deletion.py#L169)

- `shell.js` wires the browser-only typed-name gate and the focus-trap.
  [`test_http_client_deletion.py:433`](../../tests/test_http_client_deletion.py#L433)

- `/clients/new` renders the restyled form and the candidate sub-state renders the `.candidate-picker`.
  [`test_http_clients.py:275`](../../tests/test_http_clients.py#L275)
