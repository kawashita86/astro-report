---
title: "Locate the month's new and full moons"
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '20c0355b31e7634b8d2969af7be42cda0f8e470b'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 3.1-3.3 locate Aspects, Stations and Ingresses, but the transiting Moon itself
enters the Report through nothing yet — Francesco cannot see the month's new/full moons, so the closing
advice (Sections 6/7, Epic 3 Goal) has no Lunations to synthesize against the overall picture.

**Approach:** A new pure `core/transits/lunations.py` scans Δλ = (λ_Moon − λ_Sun) mod 360° across the
analyzed month on the same coarse-grid-plus-bisection method `aspects.py`/`stations.py`/`ingresses.py`
already use, locating each signed-offset zero-crossing from two fixed targets (0° = new moon, 180° =
full moon) and placing each located instant's Moon longitude in the natal chart's houses via
`core/ephemeris/chart.py`'s existing house-span lookup.

## Boundaries & Constraints

**Always:**
- Lives in `core/transits/lunations.py` (new module), pure (AD-1): no I/O, clock, network, randomness --
  only `swisseph` (via existing helpers) and what is passed in (`NatalChart`, the month interval). No
  `ComputationConfig` param: unlike Aspects/Stations/Ingresses, the body pair (Sun, Moon) and both
  targets (0°, 180°) are fixed, not configurable -- nothing in `ComputationConfig` this function would
  ever read.
- A Lunation record carries: `kind` (`"new_moon"`/`"full_moon"`), `occurred_at` (bisected UTC instant,
  full precision), `longitude` (Moon's zodiacal degree at `occurred_at`), `natal_house`.
- Δλ is monotonically increasing all month (Moon's angular speed always exceeds the Sun's; neither is
  ever retrograde against this measure) -- every crossing is a simple forward crossing; no
  direction/departed-entered concept (unlike `Ingress`).
- Deterministic: identical month + natal chart produce an identical output tuple every run.
- Zero or two Lunations of one kind in a month is a normal outcome, recorded as found, never an error.

**Never:**
- No Report Payload assembly or HTTP route.
- No fabricated fixture timestamp: `no-lunations-month.toml`'s missing new-moon entry (see Code Map) is
  corrected using real, independently-corroborated public sources (astropixels.com's canonical phase
  catalog and lunaf.com both give 2018-02-15 21:05 UTC), not invented.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Δλ crosses 0° | signed offset from target 0 changes − to + | Lunation recorded: kind=new_moon, exact UTC instant, Moon's longitude, natal house | N/A |
| Δλ crosses 180° | signed offset from target 180 changes − to + | Lunation recorded: kind=full_moon, exact UTC instant, Moon's longitude, natal house | N/A |
| Two Lunations of one kind in a month | Δλ crosses the same target twice | two distinct Lunation records, never merged | N/A |
| A month with no Lunation of a given kind | Δλ never crosses that target in the month | nothing recorded for that kind -- not an error | N/A |
| A crossing landing exactly on `month_end_utc` | offset reaches zero only at the excluded final grid probe | not reported (half-open interval, mirrors `stations.py`/`ingresses.py`'s own boundary fix) | N/A |

</frozen-after-approval>

## Code Map

- `core/transits/ingresses.py` (whole file) -- nearest precedent: coarse-grid + bisection + the
  antipodal-wrap guard (`ingresses.py:143`, `abs(d1 - d0) < HALF_CIRCLE`) to mirror verbatim, needed here
  for BOTH targets (scanning target 0° would otherwise misfire at the true full-moon instant, where the
  wrapped offset jumps +180→-180, and vice versa for target 180° at the true new-moon instant). Also
  mirror its `_require_utc_interval`/`_build_grid`/`_bisect`/`_normalize_signed`/`_signed_offset` shapes
  (`ingresses.py:198-270`) and its half-open-interval guard (`ingresses.py:168`,
  `crossed_at < month_end_utc`).
- `core/ephemeris/positions.py` -- `_calc_body:67`, `_julian_day_ut:53`, `FULL_CIRCLE`/`HALF_CIRCLE:42-43`
  (reuse); `swisseph.SUN`/`swisseph.MOON` read directly (`import swisseph as swe`) -- unlike
  `_TRANSIT_BODY_IDS` (`core/transits/aspects.py:69`), the Moon is never a valid entry there, so this
  module never imports that table.
- `core/ephemeris/chart.py` -- `_house_for_longitude:173` (`(longitude, cusp_longitudes) -> int`), reused
  via the same accepted private cross-module import pattern `ingresses.py` already sets for
  `_TRANSIT_BODY_IDS`. Called with the Moon's longitude at each `occurred_at` and
  `[cusp.longitude for cusp in natal_chart.houses]`.
- `core/types/chart.py` -- `NatalChart.houses:101` (already ordered 1..12, per `ingresses.py`'s own
  docstring).
- `core/types/transits.py` -- `Ingress:96`/`Station:55` -- add `Lunation` frozen dataclass alongside them,
  same docstring-driven style; update `__all__:18` (alphabetical).
- `tests/test_conformance.py` -- `_transit_events_for_month_fixture:283` (shaping-function precedent,
  mirror its shape for a new `_lunations_for_month_fixture`), `_IMPLEMENTED_MONTH_SCOPE:331`/
  `_STATIONS_KEY:338`/`_INGRESSES_KEY:349` (add `_LUNATIONS_SCOPE = "lunations"` alongside), `compute_output_for:352-383`
  (add an `elif scope == _LUNATIONS_SCOPE` branch returning real output, mirroring the
  `_IMPLEMENTED_MONTH_SCOPE` branch), `_expected_for_scope:386-399` (add `_LUNATIONS_SCOPE` handling +
  exclude `_LUNATIONS_SCOPE` from `"remainder"`'s slice), `_fixture_params:414-446` (emit a third
  `pytest.param(path, _LUNATIONS_SCOPE, ...)` per month fixture, but ONLY when
  `load_fixture(path).expected` already contains a `"lunations"` key -- `retrograde-station-month.toml`
  has none and stays out of scope for this story, per the epic AC's own two named fixtures),
  `_anchor_natal_chart:203`, `_month_interval_utc:162`.
- `tests/conformance/fixtures/no-lunations-month.toml` -- **correction needed**: `expected.lunations = []`
  (line 14) only accounts for the file's adversarial claim (zero *full* moons in Feb 2018, per its own
  `note`) -- real Feb 2018 also has a new moon on 2018-02-15 at 21:05 UTC (astropixels.com's canonical
  phases catalog and lunaf.com both independently agree), omitted from the original transcription. Add
  `[[expected.lunations]] type = "new_moon", date = "2018-02-15", time_utc = "21:05:00"` and a
  `correction_2026_08_19` note, mirroring this file's own existing `correction_2026_08_18` convention.
- `tests/conformance/fixtures/two-lunations-month.toml` -- already carries two correct
  `expected.lunations` entries (lines 14-22); read-only reference, no change.
- `tests/test_ingresses.py` (whole file) -- structure/monkeypatch precedent for `tests/test_lunations.py`
  (new): `_patch_calc_ut:93` needs adapting to drive Sun and Moon longitudes independently by `body_id`
  (this story needs two synthetic bodies moving at different constant rates, not one).

## Tasks & Acceptance

**Execution:**
- [x] `core/types/transits.py` -- add `Lunation` (`kind`, `occurred_at: datetime`, `longitude: Decimal`,
  `natal_house: int`) frozen dataclass; update `__all__`.
- [x] `core/transits/lunations.py` (new) -- `find_lunations(natal_chart, month_start_utc, month_end_utc)
  -> tuple[Lunation, ...]`: bisects Δλ's signed-offset sign changes from targets 0° and 180° on the
  coarse grid, resolving each crossing's natal house via `_house_for_longitude`.
- [x] `tests/test_lunations.py` (new) -- unit tests for the I/O matrix rows above, plus determinism.
- [x] `tests/test_conformance.py` -- wire `_LUNATIONS_SCOPE`, `_lunations_for_month_fixture`,
  `compute_output_for`/`_expected_for_scope`/`_fixture_params` per the Code Map.
- [x] `tests/conformance/fixtures/no-lunations-month.toml` -- add the corrected 2018-02-15 new-moon entry
  and a `correction_2026_08_19` note.

**Acceptance Criteria:**
- Given the analyzed month interval, when Lunations are located, then Δλ = (λ_Moon − λ_Sun) mod 360° is
  tracked and each Lunation records its kind, exact date, UTC time, zodiacal degree, and natal house.
- Given a month containing no Lunation of a given kind, or two of one kind, when the scan completes, then
  the result is recorded as found and requires no intervention -- neither case is an error.
- Given the `two-lunations-month`/`no-lunations-month` fixtures, when the conformance runner executes,
  then computed Lunations match on kind/date/UTC time (truncated to the minute -- see Design Notes) in
  both cases.

## Spec Change Log

- 2026-08-19: The Code Map's claim that `two-lunations-month.toml` "already carries two correct
  `expected.lunations` entries... read-only reference, no change" was wrong. Running the real
  `find_lunations()` computation against August 2023 (the fixture's own month) shows it genuinely
  contains three Lunations, not two: the two transcribed full moons (Aug 1, Aug 31) plus a real new
  moon on 2023-08-16 09:38 UTC that the original fixture never transcribed (independently corroborated
  by NASA/moon.nasa.gov, timeanddate.com and lunaf.com). Since `compare()`'s list check requires exact
  length equality, leaving the fixture at two entries would make
  `test_computed_output_matches_conformance_fixture[two-lunations-month-lunations]` fail against a
  *correct* computation. Added the missing new-moon entry (chronologically, between the two full
  moons) with a `correction_2026_08_19` note, mirroring the same correction pattern already used
  elsewhere in this fixture family (see `no-lunations-month.toml`'s own `correction_2026_08_18`/
  `correction_2026_08_19` notes) rather than narrowing the computation or the comparison to dodge the
  gap. This Code Map bullet sits outside the frozen Intent block, so no Boundaries & Constraints/
  Edge-Case Matrix change was needed.
- 2026-08-19: The Design Notes' original "round to the nearest minute, ties round up" fixture-comparison
  rule was wrong. Both of `two-lunations-month`'s real full-moon instants bisect to 38-40 seconds past
  their published minute (2023-08-01 18:31:40, 2023-08-31 01:35:38), which round-to-nearest would push
  into the *next* minute (18:32, 01:36) -- but every corroborating source (NASA, Space.com,
  timeanddate.com, Star Walk) reports the un-rounded minute (18:31, 01:35). Switched
  `_lunations_for_month_fixture` from rounding to truncating (drop seconds/microseconds, never round up);
  Design Notes updated to match. `Lunation.occurred_at` itself is unaffected either way -- full precision,
  never touched outside the test-shaping function.

## Design Notes

**No `config: ComputationConfig` param.** Aspects/Stations/Ingresses all read `config.bodies.fast/slow`
to know which bodies to scan; Lunations scan exactly Sun and Moon, always -- adding an unused param would
be speculative.

**Fixture comparison truncates to the whole minute (does not round); `Lunation.occurred_at` itself stays
full precision.** Every corroborating public source (NASA, Space.com, timeanddate.com, astropixels.com,
lunaf.com) only ever publishes a Lunation to minute precision, never seconds -- comparing a sub-second
bisected instant's raw `HH:MM:SS` string against a minute-precision reference would spuriously fail even
on a correct computation. `_lunations_for_month_fixture` truncates `occurred_at`'s seconds/microseconds
before formatting `date`/`time_utc` for the fixture comparison only -- mirrors the "honest precision"
concession `_STATION_LONGITUDE_TOLERANCE` (Story 3.2) and the bracket comparisons (Stories 3.2/3.3) already
make, scoped here to the test-shaping function, never into `core/`.

Originally implemented as "round to the nearest minute, ties round up," per this Design Notes section's
first draft -- reverted to truncation once real computation against `two-lunations-month`'s own fixture
showed both real full-moon instants bisect to ~38-40 seconds past their published minute (e.g. the real
2023-08-01 full moon is `18:31:40`, not `18:31:00`), yet NASA/Space.com/timeanddate.com/Star Walk all
still report it as `18:31`, not `18:32` -- these sources truncate, they do not round. See the Spec Change
Log.

## Verification

**Commands:**
- `uv run pytest tests/test_lunations.py tests/test_conformance.py -q` -- expected: all pass; the
  `remainder` xfail for `two-lunations-month`/`no-lunations-month` still xfails (only `transit_positions`
  remains unimplemented there); no regression on the `stations`/`ingresses` bracket tests.

## Suggested Review Order

**Scan algorithm**

- Entry point: dual-target bisection over Delta-lambda, mirroring the sibling modules' coarse-grid-plus-bisection shape.
  [`lunations.py:88`](../../core/transits/lunations.py#L88)

- The antipodal-wrap guard, needed for both targets here (unlike `ingresses.py`'s single-target case).
  [`lunations.py:136`](../../core/transits/lunations.py#L136)

- Delta-lambda itself: Moon minus Sun, mod 360 -- the relative-angle shape this module scans instead of a per-body offset.
  [`lunations.py:200`](../../core/transits/lunations.py#L200)

**Result type**

- `Lunation`: no direction/departed-entered concept, unlike `Ingress` -- Delta-lambda only ever moves forward.
  [`transits.py:123`](../../core/types/transits.py#L123)

**Conformance wiring**

- New `_LUNATIONS_SCOPE`, only emitted per fixture when `expected.lunations` already exists.
  [`test_conformance.py:525`](../../tests/test_conformance.py#L525)

- Real output shaped and truncated to the minute for comparison -- `Lunation.occurred_at` itself stays full precision.
  [`test_conformance.py:389`](../../tests/test_conformance.py#L389)

**Fixture corrections**

- `no-lunations-month.toml`: the missing 2018-02-15 new moon, independently corroborated and added.
  [`no-lunations-month.toml:16`](../../tests/conformance/fixtures/no-lunations-month.toml#L16)

- `two-lunations-month.toml`: a second real gap found during implementation -- August 2023's own new moon, also missing.
  [`two-lunations-month.toml:15`](../../tests/conformance/fixtures/two-lunations-month.toml#L15)

**Tests**

- The antipodal-wrap guard's own regression test -- every other row deliberately avoids the case this one exercises.
  [`test_lunations.py:260`](../../tests/test_lunations.py#L260)

- Both kinds crossed in one scan, checked for cross-contamination.
  [`test_lunations.py:325`](../../tests/test_lunations.py#L325)

- Sub-minute precision retained by the scan itself, guarding against a future truncation regression.
  [`test_lunations.py:171`](../../tests/test_lunations.py#L171)
