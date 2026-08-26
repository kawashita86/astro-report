---
title: 'Browse everything I have produced for a Client'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: 'a35301b089a90e3b4496e986f49d66f5b80019b4'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Francesco has no way to see a Client's prior Reports at all (FR-27) — every Report is only reachable if he already has its `run_id` from the moment he generated it. Reopening a month a client is asking about, or telling a Report generated against a chart that has since been corrected apart from a current one, is impossible today.

**Approach:** Add `GET /clients/{client_id}/reports`, listing every Gate-passed `Report` for that Client by month, each linking straight into the existing, untouched `view_report` page. Because nothing today records which `StoredNatalChart` a given `ReportRun` was generated against, `ReportRun` gains a `natal_chart_id` column, set once (forward-only) when `natal_ready` first runs — this is what lets the listing mark an entry as belonging to a superseded chart.

## Boundaries & Constraints

**Always:** The listing shows only `Report` rows (a passed Gate outcome) for the Client, joined to their `ReportRun` for `month`, ordered by `ReportRun.month` descending (most recent first) — a `ReportRun` that never reached `gate_passed` never appears. `natal_chart_id` is set exactly once, inside `drive()`'s existing per-stage success path, the first time `stage_name == "natal_ready"` succeeds — mirrors `month_start_utc`/`month_end_utc`'s own forward-only assignment; never touched by any later stage or regeneration. Reopening a listed Report navigates to the existing `/report-runs/{run_id}/report` route/template, unchanged. New migration column addition only (`nullable=True`, no backfill) — Report rows generated before this migration have `natal_chart_id = NULL` and cannot be marked superseded.

**Ask First:** Nothing identified.

**Never:** Do not touch `core/`. Do not add a client list/dashboard page — this route is reached by an already-known `client_id`, a global client index is out of scope. Do not change `view_report`, `report.html`, or any export route. Do not add pagination.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Client has no Reports | No `Report` row for `client_id` | Empty list rendered | N/A |
| Client has several Reports | N `Report` rows across months | Listed by month, most recent first | N/A |
| Reopen a listed Report | Click a listed month | Opens `/report-runs/{run_id}/report` intact (Payload/Gate reachable as before) | N/A |
| Report against a superseded chart | `ReportRun.natal_chart_id` -> `StoredNatalChart.superseded_at` is not `None` | Entry marked as belonging to a superseded chart; still opens normally | N/A |
| Unknown client | `client_id` matches no `Client` | -- | 404 |
| Pre-migration Report | `ReportRun.natal_chart_id` is `NULL` | Not marked superseded (undeterminable) | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/report_run.py` -- add `natal_chart_id: UUID | None = Field(default=None, foreign_key="natal_chart.id")` to `ReportRun` (near `client_id`, line 90) -- no existing column records which chart a run used; verified by full-codebase search, this is a real gap, not a naming miss.
- `migrations/versions/0017_report_run_natal_chart.py` (new) -- forward-only, `down_revision="0016_export_record_disposition"`, one `op.add_column("report_run", sa.Column("natal_chart_id", ...), nullable=True)`, mirrors `migrations/versions/0012_bounded_regeneration.py`'s add-column shape.
- `shell/runner/driver.py` -- `drive()` (line 621) gains keyword param `natal_chart_id: UUID`; in the stage loop's success path (line 819, `run.stage = stage_name`), add `if stage_name == "natal_ready": run.natal_chart_id = natal_chart_id` immediately before it -- this loop iteration only ever runs once for `natal_ready` per run (the module's own forward-only stage guarantee), so no separate guard is needed. `StageFn` and the five stage functions themselves are untouched.
- `shell/http/routes/report_runs.py` -- `_drive_run` (line 131): pass `natal_chart_id=stored_chart.id` to `drive(...)`.
- `shell/http/routes/clients.py` -- new `GET /clients/{client_id}/reports`: 404 if `session.get(Client, client_id)` is `None`; else `select(Report, ReportRun).join(ReportRun, Report.report_run_id == ReportRun.id).where(Report.client_id == client_id).order_by(ReportRun.month.desc())`; for each row, `session.get(StoredNatalChart, run.natal_chart_id)` (`None`-safe) to compute `superseded = chart is not None and chart.superseded_at is not None`. Reuses the already-imported `StoredNatalChart`.
- `shell/http/templates/client_reports.html` (new) -- `<ul>` of months, each linking to `/report-runs/{run_id}/report`, superseded entries visibly marked -- mirrors `style_guide_list.html`'s History `<ul>`/`<li>` shape.
- `shell/adapters/postgres/client.py` -- `delete_client_and_derived` (line 292): the `StoredNatalChart` deletion loop (currently first, line ~328) must move to run *after* the `ReportRun` deletion loop (currently last, line ~368), immediately before `session.delete(client)`. Reason: `ReportRun.natal_chart_id` (this story) is a new foreign key to `natal_chart.id`, so a `StoredNatalChart` row still referenced by a `ReportRun` would violate that constraint if deleted first -- exactly the ordering hazard this function's own docstring already documents for every other table (`ReportPayload`/`StoredReportTheme`/`ReportDraft`/`Report`/`StoredGateResult` before `ReportRun`); `StoredNatalChart` now joins that same "deleted after its referencer" rule, from the other direction. Update the docstring's ordering explanation accordingly. `_CLIENT_CASCADE_TABLES` itself needs no change (it tracks `client.id` foreign keys; `natal_chart_id` points at `natal_chart.id`).
- `tests/test_http_clients.py` -- new tests covering the I/O & Edge-Case Matrix above; add one covering the query is inherently scoped per-Client (two Clients, each with Reports, each listing shows only its own).
- `tests/test_runner_driver.py` -- extend `_drive` (line 160) with the new `natal_chart_id` keyword (default a fixed test UUID); add a test that `natal_chart_id` is set once at `natal_ready` and unaffected by a later regeneration rewind to `payload_ready`.
- `tests/test_client_store.py` -- add a regression test for the reordering above: build a Client with a `StoredNatalChart` and a `ReportRun` whose `natal_chart_id` points at it, enable real foreign-key enforcement on the test engine (`event.listens_for(engine, "connect")` issuing `PRAGMA foreign_keys=ON` -- the module's existing SQLite engine does not enforce foreign keys by default, which is why this ordering hazard was invisible to every other test in this story's first pass), then assert `delete_client_and_derived` succeeds without a `IntegrityError`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/report_run.py` -- add `natal_chart_id` column -- schema for chart traceability
- [x] `migrations/versions/0017_report_run_natal_chart.py` -- add the column -- persists the above
- [x] `shell/runner/driver.py`, `shell/http/routes/report_runs.py` -- thread and set `natal_chart_id` once at `natal_ready` -- captures which chart a run used
- [x] `shell/http/routes/clients.py` -- `GET /clients/{client_id}/reports` -- lists a Client's Reports, marks superseded ones
- [x] `shell/http/templates/client_reports.html` -- the listing UI
- [x] `shell/adapters/postgres/client.py` -- reorder `delete_client_and_derived`'s deletion loops so `StoredNatalChart` is deleted after `ReportRun` -- keeps Client deletion working now that `ReportRun.natal_chart_id` references `natal_chart.id`
- [x] `tests/test_http_clients.py`, `tests/test_runner_driver.py` -- cover the Matrix and the set-once guarantee
- [x] `tests/test_client_store.py` -- regression test (with real FK enforcement enabled) proving Client deletion still succeeds

**Acceptance Criteria:**
- Given a Client with prior Reports, when Francesco opens their history, then the Reports are listed by Client and month, in order.
- Given a prior Report in the list, when Francesco opens it, then it reopens with its Payload and Gate result intact.
- Given a Report generated against a Natal Chart that has since been superseded by a correction, when it is opened, then it remains readable and is marked as belonging to the superseded chart.
- Given a Client with a Report whose `ReportRun.natal_chart_id` is set, when that Client is deleted, then deletion succeeds with no foreign-key violation.

## Spec Change Log

- **Finding (bad_spec, review_loop_iteration 1):** The first implementation pass added `ReportRun.natal_chart_id` as a foreign key to `natal_chart.id`, but `delete_client_and_derived` (`shell/adapters/postgres/client.py`) already deletes every `StoredNatalChart` row for a Client *before* every `ReportRun` row. A database that enforces foreign keys (Postgres, by default) rejects that order once any `ReportRun.natal_chart_id` is non-NULL: deleting a Client who has ever generated a Report would fail. The test suite's SQLite engine does not enforce foreign keys by default, so all 1118 tests passed while this was broken -- caught only by the Blind Hunter review layer reading the diff, not by execution.
  **Amended:** Code Map now requires moving `StoredNatalChart` deletion to run after `ReportRun` deletion inside `delete_client_and_derived`, plus a regression test (`tests/test_client_store.py`) that turns on real foreign-key enforcement for its engine so this class of ordering bug is mechanically caught going forward. Added a fourth Acceptance Criterion covering Client deletion.
  **Known-bad state avoided:** Client deletion (an already-shipped Story 2.8 feature) silently breaking in production for any Client with report history, invisible in CI/local test runs.
  **KEEP -- preserve unchanged on re-derivation:** the `natal_chart_id` column definition and its placement on `ReportRun`; setting it inside `drive()`'s existing per-stage success block (not `StageFn`) exactly as designed, leaving `_run_natal_ready` and the other four stage functions untouched; the `GET /clients/{client_id}/reports` route's query shape, 404 behavior, and superseded-marking logic; `client_reports.html`'s structure; and the original test coverage for the I/O & Edge-Case Matrix (all of it was correct and should be reproduced, not reworked) -- the added multi-Client isolation test is a genuine gap, not a correction. Also add the same reordering rationale to `delete_client_and_derived`'s own docstring, which already documents the analogous "deleted before its referencer" constraint for every other table.

## Design Notes

`natal_chart_id` lives on `ReportRun`, not `Report`: it must be captured at `natal_ready` (the stage that actually reads the chart), long before a `Report` row exists or even before it's known whether one ever will. Setting it inside `drive()`'s existing generic per-stage success block (rather than adding it to `StageFn`'s shared signature) keeps `_run_natal_ready` and the other four stage functions byte-for-byte unchanged, and keeps the direct per-stage-function test (`test_run_gate_passed_raises_gate_failed_error_on_a_failing_gate_result`) working untouched.

Adding a foreign key *to* `natal_chart.id` (rather than the usual direction, *from* it) flips `delete_client_and_derived`'s existing ordering constraint for `StoredNatalChart`: every other table in that cascade is deleted because something else points *at* it (`report_run.id`, etc.); `StoredNatalChart` is now deleted because `ReportRun` points *at* `natal_chart.id`, so it must move to the end of the deletion sequence, not stay at the start.

## Verification

**Commands:**
- `uv run pytest tests/test_http_clients.py tests/test_runner_driver.py tests/test_report_run_store.py tests/test_client_store.py tests/test_http_client_deletion.py -q` -- expected: all pass
- `uv run ruff check .` -- expected: clean
- `uv run alembic upgrade head` against a local Postgres -- expected: `0017_report_run_natal_chart` applies cleanly

## Suggested Review Order

**Browsing a Client's Reports**

- Entry point: 404 on an unknown Client, otherwise joins `Report` to `ReportRun` by month, batches the superseded-chart lookup in one query.
  [`clients.py:618`](../../shell/http/routes/clients.py#L618)

- The listing UI: months link straight into the existing Report view; a superseded entry gets a plain marker, not an ARIA `alert`.
  [`client_reports.html:9`](../../shell/http/templates/client_reports.html#L9)

**Recording which chart a run used**

- `ReportRun` gains a nullable, indexed foreign key to the chart it was generated against.
  [`report_run.py:100`](../../shell/adapters/postgres/report_run.py#L100)

- Set exactly once, inside `drive()`'s existing per-stage success path, the first time `natal_ready` succeeds -- never touched again.
  [`driver.py:830`](../../shell/runner/driver.py#L830)

- `natal_chart_id` becomes a required keyword on `drive()`, threaded uniformly like `generator`/`vocabulary`.
  [`driver.py:627`](../../shell/runner/driver.py#L627)

- `_drive_run` passes the currently-resolved chart's id through to `drive()`.
  [`report_runs.py:144`](../../shell/http/routes/report_runs.py#L144)

**Fixing the deletion-order bug the review caught**

- `StoredNatalChart` deletion moved to run *after* `ReportRun` deletion -- the new FK points the opposite direction from every other table in this cascade, so the old order (charts first) would violate it on any database that enforces foreign keys.
  [`client.py:377`](../../shell/adapters/postgres/client.py#L377)

- An explicit `flush()` between the chart deletes and the Client delete, since nothing here declares an ORM `relationship()` for the session to infer cross-table ordering from on its own.
  [`client.py:394`](../../shell/adapters/postgres/client.py#L394)

**Schema**

- Add-column plus foreign key plus index, forward-only, mirrors this repo's existing migration shape.
  [`0017_report_run_natal_chart.py:37`](../../migrations/versions/0017_report_run_natal_chart.py#L37)

**Tests**

- The regression the review's finding demanded: real SQLite FK enforcement turned on, proving Client deletion survives a referencing `ReportRun`.
  [`test_client_store.py:344`](../../tests/test_client_store.py#L344)

- `natal_chart_id` is set once at `natal_ready` and survives a later regeneration rewind unchanged.
  [`test_runner_driver.py:249`](../../tests/test_runner_driver.py#L249)

- Full I/O & Edge-Case Matrix coverage, plus per-Client scoping.
  [`test_http_clients.py:582`](../../tests/test_http_clients.py#L582)
