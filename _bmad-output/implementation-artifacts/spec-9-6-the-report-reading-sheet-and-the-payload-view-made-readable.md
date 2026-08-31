---
title: 'The report reading sheet and the Payload view, made readable'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '74689a935fdea2a026841bb8b90931fa237bcc7d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `report.html` (the passed-Report screen) and `report_payload.html` (the Payload view) are the two operator-facing screens Epic 9 has not yet restyled: both still ship the pre-rebuild plain markup — a bare `<h2>Gate</h2>`/English copy on the report, and an untyped recursive `<dl>`/`<ul>` dump on the Payload view that actively strips every entry `id`, making the very facts a report is defended by invisible.

**Approach:** Restyle `report.html` into a 720px `body-read` sheet — `heading`-weight Section titles at 32px gaps, a scroll-spying in-page section nav, an Italian export bar (unchanged PDF/Markdown/disposition routes) and a `small` regeneration-count note. Restructure `report_payload.html` into one `<details>` disclosure per Section (first open, rest collapsed), stop stripping entry `id`s, and render them as `.badge-mono` chips. Add a generic click-to-copy enhancement to `.badge-mono` itself (shell.js), so every existing and new mono chip in the app — this story's and Story 9.5's — becomes copyable for free.

## Boundaries & Constraints

**Always:** No route, status-code, redirect, or query-shape change — `view_report` and `view_report_payload` keep their existing 401/404 contracts and `ALLOWLIST` untouched. `SECTION_TITLES`/`SECTION_ORDER` (`shell/http/draft_view.py`) stay the single source of the eight Section names/titles — do not duplicate them. `DISPOSITION_CHOICES` values (`as_generated`/`edited`) are unchanged; only their display labels may be translated. The Payload macro keeps walking arbitrary nested dict/list data generically — do not hand-write per-field renderers. Click-to-copy is a progressive enhancement: without JS, chips still show their text, just aren't clickable. `report_export.html` (WeasyPrint) stays untouched.

**Ask First:** None foreseen — this is a template/CSS/JS restyle over frozen routes and data shapes, matching Stories 9.2–9.5's pattern.

**Never:** No new DB column, model field, or migration. No change to `render_draft`/`localize_payload`/the Generator/the Gate. No custom date widget. No CDN script.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Passed Report, 1 regeneration | `stored_gate_result.regeneration_count == 1` | Note reads "Verifica superata dopo 1 rigenerazione." | N/A |
| Passed Report, 0 or ≥2 regenerations | `regeneration_count in {0, 4}` | Note reads "…dopo 0 rigenerazioni." / "…dopo 4 rigenerazioni." (plural) | N/A |
| No export yet | `latest_export is None` | Export bar shows Esporta PDF / Scarica Markdown only, no disposition UI (unchanged) | N/A |
| Exported, disposition unset | `latest_export.disposition is None` | Both disposition buttons render, Italian labels | N/A |
| Exported, disposition recorded | `latest_export.disposition == "edited"` | Recorded label shown as text, buttons gone (unchanged) | N/A |
| Payload grouping empty | `section[field]` is `[]`/falsy | Grouping omitted from its `<details>` (unchanged from today) | N/A |
| Payload entry carries an `id` | mapping with `"id"` key | Rendered as an interactive `.badge-mono` chip instead of stripped | N/A |
| Click-to-copy, clipboard API unavailable/blocked | `navigator.clipboard` throws or is undefined | No crash; chip stays as-is, no "Copiato" flash (silent no-op) | Caught in JS, no user-visible error |
| Section nav, JS disabled | no JS | Nav links still work as plain in-page anchors (`#sezione-*`); no scroll-spy highlight | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py` — `view_report` (l.511-571): add one computed value to the template context, `regeneration_note` — `f"Verifica superata dopo {n} rigenerazione."` if `n == 1` else `f"Verifica superata dopo {n} rigenerazioni."`, `n = stored_gate_result.regeneration_count`. No other context or query change. `DISPOSITION_CHOICES` (l.83-86): translate labels only — `("as_generated", "Inviato come generato")`, `("edited", "Inviato, modificato prima dell'invio")`; values untouched (Story 6.3 boundary).
- `shell/http/templates/report.html` — replace the plain `<h1>`/`<section id="gate-result">`/section loop with: `<h1>Report <span class="badge-mono">{{ run.month }}</span></h1>`; a `.exportbar` holding a `.status-badge.status-badge--success` "Verifica superata" pill, `<p class="report-note">{{ regeneration_note }}</p>`, and `.exportbar__actions` — `Vedi Payload` (`.btn--secondary`, existing `/payload` link), `Esporta PDF` / `Scarica Markdown` (`.btn--primary`/`.btn--secondary`, existing export hrefs, unchanged), then the existing `latest_export`/disposition conditional (forms restyled `.btn--secondary`, recorded state as plain text); a `.reading` row of `<nav class="report-toc" data-report-toc aria-label="Sezioni">` (one `<a href="#sezione-{{ section_name }}">{{ loop.index }} · {{ section_titles[section_name] }}</a>` per `section_order` entry) beside `<article class="report-sheet">` — same `{% for section_name in section_order %}` loop as today, `<section id="sezione-{{ section_name }}">` (mirrors Story 9.5's anchor convention in `report_draft.html`), body unchanged (`<p>`/`<ul>` per `list_section_names`).
- `shell/http/templates/report_payload.html` — `<h1>Payload</h1>` (label-map term). Wrap the existing `{% for section_name, section in payload.sections.items() %}` body in `<details class="payload-section" {% if loop.first %}open{% endif %}><summary>{{ section_titles.get(section_name, section_name) }}</summary>...</details>`; same for the `payload.day_lists` loop (each its own `<details>`, never `open` by default). `payload.day_lists`' two keys (`giorni_favorevoli`, `giorni_di_attenzione`) are themselves two of the eight Sections (6-7) — render their `<summary>` through `section_titles.get(list_name, list_name)` too, the same as the sections loop, not the raw key. In the `render_value` macro: when `key == "id"`, render `<dd><button type="button" class="badge-mono" data-copy-chip>{{ item }}</button></dd>` instead of skipping the pair; everything else in the macro (dict/list/scalar recursion) is unchanged.
- `shell/http/templates/report_draft.html` — l.18ish: change the existing non-interactive `.badge-mono` entry-id `<span>` to `<button type="button" class="badge-mono" data-copy-chip>` (markup/behavior only — no visual regression, same class).
- `shell/http/templates/home.html` — l.28: same span→button conversion for the `run.month` `.badge-mono` chip, so the dashboard's month codes become copyable too (AC3's "same mono-chip treatment" applied to an existing identifier, not just new ones).
- `shell/http/static/shell.js` — **section 8: click-to-copy mono chips** — one delegated `click` listener on `document.body` for `.badge-mono[data-copy-chip]`; `navigator.clipboard.writeText(el.textContent.trim())` in a try/catch; on success, swap `el.textContent` to `Copiato` for ~1.5s (`setTimeout`) then restore the original (stash it in a closure var, not a data-attribute, to avoid stale-state races on rapid re-clicks — cancel any pending restore timer before starting a new one). On failure/unavailable API: no-op, no thrown error. Native `<button>` gives keyboard operability for free (Enter/Space), no extra ARIA needed. **Section 9: report-sheet scroll-spy** — guarded on `document.querySelector('[data-report-toc]')`; an `IntersectionObserver` over each `.report-sheet section[id]` toggles `.is-active` on the matching `.report-toc a[href="#…"]` when a section crosses a top-anchored rootMargin band; not gated by `prefers-reduced-motion` (it's a state toggle, not an animation — only the anchor-link scroll itself is smoothed, via the existing global `scroll-behavior` rule). Update the file's header docstring "Seven jobs" → "Nine jobs" and add both entries.
- `shell/http/static/tokens.css` — add `html { scroll-behavior: smooth; }` near the existing `html`/`body` base rules (l.229-242) — the `* { scroll-behavior: auto }` reduced-motion override at l.475-482 already exists and now has an effect. Append a `PROVISIONAL — Story 9.6` block: `.exportbar` (flex row, `--space-sm` gap, `surface-sunken`, hairline bottom border, `--space-base` padding — mirrors `.violation-card` conventions), `.exportbar__actions` (flex, `--space-sm` gap, `margin-left:auto`), `.report-note` (`--font-small-*` tokens, `--ink-tertiary`), `.reading` (flex row, `--space-xl` gap, centered), `.report-toc` (`190px`, `position:sticky`, `top: --space-lg`, `--font-small-*`; `a` in `--ink-secondary`; `a.is-active` `--primary-700`, `font-weight:600`, 2px left border matching the sidebar's active-item convention), `.report-sheet` (`max-width:720px`, `surface-raised`, `1px --border-hairline`, `--radius-lg`, `--space-xxl` padding), `.report-sheet h2` (`--font-heading-*` tokens, `32px` top margin, `0` on `:first-of-type`), `.report-sheet p`/`ul` (`--font-body-read-*` tokens), `.payload-section` (`1px --border-hairline`, `--radius-md`, `--space-base` padding, `--space-md` margin-bottom) and `.payload-section > summary` (`--font-heading-*`, `cursor:pointer`), plus a `button.badge-mono` reset (`border:none; font:inherit; cursor:pointer; text-align:inherit;` — the class already carries all visual styling at l.627-636, this only neutralizes native `<button>` chrome so old and new usages render identically). Reuse `.status-badge`/`.status-badge--success`, `.btn`/`.btn--primary`/`.btn--secondary` verbatim (all exist, Stories 9.2/9.3).
- `tests/test_http_report_runs.py` — amend `test_getting_the_report_shows_all_eight_sections_and_the_gate_result` (l.1717) and its regeneration-count sibling (l.1757+) to the Italian note text, `.status-badge--success`, `.report-toc`/`.report-sheet` markup and `id="sezione-…"` anchors instead of bare `<h2>`; amend the disposition tests (l.2599-2645) to the new Italian button labels; amend `test_getting_the_payload_shows_all_eight_groupings_localized_to_the_clients_zone` (l.521-552) to assert `event_id in response.text` inside a `.badge-mono` button (reversing today's `assert event_id not in response.text`, l.551) and that `<details class="payload-section" open>` wraps the first Section; `test_getting_the_payload_hides_empty_groupings` (l.554) stays green — an empty grouping is still simply absent, now inside a `<details>` instead of a bare `<section>`. Add cases: the report-toc renders eight `<a href="#sezione-…">` links in `section_order`; a Payload section beyond the first renders `<details class="payload-section">` with no `open` attribute.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/report_runs.py` — add `regeneration_note` to `view_report`'s context; translate `DISPOSITION_CHOICES` labels (values unchanged).
- [x] `shell/http/templates/report.html` — exportbar (status pill, regeneration note, Vedi Payload / Esporta PDF / Scarica Markdown / disposition), `.reading` row (`report-toc` scroll-spy nav + `.report-sheet`), `id="sezione-{name}"` anchors, `run.month` as a `.badge-mono` chip.
- [x] `shell/http/templates/report_payload.html` — `<h1>Payload</h1>`; `<details class="payload-section">` per Section (first `open`) and per day-list; `render_value` renders `id` as an interactive `.badge-mono` chip instead of stripping it.
- [x] `shell/http/templates/report_draft.html` + `home.html` — convert the two existing `.badge-mono` `<span>` chips to `<button type="button" data-copy-chip>`.
- [x] `shell/http/static/shell.js` — section 8 (delegated click-to-copy, 1.5s "Copiato" flash, try/catch, no-op on failure); section 9 (`IntersectionObserver` scroll-spy on `.report-toc`); docstring → "Nine jobs".
- [x] `shell/http/static/tokens.css` — global `scroll-behavior: smooth`; `PROVISIONAL — Story 9.6` block (`.exportbar*`, `.report-note`, `.reading`, `.report-toc*`, `.report-sheet*`, `.payload-section*`, `button.badge-mono` reset).
- [x] `tests/test_http_report_runs.py` — amend report-view + payload-view assertions to the new markup/copy per Code Map; add the report-toc and non-first-section `<details>` cases.

**Acceptance Criteria:**
- Given `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`, when the story is done, then all pass (no *new* format flags — pre-existing repo-wide flags stand, per the Story 9.4 note).
- Given a passed Report, when `/report-runs/{id}/report` renders, then it has one `<article class="report-sheet">` with eight `<section id="sezione-…">`s in `section_order`, `heading`-weight `<h2>` titles, a `.report-toc` with eight matching links, and a `.report-note` showing the correctly-pluralized regeneration count.
- Given the Payload view, when it renders, then every Section is a `<details class="payload-section">` (first `open`, rest collapsed) and every entry `id` renders inside a `.badge-mono` chip (previously stripped entirely).
- Given any `.badge-mono` chip anywhere in the app (report, payload, draft violation cards, dashboard month codes), when clicked, then the identifier text is copied to the clipboard and "Copiato" shows for ~1.5s before reverting — and with JS disabled, the chip still displays its text.
- Given `shell.http.auth.ALLOWLIST` and every existing `/report-runs/*` status-code/404/redirect test, when the story is done, then they still pass unchanged (only report/payload markup and copy change).

## Spec Change Log

**Review round 1 (blind-hunter, patch findings).** Six findings routed as `patch` and auto-fixed directly (no loopback — each was a small, unambiguous fix, not a spec renegotiation):
1. `report_payload.html`'s day-list `<summary>` rendered the raw key (`giorni_favorevoli`) instead of its Italian title — traced to this Code Map's own incorrect claim that "day-list names aren't Section titles"; they are Sections 6-7 (`SECTION_TITLES`/`LIST_SECTION_NAMES`, `draft_view.py`). Fixed the template and corrected the Code Map bullet above; the corresponding test's stale comment/assertions were also fixed.
2. Click-to-copy (`shell.js`): re-clicking a chip while it was still showing "Copiato" (within the 1.5s window) copied the literal string "Copiato" instead of the original identifier. Fixed by reading the stashed original when `chip === copyOriginalEl`.
3. `.reading`'s two-column layout (190px sticky nav + 720px sheet) had no responsive fallback, risking horizontal overflow below ~900px and at high zoom — a documented epic-wide accessibility-floor requirement (200%/400% reflow, no horizontal page scroll). Added a stacked fallback inside the existing `@media (max-width: 899px)` block.
4. `render_value`'s new `id`-key branch rendered `{{ item }}` directly instead of recursing through `render_value(item)` like every other key — harmless today (ids are always scalar) but inconsistent with the rest of the macro. Fixed to recurse.
5. `report.html`'s new `run.month` chip in the `<h1>` was left a plain `<span>` while every other `.badge-mono` in the same diff was upgraded to an interactive `<button data-copy-chip>` — inconsistent with this story's own AC3. Fixed to match.
6. The Italian disposition label "Inviato, modificato prima dell'invio" repeated the "invio" root awkwardly. Changed to "Inviato, con modifiche"; test assertions updated to match.

Two findings were real but out of this story's scope and deferred to `deferred-work.md` (both point at Story 9.9's designated accessibility-floor audit pass): click-to-copy chips have no accessible name/`aria-live` announcement of the copy action; the scroll-spy's active TOC link has no `aria-current`. Remaining findings (missing exportbar heading, IntersectionObserver tie-break precision, no automated JS test coverage, premature pluralization-helper extraction, sprint-status timing) were rejected as either matching the approved mockup, cosmetic, consistent with this epic's established testing convention, premature abstraction, or a process-timing non-issue.

## Design Notes

**Why the id-chip fix lives in the macro, not a new Python view-model.** `payload_view.py`'s only export, `localize_payload`, is a generic tz-localizing deep-walk with no notion of "Section" or "entry" — adding Section/typed-field awareness there would be a much larger, riskier rewrite for a change AC2 only asks of presentation (stop hiding `id`, show it as a chip). The existing recursive `render_value` macro already visits every key; special-casing `key == "id"` there is the minimal, behavior-preserving fix — same reasoning Story 9.5 used to keep `stage_view.py` presentation-only.

**Click-to-copy as one delegated listener, not per-chip wiring.** `.badge-mono` already appears in three templates before this story even starts (`report_draft.html`, `home.html`) and gains two more here. A single `document.body` delegated listener keyed on `[data-copy-chip]` (mirroring the existing `htmx:beforeRequest`/`htmx:responseError` delegation pattern already in shell.js) means every current and future mono chip is copyable for free, with zero per-template JS wiring.

## Verification

**Commands:**
- `uv run pytest tests/test_http_report_runs.py` — expected: green, including the amended report/payload assertions and the new toc/disclosure cases.
- `uv run pytest` — expected: full suite green.
- `uv run ruff check .` — expected: clean.
- `uv run ruff format --check .` — expected: no new flags in files this story touches.

**Manual checks:**
- Load a passed Report: confirm the 720px sheet, 32px section gaps, the toc highlighting the section in view while scrolling, and the regeneration note's plural form at 0/1/2+.
- Load its Payload view: confirm only the first Section's disclosure is open, entry-id chips are visible, and clicking one copies it and flashes "Copiato".
- With JS off (devtools): confirm the toc links still jump to the right section and payload `<details>` still expand/collapse natively.

## Suggested Review Order

**The report sheet**

- Entry point: the new export bar + scroll-spying nav + sheet, wrapping the unchanged Epic 6 export/disposition routes.
  [`report.html:6`](../../shell/http/templates/report.html#L6)

- `regeneration_note` computed once in the route (singular/plural), not left to the template.
  [`report_runs.py:562`](../../shell/http/routes/report_runs.py#L562)

- The eight `id="sezione-{name}"` anchors the nav and scroll-spy both key off.
  [`report.html:45`](../../shell/http/templates/report.html#L45)

- Disposition button copy translated; values (`as_generated`/`edited`) untouched.
  [`report_runs.py:83`](../../shell/http/routes/report_runs.py#L83)

**The Payload disclosure**

- `render_value`'s new `id`-key branch: recurses like every other key, so a non-scalar id degrades gracefully instead of dumping a repr.
  [`report_payload.html:4`](../../shell/http/templates/report_payload.html#L4)

- Sections 6-7 (`giorni_favorevoli`/`giorni_di_attenzione`) go through `section_titles` too — the review-round fix for the raw-key regression.
  [`report_payload.html:54`](../../shell/http/templates/report_payload.html#L54)

- Only the first `<details>` opens by default.
  [`report_payload.html:30`](../../shell/http/templates/report_payload.html#L30)

- `section_titles` now passed into this route's context — the one context change beyond the spec's original Code Map.
  [`report_runs.py:405`](../../shell/http/routes/report_runs.py#L405)

**Click-to-copy and scroll-spy (shell.js)**

- Click-to-copy: reads the stashed original when a chip is mid-flash, fixing the review-round re-click bug.
  [`shell.js:606`](../../shell/http/static/shell.js#L606)

- Scroll-spy: `IntersectionObserver` over `.report-sheet section[id]`, toggling `.is-active` on the matching toc link.
  [`shell.js:663`](../../shell/http/static/shell.js#L663)

- Updated job-count docstring (Seven → Nine).
  [`shell.js:60`](../../shell/http/static/shell.js#L60)

**Styling**

- `.exportbar`/`.reading`/`.report-toc`/`.report-sheet`/`.payload-section` — the new provisional block.
  [`tokens.css:1329`](../../shell/http/static/tokens.css#L1329)

- The 899px reflow fallback added in review (stacks the toc above the sheet).
  [`tokens.css:479`](../../shell/http/static/tokens.css#L479)

- Global `scroll-behavior: smooth`, activating the pre-existing reduced-motion override.
  [`tokens.css:232`](../../shell/http/static/tokens.css#L232)

**Peripherals**

- Report/payload view test amendments (Italian copy, toc/sheet markup, `<details>` open state, id chips).
  [`test_http_report_runs.py:1748`](../../tests/test_http_report_runs.py#L1748)

- The added singular-regeneration-count case (I/O Matrix row the initial pass missed).
  [`test_http_report_runs.py:1863`](../../tests/test_http_report_runs.py#L1863)

- `.badge-mono` span→button conversions in the two pre-existing usages.
  [`report_draft.html:18`](../../shell/http/templates/report_draft.html#L18)
  [`home.html:28`](../../shell/http/templates/home.html#L28)
