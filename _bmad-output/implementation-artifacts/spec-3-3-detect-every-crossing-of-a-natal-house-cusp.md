---
title: 'Detect every crossing of a natal house cusp'
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '1ee1692efdd0e6884c3aa117d6dfdd374cf6edb7'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 3.1/3.2 locate Aspects and Stations across the analyzed month, but say nothing
about a transiting body moving through the twelve natal houses themselves -- Francesco cannot yet
name the exact moment a planet enters a new natal house, including a retrograde re-entry into one it
already left, so the day lists and *Energia generale* section have no real Ingresses to work from.

**Approach:** A new pure `core/transits/ingresses.py` function scans each configured transiting body's
longitude against each of the natal chart's twelve Placidus cusp longitudes across the analyzed month,
using the same coarse-grid-plus-bisection method `aspects.py`/`stations.py` already use, locating each
zero-crossing of the signed offset from a cusp as one Ingress -- direction of the crossing (forward vs.
retrograde) determines which house was departed and which was entered.

## Boundaries & Constraints

**Always:**
- Lives in `core/transits/ingresses.py` (new module), pure (AD-1): no I/O, clock, network, randomness --
  only `swisseph` (via existing helpers) and what is passed in (`NatalChart`, the month interval,
  `ComputationConfig`).
- Scans the same body set Stories 3.1/3.2 scan (`config.bodies.fast` + `.slow`; transiting Moon
  excluded -- it never gets an Ingress here, only Lunations, Story 3.4).
- An Ingress record carries: the body, the house departed, the house entered, and the bisected exact
  UTC instant of the crossing -- no longitude field (unlike `Station`); the crossed cusp's longitude is
  already exact and known from `NatalChart.houses`, never re-derived per event.
- A crossing is detected identically for direct and retrograde motion; repeated crossings of the same
  cusp within the month are each a separate, unmerged Ingress record (never deduplicated).
- Deterministic: identical month + natal chart + config produce an identical output tuple every run.

**Ask First:** Populating `expected.ingresses` fixture bracket data (see Tasks) requires an Astro.com
ephemeris walk to bracket a real crossing date, the same way Story 3.2 bracketed a Station -- if no
authenticated Astro.com session is available in this environment, HALT and ask the human to supply the
bracket (body, month, last-seen-in-house-A date, first-seen-in-house-B date) rather than fabricating one.

**Never:**
- No Lunation detection (Story 3.4) and no Report Payload assembly or HTTP route.
- Never treat Astro.com's own house-position display as a conformance oracle for an exact ingress
  instant -- bracket it (last-seen-in-house-A / first-seen-in-house-B), never a fabricated exact value.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Direct crossing into the next house | longitude offset from a cusp changes − to + | Ingress recorded: body, house departed, house entered = cusp's own house, exact instant | N/A |
| Retrograde crossing back into the previous house | longitude offset from a cusp changes + to − | Ingress recorded: body, house departed = cusp's own house, house entered = previous house | N/A |
| Same cusp crossed twice in one month (there and back) | offset sign flips twice | two distinct Ingress records, never merged | N/A |
| A crossing landing exactly on `month_end_utc` | offset reaches zero only at the excluded final grid probe | not reported (half-open interval, mirrors `stations.py`'s own boundary fix) | N/A |
| No body crosses a given cusp all month | offset never changes sign for that (body, cusp) pair | nothing recorded for that pair | N/A |

</frozen-after-approval>

## Code Map

- `core/transits/stations.py` (whole file) -- nearest precedent: a scalar zero-crossing scan (no
  in-orb window, unlike `aspects.py`), same `_GRID_STEP`/`_BISECTION_ITERATIONS` constants mirrored
  locally (not imported), same `_require_utc_interval`/`_build_grid`/`_bisect` shapes to mirror
  verbatim, same half-open-interval guard at `stations.py:146` (`station_at < month_end_utc`).
- `core/transits/aspects.py` -- `_TRANSIT_BODY_IDS:69` (reuse, cross-module import, accepted pattern),
  `_normalize_signed:230` (mirror this exact `(-180, 180]` wrap for the signed offset from a cusp
  longitude; target is always 0, so no `_signed_offset`/`_target_branches` machinery is needed).
- `core/types/chart.py` -- `NatalChart.houses:101` (`tuple[HouseCusp, ...]`, already ordered by
  `number` 1..12 per `core/ephemeris/chart.py:131-133`, so `houses[n-1].longitude` is house `n`'s cusp
  directly -- no lookup helper needed).
- `core/ephemeris/positions.py` -- `_calc_body:67` (`longitude` is all this module reads; unlike
  `stations.py` it never reads `speed`), `_julian_day_ut:53`.
- `core/types/transits.py` -- `Station:55`/`StandingRetrograde:76` -- add `Ingress` frozen dataclass
  alongside them, same docstring-driven style.
- `core/types/computation.py` -- `ComputationConfig.bodies.fast/slow:55` -- same body config Stories
  3.1/3.2 read; no new config needed.
- `tests/test_conformance.py` -- `_transit_events_for_month_fixture:282` (shaping precedent),
  `test_stations_fall_within_conformance_fixture_brackets:517` and its helpers
  `_stations_for_month_fixture:483`/`_station_bracket_utc:493`/`_month_fixture_params:504` (mirror this
  whole dedicated-test shape -- bracket comparison, not the generic `compare()` path -- rather than
  wiring through `compute_output_for`/`_fixture_params`), `_IMPLEMENTED_MONTH_SCOPE:330`/`_STATIONS_KEY:337`
  (add an `_INGRESSES_KEY` excluded from `"remainder"` the same way).
- `tests/conformance/fixtures/*.toml` -- all three month fixtures share the same `anchor_natal_fixture`
  (`near-midnight-birth`, cusps at `tests/conformance/fixtures/near-midnight-birth.toml:67-113`); add one
  `expected.ingresses` bracket entry to whichever of the three most plausibly shows a fast body crossing
  a cusp within its month (identify during implementation by running `find_ingresses()` against each).
- `tests/test_stations.py` (whole file) -- structure/naming/monkeypatch precedent for `tests/test_ingresses.py`
  (new): one test per I/O-matrix row plus a determinism test, `_patch_calc_ut:61` technique.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/transits.py` -- add `Ingress` (`body`, `house_departed`, `house_entered`,
  `crossed_at: datetime`) frozen dataclass.
- [x] `core/transits/ingresses.py` (new) -- `find_ingresses(natal_chart, month_start_utc, month_end_utc,
  config) -> tuple[Ingress, ...]`: per configured body and each of the twelve natal cusps, bisects each
  sign change of the signed longitude offset from that cusp on the same coarse grid `stations.py` uses.
- [x] `tests/test_ingresses.py` (new) -- unit tests for the I/O matrix rows above, plus determinism.
- [x] `tests/test_conformance.py` -- add `_INGRESSES_KEY = "ingresses"`, exclude it from `"remainder"`'s
  slice, and add a dedicated `test_ingresses_fall_within_conformance_fixture_brackets` mirroring
  `test_stations_fall_within_conformance_fixture_brackets` (match by body + house_departed/entered
  falling inside the entry's own bracket window).
- [x] One month fixture's `.toml` -- add an `expected.ingresses` bracket entry (body, house_departed,
  house_entered, bracket_start_date, bracket_end_date), transcribed per the Ask First note above.

**Acceptance Criteria:**
- Given the analyzed month interval and a Client's twelve Placidus cusps, when the scan runs, then each
  crossing is recorded with the body, house departed, house entered, and exact UTC instant.
- Given a retrograde crossing back across an already-crossed cusp, when the scan runs, then it is
  detected and recorded the same way as a direct crossing, and repeated crossings of the same cusp are
  each a separate Ingress.
- Given the month fixture carrying the transcribed bracket, when the conformance runner executes, then
  the computed Ingress falls inside that bracket on date and matches on house departed/entered.

## Spec Change Log

**2026-08-19 (implementation):** All code/test tasks done; the fixture-bracket task is HALTED per the
spec's own Ask First note -- no authenticated Astro.com session was available in this implementation
environment. Running the real, newly-implemented `find_ingresses()` against each of the three month
fixtures' real ephemeris (not Astro.com) surfaced these real candidate crossings, any of which is ready
to bracket the next time an Astro.com session is available (walk day-by-day around the given UTC instant
to find the last-seen-in-house-departed date and first-seen-in-house-entered date, the same way
`retrograde-station-month.toml`'s Mercury station was bracketed):

- `retrograde-station-month` (2022-12, anchor `near-midnight-birth`): mercury house 3 -> 4 at
  2022-12-09T03:01 UTC; venus house 3 -> 4 at 2022-12-12T18:29 UTC; sun house 3 -> 4 at
  2022-12-25T02:51 UTC.
- `two-lunations-month` (2023-08, anchor `near-midnight-birth`): mercury house 11 -> 12 at
  2023-08-02T05:54 UTC; sun house 11 -> 12 at 2023-08-29T10:12 UTC.
- `no-lunations-month` (2018-02, anchor `near-midnight-birth`): mercury house 4 -> 5 at
  2018-02-03T22:46 UTC; venus house 5 -> 6 at 2018-02-15T15:09 UTC; mercury house 5 -> 6 at
  2018-02-21T08:28 UTC; sun house 5 -> 6 at 2018-02-24T12:17 UTC.

Once a human supplies a bracket (last-seen-in-house-departed date, first-seen-in-house-entered date) for
any one of these, add it to that fixture's `.toml` as an `expected.ingresses` entry (`body`,
`house_departed`, `house_entered`, `bracket_start_date`, `bracket_end_date`) -- the dedicated conformance
test is already wired in and will pick it up with no further code changes.

**2026-08-19 (bracket added):** With an authenticated Astro.com session available (via claude-in-chrome,
user's own account), bracketed the first candidate above directly: `retrograde-station-month.toml` now
carries `expected.ingresses` for mercury house 3 -> 4 (bracket 2022-12-09/2022-12-10, see the fixture's
own `source_2026_08_19` note). `test_ingresses_fall_within_conformance_fixture_brackets` passes for all
three month fixtures; full suite: 493 passed, 3 xfailed, 0 failed. All Tasks now complete.

## Verification

**Commands:**
- `uv run pytest tests/test_ingresses.py tests/test_conformance.py -q` -- expected: all pass, zero xfail
  regressions on the other month-fixture scopes.

## Suggested Review Order

**Scan algorithm (the core design)**

- Entry point: per configured body and each natal cusp, bisects the signed longitude offset's sign change.
  [`ingresses.py:73`](../../core/transits/ingresses.py#L73)

- Direction determines which house was departed vs. entered -- derived, not stored ambiently.
  [`ingresses.py:169`](../../core/transits/ingresses.py#L169)

- The antipodal-wrap guard: rules out the spurious sign flip every body makes once per revolution opposite the cusp.
  [`ingresses.py:143`](../../core/transits/ingresses.py#L143)

- The half-open-interval fix: a crossing landing exactly on `month_end_utc` is excluded, not reported.
  [`ingresses.py:168`](../../core/transits/ingresses.py#L168)

**Result type**

- `Ingress`: four fields only -- no longitude field, since the crossed cusp's longitude is already known.
  [`transits.py:96`](../../core/types/transits.py#L96)

**Conformance wiring (bracket comparison, not dict equality)**

- Dedicated test, not the generic `compare()` path: matched by body + house_departed + house_entered + bracket window.
  [`test_conformance.py:615`](../../tests/test_conformance.py#L615)

- Real Astro.com bracket, sourced this session against the anchor natal chart's own ephemeris walk.
  [`retrograde-station-month.toml:15`](../../tests/conformance/fixtures/retrograde-station-month.toml#L15)

**Tests (peripheral)**

- One test per I/O-matrix row, using the same monkeypatched-`swe.calc_ut` technique as `test_stations.py`.
  [`test_ingresses.py:118`](../../tests/test_ingresses.py#L118)

- House-1 wraparound case, exercised separately since the main fixture cusp (house 4) never touches it.
  [`test_ingresses.py:180`](../../tests/test_ingresses.py#L180)

- Two-crossings-in-one-month case (there and back), never merged.
  [`test_ingresses.py:209`](../../tests/test_ingresses.py#L209)

- Month-end boundary regression, mirroring `test_stations.py`'s own.
  [`test_ingresses.py:252`](../../tests/test_ingresses.py#L252)
