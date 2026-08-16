# Epic 2 Context: Enter a Client once and get a natal chart I can verify

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Francesco enters the five inputs for a Client, the birthplace resolves to coordinates and the UTC
offset actually in force at the birth instant (not today's offset), and a complete Natal Chart plus
the four Domain Profiles are computed once and stored permanently. A chart wheel lets him eyeball
the result against Astro.com before trusting anything built on it, birth data can be corrected
without silently invalidating past work, and a Client can be deleted along with everything derived
from them. This is the epic where correctness guardrails meet real astronomy for the first time —
everything later (transits, prose, the trust-without-reading Report) is load-bearing on this chart
being right.

## Stories

- Story 2.1: Resolve a birthplace to coordinates and the offset in force at birth
- Story 2.2: Compute a Natal Chart as a pure function
- Story 2.3: Create a Client, or fail visibly
- Story 2.4: Resolve the Ruler of every house, traditional and modern
- Story 2.5: Assemble the four Domain Profiles
- Story 2.6: See the chart wheel and check it against Astro.com
- Story 2.7: Correct birth data, and know what it invalidates
- Story 2.8: Delete a Client and everything derived from them

## Requirements & Constraints

- Client creation requires all five inputs (name, birth date, birth time to the minute, birthplace,
  plus the per-report month); no field is optional and there is no degraded path — no noon chart, no
  solar-house fallback, no house-less reading — because houses, ascendant and midheaven are
  load-bearing for three of the four Domain Profiles. Names need not be unique.
- Birthplace resolves to latitude/longitude (≥4 decimal places) and the historical, DST-aware UTC
  offset in force at the birth instant at that location, never the present-day offset. Ambiguous
  matches must be presented for an explicit choice — nothing is silently auto-picked. Resolved places
  are cached to avoid re-querying the geocoder on repeat entries. A resolution failure blocks Client
  creation entirely and names which step failed.
- Natal Chart contents: ascendant, midheaven, sign/degree/house for the ten planets, North/South
  Lunar Nodes, all twelve Placidus cusps, and natal Aspects (conjunction, sextile, square, trine,
  opposition only) within a configurable Orb (default ±7.0°, tunable ±6.0°–±8.0°). Computed exactly
  once per Client and read from storage thereafter; recomputation happens only on a birth-data
  correction.
- Correcting birth data requires an acknowledged warning that prior Reports were generated against
  the previous chart before the change applies. The superseded chart is retained and marked
  superseded, not overwritten; prior Reports stay associated with it and remain readable.
- House Rulers are resolved in both traditional and modern systems for all twelve cusps; Scorpio,
  Aquarius and Pisces cusps record both the modern ruler and the traditional co-ruler (Pluto/Mars,
  Uranus/Saturn, Neptune/Jupiter).
- Four Domain Profiles — `amore`, `lavoro`, `denaro`, `benessere` (Italian, lowercase, never
  translated) — are assembled by fixed rule from the Natal Chart and are byte-identical across
  repeated assembly of the same chart.
- The chart wheel exists for Francesco's own verification only — it is never included in a Report or
  any Client-facing export.
- Deleting a Client removes the Client record, Natal Chart (including superseded charts) and derived
  Domain Profiles completely — no soft delete, nothing left readable. Confirmation states what will
  be removed before executing. Deletion log lines carry only the Client identifier, never name or
  birth data.
- This epic's output is what the release-gating success criteria measure later: astronomical
  conformance against Astro.com reference charts, and computational determinism — identical birth
  data and configuration must always produce identical results, on any machine.

## Technical Decisions

- `core/` stays pure: no I/O, clock, network, randomness, or imports from `shell/`. The one declared
  exception is the ephemeris (Kerykeion/pyswisseph reading vendored `.se1` files inside
  `core/ephemeris/`), needed because locating cusps and positions requires iterative computation. An
  import-boundary test enforces this in CI.
- Ephemeris identity is pinned: vendored `sepl_18.se1`/`semo_18.se1`, `swe.set_ephe_path()` called
  explicitly at boot, each file SHA-256 verified, refusing to start on a mismatch — the Moshier
  fallback is never acceptable. Every stored chart records which ephemeris identity produced it.
- All time handling is UTC in the core; core functions take timezone-aware inputs only, never touch a
  system clock or a default timezone. Conversion to local time for display happens only in
  `shell/http/`, using the historical zone resolved during geocoding.
- `Client` has no optional birth fields and no partial constructor. Birthplace and historical-offset
  resolution must complete before the row is written; failure means no row at all. The Client stores
  its own immutable snapshot of resolved latitude, longitude and IANA zone. `PLACE_CACHE`
  (Postgres-backed) is a lookup accelerator only, consulted before geocoding, never a source of truth
  for a Client already persisted. Client and Natal Chart rows both use UUIDv7 primary keys.
- All astronomical tuning values (natal Orb, house system, ruler tables, etc.) live in one versioned
  `ComputationConfig` loaded from `data/computation.toml` and passed explicitly into every core
  function that needs it — never read ambiently, never hardcoded in a function. Its version and
  content hash are recorded on every stored chart.
- Geocoding uses a `Geocoder` port with a Nominatim adapter; historical offset/zone resolution uses
  `timezonefinder` plus `zoneinfo`.
- Ruler and Domain Profile assembly are pure functions of the Natal Chart and the passed
  `ComputationConfig`.
- The chart wheel is rendered in `shell/http/` (presentation, not computation) — it is not part of
  `core/`.

## UX & Interaction Patterns

- Client creation form takes name, birth date, exact birth time (to the minute) and birthplace, all
  required, with no way to submit a partial record.
- When a birthplace resolves to multiple candidates, Francesco is shown the candidates and must pick
  one explicitly before the Client is persisted.
- Correcting birth data shows the consequences (prior Reports were generated against the old chart)
  before the change is applied, and proceeds only after acknowledgment.
- Deletion asks for confirmation and states exactly what will be removed before executing.
- The chart wheel view shows positions, cusps and natal Aspects for Francesco's own eyeballing against
  Astro.com — it has no export or Client-facing route.

## Cross-Story Dependencies

- Story 2.3 (Create a Client) depends on Story 2.1 (birthplace/offset resolution) and Story 2.2
  (chart computation) — a Client is persisted only once both resolve successfully.
- Story 2.4 (Rulers) and Story 2.5 (Domain Profiles) depend on Story 2.2's Natal Chart; Story 2.5
  additionally depends on Story 2.4's Ruler resolution.
- Story 2.6 (chart wheel) depends on a Client with a stored Natal Chart (Story 2.3).
- Story 2.7 (correction) re-runs Stories 2.1 and 2.2's resolution/computation logic against corrected
  inputs and depends on Story 2.3 existing.
- Story 2.8 (deletion) must cascade across every table this epic introduces, and is designed so any
  later Client-referencing table added by a future epic is required to join the same cascade.
- This epic depends on Epic 1's guardrails (import-boundary test, ephemeris SHA-256 boot assertion,
  `data/computation.toml`, conformance fixture harness) already being in place. Domain Profile
  assembly is independent of the transit engine (Epic 3) and can proceed in parallel with the rest of
  this epic's chart work.
