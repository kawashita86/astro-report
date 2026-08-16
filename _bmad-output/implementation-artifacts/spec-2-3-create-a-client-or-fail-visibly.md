---
title: 'Create a Client, or fail visibly'
type: 'feature'
created: '2026-08-16'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '79cb4b0a4a00db78f8682185a12e08769ff0a919'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Client cannot yet be entered. Nothing persists the five required inputs, resolves the
birthplace, computes the Natal Chart, or refuses a half-formed record — so nothing downstream (Domain
Profiles, Reports) has a Client to build on.

**Approach:** A new authenticated `/clients` form takes name, birth date, birth time (to the minute)
and birthplace. Submission resolves the birthplace (Story 2.1's `Geocoder`, presenting ambiguous
candidates for an explicit choice), computes the Natal Chart (Story 2.2's `compute_natal_chart()`),
and persists Client + Natal Chart together in one transaction — or persists nothing, naming the step
that failed.

## Boundaries & Constraints

**Always:**
- A Client row is written only after birthplace resolution, historical-offset resolution and chart
  computation all succeed; Client and Natal Chart are written in one transaction — never one without
  the other (AD-16).
- Both tables use UUIDv7 primary keys (`uuid6.uuid7`), matching `PlaceCache`.
- The Client stores its own immutable snapshot of resolved latitude, longitude and IANA zone — never
  re-read from `PLACE_CACHE` after creation.
- The stored Natal Chart records the `ComputationConfig` version + content hash and the verified
  `EphemerisIdentity` that produced it.
- An explicitly-chosen candidate (from an ambiguous match) is never written through to `PLACE_CACHE` —
  only an unambiguous geocoder match is, exactly as Story 2.1 already behaves.
- The route is authenticated by default via the existing `AuthMiddleware` (no allowlist change).
- No field is optional; no noon-chart, solar-house or house-less fallback path exists.

**Never:**
- No chart-wheel view (Story 2.6), correction (2.7), deletion (2.8), Ruler resolution (2.4) or Domain
  Profile assembly (2.5) — this route only creates and stores.
- No uniqueness constraint on Client name.
- No `superseded`/status column on Natal Chart yet — Story 2.7 adds it with its own migration.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | All 4 fields, unambiguous birthplace | Client + Natal Chart persisted in one transaction; confirmation shown | N/A |
| Ambiguous birthplace | Birthplace text matches >1 place | Form re-rendered with candidates for explicit choice; nothing persisted, no cache write | N/A |
| Missing/blank required field | e.g. birth time omitted | 422, form re-shown, field named; nothing persisted | Validation message |
| Resolution failure | Geocoding/timezone/cache step raises `PlaceResolutionError` | 422, form re-shown naming the failing step; nothing persisted | Message from `error.step` |
| Chart computation failure | `compute_natal_chart()` raises | 422, form re-shown with the error; nothing persisted, no partial Client row | Message from the raised error |
| Duplicate name | Two Clients created with the same name | Both persist as distinct rows | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/types/place.py`, `core/errors.py` (`PlaceResolutionError`, carries `.step`) -- reused as-is.
- `core/ephemeris/chart.py:97` -- `compute_natal_chart(birth_instant_utc, latitude, longitude, config) -> NatalChart`.
- `core/types/chart.py`, `core/types/computation.py:89` (`.version`/`.content_hash`), `core/ephemeris/identity.py:57` (`EphemerisIdentity`/`EphemerisFile`) -- what the stored chart records.
- `shell/adapters/postgres/place_cache.py` -- UUIDv7 `SQLModel` pattern to mirror; its
  `store_resolved_place()` nested-transaction (`begin_nested()`+`flush()`) already anticipates this
  story sharing its session.
- `shell/http/app.py:56,146-154`, `shell/config.py:131` (`sqlalchemy_url`) -- `create_app()` and the URL to build the engine from.
- `migrations/env.py:46`, `migrations/versions/0002_place_cache.py` -- engine/migration patterns to mirror.
- `tests/test_place_cache.py:20` -- sqlite in-memory `Session` fixture pattern for adapter tests.

**To create:**
- `shell/adapters/postgres/client.py` -- `Client`, `StoredNatalChart` SQLModel tables (UUIDv7 PKs,
  `client_id` FK) and `create_client_with_chart(session, ...) -> Client` writing both rows in one
  flush; Decimal fields inside `planets`/`houses`/`aspects` serialize to strings before the JSON
  column write (JSON has no native Decimal).
- `shell/http/routes/clients.py` -- `APIRouter` with `GET /clients/new` (form) and `POST /clients`
  (parses fields, calls the geocoder, branches on candidate list vs. resolved place, calls
  `compute_natal_chart()`, persists, renders confirmation or re-shows the form with a named error).
- `shell/http/templates/client_new.html` -- form mirroring `login.html`'s style; conditionally lists
  candidates as radio choices when re-shown after an ambiguous match.
- `migrations/versions/0003_client_and_natal_chart.py` -- creates both tables + the FK.
- `tests/test_client_store.py` -- sqlite-backed tests for `create_client_with_chart`.
- `tests/test_http_clients.py` -- `TestClient` tests (session dependency overridden with sqlite) for
  the I/O matrix rows.

**To modify:**
- `shell/ports/geocoder.py` -- add a `resolve_candidate(candidate, birth_local_time) -> ResolvedPlace`
  method to the `Geocoder` Protocol: finalizes an explicitly-chosen `PlaceCandidate` into a zone +
  historical offset, without a `PLACE_CACHE` write.
- `shell/adapters/nominatim/geocoder.py` -- implement `resolve_candidate()` reusing the existing
  `_zone_for()`/`_historical_offset()` logic already used by `resolve()`.
- `shell/http/app.py` -- build the engine from `settings.sqlalchemy_url` (mirrors `migrations/env.py`),
  store it on `application.state`, add a `get_session` dependency, include the new `clients` router.

## Tasks & Acceptance

**Execution:**
- [x] `shell/ports/geocoder.py` -- add `resolve_candidate()` to the `Geocoder` Protocol -- required for the explicit-choice AC
- [x] `shell/adapters/nominatim/geocoder.py` -- implement `resolve_candidate()` -- AC4
- [x] `shell/adapters/postgres/client.py` -- `Client`/`StoredNatalChart` tables + `create_client_with_chart()` -- AC3, AC5, AC6
- [x] `migrations/versions/0003_client_and_natal_chart.py` -- create both tables -- prerequisite for the above
- [x] `shell/http/app.py` -- engine, `get_session` dependency, include `clients` router -- prerequisite for the route
- [x] `shell/http/routes/clients.py` -- form + submission handler, orchestrating resolution → computation → persistence -- AC1, AC2, AC3, AC4
- [x] `shell/http/templates/client_new.html` -- form + candidate-choice rendering -- AC1, AC4
- [x] `tests/test_client_store.py` -- unit-test the I/O matrix's persistence rows -- AC3, AC6
- [x] `tests/test_http_clients.py` -- unit-test the I/O matrix's HTTP rows -- AC1, AC2, AC4, AC5

**Acceptance Criteria:**
- Given the Client creation form, when Francesco enters a Client, then it takes name, birth date, birth time (to the minute) and birthplace, all required, with no partial submission accepted.
- Given a birthplace that resolves to several candidates, when the form is submitted, then Francesco is shown the candidates and must choose one explicitly before the Client is persisted, and choosing one never writes to `PLACE_CACHE`.
- Given all inputs resolve successfully, when the Client is created, then it stores its own immutable snapshot of latitude, longitude and IANA zone, and the Natal Chart is computed once and persisted with it, both keyed by UUIDv7, in the same transaction.
- Given resolution or computation fails at any step, when creation is attempted, then no Client row and no Natal Chart row exist afterward, and the visible error names the failing step.
- Given two Clients entered with the same name, when both are created, then both persist as distinct rows.
- Given a successfully created Client, when the Natal Chart row is inspected, then it records the `ComputationConfig` version/content hash and the verified `EphemerisIdentity`.

## Spec Change Log

## Design Notes

**No new error hierarchy.** `PlaceResolutionError` (`.step`) and whatever `compute_natal_chart()` raises
are caught and rendered as-is, mirroring `login.html`'s error-banner pattern — a wrapper error type
would only re-narrate a step name the domain errors already carry.

**First route module extraction.** `healthz`/`login` stay inline in `create_app()`; `clients` becomes
the first `shell/http/routes/` module, since a second real feature route is exactly when that split
earns its keep, not before.

**Confirmation, not a redirect.** No client-detail/list route exists before Story 6.4, so success
renders a plain confirmation naming the new Client's id, mirroring `login`'s plain-text response.

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including the new adapter and HTTP tests
- `uv run ruff check .` -- clean
- `uv run alembic upgrade head` (offline, against `migrations/env.py`) -- the new revision applies cleanly after `0002_place_cache`

## Suggested Review Order

**Orchestration: the request/response flow**

- Entry point: the whole resolve → compute → persist → commit pipeline, and the one place the atomic-transaction rule (AD-16) actually plays out.
  [`clients.py:171`](../../shell/http/routes/clients.py#L171)

- The commit is the single point where a Client and its Natal Chart become real; everything above this line can fail and roll back cleanly.
  [`clients.py:249`](../../shell/http/routes/clients.py#L249)

- Explicit-candidate branch vs. fresh geocode: an already-chosen `PlaceCandidate` skips straight to `resolve_candidate()`, never re-querying `resolve()`.
  [`clients.py:217`](../../shell/http/routes/clients.py#L217)

- Form/body validation gate (missing fields, oversized or non-UTF-8 body) rejects before any resolution or computation runs.
  [`clients.py:151`](../../shell/http/routes/clients.py#L151)

**Schema: what gets persisted, and how atomically**

- `Client`/`StoredNatalChart` tables plus the write itself -- only `add()`+`flush()`, so the caller's `commit()` is the only thing that makes either row durable.
  [`client.py:93`](../../shell/adapters/postgres/client.py#L93)

- Table shapes: UUIDv7 PKs, the immutable birthplace snapshot on `Client`, and the `ComputationConfig`/`EphemerisIdentity` provenance fields on `StoredNatalChart`.
  [`client.py:31`](../../shell/adapters/postgres/client.py#L31)

- The hand-written migration DDL that must stay byte-for-byte compatible with the SQLModel classes above.
  [`0003_client_and_natal_chart.py:28`](../../migrations/versions/0003_client_and_natal_chart.py#L28)

**Port extension: finalizing an explicitly-chosen candidate**

- The gap this story closes: Story 2.1's `Geocoder` could offer candidates but never finalize one -- this is the new contract.
  [`geocoder.py:39`](../../shell/ports/geocoder.py#L39)

- Implementation: reuses `resolve()`'s own `_zone_for()`/`_historical_offset()` helpers, and deliberately never writes through to `PLACE_CACHE`.
  [`geocoder.py:114`](../../shell/adapters/nominatim/geocoder.py#L114)

**Wiring: the app's first live database engine**

- `get_session()`'s non-auto-committing contract is what makes the orchestration's single `commit()` meaningful at all.
  [`app.py:61`](../../shell/http/app.py#L61)

- Engine construction and router registration -- the two lines that turn `settings.sqlalchemy_url` and the new router into a working app.
  [`app.py:98`](../../shell/http/app.py#L98)

**Peripherals**

- The form itself, including the conditional candidate-choice radio list.
  [`client_new.html:37`](../../shell/http/templates/client_new.html#L37)

- HTTP-level coverage of every I/O matrix row, with a fake `Geocoder` and a faked `compute_natal_chart()` to isolate route orchestration from real network/ephemeris calls.
  [`test_http_clients.py:206`](../../tests/test_http_clients.py#L206)

- Adapter-level coverage of the atomic-write contract itself: nothing persists without an explicit `commit()`.
  [`test_client_store.py:97`](../../tests/test_client_store.py#L97)

