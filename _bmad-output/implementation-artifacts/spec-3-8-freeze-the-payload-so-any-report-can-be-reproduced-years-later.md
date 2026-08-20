---
title: 'Freeze the Payload so any Report can be reproduced years later'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '725c170146e86dd10c74d9ecb4a94ee18c587e45'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `assemble_payload()` (3.6) and `project_day_lists()` (3.7) are pure, unpersisted values —
nothing versions, content-hashes, or stores a `Payload`, so no citation could ever mean the same entry
twice and no Report could be reproduced later. `payload_ready` was deliberately left unwired in both
stories for exactly this reason.

**Approach:** New `core/payload/freeze.py::freeze_payload()` (AD-4) gives every event a stable
content-hash id and a total order, and emits canonical JSON. A new `REPORT_PAYLOAD` table (Postgres,
UUIDv7 row id, FR-29 cascade) stores it immutably, tagged with schema/`computation.toml`/`sections.toml`
versions and the ephemeris identity. `shell/runner/driver.py` wires `payload_ready` to call it.

## Boundaries & Constraints

**Always:**
- `core/payload/freeze.py::freeze_payload(payload, day_lists, *, config, sections_config,
  ephemeris_identity, schema_version=PAYLOAD_SCHEMA_VERSION) -> dict[str, Any]` (pure, `core/`, AD-1/AD-4).
  Every event in each `SectionPayload` tuple and both `DayLists` tuples gets an `"id"`:
  `hashlib.sha256(canonical_json_bytes(fields)).hexdigest()` of that event's own JSON-safe field dict
  (`Decimal`->str, `datetime`->isoformat), tagged by kind exactly like
  `shell/runner/driver.py::_serialize_event` already tags `run.transit_events` — never
  sequential/time/random. Each such tuple is then re-emitted sorted by `canonical_json_bytes(fields)` —
  the total order AD-4 requires, and why two calls on identical inputs are byte-identical.
- `canonical_json_bytes(value) -> bytes` = `json.dumps(value, sort_keys=True,
  separators=(",", ":")).encode()`, same module. `PAYLOAD_SCHEMA_VERSION: int = 1`, same module.
- `shell/adapters/postgres/report_payload.py::ReportPayload(SQLModel, table=True)`: `id` (UUIDv7 PK,
  matching every table), `client_id`/`report_run_id` (FKs, indexed), `schema_version`,
  `computation_config_version`/`_content_hash`, `sections_config_version`/`_content_hash`,
  `ephemeris_files` (JSON, mirrors `StoredNatalChart`), `payload` (JSON, `freeze_payload()`'s return),
  `created_at` (UTC; import `shell/adapters/postgres/report_run.py::_UTCDateTime` rather than
  duplicating it). `store_report_payload(session, *, run, frozen) -> ReportPayload`: `add()`+`flush()`
  only, mirroring `create_client_with_chart` — never commits.
- Immutability: `sqlalchemy.event.listens_for(ReportPayload, "before_update")` raises `RuntimeError`
  unconditionally, same module — no code path updates a persisted row, and an accidental one fails
  loudly.
- FR-29 cascade: add `"report_payload"` to `shell/adapters/postgres/client.py::_CLIENT_CASCADE_TABLES`;
  `delete_client_and_derived()` deletes every `ReportPayload` row for the Client before the Client row
  (mirrors `ReportRun`'s own Story 3.5 join).
- `shell/runner/driver.py`: add a `sections_config: SectionsConfig` parameter to `StageFn`, `drive()`,
  and both existing stage functions (unused there, mirroring how they already ignore params they don't
  need). Add `_deserialize_transit_events(events)` — the reverse of `_serialize_event`, splitting
  `run.transit_events` back into `TransitAspectEvent`/`Station`/`StandingRetrograde`/`Ingress`/`Lunation`
  tuples. Add `_run_payload_ready`: `resolve_house_rulers()` + `assemble_domain_profiles()` from
  `natal_chart`, `assemble_payload()`, `project_day_lists()`, `freeze_payload()`,
  `store_report_payload()`. Register it as `_STAGE_FUNCTIONS["payload_ready"]`.
- `shell/http/app.py`: eager-load `sections_config: SectionsConfig = load_sections_config()` at import
  time (mirrors `computation_config`), set on `application.state`;
  `shell/http/routes/report_runs.py::_drive_run` passes it through to `drive()`.
- New `migrations/versions/0006_report_payload.py`, `down_revision = "0005_report_run"`, mirroring
  `0005_report_run.py`'s shape.
- Schema-version readback: a reader keys on `stored.schema_version`; only `1` exists today, but the
  switch point is real, not a stub — one new branch adds a second version later.

**Ask First:** None identified.

**Never:**
- No change to `core/types/transits.py`/`core/types/payload.py`/`core/types/day_lists.py` — entry ids
  live only in `freeze_payload()`'s output dict, never added as a dataclass field (Stories 3.1–3.7 stay
  untouched).
- No filesystem write of any Payload — Postgres only.
- No update or delete function for `ReportPayload` beyond the FR-29 cascade delete.
- No "Report generated" flag or Epic 4/Generator concept — immutability applies to every persisted
  Payload unconditionally. Flagged for the human checkpoint: FR-14 reads "immutable once its Report is
  generated," but nothing in this codebase yet produces a Report, so "immutable from the moment it is
  persisted" is the only implementable reading and is a strict superset of FR-14's guarantee.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Two events with disjoint fields | An Aspect and a Lunation that share no field values | Distinct ids — the kind tag is part of the hashed tuple | N/A |
| Identical Payload+DayLists, two `freeze_payload()` calls | Same inputs | Byte-identical `canonical_json_bytes()` output both times | N/A |
| `payload_ready` runs after `transits_ready` | A `ReportRun` with `transit_events` populated | `ReportPayload` row persisted; `run.stage == "payload_ready"` | N/A |
| Attempted mutation of a persisted `ReportPayload` | Load a flushed row, mutate a field, `commit()` | `RuntimeError` from the `before_update` listener | Raised, not swallowed |
| Client deletion with a stored Payload | `delete_client_and_derived()` on a Client with a `ReportRun` and its `ReportPayload` | Both rows removed, no orphan | N/A |
| `run.transit_events` round-trip | All five event kinds present | `_deserialize_transit_events` reconstructs dataclasses equal to what `_serialize_event` was given | N/A |

</frozen-after-approval>

## Code Map

- `core/payload/day_lists.py` -- `project_day_lists:38`, `DayLists` (`core/types/day_lists.py:20`) --
  `freeze_payload()`'s second positional argument.
- `core/types/payload.py` -- `Payload:43`, `SectionPayload:24` -- the six named fields to iterate for
  freezing.
- `core/types/transits.py` -- `TransitAspectEvent:22`, `Station:55`, `StandingRetrograde:76`,
  `Ingress:96`, `Lunation:123` -- exact fields `_deserialize_transit_events` reconstructs.
- `shell/runner/driver.py` -- `_serialize_event:178`/`_json_safe:165` (mirror for
  `_deserialize_transit_events` and for `freeze_payload()`'s own JSON-safety), `_STAGE_SEQUENCE:71`
  (`"payload_ready"` already named), `_STAGE_FUNCTIONS:151`, `drive():197`, `StageFn:84`,
  `_run_transits_ready:110` (the `isinstance(Station)` split to mirror in reverse).
- `core/payload/assemble.py` -- `assemble_payload:37` -- exact signature to call.
- `core/domains/rulers.py::resolve_house_rulers:40`, `core/domains/profiles.py::assemble_domain_profiles:27`
  -- build `DomainProfiles` fresh from `natal_chart`/`config`, nothing to deserialize.
- `shell/computation.py` -- `hashlib.sha256(raw).hexdigest()` (`content_hash` pattern to reuse
  verbatim for `canonical_json_bytes`'s callers).
- `shell/adapters/postgres/client.py` -- `StoredNatalChart:66` (JSON-column + typed-metadata-columns
  shape to mirror for `ReportPayload`), `_CLIENT_CASCADE_TABLES:43`, `delete_client_and_derived:261`.
- `shell/adapters/postgres/report_run.py` -- `ReportRun:52`, `_UTCDateTime:28` (import, don't duplicate),
  `uuid7` import pattern.
- `migrations/versions/0005_report_run.py` -- exact migration shape to mirror (`op.create_table`,
  forward-only `downgrade()`).
- `shell/http/app.py` -- `computation_config:186`, `application.state.computation_config:101` -- mirror
  for `sections_config`.
- `shell/sections.py::load_sections_config:1` -- already returns `SectionsConfig` with `version`/
  `content_hash`; no changes needed there.
- `shell/http/routes/report_runs.py` -- `_drive_run:59` -- add the `sections_config` argument to its
  `drive()` call.
- `tests/test_report_run_store.py` -- SQLite-stands-in-for-Postgres fixture and cascade-test shape to
  mirror.
- `tests/test_runner_driver.py` -- existing stage-function test shape to extend for `payload_ready`.

## Tasks & Acceptance

**Execution:**
- [x] `core/payload/freeze.py` -- new `PAYLOAD_SCHEMA_VERSION`, `canonical_json_bytes()`,
  `freeze_payload()` per Boundaries.
- [x] `shell/adapters/postgres/report_payload.py` -- new `ReportPayload` table, `before_update` guard,
  `store_report_payload()`.
- [x] `shell/adapters/postgres/client.py` -- add `"report_payload"` to `_CLIENT_CASCADE_TABLES`; delete
  its rows in `delete_client_and_derived()`.
- [x] `migrations/versions/0006_report_payload.py` -- new table, `down_revision = "0005_report_run"`.
- [x] `shell/runner/driver.py` -- `_deserialize_transit_events()`, `_run_payload_ready()`, `StageFn`/
  `drive()`/existing stage functions gain `sections_config`; register `payload_ready`.
- [x] `shell/http/app.py` -- eager-load and expose `sections_config`.
- [x] `shell/http/routes/report_runs.py` -- pass `sections_config` into `drive()`.
- [x] `tests/test_payload_freeze.py` -- one test per I/O & Edge-Case Matrix row covering `freeze_payload`,
  plus purity/determinism.
- [x] `tests/test_report_payload_store.py` -- table shape, immutability guard, FR-29 cascade, mirroring
  `tests/test_report_run_store.py`.
- [x] `tests/test_runner_driver.py` -- `payload_ready` advances and persists a `ReportPayload`;
  `_deserialize_transit_events` round-trips all five event kinds.

**Acceptance Criteria:**
- Given an assembled `Payload` and its `DayLists`, when `freeze_payload()` runs, then every entry's id is
  a stable hash of its own canonical field tuple and entries are emitted in a total order over those
  fields.
- Given a `ReportPayload` being persisted, when `store_report_payload()` writes it, then it is canonical
  JSON: sorted keys, no insignificant whitespace, `Decimal` as a fixed-precision string.
- Given a stored `ReportPayload`, when it is persisted, then it records `schema_version`, the
  `computation.toml` version/content hash, the `sections.toml` version/content hash, and the ephemeris
  file identity that produced it, and it lives only in Postgres.
- Given a persisted `ReportPayload`, when any code attempts to update it, then the update fails with a
  `RuntimeError` — no path exists to modify it.
- Given a Client with a `ReportRun` and its `ReportPayload`, when `delete_client_and_derived()` runs, then
  both are removed and `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant`
  still passes.
- Given a `ReportRun` at `transits_ready`, when `drive()` is called again, then it advances to
  `payload_ready` and a `ReportPayload` row exists for it.

## Design Notes

**Why entry ids never touch `core/types/`.** AD-4 binds to `core/payload/` (ARCHITECTURE-SPINE.md's
component table), not to the event dataclasses themselves — those are shared, frozen, and already
consumed by Stories 3.1–3.9's other code without an id field. Keeping the id a `freeze_payload()`-only
addition means Stories 3.1–3.7 need no changes and the mixed `Station | StandingRetrograde` /
`TransitAspectEvent` / `Ingress` / `Lunation` shapes stay exactly as they are.

**Why `_run_payload_ready` recomputes `DomainProfiles` instead of reading them back.**
`resolve_house_rulers()`+`assemble_domain_profiles()` are cheap, pure functions of the already-in-hand
`natal_chart`/`config` — no new stored column or deserializer is needed, mirroring how `_run_natal_ready`
already recomputes the month interval rather than storing it redundantly.

**Immutability reading.** See the flagged "Never" item above — confirm at checkpoint.

## Verification

**Commands:**
- `uv run pytest tests/test_payload_freeze.py tests/test_report_payload_store.py tests/test_runner_driver.py -q`
  -- expected: all pass.
- `uv run pytest tests/test_migration_chain.py tests/test_forward_only_migrations.py -q` -- expected: all
  pass (new migration resolves and is forward-only).
- `uv run pytest tests/test_client_store.py -q` -- expected: cascade-invariant test still passes.
- `uv run pytest tests/test_import_boundary.py -q` -- expected: `core/payload/freeze.py` imports nothing
  from `shell/` and touches no forbidden facility.
- `uv run ruff check core/payload/freeze.py shell/adapters/postgres/report_payload.py shell/runner/driver.py` -- expected: no findings.

## Suggested Review Order

**Entry-hashing and canonical JSON (AD-4)**

- Every field this whole story hangs off: the frozen dict's shape, versions and identity.
  [`freeze.py:148`](../../core/payload/freeze.py#L148)

- Sorted-key, no-whitespace JSON -- the one serialization every id and every stored byte comes from.
  [`freeze.py:51`](../../core/payload/freeze.py#L51)

- Kind-tags and hashes each event, then sorts by its own canonical bytes -- the AD-4 total order.
  [`freeze.py:119`](../../core/payload/freeze.py#L119)

- Introspects `SectionPayload`'s fields rather than naming them by hand -- a review patch.
  [`freeze.py:130`](../../core/payload/freeze.py#L130)

**Immutable persistence (FR-14, FR-29)**

- The row shape: typed metadata columns plus the whole frozen dict, self-describing.
  [`report_payload.py:28`](../../shell/adapters/postgres/report_payload.py#L28)

- `unique=True` -- a review patch enforcing "exactly one Payload per run" at the schema level.
  [`report_payload.py:50`](../../shell/adapters/postgres/report_payload.py#L50)

- Unconditional `RuntimeError` on update -- the only enforcement mechanism for "no path to modify it".
  [`report_payload.py:67`](../../shell/adapters/postgres/report_payload.py#L67)

- Add-and-flush only, mirroring `create_client_with_chart` -- never decides the caller's commit.
  [`report_payload.py:83`](../../shell/adapters/postgres/report_payload.py#L83)

- New table, unique index on `report_run_id`, forward-only `downgrade()`.
  [`0006_report_payload.py:31`](../../migrations/versions/0006_report_payload.py#L31)

- FK-ordering fix: `ReportPayload` deleted before `ReportRun` since the former references the latter.
  [`client.py:264`](../../shell/adapters/postgres/client.py#L264)

- The single source of truth `delete_client_and_derived` and its own invariant test both read from.
  [`client.py:44`](../../shell/adapters/postgres/client.py#L44)

**Stage wiring (`payload_ready`)**

- Reverses `_serialize_event`, reconstructing the five event dataclasses from stored JSON.
  [`driver.py:205`](../../shell/runner/driver.py#L205)

- The new stage itself: recomputes `DomainProfiles`, assembles, projects day-lists, freezes, stores.
  [`driver.py:281`](../../shell/runner/driver.py#L281)

- Registers `payload_ready` -- the stage Stories 3.6/3.7 deliberately left unregistered.
  [`driver.py:324`](../../shell/runner/driver.py#L324)

- `sections_config` added to every stage function's signature, unused by the older two.
  [`driver.py:92`](../../shell/runner/driver.py#L92)

**Config plumbing**

- Eager-loads `sections.toml` at import time, mirroring `computation_config`'s own startup pattern.
  [`app.py:202`](../../shell/http/app.py#L202)

- Passes `sections_config` from app state into `drive()`.
  [`report_runs.py:72`](../../shell/http/routes/report_runs.py#L72)

**Tests**

- Distinct ids across event kinds, and byte-identical output across two calls -- the two load-bearing AD-4 properties.
  [`test_payload_freeze.py:96`](../../tests/test_payload_freeze.py#L96)

- A second row for the same run raises `IntegrityError` -- proves the review-patch unique constraint.
  [`test_report_payload_store.py:182`](../../tests/test_report_payload_store.py#L182)

- Mutating a persisted row raises -- proves the immutability guard actually fires.
  [`test_report_payload_store.py:159`](../../tests/test_report_payload_store.py#L159)

- Client deletion removes its `ReportPayload` rows too.
  [`test_report_payload_store.py:207`](../../tests/test_report_payload_store.py#L207)

- A full drive from scratch now reaches `payload_ready` and a row exists for it.
  [`test_runner_driver.py:165`](../../tests/test_runner_driver.py#L165)

- All five event kinds round-trip through `_deserialize_transit_events`.
  [`test_runner_driver.py:454`](../../tests/test_runner_driver.py#L454)
