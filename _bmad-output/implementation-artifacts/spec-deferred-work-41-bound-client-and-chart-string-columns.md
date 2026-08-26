---
title: 'deferred-work item 41 — Bound Client.name, Client.iana_zone, and StoredNatalChart.computation_config_content_hash'
type: 'bugfix'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'e45075208b5f22b680cec832d3fff44e2b464569'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `Client.name`, `Client.iana_zone` (`shell/adapters/postgres/client.py`) and
`StoredNatalChart.computation_config_content_hash` are unbounded `String`/`str` columns --
no upper bound exists at the schema or form-validation level beyond the unrelated
`_MAX_CLIENT_FORM_BODY_BYTES` whole-body cap (65536 bytes), so a single oversized field can
still pass that cap while remaining pathologically large.

**Approach:** Give each column an explicit, generous length bound reflecting what it actually
holds: `name` (free-text, user-typed) 200 characters; `iana_zone` (a real IANA zone id,
Geocoder-resolved, never user-typed directly -- the longest real id is ~33 characters) 64
characters; `computation_config_content_hash` (a sha256 hex digest, always exactly 64
characters) 64 characters. Enforce each via `Field(max_length=...)` on the model (which
becomes the migration's `VARCHAR(n)`), and additionally reject an over-length `name` at the
`/clients` and `/clients/{id}/edit` HTTP boundary with a 422 naming the field -- the only one
of the three a caller submits as raw text.

## Boundaries & Constraints

**Always:**
- `Client.name` gets `Field(max_length=200)`; `Client.iana_zone` and
  `StoredNatalChart.computation_config_content_hash` each get `Field(max_length=64)`.
- A new forward-only Alembic migration (`0014_...`) alters `client.name` to `VARCHAR(200)`,
  `client.iana_zone` to `VARCHAR(64)`, and `natal_chart.computation_config_content_hash` to
  `VARCHAR(64)`, mirroring every existing migration's `downgrade()` -> `RuntimeError` pattern.
- `create_client` and `correct_client` (`shell/http/routes/clients.py`) reject a `name` over
  200 characters with a 422 naming `name`, checked alongside the existing
  `_missing_fields`/blank check, before any resolution or computation runs.

**Ask First:** None.

**Never:**
- No change to `PlaceCache.iana_zone` (`shell/adapters/postgres/place_cache.py`) or
  `ReportPayload.computation_config_content_hash`/`.sections_config_content_hash`
  (`shell/adapters/postgres/report_payload.py`) -- named out of scope by the deferred item
  itself; a separate follow-up if ever needed.
- No length bound on `iana_zone`/`computation_config_content_hash` at the HTTP form boundary --
  neither is a raw form field a caller submits (`iana_zone` comes from `resolved_place`;
  the hash from `computation_config.content_hash`), so only the schema-level bound applies.
- No `pool_size`/other unrelated schema or engine changes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid name | `name` = 200 chars | Client created normally | N/A |
| Oversized name, create | `name` = 201 chars, POST `/clients` | 422, error names `name`, no Client persisted | Returned before resolve/compute run |
| Oversized name, correct | `name` = 201 chars, POST `/clients/{id}/edit` | 422, error names `name`, no correction persisted | Returned before resolve/compute run |
| Model column bounds | Inspect `Client.__table__`/`StoredNatalChart.__table__` | `name.type.length == 200`; `iana_zone.type.length == 64`; `computation_config_content_hash.type.length == 64` | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/client.py:73,78,105` -- `Client.name`, `Client.iana_zone`,
  `StoredNatalChart.computation_config_content_hash` field declarations; add
  `Field(max_length=...)` to each (currently bare `str`).
- `migrations/versions/0013_gate_result.py` -- the most recent migration; the new one's
  `down_revision` points here. Follow its `revision`/`down_revision`/forward-only
  `downgrade()` pattern exactly (no precedent for `alter_column` yet in this repo -- use
  `op.alter_column(table, column, type_=sa.String(length=n))`).
- `shell/http/routes/clients.py:69,124-125,263-270,403-411` -- `_REQUIRED_FIELDS`,
  `_missing_fields()`, and the missing-field checks in `create_client`/`correct_client`. Add a
  sibling `_MAX_NAME_LENGTH = 200` constant and a length check for `fields["name"]` in both
  handlers, in the same position as the existing `missing` check (before `birth_date` parsing).
- `tests/test_client_store.py` -- model-level tests live here (e.g.
  `test_the_stored_chart_records_the_computation_config_version_and_hash` at line 132); add
  column-length assertions near the existing model-shape tests.
- `tests/test_http_clients.py:288-313` -- `test_a_missing_required_field_is_refused_naming_it`/
  `test_a_blank_required_field_is_refused` are the sibling patterns for a new
  `test_an_oversized_name_is_refused_naming_it` test (reuses `_VALID_FORM`, `_use_geocoder`,
  `_clients(db_session)`).
- `tests/test_http_client_correction.py` -- mirror the same oversized-name test for
  `POST /clients/{id}/edit`, following that file's existing edit-route test pattern.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/client.py` -- add `Field(max_length=200)` to `Client.name`,
  `Field(max_length=64)` to `Client.iana_zone` and to
  `StoredNatalChart.computation_config_content_hash`.
- [x] `migrations/versions/0014_bound_client_and_chart_string_columns.py` -- new migration:
  `down_revision = "0013_gate_result"`; `upgrade()` alters the three columns to
  `VARCHAR(200)`/`VARCHAR(64)`/`VARCHAR(64)`; `downgrade()` raises `RuntimeError` matching
  every prior migration.
- [x] `shell/http/routes/clients.py` -- add `_MAX_NAME_LENGTH = 200` and reject an over-length
  `name` with a 422 naming the field in both `create_client` and `correct_client`, before
  `birth_date` parsing.
- [x] `tests/test_client_store.py` -- assert the three columns' SQLAlchemy `type.length`
  values.
- [x] `tests/test_http_clients.py` -- `test_an_oversized_name_is_refused_naming_it` (name =
  201 chars, expect 422 naming `name`, no Client persisted); also
  `test_a_name_at_the_maximum_length_is_accepted` (name = 200 chars, expect 200, Client
  persisted with that name) covering the matrix's "Valid name" row.
- [x] `tests/test_http_client_correction.py` -- the same oversized-name case for
  `POST /clients/{id}/edit`.

**Acceptance Criteria:**
- Given a `POST /clients` submission with a 201-character `name`, when the request is
  processed, then the response is 422, names `name`, and no `Client` row is persisted.
- Given a `POST /clients/{id}/edit` submission with a 201-character `name`, when the request
  is processed, then the response is 422, names `name`, and no correction is persisted.
- Given `Client`/`StoredNatalChart`'s SQLAlchemy metadata, when inspected, then `name` reports
  `VARCHAR(200)` and `iana_zone`/`computation_config_content_hash` each report `VARCHAR(64)`.
- Given the full Alembic chain, when `alembic upgrade head` runs offline (as
  `tests/test_migration_chain.py` already drives it), then it resolves cleanly through the new
  revision.

## Spec Change Log

## Verification

**Commands:**
- `uv run pytest tests/test_client_store.py tests/test_http_clients.py tests/test_http_client_correction.py tests/test_migration_chain.py -q` -- expected: all pass, including new tests.
- `uv run pytest -q` -- expected: full suite passes unaffected.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**HTTP-boundary validation**

- Entry point: the bound is derived from the model's own column length, not a second
  hardcoded number, so the two cannot drift apart.
  [`clients.py:77`](../../shell/http/routes/clients.py#L77)

- `create_client`'s check -- 422 naming `name`, before `birth_date` parsing or any
  resolution/computation runs.
  [`clients.py:280`](../../shell/http/routes/clients.py#L280)

- The mirrored check in `correct_client` for `POST /clients/{id}/edit`.
  [`clients.py:429`](../../shell/http/routes/clients.py#L429)

**Schema bound**

- `Client.name` -- `VARCHAR(200)`, the one of the three a caller submits as raw text.
  [`client.py:79`](../../shell/adapters/postgres/client.py#L79)

- `Client.iana_zone` -- schema-only bound; Geocoder-resolved, never user-typed.
  [`client.py:88`](../../shell/adapters/postgres/client.py#L88)

- `StoredNatalChart.computation_config_content_hash` -- schema-only bound; always a
  64-character sha256 hex digest.
  [`client.py:119`](../../shell/adapters/postgres/client.py#L119)

**Migration**

- Alters the three columns to their new `VARCHAR(n)` bounds, forward-only like every
  prior migration in this repo.
  [`0014_bound_client_and_chart_string_columns.py:40`](../../migrations/versions/0014_bound_client_and_chart_string_columns.py#L40)

**Tests**

- Column-length metadata assertion covering all three bounded columns.
  [`test_client_store.py:132`](../../tests/test_client_store.py#L132)

- Boundary (200 chars, accepted) and over-length (201 chars, refused) cases for
  `POST /clients`.
  [`test_http_clients.py:319`](../../tests/test_http_clients.py#L319)

- The same boundary and over-length cases mirrored for `POST /clients/{id}/edit`.
  [`test_http_client_correction.py:469`](../../tests/test_http_client_correction.py#L469)
