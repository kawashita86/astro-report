---
title: 'Italian everywhere, and the accessibility floor'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'b04d79b9b45e8edd351a04067881196d3e1c7421'
context: ['{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 9.1–9.8 restyled the UI but deferred full Italian coverage to this story (`base.html`/`_client_tabs.html`'s own "Screen body copy is Story 9.9" comments). `client_new.html`, `client_edit.html`, `client_delete.html`'s heading, `chart_wheel.html`, `client_reports.html`, `corpus_new.html`, `login.html`, and `report_payload.html`'s per-field sub-headings still carry raw English. Three date/time renders (Payload instants, Corpus entries, Style Guide versions) don't follow `dd/MM/yyyy HH:mm`. The Payload view's per-section dump has no scroll container for 400% reflow.

**Approach:** Sweep the remaining templates/routes for English copy and non-compliant date formatting, translate per `EXPERIENCE.md`'s label map and Voice & Tone, fix the three date-format sites, add the missing overflow wrapper. Verify (not rebuild) the focus-trap/reduced-motion/landmark mechanics `base.html`/`shell.js`/`tokens.css` already ship — those already meet the AC.

## Boundaries & Constraints

**Always:**
- Every operator-facing string becomes Italian per `EXPERIENCE.md`'s label map; a synonym for a fixed domain term (Cliente, Tema natale, Report, Payload, Bozza, Verifica di fondatezza, Sezione, Guida di stile, Corpus) is a defect.
- Dates `dd/MM/yyyy`, times `HH:mm`, timestamps `dd/MM/yyyy HH:mm` — mirror the correct pattern already at `home.py:117`/`clients.py:270-271`. `<input type="date"|"time">` `value` attributes stay ISO 8601 — never "fix" those.
- Leave already-Italian, test-covered wording untouched (`client_delete.html`'s panel body, `client_edit.html`'s supersede warning, all of `report.html`/`report_draft.html`/`report_run_poll.html`/`style_guide_*`/`corpus_list.html`/`home.html`/`client_list.html`).

**Never:**
- Touch `report_export.html` — confirm via `git log --oneline -- shell/http/templates/report_export.html` that no new commit lands there.
- Promote the backup-stale banner to a global context-processor — only translate the two existing instances (`home.html:12-17`, `client_reports.html:9-12`), reusing `home.html`'s wording on both.
- Restyle `corpus_new.html`'s/`client_reports.html`'s raw markup into `.btn`/`.list-panel`/`.field` classes — strings and a11y attributes only.
- Modify `core/` or Gate/Payload-generation logic; `run.failure_reason`/violation `detail` strings from `core/` are out of reach.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|---------------------------|----------------|
| Localized Payload instant | tz-aware ISO instant, e.g. `2026-05-14T09:03:00+00:00`, `iana_zone="Europe/Rome"` | `payload_view._localize_value` returns `"14/05/2026 11:03"` | N/A — naive/non-parseable strings still pass through unchanged |
| Corpus/Style Guide row | `entry.created_at` reaching `corpus_list.html`/`style_guide_list.html`/`style_guide_view.html` | Renders `dd/MM/yyyy HH:mm`, not Python's default `str(datetime)` | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/templates/client_new.html` — English: title:3, h1:5, `field_labels` dict:2 + refs :23/38/53/80, `<legend>`:70, submit:95.
- `shell/http/templates/client_edit.html` — same pattern: title:3, h1:6, `field_labels`:2 + refs :41/56/71/98, `<legend>`:88, birthplace helper :107-109 (EXPERIENCE.md's illustrative English lifted verbatim), submit:116.
- `shell/http/templates/client_delete.html` — title:2, h1:7 only (body already Italian).
- `shell/http/templates/chart_wheel.html` — title:2, h1:5 ("Chart wheel" → "Tema natale"), config-stale warning :8-11.
- `shell/http/templates/client_reports.html` — title:3, h1:6, backup-stale banner :9-12 (reuse `home.html:12-17` wording), "(superseded chart)" :21 (reuse `client_list.html:43`'s "tema superato").
- `shell/http/templates/corpus_new.html` — whole page: title:2, h1:4, intro :8-11, textarea label:13, `<legend>`:17 + radio labels :25/34, select label:38 + option:41, month label:53 + `title` attr:61, submit:64.
- `shell/http/templates/login.html` — h1:7, error:9, submit:21.
- `shell/http/templates/report_payload.html` — `<h3>` :34/40 render raw payload dict keys verbatim; needs a label map like `draft_view.py:72`'s `SECTION_TITLES`, wired through `report_runs.py:448-452`'s payload context.
- `shell/http/payload_view.py:46` (`_localize_value`) — the one site formatting every localized Payload instant (AD-12); currently `strftime("%Y-%m-%d %H:%M:%S %Z")`.
- `shell/http/routes/corpus.py:109-127` — passes raw `entry.created_at` into `corpus_list.html:20`.
- `shell/http/routes/style_guide.py:84-188` — passes raw `created_at` into `style_guide_list.html:35`/`style_guide_view.html:10`.
- `shell/http/static/tokens.css:788-795` (`.list-panel` `overflow-x:auto`) — pattern to reuse around `report_payload.html`'s per-section dump.
- `shell/http/static/tokens.css:253,491-519`, `shell/http/static/shell.js:160-212,275,480,704` (focus-visible, reduced-motion, `trapFocus` + 3 trap sites) — already compliant; verify only.
- `tests/test_http_shell.py:91` (`exactly_one_html`) — precedent for a sweep-assertion helper.

## Tasks & Acceptance

**Execution:**
- [x] `client_new.html` — translate title, h1, `field_labels` + refs, legend, submit.
- [x] `client_edit.html` — same pass; write real (non-literal) Italian for the birthplace helper.
- [x] `client_delete.html` — translate title + h1.
- [x] `chart_wheel.html` — translate title, h1, config-stale warning.
- [x] `client_reports.html` — translate title, h1, backup-stale banner, superseded-chart label.
- [x] `corpus_new.html` — translate every remaining string.
- [x] `login.html` — translate h1, error, submit.
- [x] `draft_view.py` + `report_runs.py` + `report_payload.html` — add an Italian field-name label dict, wire through context.
- [x] `payload_view.py:46` — `strftime` → `"%d/%m/%Y %H:%M"`.
- [x] `routes/corpus.py` — format `entry.created_at` as `dd/MM/yyyy HH:mm`, mirroring `home.py:117`.
- [x] `routes/style_guide.py` — same fix for `created_at`.
- [x] `tokens.css` — `overflow-x:auto` wrapper around `report_payload.html`'s per-section dump.
- [x] Tests — extend `test_http_shell.py`/per-screen test files asserting each fixed screen's English string is gone and its Italian replacement renders; unit-test `_localize_value`'s new format and the corpus/style-guide fix; confirm no new commit touches `report_export.html`.

**Acceptance Criteria:**
- Given each fixed screen rendered via `TestClient`, when inspected, then none of the Code Map's English strings remain and each still has exactly one `<h1>`.
- Given a keyboard-only pass over `client_new`/`client_edit`/`corpus_new`/`login`, when tabbing through, then every control is reachable with the existing visible focus ring.
- Given `report_export.html`, when this story lands, then it is byte-for-byte unchanged.
- Given `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, when run, then all pass.

## Spec Change Log

## Design Notes

**Repeated field labels.** `client_new.html`/`client_edit.html` share four birth-data fields; use identical Italian on both: *Nome* / *Data di nascita* / *Ora di nascita* / *Luogo di nascita* — matches `client_list.html`'s table headers.

**Field-name map placement.** `draft_view.py:72`'s `SECTION_TITLES` is the one Italian-heading source shared across four consumers, with a docstring explaining the explicit-dict choice. The new per-field map is the same kind of fixed vocabulary — same module, same reasoning.

## Verification

**Commands:**
- `uv run pytest` — expected: full suite green.
- `uv run ruff check .` && `uv run ruff format --check .` — expected: clean.

**Manual checks:**
- Tab through `client_new`, `client_edit`, `corpus_new`, `login` with JS on and off; confirm reachability + visible focus ring.
- Zoom `report_payload.html` to 200%/reflow 400%; confirm the per-section dump scrolls in its own container.
- `git log --oneline -- shell/http/templates/report_export.html` — expected: no new commit.

## Suggested Review Order

**Date/time formatting (the AD-12 authoritative site + its siblings)**

- The one function that formats every localized Payload instant — this is the fix the rest of the date work follows.
  [`payload_view.py:75`](../../shell/http/payload_view.py#L75)

- Corpus entry timestamps now match the mandate, applied inline via Jinja's `.strftime()`.
  [`corpus_list.html:20`](../../shell/http/templates/corpus_list.html#L20)

- Style Guide list row gets the same treatment.
  [`style_guide_list.html:35`](../../shell/http/templates/style_guide_list.html#L35)

- Style Guide read-only detail view, same fix.
  [`style_guide_view.html:10`](../../shell/http/templates/style_guide_view.html#L10)

**Payload field-name label map (closes the same class of bug `SECTION_TITLES` already solved for sections)**

- New Italian field-name map, parity-tested against `SectionPayload`'s actual fields so a future field can't silently regress.
  [`payload_view.py:38`](../../shell/http/payload_view.py#L38)

- Wired into the per-section sub-headings that used to render raw dict keys verbatim.
  [`report_payload.html:34`](../../shell/http/templates/report_payload.html#L34)

**Client screens — Italian translation + fixed error copy**

- Client create form: heading, field labels, legend, submit button all translated.
  [`client_new.html:5`](../../shell/http/templates/client_new.html#L5)

- Client correct form: same pass, plus a non-literal Italian rewrite of the birthplace re-entry helper.
  [`client_edit.html:6`](../../shell/http/templates/client_edit.html#L6)

- Delete confirmation heading translated (the panel body was already Italian from Story 9.4).
  [`client_delete.html:7`](../../shell/http/templates/client_delete.html#L7)

- Fixed-message error constants replace raw/English exception text shown to the operator.
  [`clients.py:117`](../../shell/http/routes/clients.py#L117)

- Wording softened after review — `PlaceResolutionError` also covers infra failures, not just "no match".
  [`clients.py:133`](../../shell/http/routes/clients.py#L133)

- The missing "cosa fare" follow-up was added after review, matching sibling messages' Voice & Tone.
  [`clients.py:139`](../../shell/http/routes/clients.py#L139)

**Remaining screens — chart wheel, reports tab, corpus form, login**

- Heading and the config-stale warning translated.
  [`chart_wheel.html:5`](../../shell/http/templates/chart_wheel.html#L5)

- Heading, backup-stale banner, superseded-chart label translated; the `<title>` now matches the `<h1>` after review.
  [`client_reports.html:3`](../../shell/http/templates/client_reports.html#L3)

- Entire page translated — this screen had never been touched by an earlier restyle story.
  [`corpus_new.html:4`](../../shell/http/templates/corpus_new.html#L4)

- The month-format hint is now threaded from the single `_ERROR_MONTH_INVALID` constant instead of duplicated.
  [`corpus.py:74`](../../shell/http/routes/corpus.py#L74)

- Sign-in screen fully translated.
  [`login.html:7`](../../shell/http/templates/login.html#L7)

**Layout — 400% reflow container**

- New `overflow-x: auto` wrapper for the Payload view's per-section dump, mirroring `.list-panel`'s existing pattern.
  [`tokens.css:1423`](../../shell/http/static/tokens.css#L1423)

**Peripherals**

- Parity test binding `FIELD_TITLES` to `SectionPayload`'s real fields.
  [`test_payload_view.py:151`](../../tests/test_payload_view.py#L151)

- Representative per-screen assertion that a fixed screen's known English string is gone and its Italian replacement renders (fixed after review to assert the full unescaped string).
  [`test_http_clients.py:655`](../../tests/test_http_clients.py#L655)
