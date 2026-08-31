---
title: 'Story 9.6 amendment — the report-run breadcrumb'
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

**Problem:** `EXPERIENCE.md`'s route map states `/report-runs/{run_id} — breadcrumb: Clienti / {nome} / {mese}` explicitly, but `report.html`, `report_draft.html`, `report_payload.html`, and `report_run_poll.html` never received a `client` in their route context and render no breadcrumb — opening a report gives no visible link back to whose it is or how to return, which is most of what read as "too plain and confusing."

**Approach:** A new shared partial (`_report_run_breadcrumb.html`, mirroring `_client_tabs.html`'s breadcrumb precedent) included from all four screens' `page_header` block, fed by `client`/`run` now present in every one of their route contexts.

## Suggested Review Order

**The partial and its contract**

- Entry point — the breadcrumb markup itself and its documented `client`/`run` contract.
  [`_report_run_breadcrumb.html:1`](../../shell/http/templates/_report_run_breadcrumb.html#L1)

**Wiring `client`/`run` into four routes**

- `view_report_draft` — `client`/`run` now unconditionally in context (previously only on a failed run); the template's `{% elif run %}` → `{% elif run.failed_at %}` change this required.
  [`report_runs.py:492`](../../shell/http/routes/report_runs.py#L492)

- `view_report_payload` — now also loads the `ReportRun` (previously only `ReportPayload`/`Client`) to source `run.month`.
  [`report_runs.py:426`](../../shell/http/routes/report_runs.py#L426)

- `view_report` — `bundle.client` (already loaded) added to context.
  [`report_runs.py:569`](../../shell/http/routes/report_runs.py#L569)

- `poll_report_run` — `client` (already loaded) added to context.
  [`report_runs.py:340`](../../shell/http/routes/report_runs.py#L340)

**Tests**

- The breadcrumb on all four screens, its absence from the HTMX poll fragment, the still-failed Draft path, and a decoy-client check proving the correct Client is wired.
  [`test_http_report_runs.py:2742`](../../tests/test_http_report_runs.py#L2742)

## Spec Change Log

- review-loop 1 (blind-hunter): removed the now-redundant month chip from `report.html`'s and `report_run_poll.html`'s own `<h1>` (the breadcrumb already shows it). Added `aria-current="page"` to the breadcrumb's trailing month segment. Added a regression test proving the breadcrumb still renders on `report_draft.html`'s pre-existing terminally-failed path (the `{% elif run %}` → `{% elif run.failed_at %}` change's whole reason for existing). Added a decoy-client test on `view_report` proving the wired `client` is the run's own, not merely *a* Client. Deferred: the breadcrumb's markup (a bare `<p>` with `/` separators, matching `_client_tabs.html`'s own precedent) has no `<nav>`/`<ol>` landmark structure — `tokens.css` already flags `.breadcrumb` "PROVISIONAL," naming Story 9.8 as the intended consolidation point, so fixing this partial alone would diverge it from its sibling.
