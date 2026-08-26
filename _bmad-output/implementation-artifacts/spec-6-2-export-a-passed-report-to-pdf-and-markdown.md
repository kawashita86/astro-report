---
title: 'Export a passed Report to PDF'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'ba85c819b7349b302e008e582decc68cec7b4c03'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A passed Report can only be read on-screen (Story 6.1); Francesco has no way to hand a client a clean, standalone file, and `shell/export.py::export_report()` (Story 5.3) already exists as the structural gate this story's own docstring says is waiting on: "Actual PDF/Markdown rendering is Story 6.2's job."

**Approach:** Add `GET /report-runs/{run_id}/export/pdf`, gated on the same `Report`-row-exists check `view_report` (Story 6.1) already uses. Render the eight Sections (reusing `render_draft`/`SECTION_ORDER`/`LIST_SECTION_NAMES`) plus the Client's name into a new minimal template, convert it to PDF via a new WeasyPrint adapter. The first successful export advances `run.stage` to `exported` once; every export after that only writes a new `ExportRecord` row. `ExportRecord`/its route family are built to also carry a Markdown export later (deferred-work.md), but this spec ships PDF only.

## Boundaries & Constraints

**Always:** Gate on the `Report` row's existence via `report_run_id`, mirroring `view_report`'s 404 (`shell/http/routes/report_runs.py:294-296`) — not on `run.stage`. Reuse `render_draft`/`SECTION_ORDER`/`LIST_SECTION_NAMES`/`deserialize_generated_draft`; never re-derive Section content. The exported PDF contains only the eight Sections and the Client's name — no chart wheel, no Payload, no Gate result, no run identifier, no internal metadata. `ExportRecord` (new table) joins `_CLIENT_CASCADE_TABLES`/`delete_client_and_derived` (`shell/adapters/postgres/client.py`), deleted before `Report` rows since its FK targets `report.id`. New migration is forward-only, mirroring `migrations/versions/0013_gate_result.py`. **`tests/test_export_boundary.py` statically enforces two invariants across all of `core/`+`shell/` — do not violate them:** (1) exactly one function anywhere may have a name starting with `export` — `shell/export.py::export_report` — so name every new function here something else (e.g. `download_report_pdf`, `html_to_pdf`, `store_export_record`); (2) no function taking a `GeneratedDraft`-typed parameter may have "export" anywhere in its name.

**Ask First:** Nothing identified.

**Never:** Do not build the Markdown export route or renderer here — deferred to a follow-up spec (`deferred-work.md`); `ExportRecord.format` still stores whatever string is passed (`"pdf"` today) so that follow-up needs no schema change. Do not add send-disposition or elapsed-time recording — Story 6.3's job; `ExportRecord` here carries only `id`, `client_id`, `report_id`, `format`, `created_at`. Do not touch `core/`. Do not modify `shell/export.py::export_report()`. Do not change `view_report`/`view_report_draft`/`view_report_payload` or their templates beyond adding one link in `report.html`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Anonymous request | No session cookie | `GET /report-runs/{run_id}/export/pdf` | 401 (AuthMiddleware) |
| Gate not yet passed | No `Report` row for `run_id` | — | 404 |
| First export | `Report` exists, `run.stage == "gate_passed"` | 200; PDF downloads; `run.stage` becomes `"exported"`; one `ExportRecord` row written (`format="pdf"`) | N/A |
| Repeat export | `run.stage` already `"exported"` | 200; PDF downloads again; `run.stage` unchanged; one more `ExportRecord` row written | N/A |
| Exported content | Gate passed | Downloaded PDF contains exactly the eight Sections + Client's name, nothing else | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/export_record.py` (new) -- `ExportRecord` model (`id`, `client_id` FK, `report_id` FK to `report.id`, `format: str`, `created_at`) + `store_export_record(session, *, report: Report, format: str)`, mirroring `shell/adapters/postgres/gate_result.py` exactly (immutable via `before_update` listener, `add()`+`flush()` only, never commits).
- `migrations/versions/0015_export_record.py` (new) -- forward-only, `down_revision="0014_bound_client_and_chart_string_columns"`, mirrors `0013_gate_result.py`'s `op.create_table`/index shape.
- `shell/adapters/postgres/client.py` -- add `"export_record"` to `_CLIENT_CASCADE_TABLES` (line 48-58); add a deletion block in `delete_client_and_derived` querying `ExportRecord` by `client_id`, placed before the existing `Report` deletion block (line 346) since `export_record.report_id` FKs to `report.id`.
- `shell/adapters/weasyprint/render.py` (new) -- `html_to_pdf(html: str) -> bytes`, thin wrapper around `weasyprint.HTML(string=html).write_pdf()`. New package dir mirrors `shell/adapters/{gemini,local,nominatim,postgres}`.
- `shell/http/templates/report_export.html` (new) -- minimal HTML for WeasyPrint input: Client name + eight Sections only, no gate/payload/run id -- section loop copied from `report.html`'s (lines 19-32) minus the gate-result block.
- `shell/http/routes/report_runs.py` -- add `download_report_pdf` at `GET /report-runs/{run_id}/export/pdf`, after `view_report` (line 343+). Does `view_report`'s own row lookups (lines 294-318: `Report` by `report_run_id` -> `ReportRun`/latest `ReportDraft`/`ReportPayload`/`Client`, `RuntimeError`-guarded), renders via `render_draft`, renders `report_export.html` to a string via `_templates.get_template(...).render(...)`, calls `html_to_pdf(...)`, then: sets `run.stage = "exported"` only if not already, calls `store_export_record(session, report=stored_report, format="pdf")`, commits, and returns `Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="report-{run_id}.pdf"'})`.
- `shell/http/templates/report.html` -- add an "Export PDF" link next to the existing Payload link (line 16).
- `pyproject.toml` -- add `weasyprint` dependency.
- `tests/test_export_record_store.py` (new) -- mirrors `tests/test_gate_result_store.py`'s shape: persist, immutability, cascade-deletion-on-client-delete.
- `tests/test_client_store.py` -- add `test_the_cascade_constant_includes_export_record`, mirroring `test_the_cascade_constant_includes_gate_result` (line 307).
- `tests/test_http_report_runs.py` -- new tests after Story 6.1's, covering the I/O & Edge-Case Matrix above.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` -- add `weasyprint` dependency -- enables PDF rendering
- [x] `shell/adapters/postgres/export_record.py` -- `ExportRecord` model + `store_export_record()` -- persists one row per export
- [x] `migrations/versions/0015_export_record.py` -- create `export_record` table -- schema for the above
- [x] `shell/adapters/postgres/client.py` -- join `export_record` to the FR-29 cascade -- no orphaned export history after Client deletion
- [x] `shell/adapters/weasyprint/render.py` -- `html_to_pdf()` -- HTML -> PDF bytes
- [x] `shell/http/templates/report_export.html` -- minimal export template -- shared HTML source for the PDF route
- [x] `shell/http/routes/report_runs.py` -- `download_report_pdf` route -- fulfills the story
- [x] `shell/http/templates/report.html` -- export link -- reachable from the Report view
- [x] `tests/test_export_record_store.py`, `tests/test_client_store.py`, `tests/test_http_report_runs.py` -- cover the Matrix and cascade -- proves the boundaries hold

**Acceptance Criteria:**
- Given a Report whose Gate has passed, when Francesco exports it as PDF, then the downloaded file contains only the eight Sections and the Client's name.
- Given a Report exported once already, when Francesco exports it again, then `run.stage` stays `exported` and a new `ExportRecord` row is written rather than the stage advancing again.

## Spec Change Log

## Design Notes

`export_record.report_id` (not `report_run_id`) matches the ERD (`REPORT ||--o{ EXPORT_RECORD`, `ARCHITECTURE-SPINE.md:394`) and keeps one `ExportRecord` tied to exactly the `Report` it came from, consistent with `Report.report_run_id` being unique per run. The route stays in `shell/http/routes/report_runs.py` rather than a new file: it extends the same `report-runs/{run_id}/...` family `view_report`/`view_report_draft`/`view_report_payload` already establish. `ExportRecord.format` is a plain string, not an enum, so the deferred Markdown follow-up needs no migration to add `"markdown"` as a value.

## Verification

**Commands:**
- `uv run pytest tests/test_export_boundary.py tests/test_export_record_store.py tests/test_client_store.py tests/test_http_report_runs.py -q` -- expected: all pass, including the pre-existing static-scan invariants
- `uv run mypy shell/adapters/weasyprint/render.py shell/http/routes/report_runs.py` -- expected: no new errors
- `uv run alembic upgrade head` against a local Postgres -- expected: `0015_export_record` applies cleanly

## Suggested Review Order

**The export route**

- Entry point: gated on the `Report` row's mere existence, mirroring `view_report`'s own boundary rather than checking `run.stage`.
  [`report_runs.py:348`](../../shell/http/routes/report_runs.py#L348)

- HTML assembled from `report_export.html` and handed to `html_to_pdf`, then `run.stage` advances to `"exported"` only once and an `ExportRecord` is written on every call.
  [`report_runs.py:191`](../../shell/http/routes/report_runs.py#L191)

**Persisting the export**

- `ExportRecord` model: `format` bounded to 16 chars (mirrors deferred-work-41's fix elsewhere), `report_id` FKs to `report.id` per the ERD, not `report_run_id`.
  [`export_record.py:33`](../../shell/adapters/postgres/export_record.py#L33)

- `store_export_record()`: add+flush only, never commits, mirrors `store_gate_result()`.
  [`export_record.py:73`](../../shell/adapters/postgres/export_record.py#L73)

- Migration creates `export_record` with the same bounded column, non-unique index on `report_id`.
  [`0015_export_record.py:35`](../../migrations/versions/0015_export_record.py#L35)

**Cascade wiring**

- `export_record` joins `_CLIENT_CASCADE_TABLES`, the single source of truth the invariant test checks against.
  [`client.py:58`](../../shell/adapters/postgres/client.py#L58)

- Deleted before `Report` rows specifically, since `export_record.report_id` is itself a foreign key to `report.id`.
  [`client.py:352`](../../shell/adapters/postgres/client.py#L352)

**PDF rendering boundary**

- `html_to_pdf()`: the one place HTML becomes PDF bytes -- no template or Section knowledge lives here.
  [`render.py:19`](../../shell/adapters/weasyprint/render.py#L19)

- `report_export.html`: Client name + eight Sections only -- no chart wheel, no Payload, no Gate result, no run identifier.
  [`report_export.html:1`](../../shell/http/templates/report_export.html#L1)

- "Export PDF" surfaced from the Report view, next to the existing Payload link.
  [`report.html:17`](../../shell/http/templates/report.html#L17)

**Tests**

- First export: PDF downloads, `run.stage` advances, exactly one `ExportRecord` is written.
  [`test_http_report_runs.py:1451`](../../tests/test_http_report_runs.py#L1451)

- Content-exactness: proves the assembled HTML carries only the Client's name and the eight Sections, nothing else.
  [`test_http_report_runs.py:1529`](../../tests/test_http_report_runs.py#L1529)

- Data-integrity guards: each of `ReportRun`/`ReportDraft`/`ReportPayload`/`Client` missing after a `Report` exists raises rather than 404s.
  [`test_http_report_runs.py:1602`](../../tests/test_http_report_runs.py#L1602)
