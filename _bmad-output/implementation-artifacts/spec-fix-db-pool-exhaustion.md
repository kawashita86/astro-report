---
title: 'Stop DB connection-pool exhaustion on the PDF export and engine'
type: 'bugfix'
created: '2026-10-01'
status: 'done'
baseline_commit: '33e4eb0e6e882e6f74fb6eee35e63914099d8d23'
review_loop_iteration: 1
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** On the Coolify instance (one uvicorn worker, `background` run mode) a PDF download hung and every request plus every scheduler tick failed with `QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00`. `download_report_pdf` keeps its request session's connection checked out for the whole CPU-heavy WeasyPrint render, and the engine has no connect, statement or recycle limits, so a stalled or silently dead Postgres connection holds its pool slot forever.

**Approach:** Release the PDF route's connection before `html_to_pdf` runs and do the post-render `ExportRecord` write in a fresh short transaction; give the engine a connect timeout, TCP keepalives, a server-side `statement_timeout` and `pool_recycle`, so no checkout can hang indefinitely.

## Boundaries & Constraints

**Always:** Keep the route's existing semantics (404 gate, first export advances `run.stage` to `exported` once, one `ExportRecord` per export, written only after a successful render). Timeout values are code constants in `shell/http/app.py` — operational tuning, not env vars — so `shell/config.py` and `Settings` are unchanged. Full type hints; existing docstring style.

**Ask First:** Any `idle_in_transaction_session_timeout` (the `draft_ready` stage legitimately holds a transaction across the Gemini call); changing pool size or worker count; touching the scheduler.

**Never:** No migration. No change to `download_report_markdown` (its render is in-memory string formatting, holds the connection for microseconds). No change to `get_session` or the dependency-override test pattern.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Render holds no connection | Passed report, GET `/export/pdf` | While `html_to_pdf` runs the request session is not in a transaction (no connection checked out); response 200 PDF | N/A |
| First export after release | Run at `gate_passed` | `run.stage` becomes `exported`, one `ExportRecord` row | N/A |
| Render fails | `html_to_pdf` raises | No `ExportRecord`, `run.stage` unchanged | Exception propagates (500) as today |
| Engine construction | `create_app(settings)` | `create_engine` receives `pool_pre_ping=True`, `pool_recycle`, and `connect_args` with `connect_timeout` and keepalives; a pool `connect` event runs `SET statement_timeout` on every new connection (never the `options` startup parameter, which PgBouncer-style poolers refuse) | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py:1471-1550` -- `download_report_pdf`: loads bundle + chart, builds `export_html`, then `html_to_pdf(...)` at ~1528, then stage/`store_export_record`/`commit`. Insert `session.rollback()` between building `export_html` and `html_to_pdf`. After rollback `bundle.run`/`bundle.report` stay attached but expired; the post-render code reloads them lazily in a new short transaction — no other edit needed.
- `shell/http/app.py:158` -- `create_engine(settings.sqlalchemy_url, pool_pre_ping=True)`. `sqlalchemy_url` is always `postgresql+psycopg://`, so psycopg connect args are safe unconditionally (engine creation does not connect; tests use their own SQLite engines via `get_session` override).
- `shell/adapters/postgres/export_record.py:~100` -- `store_export_record` reads `report.client_id`/`report.id` (fine on a refreshed object).
- `tests/test_http_report_runs.py:3777-3920` -- existing Story 6.2 PDF tests; fixtures `authenticated_client`, `db_session` (shared session injected via `dependency_overrides[get_session]`), helpers `_create_client_with_real_chart`, `_stored_chart_id`, `_a_frozen_payload_with_one_aspect`, `_a_generated_draft_for`, `_store_passed_report`, `_export_records`. Patch `report_runs_module.html_to_pdf` via `monkeypatch` (module pattern used at line ~204).
- `tests/test_http_app.py:113` -- `test_engine_construction_enables_pre_ping` spy pattern on `shell_http_app.create_engine`; extend alongside it.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/app.py` -- add module constants (`_DB_CONNECT_TIMEOUT_SECONDS = 10`, `_DB_STATEMENT_TIMEOUT_MS = 30_000`, `_DB_POOL_RECYCLE_SECONDS = 300`, keepalive idle/interval/count) with `#:` comments explaining the production incident; pass `pool_recycle` and `connect_args={"connect_timeout": ..., "keepalives": 1, "keepalives_idle": ..., "keepalives_interval": ..., "keepalives_count": ...}` to `create_engine`, and register a typed `connect` listener that runs `SET statement_timeout` under autocommit (restoring the previous autocommit) so the setting survives the pool's reset-on-return rollback.
- [x] `shell/http/routes/report_runs.py` -- in `download_report_pdf`, call `session.rollback()` after `export_html` is rendered and before `html_to_pdf`, with a comment; add a short paragraph to the docstring on why the connection is released.
- [x] `tests/test_http_report_runs.py` -- add a test whose patched `html_to_pdf` records `db_session.in_transaction()` and returns `b"%PDF-fake"`; assert it was `False`, response 200, stage `exported`, one record. Add a test where patched `html_to_pdf` raises: no `ExportRecord`, stage still `gate_passed`.
- [x] `tests/test_http_app.py` -- extend the spy test (or add a sibling) asserting `pool_recycle` and each `connect_args` key/value.

- [x] `tests/test_engine_on_postgres.py` -- (review loop 2 patch) real-Postgres check, gated on `MIGRATION_TEST_DATABASE_URL`, that two checkouts both report `statement_timeout = 30s` -- the fake DBAPI test cannot show the `SET` survives reset-on-return.

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it passes with the existing PDF tests unchanged.

## Spec Change Log

- Review loop 1 (blind-hunter): statement_timeout passed as the libpq `options` startup parameter would make every connection fail behind a PgBouncer-style pooler (Neon's pooled endpoint included) -- a whole-app outage. Human chose (2026-10-01) to amend the frozen matrix row: apply it with `SET statement_timeout` in a pool `connect` event instead. Known-bad state avoided: `"options"` in `connect_args`. KEEP: the `session.rollback()` before `html_to_pdf` and both route tests, `pool_recycle`, `connect_timeout` and keepalive constants unchanged.

## Design Notes

`rollback()` (not `close()`) is deliberate: the tests share one `db_session` with the route, and `close()` would detach the test's own objects. Rollback ends the transaction, which returns the connection to the pool, while keeping objects attached so later attribute access reloads them in a new, short transaction. Everything the template needs is already materialized into `export_html` before the rollback.

## Verification

**Commands:**
- `uv run pytest tests/test_http_report_runs.py tests/test_http_app.py -q` -- expected: pass
- `uv run pytest -q` -- expected: pass

## Suggested Review Order

**Releasing the connection before the PDF render**

- Entry point: rollback ends the read transaction so WeasyPrint renders with no pooled connection held.
  [`report_runs.py:1544`](../../shell/http/routes/report_runs.py#L1544)

- Docstring records why; the post-render write reloads the expired objects in a short transaction.
  [`report_runs.py:1510`](../../shell/http/routes/report_runs.py#L1510)

**Bounding every engine checkout**

- Connect timeout and keepalives; no `options` startup parameter, which poolers refuse.
  [`app.py:104`](../../shell/http/app.py#L104)

- `SET statement_timeout` under autocommit, so reset-on-return rollback cannot undo it.
  [`app.py:113`](../../shell/http/app.py#L113)

- Wiring: pool_recycle plus the connect listener on the one app engine.
  [`app.py:210`](../../shell/http/app.py#L210)

**Tests**

- Regression test: the session is outside any transaction while html_to_pdf runs.
  [`test_http_report_runs.py:3927`](../../tests/test_http_report_runs.py#L3927)

- A failed render records nothing and leaves the stage alone.
  [`test_http_report_runs.py:3954`](../../tests/test_http_report_runs.py#L3954)

- Engine kwargs and listener registration, plus autocommit handling on a fake DBAPI connection.
  [`test_http_app.py:132`](../../tests/test_http_app.py#L132)

- Real-Postgres check (gated on MIGRATION_TEST_DATABASE_URL) that the SET survives checkouts.
  [`test_engine_on_postgres.py:45`](../../tests/test_engine_on_postgres.py#L45)
