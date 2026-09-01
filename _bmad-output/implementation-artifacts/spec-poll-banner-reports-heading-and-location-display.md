---
title: 'Poll-error banner visibility, a reports-list heading, and clarifying the missing birthplace display'
type: 'bugfix'
created: '2026-09-01'
status: 'done'
route: 'one-shot'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The report-run poll screen's "Connessione persa" banner rendered even though it carried the `hidden` attribute; the client reports page had no label distinguishing the "create a report" form from the list of existing reports below it; and it was unclear whether the missing birthplace name in the Anagrafica edit form and on the SVG birth chart's "Location" field was a bug or intentional.

**Approach:** Fixed the CSS cascade bug that kept `[hidden]` elements visible (`.banner`, and the same bug found in `.btn` during review) in `shell/http/static/tokens.css`; added an `<h2>Report disponibili</h2>` heading above the reports list in `client_reports.html`; confirmed via code and docstrings that the missing birthplace/location display is an intentional, documented design decision (the `Client` model never stores a free-text place name — only resolved lat/lon/timezone) and made no code change for it.

## Boundaries & Constraints

**Always:** Preserve the existing per-component `[hidden]` override convention already established by `.modal-scrim[hidden]` — do not introduce a blanket `[hidden] { display: none }` rule that would silently change the cascade for every component at once.

**Never:** Fabricate or reverse-geocode a birthplace name to fill the "Location" display — no such data is stored, and inventing one is a schema/feature decision, not a one-shot fix.

</frozen-after-approval>

## Code Map

- `shell/http/static/tokens.css` -- `.banner`/`.btn` both set their own `display`, which beat the UA `[hidden]` rule in the cascade; needed a matching `[hidden]` override each.
- `shell/http/templates/report_run_poll.html` -- the poll-error banner and the `Riprova` retry button, both rendered with the `hidden` attribute this fix restores.
- `shell/http/templates/client_reports.html` -- the reports list, now labelled.
- `shell/http/routes/clients.py` -- `client_edit_form`'s docstring documents why birthplace starts blank (no free-text place name is ever stored).
- `shell/http/chart_wheel.py` -- `build_subject`'s docstring documents why the SVG chart's `city`/`nation` (its "Location" line) are always empty.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/static/tokens.css` -- add `.banner[hidden] { display: none; }` and `.btn[hidden] { display: none; }` -- restores the `hidden` attribute's effect on both components
- [x] `shell/http/templates/client_reports.html` -- add `<h2>Report disponibili</h2>` above the entries list -- labels the list so it reads distinctly from the "Nuovo report" form above it
- [x] `tests/test_http_clients.py` -- assert the new heading's absence in the empty state and presence when reports exist -- locks in the new markup

**Acceptance Criteria:**
- Given a report run whose poll request fails, when the failure banner's `hidden` attribute is removed by `shell.js`, then the banner becomes visible (and stays hidden until then) — same for the `Riprova` button.
- Given a client with at least one report, when `/clients/{id}/reports` renders, then `<h2>Report disponibili</h2>` appears above the list; given a client with none, the heading is absent and the existing empty state shows instead.

## Design Notes

The blind-hunter review surfaced that `.btn` had the identical `[hidden]`-losing-to-`display` cascade bug as `.banner` (the `Riprova` retry button in the same `report_run_poll.html` block), so it was patched in the same pass rather than deferred — it's the same defect class the user reported, in the same screen. A third instance (`.corpus-entry__expand` in `corpus_list.html`) is currently masked by how `shell.js` uses it and was deferred instead (see `deferred-work.md`), along with a broader note that a single generic `[hidden]` rule would close this whole class of bug at the cost of deviating from the codebase's current per-component convention.

## Verification

**Commands:**
- `.venv/bin/python -m pytest tests/test_http_clients.py -k reports tests/test_http_shell.py -q` -- expected: all pass (8 passed)

**Manual checks (if no CLI):**
- Load a report-run poll page, force a failed poll (e.g. stop the backend mid-poll), and confirm the "Connessione persa" banner and "Riprova" button only appear after a failure, not on initial load.

## Suggested Review Order

**Hidden-attribute cascade fix**

- The root cause: `.banner`/`.btn` each declare `display`, which beats the UA `[hidden]` rule regardless of specificity — author rules win ties.
  [`tokens.css:607`](../../shell/http/static/tokens.css#L607)

- The fix for the reported banner, following the existing `.modal-scrim[hidden]` convention.
  [`tokens.css:626`](../../shell/http/static/tokens.css#L626)

- The same fix applied to `.btn`, after review surfaced the retry button had the identical bug.
  [`tokens.css:1117`](../../shell/http/static/tokens.css#L1117)

- The two elements this fix restores correct behavior for.
  [`report_run_poll.html:28`](../../shell/http/templates/report_run_poll.html#L28)

**Reports-list heading**

- The new heading, labelling the list distinctly from the "Nuovo report" form above it.
  [`client_reports.html:37`](../../shell/http/templates/client_reports.html#L37)

- Coverage locking the heading's presence/absence in both states.
  [`test_http_clients.py:859`](../../tests/test_http_clients.py#L859)
  [`test_http_clients.py:989`](../../tests/test_http_clients.py#L989)

**Location display — confirmed intentional, no change**

- Why the Anagrafica edit form's birthplace field always starts blank.
  [`clients.py:481`](../../shell/http/routes/clients.py#L481)

- Why the SVG birth chart's "Location" line is always empty.
  [`chart_wheel.py:78`](../../shell/http/chart_wheel.py#L78)

