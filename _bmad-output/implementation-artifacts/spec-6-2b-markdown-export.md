---
title: 'Export a passed Report to Markdown'
type: 'feature'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/spec-6-2-export-a-passed-report-to-pdf-and-markdown.md'
  - '_bmad-output/implementation-artifacts/epic-6-context.md'
  - '_bmad-output/implementation-artifacts/epic-6-retro-2026-08-27.md'
baseline_commit: '452c5275fe94fc35562a6ab5914ce0400337ce97'
origin: 'epic-6 retrospective, action item 47 — the "Both PDF and Markdown" requirement was kept, not descoped; this is the scheduled follow-up.'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `epic-6-context.md` requires "Both PDF and Markdown must be produced" for a
passed Report. Story 6.2 shipped PDF only and explicitly deferred the Markdown route to a
follow-up spec (`spec-6-2-*.md` Boundaries → "Never"; `deferred-work.md:525`). Francesco has
no plain-text artifact to hand a client or paste into email/messaging without the PDF
round-trip.

**Approach:** Add `GET /report-runs/{run_id}/export/markdown`, structurally identical to
`download_report_pdf` (`shell/http/routes/report_runs.py:435`): the same
`_load_passed_report_bundle(session, run_id)` gate, the same eight-Sections-plus-Client-name
content model, the same first-export-advances-`run.stage` / every-export-writes-an-`ExportRecord`
semantics. The only differences are the body serializer (Markdown instead of
`html_to_pdf`) and `ExportRecord.format == "markdown"`. `ExportRecord.format` already stores
an arbitrary string, so **no schema change and no migration** are needed.

## Boundaries & Constraints

**Always:**
- Gate on the `Report` row's existence via `_load_passed_report_bundle` — the same 404
  surface `download_report_pdf` uses, never on `run.stage`.
- Reuse `render_draft` / `SECTION_ORDER` / `LIST_SECTION_NAMES` to obtain Section content;
  never re-derive it. The Markdown renderer consumes the same `bundle.rendered` structure the
  PDF template does.
- The Markdown body contains only the eight Sections (in `SECTION_ORDER`) and the Client's
  name — no chart wheel, no Payload, no Gate result, no run identifier, no internal metadata.
- First successful export advances `bundle.run.stage` to `"exported"` exactly once; every
  export (first or repeat) writes one `ExportRecord` via `store_export_record(session,
  report=bundle.report, format="markdown", elapsed_seconds=…)`.
- Response: `media_type="text/markdown; charset=utf-8"`, `Content-Disposition: attachment;
  filename="report-{run_id}.md"`.
- `tests/test_export_boundary.py` statically forbids any new function whose name starts with
  `export` and any `export`-named function taking a `GeneratedDraft` parameter. Name the new
  symbols accordingly — e.g. `download_report_markdown` (route handler) and
  `render_report_markdown` (serializer, in a new `shell/http/report_markdown.py` or alongside
  `render_draft`).

**Ask First:**
- Whether the Markdown section headings should use the same shared `snake_case → Italian-title`
  map introduced by retro item 50 (`report_export.html` headings). Default assumption: **yes**,
  reuse it — build item 50 first or in the same change, and this spec consumes it.
- Whether list Sections (`LIST_SECTION_NAMES`) render as Markdown bullet lists vs. the PDF's
  layout. Default assumption: one `-` bullet per day-list entry, date-prefixed, mirroring
  `report_export.html`.

**Never:**
- No change to `shell/export.py::export_report()` or its one-export-function invariant.
- No change to `download_report_pdf`, `view_report`, `view_report_draft`,
  `view_report_payload`, or their templates beyond adding one "Download Markdown" link next to
  the existing PDF link.
- No `core/` changes. No new migration. No `ExportRecord` schema change.
- No send-disposition or elapsed-time UI changes — Story 6.3 owns that; this route only
  populates `ExportRecord.elapsed_seconds` the same way the PDF route does.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior |
|----------|--------------|---------------------------|
| Passed Report exists | `run_id` with a `Report` row | 200, `text/markdown` body, attachment filename `report-{run_id}.md`; `ExportRecord(format="markdown")` written; `run.stage` → `exported` if not already |
| No such `ReportRun` | unknown `run_id` | 404 (same as `download_report_pdf`) |
| `ReportRun` exists, Gate not passed / no `Report` row | `run_id` mid-run | 404 (same structural gate) |
| Repeat export | second+ call for same `run_id` | 200; new `ExportRecord` row; `run.stage` left at `exported` |
| Downstream rows missing after `Report` exists | `ReportDraft`/`ReportPayload`/`Client` absent | `RuntimeError` (data-integrity bug), never a 404 — mirrors `_load_passed_report_bundle` |
| Incidental GET (prefetch/crawl) | bot hits the URL | Accepted deviation, same as `download_report_pdf` (retro item 49): a harmless extra `ExportRecord`, monotonic `stage` advance |
| Section prose contains Markdown metacharacters | `*`, `_`, `#`, `` ` `` in generated text | Rendered as-is (client-facing prose, not a code context); no escaping unless review finds a concrete rendering break |

## Code Map

- `shell/http/routes/report_runs.py` — new `download_report_markdown` handler, sibling of
  `download_report_pdf`; `@router.get("/report-runs/{run_id}/export/markdown",
  include_in_schema=False)`.
- `shell/http/report_markdown.py` *(new)* — `render_report_markdown(rendered, *, client_name,
  section_order, list_section_names) -> str`. Pure string assembly; no I/O.
- `shell/http/templates/report.html` — one added link, next to the existing PDF export link.
- `tests/test_http_export_markdown.py` *(new)* — mirrors `tests/test_http_export_pdf.py`'s
  cases (gate, content, first-vs-repeat `ExportRecord`, `stage` advance, 404s).
- No change to `shell/adapters/postgres/export_record.py`, `shell/export.py`, any migration.

## Tasks & Acceptance

1. `render_report_markdown` produces the eight Sections in `SECTION_ORDER` with headings and
   the Client's name, list Sections as bullet lists. Unit-tested against a
   `freeze_payload()`-derived `render_draft` output, not hand-built fixtures.
2. `download_report_markdown` wired with the `_load_passed_report_bundle` gate, `ExportRecord`
   write, and one-time `stage` advance. HTTP-tested for all matrix rows.
3. `report.html` shows a "Download Markdown" link alongside "Download PDF" for a passed Report.
4. `tests/test_export_boundary.py` still passes unchanged (no `export`-prefixed new symbol).
5. Full suite green; `ruff check` clean.

**Acceptance:** a passed Report downloads as a `.md` file containing exactly its eight Sections
and the Client's name; a second download writes a second `ExportRecord(format="markdown")` and
does not re-advance `run.stage`; a non-passed run 404s.

## Design Notes

- This is deliberately a thin sibling of the PDF route. If review finds the two handlers are
  >80% identical, extract a shared `_finalize_export(session, bundle, *, format, body,
  media_type, filename)` helper rather than duplicating the `ExportRecord` + `stage` block a
  third time (it is already duplicated once between the PDF route and this one — the same
  duplication class as retro item 51).
- `ExportRecord.format` is a free string today; if a third format is ever added, consider a
  CHECK constraint or enum then, not now.

## Suggested Review Order

1. `render_report_markdown` + its unit test — is the content model exactly the PDF's?
2. `download_report_markdown` — does it share the PDF route's gate and side-effect semantics
   precisely?
3. `test_export_boundary.py` — confirm no invariant regression.
4. The `report.html` link.

</frozen-after-approval>
