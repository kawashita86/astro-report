---
title: 'Read a Report with its facts one click away'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '6f798316ce524263ad65d2fc805c3959012f1d5c'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Once a `ReportRun`'s Gate passes, Francesco has no page that shows the finished Report: the poll page's stage-exact links stop at the Draft, and nothing surfaces the persisted Gate verdict or a way to reach the Payload without leaving the screen.

**Approach:** Add `GET /report-runs/{run_id}/report`, gated on a persisted `Report` row (Gate passed), rendering the same eight Sections the Draft view already renders plus the persisted `StoredGateResult` (passed + regeneration count) and a link to the existing Payload view. Add a "View Report" link from the poll page once `stage` reaches `gate_passed` or `exported`.

## Boundaries & Constraints

**Always:** Gate access on the `Report` row's existence (not on `run.stage`), mirroring `shell/export.py`'s own boundary and `view_report_payload`'s "row missing = not ready" pattern. Read the Gate verdict from the persisted `StoredGateResult` row (`passed=True`), never recompute it live (epic-5-retro-item-38's precedent). Reuse `render_draft`/`SECTION_ORDER`/`LIST_SECTION_NAMES` (`shell/http/draft_view.py`) and `localize_payload`'s existing localization path — do not re-derive section rendering. New route only; `view_report_draft`/`view_report_payload` stay byte-for-byte unchanged.

**Ask First:** Nothing identified.

**Never:** Do not touch `core/`. Do not build Story 6.2 (export) or 6.3 (send disposition) here — this route is read-only. Do not rename or remove the existing `/draft` route.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Anonymous request | No session cookie | `GET /report-runs/{id}/report` | 401 (AuthMiddleware) |
| Unknown run | `run_id` matches no `ReportRun` | — | 404 |
| Gate not yet passed | `ReportRun` exists, no `Report` row (e.g. still `draft_ready`, or terminally failed) | — | 404 |
| Gate passed, no regenerations | `Report` + `StoredGateResult(passed=True, regeneration_count=0)` exist | 200; all eight Sections in fixed order; "Passed", regeneration count 0; Payload link present | N/A |
| Gate passed after regenerating | `StoredGateResult(passed=True, regeneration_count=2)` differs from `run.regeneration_count` | 200; regeneration count shown is the **stored** value (2), not read from `run` | N/A |
| Report generated months earlier | Same rows, `created_at` far in the past | 200; Payload and Gate result render identically to a fresh Report | N/A |
| Poll page before Gate passes | `run.stage` in `natal_ready`..`draft_ready` | No "View Report" link | N/A |
| Poll page after Gate passes | `run.stage` is `gate_passed` or `exported` | "View Report" link to `/report-runs/{run.id}/report` | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py` -- add `view_report(run_id, request, session)` at `GET /report-runs/{run_id}/report`, after `view_report_draft` (line 189+). Query `Report` (`shell/adapters/postgres/report.py`) by `report_run_id`; 404 if missing. Then latest `ReportDraft`, `ReportPayload`, `Client` -- mirror lines 224-243's lookups and `RuntimeError`-on-missing guards verbatim. Read `StoredGateResult` where `report_run_id == run_id and passed.is_(True)` (already imported line 34). Render via `deserialize_generated_draft`/`render_draft` exactly as lines 242-243 do.
- `shell/http/templates/report.html` -- new template. Loop `section_order`/`list_section_names` exactly like `report_draft.html`'s loop (lines 32-45); add "Gate: Passed (regenerated N times)" and `<a href="/report-runs/{{ run_id }}/payload">`.
- `shell/http/templates/report_run_poll.html` -- add `{% if run.stage == "gate_passed" or run.stage == "exported" %}` after the `draft_ready` block (lines 31-33), linking "View Report" to `/report-runs/{{ run.id }}/report`. Existing blocks untouched.
- `tests/test_http_report_runs.py` -- new tests after line 767, using this file's existing `_create_client_with_real_chart`/`store_report_payload`/`store_report_draft`/`store_gate_result` conventions; import `Report`/`store_report` for the passing-state setup.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/report_runs.py` -- add `view_report` route -- serves the finished, Gate-passed Report
- [x] `shell/http/templates/report.html` -- new template rendering Sections + Gate result + Payload link -- fulfills AC1/AC2
- [x] `shell/http/templates/report_run_poll.html` -- add "View Report" link for `gate_passed`/`exported` stages -- fulfills "one click away" from the natural run-completion flow
- [x] `tests/test_http_report_runs.py` -- cover the I/O & Edge-Case Matrix above -- proves the route and the persisted-verdict rule

**Acceptance Criteria:**
- Given a Report that has passed the Gate, when Francesco opens it, then all eight Sections are displayed in their fixed order and the Gate result is visible, including the regeneration count.
- Given the displayed Report, when Francesco wants the underlying facts, then the Payload view (Story 3.9) is reachable in one interaction, without leaving the Report.
- Given a Report generated months earlier, when it is opened, then its Payload and Gate result are intact and equally reachable.

## Spec Change Log

## Design Notes

`Report`'s mere existence is the gate, exactly as Story 6.2's export boundary will read it. `regeneration_count` is read off `StoredGateResult`, not `ReportRun.regeneration_count` -- they never actually diverge for a passed run, but the persisted read matches the epic-5-retro-item-38 precedent and costs nothing.

## Verification

**Commands:**
- `uv run pytest tests/test_http_report_runs.py -q` -- expected: all tests pass, including the new ones
- `uv run mypy shell/http/routes/report_runs.py` -- expected: no new errors

## Suggested Review Order

**Gate-passed gating**

- Entry point: the new route, gated on the `Report` row's mere existence, never `run.stage`.
  [`report_runs.py:267`](../../shell/http/routes/report_runs.py#L267)

- 404 boundary: no `Report` row means the Gate never passed for this run -- mirrors `export_report()`'s own read.
  [`report_runs.py:294`](../../shell/http/routes/report_runs.py#L294)

**Reading back the rows a passed Report implies**

- `ReportRun`/`ReportDraft`/`Client` reads, each `RuntimeError`-guarded as data-integrity, not 404, once `Report` exists.
  [`report_runs.py:298`](../../shell/http/routes/report_runs.py#L298)

- Latest attempt's draft, ordered like `view_report_draft`'s own lookup.
  [`report_runs.py:302`](../../shell/http/routes/report_runs.py#L302)

- Client fetched for `iana_zone`, reused by `render_draft`'s localization.
  [`report_runs.py:316`](../../shell/http/routes/report_runs.py#L316)

**Persisted Gate verdict, not recomputed**

- The passing `StoredGateResult`, ordered defensively by `regeneration_count` -- epic-5-retro-item-38's precedent.
  [`report_runs.py:320`](../../shell/http/routes/report_runs.py#L320)

**One-click Payload, in context**

- Gate result + month heading + the one-click Payload link, all in the new template.
  [`report.html:11`](../../shell/http/templates/report.html#L11)

- "View Report" surfaced from the natural run-completion flow, once `gate_passed`/`exported`.
  [`report_run_poll.html:34`](../../shell/http/templates/report_run_poll.html#L34)

**Tests**

- Happy path: all eight Sections, Gate result, Payload link.
  [`test_http_report_runs.py:1187`](../../tests/test_http_report_runs.py#L1187)

- Multiple `StoredGateResult` rows: proves the `order_by` picks the passing one, not an arbitrary one.
  [`test_http_report_runs.py:1282`](../../tests/test_http_report_runs.py#L1282)

- `exported`-stage coverage: proves gating is on `Report`, not `run.stage`.
  [`test_http_report_runs.py:1325`](../../tests/test_http_report_runs.py#L1325)
