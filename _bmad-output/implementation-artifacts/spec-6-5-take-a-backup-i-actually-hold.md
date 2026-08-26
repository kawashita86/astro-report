---
title: 'Take a backup I actually hold'
type: 'feature'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '498dd66657914095321d67782222bd13a18f7f90'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every durability-critical row (Clients, Natal Charts, Reports, and everything a Report needs to reopen) lives only in the hosted Postgres instance. The free-tier host's point-in-time restore is a roughly six-hour window with no scheduled backups — epic-6-context.md is explicit that this does not satisfy the durability requirement, so a real, operator-held export is the actual mechanism.

**Approach:** Add one authenticated `GET /backup` route that reads every row of every durability-relevant table — in an order a future restore (Story 8.5) can insert without violating foreign keys — serializes each row with SQLModel's own `model_dump(mode="json")`, and returns the whole thing as one downloadable JSON file.

## Boundaries & Constraints

**Always:** One parameterless `GET /backup` route. It reads and serializes every row from, in this exact order (each table only after every table it foreign-keys into): `client`, `natal_chart`, `report_run`, `report`, `report_payload`, `report_draft`, `report_theme`, `gate_result`, `export_record`, `style_guide`. Each row is serialized with `.model_dump(mode="json")` (UUID -> str, datetime -> ISO 8601, existing JSON columns pass through unchanged) — no hand-written per-table serializer. The response is `application/json` with a `Content-Disposition: attachment` header, built fully in memory (no streaming), mirroring `download_report_pdf`'s exact `Response(...)` shape. The route is not added to `shell.http.auth.ALLOWLIST`, so `AuthMiddleware` authenticates it like every other route with zero new auth code.

**Ask First:** Nothing identified — open scope questions (Corpus, and which non-AC tables to include) were already resolved with the human this session.

**Never:** Do not implement restore itself (Story 8.5, out of scope here). Do not include `place_cache` (a recomputable geocoding cache) or a Corpus table (Epic 7 is still backlog — no such table exists in the codebase yet). Do not add pagination, filtering, streaming, or any UI page — the only planned UI surface (a staleness warning) is Story 6.6, a separate story that depends on this route existing. Do not touch `core/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Empty database | No `Client` rows exist | Downloads JSON with all ten table keys present, each an empty list | N/A |
| Populated pipeline | Several Clients, each with a full `ReportRun` -> `Report` -> `ReportPayload`/`ReportDraft`/`ReportTheme`/`GateResult` chain, some with `ExportRecord`s | Every row across every included table appears exactly once, in the FK-safe table order above | N/A |
| Pre-story-6.4 ReportRun | `ReportRun.natal_chart_id` is `NULL` | Row still included, with `natal_chart_id: null` | N/A |
| Multiple StyleGuide versions | >1 `StyleGuide` row (Story 4.2 edits) | All versions included, not only the current one | N/A |
| Anonymous request | No session cookie | -- | 401 (existing `AuthMiddleware`; no route-level code) |

</frozen-after-approval>

## Code Map

- `shell/http/routes/backup.py` (new) -- `GET /backup`: for each of the ten models (imported from their existing `shell/adapters/postgres/*` modules), `session.exec(select(Model)).all()`, `.model_dump(mode="json")` each row, assemble an ordered `dict[str, list[dict]]` keyed by `__tablename__`, `json.dumps(...).encode()`, return via `Response(content=..., media_type="application/json", headers={"Content-Disposition": f'attachment; filename="backup-{timestamp}.json"'})` -- exact shape of `download_report_pdf` (`shell/http/routes/report_runs.py:471`), `timestamp` from `datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")`.
- `shell/http/app.py` (~lines 114-139) -- import `backup_router` alongside the other four deferred router imports and `include_router(backup_router)` -- same registration pattern as `clients_router`/`report_runs_router`.
- `tests/test_http_backup.py` (new) -- covers the I/O matrix above, built on `tests/test_http_clients.py`'s fixture shape (`db_session`, `app_instance`, `client`, `authenticated_client`).

**ReportDraft correction:** the human's initial scope call excluded `ReportDraft` (framed as "reproducible only by rerunning generation"). Investigation of `view_report` (`shell/http/routes/report_runs.py:302`) shows that framing was wrong: opening any Report unconditionally reads its latest `ReportDraft` and raises `RuntimeError` if none exists. Excluding it would make every restored Report unopenable, directly violating "complete enough that a restore reconstructs the application's state." `report_draft` is therefore included.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/backup.py` -- new `GET /backup` handler -- produces the export
- [x] `shell/http/app.py` -- register `backup_router` -- exposes the route
- [x] `tests/test_http_backup.py` -- new -- covers the I/O matrix and FK-safe ordering

**Acceptance Criteria:**
- Given an authenticated request to `/backup`, when it runs, then it downloads a JSON file containing every row of the ten included tables.
- Given the export's table order, when tables are read back top to bottom, then no row references an id from a table appearing later in the file (restorable without a foreign-key violation).
- Given an anonymous request to `/backup`, when it is made, then it is rejected with 401 exactly like every other route.

## Spec Change Log

## Design Notes

`model_dump(mode="json")` (Pydantic v2, which SQLModel 0.0.39 sits on) is what makes this a one-line-per-table export: it converts `UUID` -> `str` and `datetime` -> ISO 8601 automatically, and the existing `JSON`-typed columns (`planets`, `payload`, `theme`, `violations`, `draft`, `transit_events`) are already plain `dict`/`list` values that pass through unchanged — no custom encoder needed anywhere in this codebase's `json.dumps` usage today, and none is needed here either.

Table order is the whole trick for restorability: `client` has no dependencies; `natal_chart` and `report_run` depend only on `client`; `report`/`report_payload`/`report_draft`/`report_theme`/`gate_result` depend on `report_run` (and `client`); `export_record` depends on `report`; `style_guide` is global and independent. Listing them in that order means a future restore (Story 8.5) can insert the file's arrays in file order without ever hitting a foreign key that doesn't exist yet.

## Verification

**Commands:**
- `uv run pytest tests/test_http_backup.py tests/test_auth.py -q` -- expected: all pass, including the existing allowlist-walk test picking up `/backup` as authenticated by default
- `uv run ruff check .` -- expected: clean

## Suggested Review Order

**Producing the export**

- Entry point: every row of ten tables, read in FK-safe order, serialized with `model_dump(mode="json")`, returned as one JSON download.
  [`backup.py:76`](../../shell/http/routes/backup.py#L76)

- The table set and its order -- the single source of truth every other stop in this review checks against.
  [`backup.py:61`](../../shell/http/routes/backup.py#L61)

- Deterministic per-table row order (`order_by(model.id)`) and the `Cache-Control: no-store` header, both added during review since the response is unfiltered Client PII.
  [`backup.py:93`](../../shell/http/routes/backup.py#L93)

**Wiring it in**

- Registered like every other router -- no new auth code, since `AuthMiddleware` guards by default.
  [`app.py:114`](../../shell/http/app.py#L114)

**Review-driven completeness and correctness guards**

- The table set is checked against `_CLIENT_CASCADE_TABLES`, the codebase's existing guarded single source of truth for client-scoped tables -- a future table added there and forgotten here now fails loudly.
  [`test_http_backup.py:391`](../../tests/test_http_backup.py#L391)

- The FK-safe ordering claim this whole story rests on, verified structurally against each model's real foreign keys rather than asserted in prose.
  [`test_http_backup.py:407`](../../tests/test_http_backup.py#L407)

- An uneven shape (two `ExportRecord`s, no Draft/Theme/GateResult) proving rows are associated by id, not just counted.
  [`test_http_backup.py:433`](../../tests/test_http_backup.py#L433)

- `Decimal` and JSON-column values verified to round-trip correctly, not just their presence.
  [`test_http_backup.py:473`](../../tests/test_http_backup.py#L473)

**Story's own I/O & Edge-Case Matrix**

- Anonymous request, empty database, the fully-chained populated pipeline, a pre-Story-6.4 `ReportRun` with a null `natal_chart_id`, and multiple `StyleGuide` versions.
  [`test_http_backup.py:266`](../../tests/test_http_backup.py#L266)
