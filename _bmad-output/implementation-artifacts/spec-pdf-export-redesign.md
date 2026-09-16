---
title: 'Redesign the client-facing PDF export to the approved "PDF export document" design'
type: 'feature'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'b63915e4c06337345f0b420ea28e55c2c228914a'
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/mockups/key-pdf-export.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `report_export.html` is a bare Georgia document (Client name + 8 Sections). The operator approved a full redesign (EXPERIENCE.md → "PDF export document", 2026-09-16): three A4 pages, a new type system, plus birth data / natal wheel / Sun-Moon-Ascendant placements that Story 6.2 originally excluded.

**Approach:** Rewrite `report_export.html` to match `mockups/key-pdf-export.html` (adapted to real WeasyPrint `@page` pagination, not the mock's static 3 sheets), wire the new data into `download_report_pdf`, and bundle the two font families locally.

## Boundaries & Constraints

**Always:**
- `report_export.html` stays standalone: own `<html>`, no `{% extends %}`, never inherits `DESIGN.md`/`tokens.css` (`tests/test_http_shell.py:567-591` must keep passing unmodified).
- Every value traces to real Report/ReportRun/Client/StoredNatalChart data — no invented copy. Wheel + placements come from `ReportRun.natal_chart_id`'s chart, never the Client's current chart.
- Fonts are local files via `@font-face` — no runtime network fetch.
- New day-list date reshaping (day + Italian month abbreviation) is local to this feature; `draft_view.py`'s shared `render_draft()`/`date` (dd/mm/yyyy, used by `report.html` + Markdown) is never touched.
- Cards never split (`break-inside: avoid`); Section order stays 1→8. Still excluded: Payload, Gate result, run id, citations, internal metadata.

**Ask First:**
- If the Kerykeion wheel's `var(--kerykeion-*)` colors don't resolve under WeasyPrint 69 and a literal-color override still renders wrong — ask before rasterizing to PNG (design's stated fallback, but bigger than the default path).
- If Google Fonts no longer serves the exact weights needed (Cormorant Garamond 500/600/500-italic, Jost 400/500) — ask before substituting.

**Never:** touch `report.html`, `report_draft.html`, the Markdown export, or the Dockerfile/apt packages (unless verification proves bundled fonts fail in-container).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|------------------|-----------------|
| Birthplace NULL | `client.birthplace_name is None` | *Luogo di nascita* row omitted | N/A |
| Uncited day-list entry | no citing Sentence | dot + date shown, no caption prose | N/A |
| Long Section prose | overflows page | card flows whole to next page, never splits | N/A |
| `natal_chart_id` missing on passed run | impossible once `gate_passed` | `RuntimeError` naming report id (mirrors existing guards) | `RuntimeError` |

</frozen-after-approval>

## Code Map

- `shell/http/templates/report_export.html` — rewrite target (currently Georgia-only, no wheel/placements/real pagination).
- `mockups/key-pdf-export.html` / `key-pdf-export-wheel.svg` — pixel reference; wheel SVG shows its own `<style>:root{--kerykeion-*}` block (the CSS-var risk above).
- `shell/http/routes/report_runs.py:220-287` `_load_passed_report_bundle` — reused unchanged.
- `shell/http/routes/report_runs.py:1262-1334` `download_report_pdf` — add: resolve `StoredNatalChart` via `bundle.run.natal_chart_id` (`RuntimeError`-guarded like its siblings), build wheel SVG, call new view module, pass `base_url` to `html_to_pdf`; refresh stale "no chart wheel" docstring text.
- `shell/http/routes/chart.py:47-88` — mirror this wheel-build pattern: `chart_wheel.build_subject()` → `ChartDataFactory.create_natal_chart_data()` → `ChartDrawer(...)`, orb from `request.app.state.computation_config.orbs.natal`. Implementation uses `ChartDrawer(...).generate_wheel_only_svg_string()`, not `.generate_svg_string()` — see Spec Change Log.
- `shell/adapters/postgres/client.py:69-146` — `Client.birth_date/birth_time/birthplace_name`; `StoredNatalChart.planets` (dicts: `sign`/`degree` 0-30 Decimal/`house`), `.ascendant` (absolute longitude, needs decomposing).
- `core/ephemeris/chart.py:70-83` `_ZODIAC_SIGNS`, `core/gate/run.py:108-128` `_SIGN_MAP` — pattern references only (both private; reimplement a small local Italian sign map + sign/degree split, AD-1 forbids importing).
- `shell/http/draft_view.py` `render_draft`/`SECTION_TITLES`/`LIST_SECTION_NAMES` — reused unchanged; its `date` field (dd/mm/yyyy) is reformatted locally for this feature only, never edited in place.
- `shell/adapters/weasyprint/render.py` `html_to_pdf` — add required `base_url` kwarg → `weasyprint.HTML(string=..., base_url=...)` so local `@font-face` paths resolve.
- `shell/http/report_export_view.py` — **new**, mirrors `draft_view.py`/`payload_view.py`'s "view-shaping lives in `shell/http/`" pattern: birth-date/time formatting, Sun/Moon/Ascendant extraction, `run.month` (`"YYYY-MM"`) → `"Ottobre 2026"`, day-list `dd/mm/yyyy` → (day, month abbreviation).
- `shell/http/templates/fonts/` — **new**, vendored OFL WOFF2s (Cormorant Garamond 500/600/500-italic, Jost 400/500) + `OFL.txt`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/templates/fonts/*.woff2`, `OFL.txt` — fetched the variable-font sources from Google Fonts' `google/fonts` GitHub OFL repo and instantiated static per-weight WOFF2s locally via `fontTools` (see Spec Change Log); committed as binary assets.
- [x] `shell/http/report_export_view.py` — new module per Code Map; no changes to `draft_view.py`.
- [x] `shell/adapters/weasyprint/render.py` — add required `base_url: str` to `html_to_pdf`.
- [x] `shell/http/routes/report_runs.py` — wire the run's chart + wheel SVG + view module into `download_report_pdf`; refresh docstring.
- [x] `shell/http/templates/report_export.html` — full rewrite: real `@page` A4 CSS with repeating footer (client · month, `counter(page)`/`counter(pages)`), `@font-face`, Page 1 (header/birth-data/positions+wheel/Energia generale), Page-2 group (4 domain cards, `break-before: page`), Page-3 group (2 timelines + Consiglio finale, `break-before: page`).
- [x] Manual verification — see below; the wheel-color Ask-First risk's first half triggered (confirmed empirically) but resolved via the literal-color override without ever needing the PNG-rasterization fallback or a question; the font-substitution Ask-First risk never triggered (Google Fonts still serves the exact weights needed). See Spec Change Log.
- [x] `tests/test_http_report_runs.py` — dedicated automated coverage for all four I/O & Edge-Case Matrix rows (review-loop feedback: manual verification alone was not enough); see Verification below for the five test names.
- [x] Blind-hunter review pass — 9 auto-fixable patches applied (silent-fallback guard on the wheel-color settings, `tests/test_report_export_view.py` added, control-character CSS escaping, `break-inside: avoid` on the three multi-card row containers, a tightened heading-markup assertion, `overflow-wrap` on three unbounded text classes, an Italian `<title>`, a `RuntimeError` guard on `_placement()`'s key reads, and a revert of unrelated formatting-only churn in `tests/test_http_report_runs.py`); two further findings (semantic headings, the Kerykeion CSS-custom-property risk) were out of scope for this pass and are in `deferred-work.md`. See Spec Change Log.

**Acceptance Criteria:**
- Given a Gate-passed Report, when `/export/pdf` is requested, then the PDF shows the wheel + Sun/Moon/Ascendant from `ReportRun.natal_chart_id`, not the Client's current chart.
- Given `birthplace_name = NULL`, then the *Luogo di nascita* row is omitted, not blank.
- Given `report.html`/`report_draft.html`/Markdown, then none of their output or `draft_view.py`'s date format changes.
- Given no internet access at render time, then the PDF still renders (fonts resolve locally).

## Spec Change Log

- **Wheel renderer: `generate_wheel_only_svg_string()`, not `generate_svg_string()`.** Kerykeion's full-chart SVG (`generate_svg_string()`) also draws a position table, an aspect grid and an elements/qualities panel beside the wheel circle — none of which the design's "Il tuo tema natale" card wants. `generate_wheel_only_svg_string()` renders the wheel alone with its own fitted `viewBox`; verified its output's `viewBox` value is byte-identical to the mockup's own reference `key-pdf-export-wheel.svg`, confirming the mockup was produced the same way. Tried first: cropping the full chart's `viewBox` by hand — rejected after it left stray text fragments bleeding into the crop on some data (a longer elements-percentage string shifted a side panel by a few px).
- **Wheel colors: literal hex overrides, not `var(--kerykeion-*)`.** The Ask-First risk's first half triggered — verified empirically that WeasyPrint 69 does not resolve `var(--kerykeion-*)` custom properties referenced from an *inlined* SVG's own presentation attributes (the wheel rendered as a solid black disc). Resolved via the spec's own named fallback (a literal-color override), built once at import time from Kerykeion's public `kerykeion.settings.chart_defaults.DEFAULT_*` constants with every `var(...)` replaced by a color from this design's copper/ink palette, plus `transparent_background=True`. Renders correctly (verified against a rasterized PDF page) — the PNG-rasterization fallback and the "ask before" gate were never reached.
- **Footer rule: `@bottom-left`/`@bottom-right` each at `width: 50%` with their own `border-top`, not a `position: fixed` rule element.** First attempt used a `position: fixed` div spanning the page width for the rule, relying on `@page` margin boxes only for the text/counters. Rejected after empirical testing showed WeasyPrint 69 resolves a fixed element's `bottom` offset against the page's *content* box, not the full page box, so the rule landed well above the margin area instead of near the footer text. Giving the two margin boxes an explicit `width: 50%` each instead makes their borders meet edge-to-edge with no gap, producing one continuous rule with no extra element.
- **Footer text: a pre-escaped CSS string literal (`footer_left_css`), not `string-set: ... content()`.** WeasyPrint 69 supports neither `string-set: ... content();` nor `leader()` (both verified empirically to silently drop the declaration). `report_export_view.py`'s `_css_single_quoted_string()` builds a CSS-escaped `'...'` literal (backslash/quote/`<` escaped) emitted via `|safe` into the `<style>` block, avoiding both the missing-`content()` gap and Jinja's HTML-entity escaping mangling an apostrophe in a Client's name.
- **Fonts: fontTools-instantiated static WOFF2s, not the Google Fonts CSS2 API's own files directly.** The CSS2 API serves Cormorant Garamond 500/600 (normal) from the *same* underlying variable-font resource for both weights (relies on the browser reading the file's own `fvar` table against the declared CSS `font-weight` — real, modern browser behavior, but an unverified risk under WeasyPrint's own font pipeline). Downloaded the variable TTF sources from `github.com/google/fonts` instead and instantiated genuinely distinct static per-weight files locally via `fontTools.varLib.instancer`, then subset+compressed to WOFF2 — verified each weight renders visibly distinct under WeasyPrint.
- **Added dedicated automated coverage for the I/O & Edge-Case Matrix (review-loop feedback).** The first implementation pass only verified the four matrix rows manually (a rendered, rasterized PDF inspected by eye) and flagged that as a risk rather than closing it. Added five tests to `tests/test_http_report_runs.py`: `test_the_exported_html_omits_the_birthplace_row_when_birthplace_name_is_null`, `test_the_exported_html_shows_an_uncited_day_list_entry_as_date_only` (reuses the existing `_a_frozen_payload_with_one_aspect()`/`_a_generated_draft_for()` fixture pair, which already produces one cited and one uncited day-list entry for free), `test_report_export_html_cards_never_split_across_a_page_break` (a structural assertion on the template's static `.card` CSS rule — real WeasyPrint pagination is not exercised anywhere in this suite, so this checks the rule that guarantees the behavior rather than the rendered behavior itself), and two `RuntimeError`-guard tests (`test_downloading_the_export_pdf_for_a_run_with_no_natal_chart_id_raises`, `test_downloading_the_export_pdf_for_a_report_with_a_deleted_natal_chart_raises`) mirroring the four pre-existing sibling guards in the same file.
- **Blind-hunter review pass: 9 auto-fixable patches (not spec problems, no loopback).**
  1. `_literal_wheel_colors_settings()` (`report_runs.py`) now raises `RuntimeError` naming any key it built that still contains the substring `"var("` after the if/elif chain runs — a future Kerykeion settings key this function doesn't yet recognize now fails loudly at import time instead of silently reintroducing the black-disc wheel bug the whole function exists to prevent.
  2. Added `tests/test_report_export_view.py` — 16 direct unit tests for `report_export_view.py`'s pure functions, previously only exercised indirectly through the full HTTP route tests: `_split_degree`'s minute-rollover, `_ascendant_placement`'s sign-index wraparound at the 0°/360° boundary (including the defensive `% 12` at exactly 360°, which a bare `divmod` would otherwise index out of range with), `_placement`'s new key-existence guard (point 8 below), `_month_label`/`_format_birth_date`/`_format_birth_time`/`_split_day_list_date`, `_css_single_quoted_string`'s escaping, and one `build_export_context` spot-check for a NULL birthplace passing through unmodified.
  3. `_css_single_quoted_string` now also CSS-escapes every C0 control character and DEL (0x00-0x1F, 0x7F) via the general hex-escape form (`\{hex} `), not just backslash/quote/`<` — a raw, unescaped newline inside a CSS string is a parse error, not merely cosmetic, and a Client name is not guaranteed newline-free.
  4. `report_export.html`: `.header-row`, `.positions-wheel-row` and `.day-lists-row` now also carry `break-inside: avoid`, so a page break can no longer land between sibling cards meant to read as one visual group (e.g. splitting "Le tue posizioni" from "Il tuo tema natale").
  5. The heading assertion in `tests/test_http_report_runs.py` (the wheel/sections test) now asserts the template's real emitted markup, `<p class="label">{heading}</p>`, not the weaker `>{heading}<` (which would have matched any wrapping element).
  6. `.report-title`, `.report-subtitle` and `.placement-sign` now carry `overflow-wrap: break-word`, matching `.prose`'s existing overflow protection, so an unusually long Client name can't overflow its container unwrapped.
  7. `<title>` is now `Report astrologico — {{ client_name }}` (was English `Report — …`) to match `lang="it"` and the rest of the document.
  8. `_placement()` (`report_export_view.py`) now explicitly guards `sign`/`degree`/`house` key presence before reading them, raising `RuntimeError` (naming the chart id, planet name and missing key) instead of a bare `KeyError` — mirrors `_planet_by_name`'s own guard.
  9. Reverted five formatting-only hunks in `tests/test_http_report_runs.py` that an earlier `ruff format` pass collapsed/reformatted with no semantic connection to this feature (a docstring quote spacing fix, and four calls reformatted onto one line) — restored to their exact baseline (`b63915e`) form so the diff stays focused on the actual change.

  Two further findings from the same review were legitimate but out of scope for this pass (semantic heading elements instead of styled `<p>`s; the Kerykeion `var(--kerykeion-*)` / WeasyPrint incompatibility as a standing platform risk beyond this one wheel) — appended to `deferred-work.md` rather than looped back, since neither is an intent gap or a spec defect.

## Design Notes

**Pagination:** force `break-before: page` only at the two natural group starts (first domain card; the day-lists row) and rely on `break-inside: avoid` per card elsewhere — matches "show intent, not fixed breaks."

**Fonts:** file-based `@font-face` + `base_url` (not base64) keeps the template readable. Georgia/Times stay in the CSS fallback chain, so the existing "Georgia" assertion in `test_http_shell.py` stays true unmodified; `fonts-liberation` in the Dockerfile is untouched (last-resort fallback only).

**Degree/minute:** `whole = int(degree); minutes = round((degree - whole) * 60)`, rolling `minutes == 60` into `whole += 1`. Ascendant: decompose `chart.ascendant` the same way (`divmod(longitude, 30)`), reimplemented locally since `_sign_and_degree` is private.

## Verification

**Commands:**
- `uv run pytest tests/test_http_shell.py tests/test_draft_view.py tests/test_dockerfile_weasyprint_runtime.py` -- expected: unchanged, all pass.
- `uv run pytest` -- expected: green.
- `uv run pytest tests/test_http_report_runs.py -k "birthplace_row or uncited_day_list or cards_never_split or no_natal_chart_id or deleted_natal_chart"` -- the five I/O & Edge-Case Matrix tests specifically.

**I/O & Edge-Case Matrix -- automated coverage (`tests/test_http_report_runs.py`):**
- Birthplace NULL -> `test_the_exported_html_omits_the_birthplace_row_when_birthplace_name_is_null`.
- Uncited day-list entry -> `test_the_exported_html_shows_an_uncited_day_list_entry_as_date_only`.
- Long Section prose (cards never split) -> `test_report_export_html_cards_never_split_across_a_page_break` (structural: asserts `break-inside: avoid` on `.card`, since real pagination isn't exercised by this suite).
- `natal_chart_id` missing on passed run -> `test_downloading_the_export_pdf_for_a_run_with_no_natal_chart_id_raises` (never set) and `test_downloading_the_export_pdf_for_a_report_with_a_deleted_natal_chart_raises` (set, then the row deleted).

**Manual checks (still worth doing before a real release; not substitutes for the above):**
- Open a real `/export/pdf` download: wheel in copper/ink tones (not black/broken), Cormorant Garamond/Jost visibly render, footer + page count repeat every page, no card splits mid-sentence.

## Suggested Review Order

**Data wiring — the route**

- Entry point: where the run's own chart, wheel and view context get assembled before rendering.
  [`report_runs.py:1402`](../../shell/http/routes/report_runs.py#L1402)

- `RuntimeError`-guards the run's own chart lookup, never the Client's current one — a correction can make them disagree.
  [`report_runs.py:413`](../../shell/http/routes/report_runs.py#L413)

**Wheel rendering — WeasyPrint's CSS-var gap**

- Kerykeion's `var(--kerykeion-*)` colors don't resolve inside an inlined SVG under WeasyPrint 69; builds a literal-color settings dict instead, with a fail-loud guard for an unrecognized future settings key.
  [`report_runs.py:145`](../../shell/http/routes/report_runs.py#L145)

- Uses `generate_wheel_only_svg_string()` (not the full-chart SVG) so the card shows just the wheel, matching the mockup's own reference SVG.
  [`report_runs.py:197`](../../shell/http/routes/report_runs.py#L197)

**View-shaping — the new module**

- Every value the template reads, built from the run's own chart plus `render_draft()`'s already-rendered output.
  [`report_export_view.py:252`](../../shell/http/report_export_view.py#L252)

- Ascendant sign/degree decomposition — `StoredNatalChart.ascendant` is an absolute longitude, never pre-split like a stored planet.
  [`report_export_view.py:160`](../../shell/http/report_export_view.py#L160)

- Degree → degrees/minutes with the 29.999°→30°00′ rollover case.
  [`report_export_view.py:105`](../../shell/http/report_export_view.py#L105)

- CSS-escapes the footer's running text (Client name) so it can't break out of the `<style>` block; escapes control characters too.
  [`report_export_view.py:227`](../../shell/http/report_export_view.py#L227)

**Template — real WeasyPrint pagination**

- `@font-face` for the five bundled local weights — no runtime network fetch.
  [`report_export.html:25`](../../shell/http/templates/report_export.html#L25)

- `@page` A4 CSS: the repeating footer/page-count via margin boxes, not app chrome.
  [`report_export.html:56`](../../shell/http/templates/report_export.html#L56)

- `break-inside: avoid` on cards and, after the review pass, on the multi-card row containers too.
  [`report_export.html:138`](../../shell/http/templates/report_export.html#L138)

**Font/render plumbing**

- `html_to_pdf` now requires `base_url` so the template's local `@font-face` paths resolve.
  [`render.py:26`](../../shell/adapters/weasyprint/render.py#L26)

- Vendored OFL font files + attribution.
  [`fonts/OFL.txt`](../../shell/http/templates/fonts/OFL.txt)

**Tests**

- Direct unit coverage for the new view module's pure functions.
  [`test_report_export_view.py`](../../tests/test_report_export_view.py)

- HTTP-level coverage for the I/O & Edge-Case Matrix and the wheel/sections boundary.
  [`test_http_report_runs.py`](../../tests/test_http_report_runs.py)
