---
title: 'Record how the Report went out, in one interaction'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '31744ea3f8a0cf1b1cdf2a3e01017751b865a747'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 6.2's `ExportRecord` has no way to capture whether a Report was actually sent as generated or edited first, and no elapsed-time figure — both named explicitly as this story's job in 6.2's own Design Notes, and both feed the epic's unedited-send-rate and per-Report time-budget success metrics.

**Approach:** `elapsed_seconds` (`ExportRecord.created_at` minus `ReportRun.created_at`, i.e. Client selection to export) is computable the moment an export happens, so `download_report_pdf` stores it directly. `disposition` can only be known after Francesco actually sends the Report, so a new `POST /report-runs/{run_id}/export/disposition` route sets it later, in one click, on the run's latest `ExportRecord`. Two one-click forms on `report.html` — "Sent as generated" / "Sent, edited first" — appear once an export exists and disappear (replaced by the recorded choice) once disposition is set.

## Boundaries & Constraints

**Always:** `elapsed_seconds` is computed and stored at export time (`download_report_pdf`), never estimated later. `disposition` starts `NULL` and is set through a Core-level `UPDATE ... WHERE disposition IS NULL` (`sqlmodel.update`), never through the ORM object — `ExportRecord`'s existing `before_update` listener (`shell/adapters/postgres/export_record.py`) unconditionally forbids ORM-driven mutation and stays untouched; the `WHERE disposition IS NULL` clause makes "set exactly once" atomic and makes re-recording a no-op (zero rows affected) rather than an error. The disposition route acts on the **latest** `ExportRecord` for the run (by `created_at` descending), found via `Report.report_run_id == run_id` -> `ExportRecord.report_id`. `view_report`/`report.html` may now be extended (6.2's "stay untouched beyond one link" was 6.2's own constraint on itself, not a permanent one). New migration column additions only (`nullable=True`, no backfill — existing rows simply have no recorded value).

**Ask First:** Nothing identified.

**Never:** Do not touch `core/`. Do not relax or modify `ExportRecord`'s `before_update` listener. Do not add a third disposition value or free-text field — exactly two: `"as_generated"` / `"edited"`. Do not change `download_report_pdf`'s PDF-content behavior, `view_report_draft`, or `view_report_payload`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Export happens | `download_report_pdf` succeeds | New `ExportRecord` has `elapsed_seconds = (created_at - run.created_at)` in whole seconds, `disposition = NULL` | N/A |
| Recording, no prior export | No `ExportRecord` exists for the run's `Report` | — | 404 |
| Recording, first time | Latest `ExportRecord.disposition IS NULL` | Redirect to `/report-runs/{run_id}/report`; that `ExportRecord.disposition` now set | N/A |
| Recording, already set | Latest `ExportRecord.disposition` already non-`NULL` | Redirect to `/report-runs/{run_id}/report`, unchanged (idempotent, zero rows updated) | N/A |
| Report view, no export yet | No `ExportRecord` for the run | Neither the disposition buttons nor a recorded-disposition line render | N/A |
| Report view, disposition pending | Latest `ExportRecord.disposition IS NULL` | Both one-click forms render | N/A |
| Report view, disposition recorded | Latest `ExportRecord.disposition` set | Recorded choice shown as text, no buttons | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/export_record.py` -- add `elapsed_seconds: int | None` and `disposition: str | None = Field(default=None, max_length=16)` to `ExportRecord` (line 33-58); extend `store_export_record(session, *, report, format, elapsed_seconds)` to accept and set `elapsed_seconds`; add `record_send_disposition(session, *, run_id: UUID, disposition: str) -> bool` using `sqlmodel.update(ExportRecord).where(ExportRecord.id == <latest id>, ExportRecord.disposition.is_(None)).values(disposition=disposition)` -- returns whether a row was actually updated (for the 404-vs-no-op distinction). Name avoids the `export`-prefix boundary (`tests/test_export_boundary.py`).
- `migrations/versions/0016_export_record_disposition.py` (new) -- forward-only, `down_revision="0015_export_record"`, two `op.add_column` calls (both nullable, no `server_default`), mirrors `migrations/versions/0012_bounded_regeneration.py`'s add-column shape.
- `shell/http/routes/report_runs.py` -- `download_report_pdf` (line 349+): compute `elapsed_seconds = int((datetime.now(UTC) - run.created_at).total_seconds())` before calling `store_export_record(...)`, pass it through. Add `record_send_disposition` route at `POST /report-runs/{run_id}/export/disposition`, `disposition: str = Form(...)` validated against `{"as_generated", "edited"}` (422 otherwise), calling the new adapter function; 404 if it returns "no such run/Report"; redirect `303` to `/report-runs/{run_id}/report` on success or no-op. `view_report` (line 267+): also look up the run's latest `ExportRecord` (same `Report` row it already has), pass `latest_export`/`disposition_choices` into the template context.
- `shell/http/templates/report.html` -- after the existing "Export PDF" link (line 17): `{% if latest_export %}` block -- if `latest_export.disposition` is `None`, render the two one-click forms (mirrors `client_delete.html`'s hidden-input-plus-submit-button shape); else render the recorded choice as text.
- `tests/test_export_record_store.py` -- extend for `elapsed_seconds`/`disposition` columns, `store_export_record`'s new parameter, and `record_send_disposition`'s set-once/no-op/missing-row behavior.
- `tests/test_http_report_runs.py` -- new tests after Story 6.2's, covering the I/O & Edge-Case Matrix above.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/export_record.py` -- add columns, extend `store_export_record`, add `record_send_disposition` -- persists both new facts
- [x] `migrations/versions/0016_export_record_disposition.py` -- add the two columns -- schema for the above
- [x] `shell/http/routes/report_runs.py` -- compute+store `elapsed_seconds`; add the disposition route; extend `view_report`'s context -- fulfills the story
- [x] `shell/http/templates/report.html` -- disposition UI -- one-click recording, visible confirmation once set
- [x] `tests/test_export_record_store.py`, `tests/test_http_report_runs.py` -- cover the Matrix -- proves the boundaries hold

**Acceptance Criteria:**
- Given a Report Francesco has just exported, when he wants to record how it went out, then one click ("Sent as generated" or "Sent, edited first") is all that's required.
- Given a disposition already recorded for the latest export, when the Report view is reopened, then the recorded choice is shown and cannot be silently overwritten by a second click.
- Given an export, when its `ExportRecord` is inspected, then `elapsed_seconds` reflects the time from that run's `created_at` (Client selection) to the export.

## Spec Change Log

## Design Notes

`disposition` is set via a Core-level `UPDATE` (`session.exec(update(ExportRecord)...)`), not by loading the ORM object and mutating it -- SQLAlchemy's mapper-level `before_update` event (which `ExportRecord`'s immutability guard relies on) only fires for ORM unit-of-work flushes, not Core `update()` statements, so this is the one deliberate, narrow bypass rather than a change to the guard itself. The `WHERE disposition IS NULL` clause is what makes "exactly once" hold even under a double-click: the second request's `UPDATE` matches zero rows.

## Verification

**Commands:**
- `uv run pytest tests/test_export_boundary.py tests/test_export_record_store.py tests/test_http_report_runs.py -q` -- expected: all pass, including the pre-existing static-scan invariants
- `uv run ruff check .` -- expected: clean
- `uv run alembic upgrade head` against a local Postgres -- expected: `0016_export_record_disposition` applies cleanly

## Suggested Review Order

**Recording disposition, in one click**

- Entry point: validates the closed two-value set, 404s before the latest `ExportRecord` is missing, otherwise records and redirects -- idempotent on a second call.
  [`report_runs.py:478`](../../shell/http/routes/report_runs.py#L478)

- The Core-level `UPDATE ... WHERE disposition IS NULL`: the one deliberate bypass of `ExportRecord`'s ORM immutability guard, atomic "set exactly once".
  [`export_record.py:122`](../../shell/adapters/postgres/export_record.py#L122)

**Capturing elapsed time at export**

- Computed from `run.created_at` (Client selection) to now, at the moment of export -- never estimated later.
  [`report_runs.py:464`](../../shell/http/routes/report_runs.py#L464)

- `store_export_record()` extended to require and persist it, alongside the existing `format`.
  [`export_record.py:98`](../../shell/adapters/postgres/export_record.py#L98)

**Data model**

- `ExportRecord` gains two nullable columns; `disposition` bounded to 16 chars, `elapsed_seconds` a plain int -- both `None` for rows written before this story.
  [`export_record.py:45`](../../shell/adapters/postgres/export_record.py#L45)

- Migration: add-column only, no backfill, mirrors `0012_bounded_regeneration.py`'s own shape.
  [`0016_export_record_disposition.py:37`](../../migrations/versions/0016_export_record_disposition.py#L37)

**Finding the latest export**

- Shared by `view_report` (UI) and the disposition route (404 gate) -- `created_at` descending with an `id` tiebreaker for deterministic ordering under same-timestamp collisions.
  [`report_runs.py:91`](../../shell/http/routes/report_runs.py#L91)

- `view_report`'s context now also carries `latest_export`/`disposition_choices`.
  [`report_runs.py:382`](../../shell/http/routes/report_runs.py#L382)

**The disposition UI**

- Two one-click forms while pending, the recorded choice as text once set -- mirrors `client_delete.html`'s hidden-input-plus-submit-button shape.
  [`report.html:19`](../../shell/http/templates/report.html#L19)

**Tests**

- Elapsed time reflects Client-selection-to-export, in whole seconds.
  [`test_http_report_runs.py:1708`](../../tests/test_http_report_runs.py#L1708)

- Error-path precedence: an invalid value 422s even against a never-exported run, never a 404.
  [`test_http_report_runs.py:1794`](../../tests/test_http_report_runs.py#L1794)

- First-time recording: redirects, sets the choice, matches the I/O Matrix.
  [`test_http_report_runs.py:1828`](../../tests/test_http_report_runs.py#L1828)
