---
title: 'Date every Station and know what is standing retrograde'
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'bcf9721a4f877030b812aa32b442e480d7ac1510'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The month scan (Story 3.1) locates Aspects but says nothing about retrograde motion
itself — Francesco cannot yet name the exact moment a body turns retrograde or direct, nor record a
body that is retrograde all month with no turn inside it, so *Giorni di attenzione* and the general
energy section have no real Stations to work from.

**Approach:** A new pure `core/transits/stations.py` function scans each configured transiting body's
longitudinal velocity (dλ/dt, from the same `_calc_body` speed value Story 3.1 already reads) across
the analyzed month, locating each direction-change instant by the same coarse-grid-plus-bisection
method `aspects.py` uses for perfection instants, and records a standing condition for a body
retrograde the whole month with no turn inside it.

## Boundaries & Constraints

**Always:**
- Lives in `core/transits/stations.py` (new module), pure (AD-1): no I/O, clock, network, randomness —
  only `swisseph` and what is passed in (month interval, `ComputationConfig`). No `NatalChart` input —
  retrograde motion depends only on the transiting body's own velocity.
- Scans the same body set Story 3.1 scans (`config.bodies.fast` + `.slow`; transiting Moon excluded —
  it never stations).
- Retrograde condition: `dλ/dt < 0`, read from `_calc_body`'s existing `speed` return value — no new
  swisseph call shape.
- A Station record carries: the body, the direction of the turn (the motion *entered*, `"retrograde"`
  or `"direct"`), the bisected exact UTC instant of the sign change, and the zodiacal degree at that
  instant.
- A body retrograde for the entire analyzed month with no sign change inside it is recorded as a
  standing condition (body + the month interval, clamped exactly like `TransitAspectEvent.orb_entry_at`
  clamps to a boundary already in view) — never silently omitted.
- A body direct the entire month is not recorded at all (nothing to report — matches how Story 3.1
  never emits absence).
- Deterministic: identical month + config produce an identical output tuple every run.

**Ask First:** none identified during planning.

**Never:**
- No Ingress/Lunation detection (Stories 3.3/3.4) and no Report Payload assembly or HTTP route.
- Never treat Astro.com's own station-time claim as a conformance oracle — it publishes no exact
  instant, only a last-seen-direct / first-seen-retrograde bracket (see the fixture). Conformance
  checks that the computed instant falls inside that bracket, not against a fabricated exact value.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Direct-to-retrograde turn inside the month | speed sign changes + to − | Station recorded: body, `direction="retrograde"`, bisected instant, longitude | N/A |
| Retrograde-to-direct turn inside the month | speed sign changes − to + | Station recorded: body, `direction="direct"`, bisected instant, longitude | N/A |
| Retrograde the whole month, no turn inside it | speed stays < 0 across the interval | standing condition recorded with the (clamped) month span, not omitted | N/A |
| Direct the whole month | speed stays > 0 across the interval | nothing recorded for that body | N/A |
| Two turns for the same body in one month | speed changes sign twice (station, then station back) | two distinct Station records, never merged | N/A |

</frozen-after-approval>

## Code Map

- `core/transits/aspects.py` -- `find_transit_aspects:94`, `_TRANSIT_BODY_IDS:69` (reuse this body-id
  map rather than redefining it — `test_conformance.py` already imports it across modules, so a private
  cross-module import is an accepted pattern here), `_GRID_STEP:78`/`_BISECTION_ITERATIONS:88` (mirror
  the same coarse-grid-plus-bisection constants/approach for the speed sign-change search).
- `core/ephemeris/positions.py` -- `_calc_body:67` already returns `(longitude, speed)`; `speed`'s sign
  is the retrograde test. `_julian_day_ut:53`, `_to_normalized_decimal:84` for the same instant/decimal
  handling Story 3.1 already established.
- `core/types/transits.py` -- `TransitAspectEvent:21` -- add `Station` and `StandingRetrograde` frozen
  dataclasses alongside it, following the same docstring-driven style.
- `core/types/computation.py` -- `ComputationConfig.bodies.fast/slow:55` -- same body config Story 3.1
  reads; no new config needed.
- `tests/conformance/fixtures/retrograde-station-month.toml:15-23` -- `expected.stations` (Mercury,
  `bracket_start_date`/`bracket_end_date`/`_longitude`/`_retrograde`) -- the one fixture with a real
  Station; `two-lunations-month.toml` and `no-lunations-month.toml` have no `expected.stations` table
  (both real-checked against an empty computed tuple).
- `tests/test_conformance.py` -- `_transit_events_for_month_fixture:267` (shaping pattern to mirror),
  `_IMPLEMENTED_MONTH_SCOPE:312`, `compute_output_for:315`, `_expected_for_scope:346`, `_fixture_params:372`
  (the `"remainder"` xfail scope currently bundles stations/lunations/transit_positions together — this
  story splits out a real `"stations"` scope, narrowing `"remainder"` to lunations/transit_positions
  only, exactly as Story 3.1 narrowed the original whole-fixture xfail down to `"remainder"`).
- `tests/test_transit_aspects.py` -- structure/naming precedent for `tests/test_stations.py` (new): one
  test per I/O-matrix row plus a determinism test, using a monkeypatched synthetic ephemeris.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/transits.py` -- add `Station` (`body`, `direction`, `station_at: datetime`,
  `longitude: Decimal`) and `StandingRetrograde` (`body`, `retrograde_start_utc`, `retrograde_end_utc`)
  frozen dataclasses -- distinct shapes because a turn and a whole-month condition carry different facts.
- [x] `core/transits/stations.py` (new) -- `find_stations(month_start_utc, month_end_utc, config) ->
  tuple[Station | StandingRetrograde, ...]`: per configured body, samples speed on the same coarse grid
  `aspects.py` uses, bisects each sign change to sub-second precision, and emits a `StandingRetrograde`
  for any body whose speed never changes sign across the whole interval and is negative throughout.
- [x] `tests/test_stations.py` (new) -- unit tests for the I/O matrix rows above, plus a determinism
  test (repeated identical-input runs produce an identical tuple).
- [x] `tests/test_conformance.py` -- add a real `"stations"` scope: shape `find_stations()`'s output for
  each month fixture and assert the computed Station's `station_at` falls strictly inside the fixture's
  `bracket_start_date`/`bracket_end_date` window and `direction` matches `motion` (bracket comparison,
  not exact equality — the generic `compare()` dict-equality path doesn't fit a bracket, so this needs
  its own assertion, not a reshaped dict fed through `compare()`); narrow `_fixture_params()`'s
  `"remainder"` xfail scope to exclude `stations`.

**Acceptance Criteria:**
- Given the analyzed month interval and a `ComputationConfig`, when retrograde condition is determined,
  then it is derived from `_calc_body`'s longitudinal velocity — a body is retrograde where dλ/dt < 0.
- Given a body whose longitudinal velocity changes sign within the month, when the Station is located,
  then it records the body, the direction of the turn, the exact UTC instant, and the zodiacal degree.
- Given a body retrograde for the entire month with no Station inside it, when the scan completes, then
  it is recorded as a standing condition with the month's retrograde span, not omitted.
- Given the month fixture that targets a retrograde station, when the conformance runner executes, then
  the computed Station matches Astro.com on body, direction, and falls inside the transcribed bracket on
  date/time and degree.

## Spec Change Log

## Design Notes

Mirrors Story 3.1's own stated plan (its Design Notes: "symmetric with how Stations will be located in
Story 3.2"): sample `_calc_body`'s speed on the existing 6-hour grid, bisect `f(t) = speed(t)` for a
sign change (no target-angle offset needed — zero itself is the root). No natal chart is threaded
through this module at all, unlike `aspects.py` — retrograde is a fact about the transiting body alone.

## Suggested Review Order

**Scan algorithm (the core design)**

- Entry point: per configured body, samples speed on a 6-hour grid and bisects each sign change.
  [`stations.py:67`](../../core/transits/stations.py#L67)

- The half-open-interval fix: a sign change landing exactly on `month_end_utc` is excluded, not reported.
  [`stations.py:146`](../../core/transits/stations.py#L146)

- A body with zero turns and negative speed throughout is recorded as standing retrograde, not omitted.
  [`stations.py:159`](../../core/transits/stations.py#L159)

- Shared low-level helpers: `_require_utc_interval`, `_build_grid`, `_speed_at`, `_bisect` -- mirror `aspects.py`'s shapes for a simpler root (zero, not a target-angle offset).
  [`stations.py:171`](../../core/transits/stations.py#L171)

**Result types**

- `Station`/`StandingRetrograde`: distinct shapes for a turn vs. a whole-month condition -- deliberately no merged/optional-field design.
  [`transits.py:55`](../../core/types/transits.py#L55)

**Conformance wiring (bracket comparison, not dict equality)**

- Dedicated test, not the generic `compare()` path: Astro.com gives a bracket, never an exact station instant.
  [`test_conformance.py:517`](../../tests/test_conformance.py#L517)

- Matches each fixture entry to the computed Station whose instant falls inside *that entry's own* bracket, not by body name alone -- robust to a future multi-turn fixture.
  [`test_conformance.py:546`](../../tests/test_conformance.py#L546)

- Longitude check: circular distance to the nearer bracket endpoint, generous enough for honest drift but two-figure-tighter than the sign-error class it must catch.
  [`test_conformance.py:465`](../../tests/test_conformance.py#L465)

**Fixture data correction (pre-existing transcription bug this story's real computation caught)**

- Mercury's station-bracket longitude was one zodiac sign short, the same bug class already fixed for Mars/Jupiter in this file.
  [`retrograde-station-month.toml:23`](../../tests/conformance/fixtures/retrograde-station-month.toml#L23)

**Tests (peripheral)**

- One test per I/O-matrix row, using the same monkeypatched-`swe.calc_ut` technique as `test_transit_aspects.py`.
  [`test_stations.py:216`](../../tests/test_stations.py#L216)

- Regression test for the month-end boundary fix, verified to actually catch the bug before the fix was reapplied.
  [`test_stations.py:258`](../../tests/test_stations.py#L258)

- Boundary-equality case (`month_start == month_end`), added alongside the existing reversed-order test.
  [`test_stations.py:372`](../../tests/test_stations.py#L372)

