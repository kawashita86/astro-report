---
title: '10.1 A PDF in seconds, and instantly the second time'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: 'b607bc7554f002446eddc797388fd9cc53c1555b'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `report_export.html` nests prose in ~20 flex/grid containers; WeasyPrint re-measures every word, so a PDF takes 3.5 s locally and 20–25 s in production, and every repeat download pays it again.

**Approach:** Move the prose cards to block layout (≈1.0 s locally) and store each exported PDF keyed by a fingerprint of everything it depends on, so an unchanged repeat download serves stored bytes with no WeasyPrint call.

## Boundaries & Constraints

**Always:** Migration is forward-only (`downgrade()` raises, per the existing revisions and `tests/test_forward_only_migrations.py`). `ExportRecord` and `run.stage` are written on every download, hit or miss. The DB connection is released (`session.rollback()`) before any render. Every module opens with a why-docstring; every function fully type-hinted. Visual result stays faithful to `mockups/key-pdf-export.html`.

**Ask First:** Any visible change to page breaks, fonts, colours or copy beyond what block layout forces.

**Never:** Edit `data/ephemeris/*`. Add an env var. Touch `html_to_pdf`'s signature. Add `exported_pdf` to `_BACKUP_MODELS` (derived cache, rebuilt on demand). Put the fingerprint or PDF bytes in any template/log.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First download | No `exported_pdf` row | Render, store row, return PDF | Store failure (e.g. race on unique `report_id`) never fails the download |
| Repeat download | Row fingerprint matches | Stored bytes returned; `html_to_pdf` not called; new `ExportRecord` written | N/A |
| Section hand-corrected | Draft text changed | Fingerprint differs → re-render, row replaced | N/A |
| Client/birth/chart/template change | Any hashed input differs | Miss → re-render, row replaced | N/A |
| Client deleted | Report has `exported_pdf` row | Row deleted before `report` rows; no FK error | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/templates/report_export.html` -- 593 lines, 47 flex/grid hits in `<style>` (l.24–416): `.header-row`, `.positions-wheel-row` (grid 210px/1fr), `.day-lists-row` (grid 2-col), `.timeline-item`, and the card containers (`.icon-card`, `.domain-card`, `.day-list-card`, `.final-advice-card`, `.wheel-card`, `.birth-data-card`, `.positions-card` all `display:flex; flex-direction:column; gap`) → block + margins/floats/`display: table`. Keep flex only on `.data-row`, `.placement-row`, `*-header` (icon + heading).
- `shell/http/routes/report_runs.py:1471` `download_report_pdf` -- builds wheel (`_build_wheel_svg`), `build_export_context`, renders, `session.rollback()`, `html_to_pdf`, then stage/`ExportRecord`/commit. Add cache lookup before wheel build and store after.
- `shell/http/report_export_view.py:252` `build_export_context` -- inputs to the fingerprint (client name, birth date/time/place, `rendered` draft text).
- `shell/adapters/postgres/export_record.py` -- model/store style to mirror (`_UTCDateTime`, uuid7 id, FK to `report.id`).
- `shell/adapters/postgres/client.py:53,425-470` -- `_CLIENT_CASCADE_TABLES` (only tables with a `client_id` FK; `exported_pdf` has none, so it is NOT added) and `delete_client_and_derived`: delete `ExportedPdf` for the client's reports before `Report` rows.
- `migrations/versions/0023_gate_violation_review.py` -- migration style; next is `0024_…`, `down_revision = "0023_gate_violation_review"`.
- `tests/test_migration_chain_on_postgres.py`, `tests/test_forward_only_migrations.py`, `tests/_fk.py` (use `fk_enforcing_session()` for the cascade test), `tests/test_export_record_store.py` (pattern), `tests/test_http_report_runs.py` (route tests).
- `shell/adapters/weasyprint/render.py` -- `html_to_pdf` unchanged.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/templates/report_export.html` -- replace flex/grid on prose cards and the two row layouts with block/float/`display: table` -- removes WeasyPrint flex re-measurement
- [x] `shell/adapters/postgres/exported_pdf.py` -- `ExportedPdf` model (`id`, `report_id` FK unique, `fingerprint` str(64), `pdf_bytes` LargeBinary, `created_at`), `export_fingerprint(...)`, `get_stored_pdf(session, report_id, fingerprint)`, `store_pdf(...)` (replace-by-report_id inside `begin_nested()`, swallow `IntegrityError`) -- the cache
- [x] `migrations/versions/0024_exported_pdf.py` -- create table + unique index on `report_id`; forward-only
- [x] `shell/adapters/postgres/client.py` -- delete `ExportedPdf` rows before reports in `delete_client_and_derived`; import the model so `metadata` knows it
- [x] `shell/http/routes/report_runs.py` -- fingerprint = sha256 over canonical JSON of {`rendered`, client name + birth date/time/place, run chart id, template file hash, natal orbs}; hit skips wheel build and WeasyPrint; miss renders then stores in the post-render transaction
- [x] `tests/test_pdf_render_perf.py` -- realistic-length fixture + real wheel; `html_to_pdf` ≤ 1.2 s (best of 3 after one warm-up)
- [x] `tests/test_exported_pdf_store.py` + route tests in `tests/test_http_report_runs.py` -- hit/miss/hand-correct/ExportRecord-on-hit/stage; FK-enforcing cascade delete; fingerprint changes per hashed input
- [x] `tests/test_migration_chain_on_postgres.py` -- cover `exported_pdf`; run with `MIGRATION_TEST_DATABASE_URL` against throwaway Postgres

**Acceptance Criteria:**
- Given the redesigned template, when rendered with the realistic fixture, then no prose card, day list or Consiglio finale container uses flex/grid, and the PDF visually matches `mockups/key-pdf-export.html` (rasterize and inspect all three pages).
- Given a downloaded PDF, when the same report is downloaded again unchanged, then bytes are identical, `html_to_pdf` is not called, and a second `ExportRecord` exists.
- Given a Section hand-correction, when downloaded, then a fresh render is stored.

## Spec Change Log

## Design Notes

Fingerprint deliberately excludes the wheel SVG so a hit costs no Kerykeion work; the wheel is a pure function of the chart id (in the hash) and natal orbs (also hashed). One row per report (replace on miss) keeps storage bounded: ~100–300 KB × reports. The cache is derivable, hence excluded from backup/restore.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `MIGRATION_TEST_DATABASE_URL=<throwaway> uv run pytest tests/test_migration_chain_on_postgres.py` -- expected: pass
- `uv run ruff check . && uv run mypy .` (whichever CI runs in `.github/workflows/ci.yml`) -- expected: clean

**Manual checks (if no CLI):**
- Rasterize a real report's PDF (pdftoppm) and compare each page to the mockup; second download is visibly instant.

## Suggested Review Order

**The cache (design entry point)**

- Route checks the fingerprint first; a hit skips wheel build and WeasyPrint.
  [`report_runs.py:1553`](../../shell/http/routes/report_runs.py#L1553)

- Fingerprint hashes every input the PDF depends on, excluding the derived wheel.
  [`exported_pdf.py:54`](../../shell/adapters/postgres/exported_pdf.py#L54)

- Best-effort store inside a savepoint; a race never fails the download.
  [`exported_pdf.py:101`](../../shell/adapters/postgres/exported_pdf.py#L101)

- Miss path stores after render, in the same transaction as `ExportRecord`.
  [`report_runs.py:1581`](../../shell/http/routes/report_runs.py#L1581)

**Schema and cascade**

- One row per report, unique on `report_id`; forward-only.
  [`0024_exported_pdf.py:27`](../../migrations/versions/0024_exported_pdf.py#L27)

- Rows deleted before `Report` on client deletion; no `client_id` so not in the constant.
  [`client.py:449`](../../shell/adapters/postgres/client.py#L449)

**Block layout**

- Flex/grid replaced by floats and `display: table` on prose cards.
  [`report_export.html:168`](../../shell/http/templates/report_export.html#L168)

**Tests**

- Perf budget (≤1.2 s) and flex/grid guard with negative test.
  [`test_pdf_render_perf.py:110`](../../tests/test_pdf_render_perf.py#L110)

- Store, fingerprint sensitivity and FK-enforcing cascade.
  [`test_exported_pdf_store.py`](../../tests/test_exported_pdf_store.py)
