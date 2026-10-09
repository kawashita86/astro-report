---
title: '11-2 Resolve a place and compute a natal chart on request'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '6385001a2087407558eb2fd45d77877af6a1abf7'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `/api/v1` skeleton has no endpoint, so the alerenzi plugin can neither confirm a birthplace nor get computed natal positions for a consultation draft.

**Approach:** Add `POST /api/v1/places/resolve` and `POST /api/v1/charts/natal` on the skeleton, reusing the Nominatim adapter, `compute_natal_chart` and `resolve_house_rulers`. Add a separate time-unknown chart type in `core/ephemeris/`, and the subject parsing and local-to-UTC conversion that Stories 11.3–11.5 reuse.

## Boundaries & Constraints

**Always:** Bodies, signs and aspects use glossary ids verbatim; angles are 4-place decimal strings in `[0, 360)`; coordinates in responses are quantized to 4 places (so a cache hit and a miss give identical bytes); instants are ISO-8601 `Z`; `utc_offset` is `±HH:MM`. Bodies are `canonical_json_bytes`; every chart response carries `build_meta(...)`. The subject is `{label, birth_date, birth_time, time_known, place:{latitude, longitude, iana_zone, display_name}}`; `birth_time` is required when `time_known` is true. Local time is converted with the offset in force at that instant; a DST gap or fold is `invalid_request` with `field: "subject.birth_time"`. A birth year outside the vendored ephemeris span is `ephemeris_out_of_range`, field `subject.birth_date`. Handlers are sync, create no thread, executor or task, and compute only through `core/ephemeris/` entry points that bind the verified ephemeris path. Resolve lists every candidate with its IANA zone, cache first; zero matches is `place_unresolved`. `time_known: false`: the chart is the noon civil-time chart; `ascendant`, `midheaven`, `houses` and every `house` field are `null`; every body carries `range:{from,to}` (longitude at local 00:00 and next 00:00) and `sign_uncertain`; aspects exclude angles and every aspect involving the Moon. The only row ever written is `PLACE_CACHE`, and the natal endpoint writes none; a repeat request returns a byte-identical body.

**Ask First:** Caching ambiguous (multi-candidate) results — today only an unambiguous match is cached (AD-16), so a repeat ambiguous query re-queries Nominatim. Any change to `PLACE_CACHE` or any migration.

**Never:** Persist or log a subject, birth data or coordinate. Add a table or a migration. Touch the `RunDriver`. Feed an API result into Payload assembly, the Generator or the Gate. Change what `compute_natal_chart` computes. Accept a second house system.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Known time | Milan 1985-03-12 14:30, `time_known: true` | `meta`, `subject` (echoes `birth_instant_utc`, `utc_offset`), `chart` equal field for field to `compute_natal_chart` + house rulers; matches the Astro.com natal fixture | N/A |
| Unknown time | same, `time_known: false` | noon chart, ranges, omissions as above | N/A |
| Sign boundary | a body crossing a sign during the birth day | `sign_uncertain: true` for it | N/A |
| Moon sign change | birth day with a Moon ingress | Moon `range` spans both signs, `sign_uncertain: true` | N/A |
| DST gap / fold | local time that is skipped / repeated | none | `invalid_request`, `subject.birth_time` |
| Missing time | `time_known: true`, no `birth_time` | none | `invalid_request`, `subject.birth_time` |
| Bad zone / coordinate | unknown IANA zone, lat outside ±90 | none | `invalid_request`, field names the key |
| Out of ephemeris | year 1700 | none | `ephemeris_out_of_range` |
| Place, many matches | ambiguous query | all candidates, each with zone | N/A |
| Place, none | unmatched query | none | `place_unresolved` |
| Place, repeat | cached unambiguous query | same bytes, Nominatim not called | N/A |

</frozen-after-approval>

## Code Map

- `core/ephemeris/chart.py` -- `compute_natal_chart` (l.104): the known-time engine, reused unchanged; `_PLANET_BODIES`, `_sign_and_degree`, `_detect_aspects` are the pieces the time-unknown type reuses (promote what is needed rather than copy).
- `core/ephemeris/positions.py` -- `_calc_body` binds the verified path per thread; `_julian_day_ut`, `QUANTUM`.
- `core/types/chart.py` -- add the time-unknown result type (separate from `NatalChart`, no angles/houses fields). `core/types/place.py` -- add the candidate type carrying the zone.
- `core/domains/rulers.py:40` -- `resolve_house_rulers(chart, config)`.
- `shell/adapters/nominatim/geocoder.py` -- `NominatimGeocoder`; `_historical_offset` (l.166) holds the gap/fold logic to extract; `_zone_for`, `_geocode`, `_lookup_cache` for a new `list_candidates`. `shell/adapters/postgres/place_cache.py` -- `store_resolved_place` only flushes, so the endpoint commits.
- `shell/http/routes/clients.py:283,423` -- `get_geocoder` dependency pattern and the `(local - offset).replace(tzinfo=UTC)` conversion; `shell/http/app.py:145` `get_session`.
- `shell/http/api/{router,errors,meta}.py` -- mount routes here; `map_exception` gets the new typed error; `build_meta` is used as is (no synastry orb yet).
- `core/errors.py` -- new typed error for gap/fold. `tests/test_geocoder_nominatim.py` must stay green. `tests/conformance/fixtures/near-midnight-birth.toml`, `tests/test_conformance.py:157` (`_shape_chart_for_conformance`) -- the Astro.com natal fixture; `tests/_fk.py`, `tests/test_api_skeleton.py` -- fixtures and fake-injection patterns.

## Tasks & Acceptance

**Execution:**
- [ ] `core/errors.py`, `shell/local_time.py` -- typed gap/fold error and a pure-shell `local → (utc instant, offset)` function; geocoder delegates and re-raises its existing `PlaceResolutionError` messages -- one conversion, two consumers
- [ ] `core/types/chart.py`, `core/types/place.py`, `core/ephemeris/time_unknown.py` -- time-unknown types and `compute_time_unknown_chart(noon_utc, day_start_utc, day_end_utc, config)`; pure
- [ ] `shell/adapters/nominatim/geocoder.py` -- `list_candidates(query)` (cache first, otherwise all geocoder matches with zone; writes the cache only for a single match as today)
- [ ] `shell/http/api/subject.py`, `places.py`, `charts.py` -- request models, validation to `invalid_request` fields, endpoints, serialisers; `errors.py` maps the new error
- [ ] `tests/test_api_natal.py`, `tests/test_time_unknown_chart.py`, `tests/test_local_time.py` -- every matrix row; a row-count test over every table (only `place_cache` may grow, natal grows nothing); repeat-bytes; fixture match; sign-boundary and Moon-sign-change cases
- [ ] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 11-2 to `review` when done

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access, concurrency and route-walk guards.
- Given a place-resolve or natal request, when handled, then no log record contains the query, birth data or coordinates.

## Spec Change Log

## Design Notes

`time_known: true` calls `compute_natal_chart` with the same inputs the Client flow uses, so equality holds by construction; the test pins it. The time-unknown type takes three UTC instants computed by the shell (noon, 00:00, next 00:00 local; each with its own offset, only noon strict about gap/fold), so `core/` does no timezone work. Null is used (not omitted keys) for the omitted angle and house fields so the shape is stable for the plugin.

## Verification

**Commands:**
- `uv run pytest tests/test_api_natal.py tests/test_time_unknown_chart.py tests/test_local_time.py tests/test_geocoder_nominatim.py tests/test_api_skeleton.py tests/test_import_boundary.py tests/test_concurrency_boundary.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**Local civil time to UTC**

- One conversion for gap/fold, shared by the geocoder and the API; `strict=False` for day boundaries.
  [`local_time.py:30`](../../shell/local_time.py#L30)

- The geocoder now delegates here and keeps its old messages.
  [`geocoder.py:211`](../../shell/adapters/nominatim/geocoder.py#L211)

- Gap/fold becomes `invalid_request` on `subject.birth_time`.
  [`errors.py:97`](../../shell/http/api/errors.py#L97)

**Natal endpoint and request parsing**

- Entry point: known/unknown branch, meta, canonical bytes.
  [`charts.py:115`](../../shell/http/api/charts.py#L115)

- Subject validation, ephemeris span check, instants.
  [`subject.py:119`](../../shell/http/api/subject.py#L119)

**Time-unknown chart (pure core)**

- Noon chart with day-range, no angles or houses, Moon aspects excluded.
  [`time_unknown.py:37`](../../core/ephemeris/time_unknown.py#L37)

- Separate result type, so no `NatalChart` field can be faked.
  [`chart.py:135`](../../core/types/chart.py#L135)

**Place resolution**

- Cache first, else every match with its zone; cache written only for a single match.
  [`geocoder.py:138`](../../shell/adapters/nominatim/geocoder.py#L138)

- Endpoint commits the session, since the cache write only flushes.
  [`places.py:69`](../../shell/http/api/places.py#L69)

**Tests**

- Field-for-field engine equality, fixture match, row-count and repeat-bytes checks.
  [`test_api_natal.py:122`](../../tests/test_api_natal.py#L122)
