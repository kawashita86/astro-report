---
title: 'Be told when my backup is out of date'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '00989852796f4be5738334d03ddad89407f5ef27'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `/backup` route (Story 6.5) is a manual, easy-to-forget action. Nothing today tells Francesco that new Reports exist that his last backup does not cover, so the durability gap this route exists to close can reopen silently.

**Approach:** Record a timestamp every time `/backup` completes. On the Report History page (Story 6.4's `client_reports.html` — chosen as the one page Francesco returns to repeatedly during a batch, since this app has no shared layout or home page today), show a warning whenever the newest `Report` across the whole system is younger than the last recorded backup.

## Boundaries & Constraints

**Always:** A new append-only `backup_record` table (id, `created_at`), mirroring `StyleGuide`'s global/versionless shape (`shell/adapters/postgres/style_guide.py`) — no `client_id`, so it is correctly excluded from the FR-29 cascade automatically. `download_backup` (`shell/http/routes/backup.py`) inserts one row and commits, only after the export body is already built, right before returning the `Response`. `list_client_reports` (`shell/http/routes/clients.py`) computes staleness globally — the newest `Report.created_at` across every Client, not just the one being viewed — against the latest `backup_record.created_at`, and passes a single `backup_stale: bool` into the template. No Reports yet anywhere -> never stale. No `backup_record` row yet and at least one `Report` exists -> stale.

**Ask First:** Nothing identified — the warning's placement (Report History page only) was already resolved with the human this session.

**Never:** Do not add a shared base template, home page, or touch any other template. Do not add `backup_record` to `download_backup`'s own exported table set — the failure mode of a restored database with no `backup_record` row is "shows stale until the next backup," which is the safe default, not a gap worth extra scope. Do not touch `core/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Never backed up | >=1 `Report` exists, `backup_record` empty | `list_client_reports` renders with `backup_stale=True` | N/A |
| Fresh backup | Newest `backup_record.created_at` > newest `Report.created_at` | `backup_stale=False` | N/A |
| New Report after last backup | Newest `Report.created_at` > newest `backup_record.created_at` | `backup_stale=True` | N/A |
| No Reports anywhere yet | `report` table empty | `backup_stale=False` | N/A |
| Backup taken | `GET /backup` completes | One new `backup_record` row committed, `created_at = now()` | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/backup_record.py` (new) -- `BackupRecord` model (`id`, `created_at`, `_UTCDateTime` from `shell/adapters/postgres/report_run.py`) + `store_backup_record(session) -> BackupRecord` (add+flush, mirrors `store_export_record`) + `latest_backup_record(session) -> BackupRecord | None` (`order_by(created_at.desc()).first()`, mirrors `current_style_guide`, `shell/adapters/postgres/style_guide.py:82`).
- `shell/http/routes/backup.py:75` `download_backup` -- after building `backup` dict, call `store_backup_record(session)` then `session.commit()`, before constructing the `Response`.
- `shell/http/routes/clients.py:617` `list_client_reports` -- add a module-level helper `_backup_is_stale(session) -> bool`: `select(Report.created_at).order_by(Report.created_at.desc()).limit(1)`.first() vs `latest_backup_record(session)`; pass `"backup_stale": _backup_is_stale(session)` into the existing template context dict (line 670).
- `shell/http/templates/client_reports.html` -- inside `<main>`, above the `{% if entries %}` block: `{% if backup_stale %}<p class="warning">Backup out of date — new Reports exist since the last backup.</p>{% endif %}`.
- `migrations/versions/0018_backup_record.py` (new) -- `create_table("backup_record", id UUID PK, created_at TIMESTAMPTZ NOT NULL)`, `down_revision = "0017_report_run_natal_chart"`, forward-only `downgrade()` mirroring `0015_export_record.py`.
- `tests/test_http_backup.py` -- extend to assert a `backup_record` row is committed after `GET /backup`.
- `tests/test_http_clients.py` -- new cases covering the I/O matrix's `backup_stale` scenarios on `list_client_reports`.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0018_backup_record.py` -- new -- creates the table
- [x] `shell/adapters/postgres/backup_record.py` -- new -- model + store/read functions
- [x] `shell/http/routes/backup.py` -- record a backup on every completed download
- [x] `shell/http/routes/clients.py` -- compute and pass `backup_stale` in `list_client_reports`
- [x] `shell/http/templates/client_reports.html` -- render the warning
- [x] `tests/test_http_backup.py`, `tests/test_http_clients.py` -- cover the I/O matrix

**Acceptance Criteria:**
- Given a newest Report that postdates the last recorded backup, when Francesco opens any Client's Report History, then a warning is displayed.
- Given a fresh backup, when it completes, then the next Report History view shows no warning.
- Given the last-backup timestamp, when it is stored, then it lives in `backup_record` in Postgres, not on the container filesystem.

## Design Notes

Staleness is computed fresh on every `list_client_reports` request (two small `ORDER BY ... LIMIT 1` reads) rather than cached — this app has no request volume where that matters, and it keeps the warning always correct with no invalidation logic.

## Verification

**Commands:**
- `uv run pytest tests/test_http_backup.py tests/test_http_clients.py tests/test_migration_chain.py -q` -- expected: all pass
- `uv run ruff check .` -- expected: clean

## Suggested Review Order

**Recording a backup**

- `BackupRecord`'s model and its two functions — the single source of truth every other stop checks against.
  [`backup_record.py:34`](../../shell/adapters/postgres/backup_record.py#L34)

- `download_backup` records the backup only after the export body is already built, right before the response returns.
  [`backup.py:102`](../../shell/http/routes/backup.py#L102)

- The migration creating `backup_record`, chained after `0017_report_run_natal_chart`.
  [`0018_backup_record.py:34`](../../migrations/versions/0018_backup_record.py#L34)

**Computing and showing staleness**

- `_backup_is_stale` — the newest `Report` globally vs. the latest `backup_record`, and its two "no data yet" edge cases.
  [`clients.py:618`](../../shell/http/routes/clients.py#L618)

- `backup_stale` wired into `list_client_reports`'s existing template context.
  [`clients.py:705`](../../shell/http/routes/clients.py#L705)

- The warning itself: an alert role for accessibility, plus a direct link back to `/backup` so Francesco can act on it immediately.
  [`client_reports.html:13`](../../shell/http/templates/client_reports.html#L13)

**Review-driven completeness guards**

- A `backup_record` row is confirmed unaffected by the FR-29 Client-deletion cascade, not merely asserted to be by omission.
  [`test_client_store.py:328`](../../tests/test_client_store.py#L328)

- `store_backup_record`/`latest_backup_record` exercised directly, not only indirectly through the HTTP route tests.
  [`test_backup_record_store.py:35`](../../tests/test_backup_record_store.py#L35)

**Story's own I/O & Edge-Case Matrix**

- Never backed up, a fresh backup, a new Report after the last backup, no Reports anywhere, and staleness computed globally rather than per-Client.
  [`test_http_clients.py:711`](../../tests/test_http_clients.py#L711)

- One `backup_record` row per completed download, and its deliberate absence from the export body itself.
  [`test_http_backup.py:471`](../../tests/test_http_backup.py#L471)
