---
title: 'Story 2.1 — Resolve a birthplace to coordinates and the offset in force at birth'
type: 'feature'
created: '2026-08-16'
status: 'done'
review_loop_iteration: 0
baseline_commit: '51288f0ef45ac21e1827e2e9bf55b51995498be0'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing in the codebase resolves a free-text birthplace to coordinates or to the *historical* UTC offset in force at the birth instant. Using today's offset instead of the historical one is the difference between a correct chart and one an hour off — e.g. a 1975 Italian birth must read as CEST (+02:00), not today's CET (+01:00).

**Approach:** Add a `Geocoder` port with a Nominatim adapter (via `geopy`), backed by a Postgres `PLACE_CACHE` table consulted before every geocode call. Historical offset/zone is derived from `timezonefinder` (coordinates → IANA zone) plus `zoneinfo` (historical DST rules at the birth instant). A typed `PlaceResolutionError` in `core/errors.py` names which step failed; resolution never returns `None`.

## Boundaries & Constraints

**Always:**
- `Geocoder` port lives in `shell/ports/`; the Nominatim adapter lives in `shell/adapters/nominatim/`, using `geopy`'s `Nominatim` geocoder with a fixed, descriptive `User-Agent` string (Nominatim's usage policy requires one).
- Historical offset/zone: look up the IANA zone from resolved lat/lon via `timezonefinder`, then resolve the UTC offset in force *at the supplied birth instant* in that zone via `zoneinfo` — never today's offset.
- `PLACE_CACHE` is a new Postgres table (Alembic migration), read/written from `shell/adapters/postgres/`, keyed on the normalized query text, consulted before geocoding and write-through on a fresh successful resolution. Per AD-16 it is a lookup accelerator only — never a source of truth once a Client has persisted its own immutable lat/lon/zone snapshot.
- Coordinates resolve to at least four decimal places.
- Ambiguous matches (more than one candidate) are returned as a list for an explicit human choice; nothing is auto-picked.
- Resolution failure (place not found, geocoder unreachable) raises `PlaceResolutionError` from `core/errors.py`, naming the failed step (geocoding vs. timezone/offset resolution vs. cache read); it never returns `None`.
- Add `geopy` and `timezonefinder` as new runtime dependencies in `pyproject.toml`/`uv.lock`.
- All I/O (HTTP geocoding, Postgres cache) lives in `shell/`, mirroring AD-1; `core/` gains only the frozen result types and the error class, no I/O.

**Ask First:** None anticipated — the Nominatim/geopy/timezonefinder/PLACE_CACHE shape is specified by the epic AC and the original product research; no open design question remains.

**Never:**
- No Client-creation wiring (Story 2.3) — this story delivers the resolution capability itself, callable and tested standalone.
- No Natal Chart computation (Story 2.2).
- No HTTP route or form for candidate selection (Story 2.3) — resolution returns candidates as data only.
- No caching of a failed resolution — only a successful one populates `PLACE_CACHE`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Single unambiguous match | Free-text place + birth date/time | lat/lon (≥4 decimal places), IANA zone, UTC offset in force at that instant | N/A |
| Historical DST | "Milan, Italy", 1975-06-15 | offset resolves to +02:00 (CEST), not +01:00 | N/A |
| Ambiguous place name | Place matching >1 location | List of candidates returned; none auto-selected | N/A |
| Repeat place | Place already resolved and cached | Served from `PLACE_CACHE`; geocoder not called | N/A |
| Unresolvable place / geocoder unreachable | Nonsense string, or network failure | — | `PlaceResolutionError` naming the failed step |
| `PLACE_CACHE` vs. a persisted Client | Client already stores its own lat/lon/zone snapshot | Cache is never consulted to override it | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/errors.py` -- existing typed-error pattern (`EphemerisIntegrityError`, `ComputationConfigError`) to extend with `PlaceResolutionError`.
- `shell/ports/__init__.py`, `shell/adapters/__init__.py` -- existing docstring stubs already naming `Geocoder`/`nominatim` as the intended shape.
- `shell/computation.py` -- the load-validate-freeze pattern (typed error naming every offending field) to mirror for `PLACE_CACHE` row validation.
- `migrations/versions/0001_baseline.py`, `migrations/env.py`, `alembic.ini` -- forward-only migration chain this story's new migration attaches to.
- `_bmad-output/planning-artifacts/epics.md:593-624` -- Story 2.1 acceptance criteria verbatim.
- Architecture spine AD-12 (UTC in core, local time at the edges), AD-16 (Client cannot exist partial; `PLACE_CACHE` is accelerator-only), AD-18 (no ambient config) -- constraints this story must satisfy.

**To create:**
- `shell/ports/geocoder.py` -- `Geocoder` port (Protocol/ABC): resolve a place + birth instant to a single result or a candidate list.
- `shell/adapters/nominatim/geocoder.py` -- geopy-backed adapter implementing the port; historical offset/zone via `timezonefinder` + `zoneinfo`.
- `shell/adapters/postgres/place_cache.py` -- `PLACE_CACHE` read-before-geocode / write-through-after-resolve, SQLModel-backed.
- `core/types/place.py` -- frozen dataclasses for a resolved place and a candidate match (mirrors `core/types/computation.py`'s pattern of pure types loaded/produced by the shell).
- `migrations/versions/0002_place_cache.py` -- creates the `PLACE_CACHE` table.
- `tests/test_geocoder_nominatim.py`, `tests/test_place_cache.py` -- I/O matrix coverage, including the historical-DST case and the failure-naming case.

**To modify:**
- `core/errors.py` -- add `PlaceResolutionError`.
- `pyproject.toml`, `uv.lock` -- add `geopy`, `timezonefinder`.

## Tasks & Acceptance

**Execution:**
- [x] `core/errors.py` -- add `PlaceResolutionError` naming the failed step -- AC5
- [x] `core/types/place.py` -- frozen `ResolvedPlace`/`PlaceCandidate` types -- prerequisite for AC1, AC3
- [x] `pyproject.toml`, `uv.lock` -- add `geopy`, `timezonefinder` (and `uuid6`, needed for UUIDv7 on Python 3.13) -- prerequisite for all
- [x] `migrations/versions/0002_place_cache.py` -- `PLACE_CACHE` table, UUIDv7 primary key -- AC4, AC6
- [x] `shell/ports/geocoder.py` -- `Geocoder` port definition -- AC1
- [x] `shell/adapters/nominatim/geocoder.py` -- Nominatim adapter: geocode, then `timezonefinder`+`zoneinfo` for the historical offset -- AC1, AC2
- [x] `shell/adapters/postgres/place_cache.py` -- cache read-before-geocode, write-through on success -- AC4, AC6
- [x] Test the I/O matrix's six rows, including the 1975-06-15 CEST case and a mocked geocoder failure

**Acceptance Criteria:**
- Given a free-text birthplace and birth date/time, when resolved, then latitude/longitude (≥4 decimal places), the IANA zone, and the UTC offset in force at that instant are returned.
- Given a birth in Italy on 1975-06-15, when resolved, then the applied offset is +02:00 (CEST), never +01:00.
- Given a place name matching more than one location, when resolved, then all candidates are returned and none is silently chosen.
- Given a birthplace resolved before, when resolved again, then the result comes from `PLACE_CACHE` without a new geocoder query.
- Given an unresolvable place or an unreachable geocoder, when resolution is attempted, then a typed `PlaceResolutionError` is raised naming the failed step, and `None` is never returned.
- Given the `PLACE_CACHE` table, when queried, then it is confirmed as a lookup accelerator only, never authoritative over a Client's own persisted snapshot.

## Spec Change Log

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including new geocoder/cache tests
- `uv run ruff check .` -- clean
- `uv run --env-file .env alembic upgrade head` -- new migration applies cleanly against local Postgres

## Suggested Review Order

**Resolution and the historical-offset edge cases**

- Start here: cache-first, then geocode, then derive the offset -- the shape the rest of the file supports.
  [`geocoder.py:64`](../../shell/adapters/nominatim/geocoder.py#L64)

- DST fall-back and spring-forward are refused rather than silently resolved, mirroring the ambiguous-place-candidate rule below.
  [`geocoder.py:143`](../../shell/adapters/nominatim/geocoder.py#L143)

- Every failure step (geocoding, timezone lookup, cache read) is wrapped so nothing raw escapes untyped -- added after review found the cache-read path uncovered.
  [`geocoder.py:114`](../../shell/adapters/nominatim/geocoder.py#L114)
  [`geocoder.py:120`](../../shell/adapters/nominatim/geocoder.py#L120)
  [`geocoder.py:129`](../../shell/adapters/nominatim/geocoder.py#L129)

**PLACE_CACHE and transaction ownership**

- A cache write is scoped to its own `SAVEPOINT` and flushed, not committed -- a caller building other pending work on the same session (a future Client persist) can't have it silently force-committed or discarded. Added after review found the original `session.commit()` did exactly that.
  [`place_cache.py:73`](../../shell/adapters/postgres/place_cache.py#L73)

- The hand-written migration a reviewer would otherwise have to trust matches the SQLModel table by eye; a test now checks the emitted SQL directly.
  [`0002_place_cache.py:27`](../../migrations/versions/0002_place_cache.py#L27)

**The typed error surface**

- `step` is a closed `Literal`, not a free string, so a future call site can't introduce an inconsistent label.
  [`errors.py:17`](../../core/errors.py#L17)

  [`errors.py:53`](../../core/errors.py#L53)

**Port and pure types**

- The port contract: a naive local birth time in, a resolved place or an explicit candidate list out, never `None`.
  [`ports/geocoder.py:21`](../../shell/ports/geocoder.py#L21)

- `utc_offset` lives on the result, not the cached place -- the same coordinates yield a different offset for a different date.
  [`types/place.py:35`](../../core/types/place.py#L35)

**Tests**

- The DST edge cases review surfaced: an ambiguous fall-back hour and a nonexistent spring-forward hour, both refused.
  [`test_geocoder_nominatim.py:215`](../../tests/test_geocoder_nominatim.py#L215)
  [`test_geocoder_nominatim.py:232`](../../tests/test_geocoder_nominatim.py#L232)

- Proves a cache hit still re-derives the offset per birth instant rather than caching a stale one.
  [`test_geocoder_nominatim.py:128`](../../tests/test_geocoder_nominatim.py#L128)

- Proves a duplicate cache write no longer touches unrelated session state -- exercised for real against Postgres, not just SQLite, during implementation.
  [`test_place_cache.py:54`](../../tests/test_place_cache.py#L54)
