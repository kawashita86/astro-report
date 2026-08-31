---
title: 'Story 9.3 amendment — the Report tab''s missing Nuovo report control'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 0
route: 'one-shot'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-31.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
---

## Intent

**Problem:** `EXPERIENCE.md`'s route map and Month Selection section both specify a "Nuovo report" control — a `YYYY-MM` field defaulted to next month — on the Client's Report tab, posting to the existing `POST /clients/{id}/report-runs`. `client_reports.html` shipped only the report-history list; no template anywhere posted to that route, so there was no way to start a report run from the UI at all (correct-course, `sprint-change-proposal-2026-08-31.md`).

**Approach:** Add the control to `client_reports.html`, gated on the Client having a current (non-superseded) chart, with the month field prefilled to next calendar month per EXPERIENCE.md. Extracted the "current chart for a client" query — until now duplicated between this new check and `report_runs.py::_current_chart` — into a single shared `current_chart_for_client` in the adapter module.

## Suggested Review Order

**The missing control**

- Entry point — the form and its gating, matching EXPERIENCE.md's exact copy and route.
  [`client_reports.html:15`](../../shell/http/templates/client_reports.html#L15)

- Route context now computes `has_chart` and the next-month default the template renders.
  [`clients.py:858`](../../shell/http/routes/clients.py#L858)

- `_next_calendar_month` takes an optional `today` so the December→January rollover is testable without waiting for December.
  [`clients.py:898`](../../shell/http/routes/clients.py#L898)

**Removing the duplicated chart query**

- New shared helper both `clients.py` and `report_runs.py` now call instead of each keeping its own copy of the same predicate.
  [`client.py:222`](../../shell/adapters/postgres/client.py#L222)

- `report_runs.py`'s `_current_chart` becomes a thin alias onto the shared helper — its two call sites (`start_report_run`, the poll-time chart check) are unchanged.
  [`report_runs.py:127`](../../shell/http/routes/report_runs.py#L127)

**Styling**

- `.new-run-form` — a compact field-beside-button row rather than the full 560px stacked form, since it's one value with a sensible default; wraps on narrow viewports.
  [`tokens.css:1094`](../../shell/http/static/tokens.css#L1094)

**Tests**

- Form renders correctly for a Client with a chart, absent for one with none or only a superseded one; `_next_calendar_month` unit-tested directly for the rollover.
  [`test_http_clients.py:861`](../../tests/test_http_clients.py#L861)

**Documentation**

- `epic-9-context.md` and `deferred-work.md` updated: this control is now built; the three other correct-course items (auth redirect, report breadcrumb, sign-in styling) are explicitly marked not-yet-built so a future reader doesn't mistake the forward-looking context for shipped behavior.
  [`epic-9-context.md:36`](../../_bmad-output/implementation-artifacts/epic-9-context.md#L36)
