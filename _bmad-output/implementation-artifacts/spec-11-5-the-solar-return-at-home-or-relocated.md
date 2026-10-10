---
title: '11-5 The solar return, at home or relocated'
type: 'feature'
created: '2026-10-10'
status: 'done'
baseline_commit: '5ebcaca130cbfb7332a71de9ec3f5a4228f0ff50'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The annual consultation needs the solar return chart for where the customer spends the birthday, read against the natal chart, and the API has no such endpoint.

**Approach:** Add `POST /api/v1/charts/solar-return` on an 11.2 subject plus `year` and an optional `location`. A new pure `core/ephemeris/returns.py` finds the return instant with `swe.solcross_ut`; the existing chart code casts the return chart; a pure comparison reads it against the natal chart.

## Boundaries & Constraints

**Always:** Request `{subject, year, location?}`; `location` is a `PlaceModel` and defaults to the subject's birthplace. Response `meta`, `subject`, `return_instant_utc`, `location`, `chart`, `comparison`; body `canonical_json_bytes`, byte-identical on repeat. `chart` is the 11.2 known-time shape (`known_chart_json`), cast at the return instant and `location`, Placidus, aspects within `orbs.natal`. Return instant: the first Sun crossing of the natal Sun's unrounded tropical longitude at or after local 00:00 two days before the birthday in `year`, in the birthplace zone (28 February is the birthday of a 29 February birth in a non-leap year); a whole-second UTC `Z` string. `comparison`: `rs_ascendant_in_natal_house` (int); `rs_planets_in_natal_houses` `[{body, house}]` for the ten planets and both nodes; `rs_to_natal_aspects` `[{rs_body, natal_body, aspect, orb}]` over RS and natal planets, nodes, ascendant and midheaven, five majors, `orbs.natal`, no applying flag. `time_known: false` ⇒ `birth_time_required`, field `subject.time_known` (computation-tables wins over change-request §4.7). `year` below the birth year ⇒ `invalid_request` on `year`; outside 1801–2399 or a crossing beyond the ephemeris ⇒ `ephemeris_out_of_range` on `year`. A DST gap or fold in the birth time ⇒ `invalid_request` on `subject.birth_time`. `returns.py` binds the verified ephemeris path before `solcross_ut` and confirms the result through the checked `_calc_body` path (no silent Moshier). Sync handler; nothing stored or logged about the subject.

**Ask First:** Any change to existing orbs, natal, transit or synastry output.

**Never:** Touch the `RunDriver`, add a table or migration, feed results into Payload/Generator/Gate, add targeted solar return or an applying flag, make the return-instant rule request-selectable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Birthplace | no `location` | `location` is the birthplace; chart cast there | N/A |
| Relocated | `location` elsewhere | same `return_instant_utc`; different angles and cusps | N/A |
| Return instant | any valid input | RS Sun equals natal Sun within 0.0001° | N/A |
| Near New Year | birthday 31 Dec / 1 Jan | instant in the requested `year`, not a neighbour | N/A |
| Leap day | born 29 Feb, `year` non-leap | instant near 28 Feb–1 Mar, found | N/A |
| Unknown time | `time_known: false` | none | `birth_time_required`, `subject.time_known` |
| Early year | `year` < birth year | none | `invalid_request`, `year` |
| Out of span | `year` 1700 / 2400 | none | `ephemeris_out_of_range`, `year` |
| Bad subject | birth time in DST gap | none | `invalid_request`, `subject.birth_time` |
| Repeat | identical request | identical bytes, no row written | N/A |

</frozen-after-approval>

## Code Map

- `core/ephemeris/returns.py` (new) -- `solar_return_instant(birth_utc, search_start_utc)`; `_julian_day_ut`, `_calc_body`, `swe.jdut1_to_utc`; `bind_verified_ephemeris_path_to_current_thread` (known pitfall).
- `core/ephemeris/chart.py` -- `compute_natal_chart` casts the RS chart; `_house_for_longitude` for the RS ascendant; `PLANET_BODIES`.
- `core/synastry/inter_aspects.py` (`known_points`, `inter_aspects`) and `overlays.py` (`overlay`) -- reused for the comparison; `core/types/synastry.py` -- `OverlayEntry`.
- `core/returns/comparison.py`, `core/types/returns.py` (new) -- pure `compare_to_natal(rs_chart, natal_chart, orb)` and the `RsToNatalAspect`/comparison types.
- `shell/http/api/solar_return.py` (new), `__init__.py` (register) -- endpoint, search-start date, year checks.
- `shell/http/api/charts.py` (`jsonable`, `known_chart_json`, `subject_json`), `subject.py` (`parse_subject`, `known_time_instant`, `PlaceModel`, `quantize_coordinate`), `errors.py` (`ErrorCode.BIRTH_TIME_REQUIRED`), `meta.py`.
- `tests/test_api_synastry.py` -- app/bearer/FK-engine fixtures to copy; `tests/test_api_skeleton.py` route-walk and error-code lists; `tests/test_import_boundary.py`, `tests/test_concurrency_boundary.py`.

## Tasks & Acceptance

**Execution:**
- [x] `core/ephemeris/returns.py` -- return-instant search, path-bound, verified against the natal Sun
- [x] `core/types/returns.py`, `core/returns/comparison.py` -- pure comparison from existing helpers
- [x] `shell/http/api/solar_return.py`, `__init__.py` -- endpoint, location default, error mapping
- [x] `tests/test_returns_core.py`, `tests/test_api_solar_return.py` -- every matrix row, repeat bytes, row count, sync route, a thread-bound path check
- [x] `tests/test_returns_core.py` -- check the three transcribed fixtures (`solar-return-*.toml`, `solar_return_of` key, already added with the `test_conformance.py` skip): instant ±2 s, planets 0.005°, angles and cusps 0.005°
- [x] `sprint-status.yaml` -- 11-5 to `review`

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access, concurrency and route-walk guards.
- Given the three Astro.com fixtures (leap-day birthplace, same chart relocated to Milan, 1 January birth in 2027), when the endpoint's core runs, then instant, planets, angles and cusps match within the fixture tolerances.

## Spec Change Log

## Design Notes

The crossing target is the natal Sun straight from `calc_ut`, not the 4-place decimal, which could move the instant by seconds. Searching from two days before the birthday always lands on the nearest return because the Sun crosses a given longitude once a year and the birthday's date drift is under a day.

Fixtures were transcribed from Astro.com (btyp=32) during planning and cross-checked against `swe` (instants within 1 s, planets within 1", angles within 0.004°). Three charts cover the four epic cases: the leap-day birthplace chart is also the plain birthplace case. Invariant tests (RS Sun = natal Sun, relocation changes only angles and houses) sit beside them.

## Verification

**Commands:**
- `uv run pytest tests/test_returns_core.py tests/test_api_solar_return.py tests/test_import_boundary.py tests/test_concurrency_boundary.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**Endpoint**

- Entry point: year checks, search start, return chart, comparison, canonical bytes.
  [`solar_return.py:65`](../../shell/http/api/solar_return.py#L65)

- Search starts local midnight two days before the birthday, in the birthplace zone.
  [`solar_return.py:82`](../../shell/http/api/solar_return.py#L82)

**Return instant**

- First Sun crossing of the unrounded natal Sun, path bound first.
  [`returns.py:45`](../../core/ephemeris/returns.py#L45)

- Verified through the checked ephemeris path, so a silent Moshier fallback fails.
  [`returns.py:76`](../../core/ephemeris/returns.py#L76)

**Reading it against the natal chart**

- Natal houses for the RS ascendant and bodies, aspects via synastry helpers.
  [`comparison.py:23`](../../core/returns/comparison.py#L23)

- Result type names each side, no applying flag.
  [`returns.py:20`](../../core/types/returns.py#L20)

**Tests**

- Three Astro.com fixtures: instant, planets, angles, cusps.
  [`test_returns_core.py:44`](../../tests/test_returns_core.py#L44)

- API matrix: relocation, New Year, leap day, errors, statelessness.
  [`test_api_solar_return.py:100`](../../tests/test_api_solar_return.py#L100)
