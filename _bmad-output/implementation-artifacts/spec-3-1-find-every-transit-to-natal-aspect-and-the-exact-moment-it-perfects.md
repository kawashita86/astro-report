---
title: 'Find every transit-to-natal Aspect and the exact moment it perfects'
type: 'feature'
created: '2026-08-18'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '7e2b9889abc591d6e205217008c6b1de764efd2d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Francesco can only manually sample four dates a month against a Client's Natal Chart, so
he can say "around the 10th" but never the exact day a transit-to-natal Aspect perfects — and nothing
downstream (Sections 6/7 day lists, the Report Payload) can be built on a guess like that.

**Approach:** A new pure `core/transits/` function scans the configured fast/slow transiting bodies
against every natal point across a Client's analyzed month, reusing the existing natal-Aspect matching
math in `core/ephemeris/chart.py`, and locates each perfection instant by bisection.

## Boundaries & Constraints

**Always:**
- Lives in `core/transits/` (new module), pure (AD-1): no I/O, clock, network, randomness — only
  `swisseph` and what is passed in (`NatalChart`, month interval, `ComputationConfig`).
- Analyzed month is one half-open UTC interval `[start, end)` derived once from the Client's local
  calendar-month boundaries via `Client.iana_zone`; every event's membership is decided against that
  one interval.
- Fast bodies (sun, mercury, venus, mars) and slow bodies (jupiter, saturn, uranus, neptune, pluto)
  read from `config.bodies`; the transiting Moon is excluded entirely.
- Natal targets: the ten natal planets plus ascendant, midheaven, true node and south node (all already
  present on `NatalChart`).
- Aspects limited to the five in `core/ephemeris/chart.py`'s `_ASPECTS` table; orb from
  `config.orbs.transit`.
- Each recorded event carries the transiting body, natal point, aspect type, the bisected exact
  perfection UTC instant (or a `never_perfected` flag when in orb but never crossing), and in-orb entry
  and exit dates.
- Deterministic: identical `NatalChart` + month + config produce an identical event tuple every run.
- Extract the shared low-level swisseph helpers (`_julian_day_ut`, `_calc_body`, `_to_normalized_decimal`,
  `_angular_separation`) that both natal and transit computation need into a shared module rather than
  duplicating them — `core/ephemeris/chart.py`'s public behavior stays unchanged.

**Ask First:** none identified during planning.

**Never:**
- No Station/Ingress/Lunation detection (Stories 3.2–3.4) and no Report Payload assembly or HTTP route.
- Never treat a third-party "exact perfection time" claim as a conformance oracle — Astro.com exposes no
  such value. External verification is the snapshot-moment orb/aspect data already in the month
  fixtures; the bisected instant itself is verified structurally instead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| In orb all month, never perfects | separation stays within orb but never crosses the target angle | recorded with `perfected_at=None`, `never_perfected=True`, orb entry/exit dates set | N/A |
| Perfection near a month boundary | bisected instant lands at/near the local-month boundary | assigned to exactly one month by the single half-open UTC interval | N/A |
| Approach while retrograde | transiting body's speed sign changes while nearing the orb | perfection instant still located correctly by bisection on separation | N/A |
| Same pair re-enters orb (retrograde loop) | a body stations back into orb and separates again within the month | two distinct events recorded, never merged or deduplicated | N/A |

</frozen-after-approval>

## Code Map

- `core/ephemeris/chart.py` -- existing natal-Aspect matching math (`_ASPECTS`, `_angular_separation`,
  `_match_aspect`, `_is_applying`) and low-level swisseph helpers (`_julian_day_ut:165`, `_calc_body:179`,
  `_to_normalized_decimal:196`) to extract and reuse, not reimplement.
- `core/types/chart.py` -- `NatalChart:87`/`PlanetPosition:21`; natal targets already include ascendant,
  midheaven, true_node, south_node.
- `core/types/computation.py` -- `ComputationConfig.orbs.transit:37`, `.bodies.fast/slow:55` already
  validated and loaded; no new config needed.
- `core/transits/__init__.py` -- currently an empty docstring-only scaffold; new module(s) land here.
- `shell/adapters/postgres/client.py:56` -- `Client.iana_zone` -- the persisted field the month-interval
  derivation reads.
- `tests/conformance/fixtures/two-lunations-month.toml:75-133`, `no-lunations-month.toml`,
  `retrograde-station-month.toml` -- existing `expected.transit_events` tables (snapshot-moment aspect
  checks) already shaped for this story; `expected.lunations`/`expected.stations` in the same files
  belong to later stories.
- `tests/test_conformance.py:121,75` -- `compute_output_for()` currently raises `NotImplementedError`
  for every month fixture via `_is_natal_fixture()`; needs a narrower touch point for `transit_events`
  only.
- `tests/conformance/runner.py` -- generic `compare()`/`Fixture` machinery, unchanged.

## Tasks & Acceptance

**Execution:**
- [x] `core/ephemeris/positions.py` (new) -- extract `_julian_day_ut`, `_calc_body`,
  `_to_normalized_decimal`, `_angular_separation` from `core/ephemeris/chart.py` into a shared pure
  module; update `chart.py` to import from it -- natal and transit computation need identical position
  math, and duplicating it risks silent divergence.
- [x] `core/types/transits.py` (new) -- `TransitAspectEvent` frozen dataclass: `transiting_body`,
  `natal_point`, `aspect`, `perfected_at: datetime | None`, `never_perfected: bool`,
  `orb_entry_at: datetime`, `orb_exit_at: datetime | None` -- mirrors `core/types/chart.py`'s `Aspect`,
  extended for time.
- [x] `core/transits/aspects.py` (new) -- `find_transit_aspects(natal_chart, month_start_utc,
  month_end_utc, config) -> tuple[TransitAspectEvent, ...]`: walks fast+slow bodies against every natal
  point across the interval using the extracted helpers plus bisection to locate each perfection instant
  and orb boundary.
- [x] `tests/test_transit_aspects.py` (new) -- unit tests for the I/O matrix rows above, plus a
  determinism test (repeated identical-input runs produce an identical tuple) and a numeric-tolerance
  test that a located `perfected_at` puts the separation within quantization tolerance of the target
  angle.
- [x] `tests/test_conformance.py` -- extend `compute_output_for()`/`_fixture_params()` so the three month
  fixtures' `expected.transit_events` run for real against `find_transit_aspects()`'s output at
  `transit_snapshot_utc`, while `expected.lunations`/`expected.stations` stay `xfail` until Stories
  3.2/3.4.

**Acceptance Criteria:**
- Given a Client's Natal Chart, a month and a `ComputationConfig`, when the scan runs, then it covers
  exactly the configured fast+slow bodies against the ten natal planets, ascendant, midheaven and both
  Lunar Nodes, using only the five major aspects.
- Given a detected transit-to-natal Aspect, when it's recorded, then it carries the transiting body,
  natal point, aspect type, bisected perfection instant (or `never_perfected=True`), and orb entry/exit
  dates.
- Given the three month conformance fixtures, when the conformance runner executes, then computed
  `transit_events` at each fixture's `transit_snapshot_utc` match `expected.transit_events` within the
  runner's existing numeric tolerance.
- Given the same Natal Chart, month and config run twice, when compared, then the two output tuples are
  identical.

## Spec Change Log

## Design Notes

- Bisection target: `f(t) = _angular_separation(transiting_longitude(t), natal_longitude) -
  target_degrees`, sign-changing near perfection; standard bisection to sub-second precision (mirrors
  the epic's stated approach for Lunations, symmetric with how Stations will be located in Story 3.2).
- Astro.com never publishes an exact aspect-perfection instant, so unlike the natal-Aspect fixtures
  (Story 2.2) there is no external oracle for `perfected_at` itself -- conformance is proven two ways:
  (1) the snapshot-moment orb/aspect values already in the fixtures (external, Astro.com-derived) and
  (2) a structural check that re-evaluating separation at the returned `perfected_at` lands within the
  quantization tolerance of the target angle (internal, self-consistent).

## Verification

**Commands:**
- `uv run pytest tests/test_transit_aspects.py tests/test_conformance.py -v` -- expected: all pass, no
  new xfail regressions on the natal fixtures.
- `uv run pytest` -- expected: full suite green.

## Suggested Review Order

**Scan algorithm (the core design)**

- Entry point: scans every configured body against all fourteen natal targets, five aspects, both branches.
  [`aspects.py:94`](../../core/transits/aspects.py#L94)

- Why two branches per aspect: sextile/square/trine fold "ahead" and "behind" into one separation, so both must be scanned separately.
  [`aspects.py:166`](../../core/transits/aspects.py#L166)

- Why a signed, target-centered offset instead of the natal detector's unsigned separation: bisection needs a real sign change through zero.
  [`aspects.py:240`](../../core/transits/aspects.py#L240)

- Fixed-iteration bisection refines the coarse 6-hour grid to sub-second precision for entry/perfection/exit.
  [`aspects.py:260`](../../core/transits/aspects.py#L260)

- Per-pair walk: one event per contiguous in-orb interval; a retrograde re-entry produces a second, independent event.
  [`aspects.py:284`](../../core/transits/aspects.py#L284)

**Extracted shared ephemeris helpers**

- Low-level swisseph/Julian-day/normalization helpers moved out of the natal chart builder so both engines share one implementation.
  [`positions.py:53`](../../core/ephemeris/positions.py#L53)

- `chart.py` now imports the shared helpers instead of owning them; `compute_natal_chart`'s own behavior is unchanged.
  [`chart.py:31`](../../core/ephemeris/chart.py#L31)

**Result type**

- `TransitAspectEvent`: perfection instant or `never_perfected`, plus orb entry/exit -- deliberately no orb value (see Design Notes).
  [`transits.py:21`](../../core/types/transits.py#L21)

**Conformance wiring (per-fixture-section, not per-fixture)**

- `compute_output_for` now branches per month-fixture scope: `transit_events` runs for real, the rest stays `xfail` until Stories 3.2-3.4.
  [`test_conformance.py:315`](../../tests/test_conformance.py#L315)

- Recomputes each fixture's snapshot-moment orb directly from the same low-level position math the scan itself uses.
  [`test_conformance.py:267`](../../tests/test_conformance.py#L267)

- Fixture-input validation added by review: names the offending fixture and field instead of a bare exception.
  [`test_conformance.py:146`](../../tests/test_conformance.py#L146)

**Fixture data corrections (pre-existing transcription bugs this story's real computation caught)**

- Mercury's longitude was one zodiac sign off, and Jupiter's retrograde flag was a false positive.
  [`no-lunations-month.toml:6`](../../tests/conformance/fixtures/no-lunations-month.toml#L6)

- Mars and Jupiter's longitudes were each one zodiac sign short; `transit_events` was entirely absent until now.
  [`retrograde-station-month.toml:6`](../../tests/conformance/fixtures/retrograde-station-month.toml#L6)

**Tests (peripheral)**

- One test per I/O-matrix row, using a monkeypatched synthetic ephemeris for precise control over approach shape.
  [`test_transit_aspects.py:202`](../../tests/test_transit_aspects.py#L202)

- Retrograde-loop re-entry: confirms two distinct, non-merged events when a pair separates and re-enters orb.
  [`test_transit_aspects.py:323`](../../tests/test_transit_aspects.py#L323)
