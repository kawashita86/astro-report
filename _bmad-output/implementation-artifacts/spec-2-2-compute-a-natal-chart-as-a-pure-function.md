---
title: 'Story 2.2 — Compute a Natal Chart as a pure function'
type: 'feature'
created: '2026-08-16'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd6e8785472d020f51ddc51563bb5bbf4ce44e1d4'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing computes a Natal Chart from resolved birth data yet. `tests/test_conformance.py::compute_output_for()` is a `NotImplementedError` stub, and everything later (Rulers, Domain Profiles, transits, the Report) is load-bearing on this being right.

**Approach:** Add a pure `compute_natal_chart()` in `core/ephemeris/`, calling `pyswisseph` directly (no Kerykeion) for planetary positions, Placidus cusps and natal Aspects, all as frozen `Decimal`-typed dataclasses, then wire it into the conformance harness's one call site.

## Boundaries & Constraints

**Always:**
- New `core/ephemeris/chart.py` is pure: no I/O, clock, network or randomness; imports only `swisseph` and `core/types/`.
- Ten planets (Sun–Pluto) + True Node via `swe.calc_ut()` with `SEFLG_SWIEPH`; the return flag is checked to confirm the Swiss Ephemeris bit is set, raising rather than silently accepting a Moshier fallback (mirrors the "Moshier never acceptable" rule already enforced at boot by `core/ephemeris/identity.py`).
- Ascendant, midheaven and the twelve Placidus cusps via `swe.houses(hsys=b'P')`; ascendant **is** the house-1 cusp and midheaven **is** the house-10 cusp, not separately derived.
- South Lunar Node = True Node longitude + 180°, normalized into `[0, 360)`.
- Every longitude/cusp: `Decimal(str(value))` then quantized to 4 decimal places — matches the precision Astro.com's values were transcribed at (mirrors `_to_decimal()`, `shell/adapters/nominatim/geocoder.py:178`).
- Natal Aspects: conjunction/sextile/square/trine/opposition only, within `ComputationConfig.orbs.natal` (default ±7.0°). Orb is stored as an unsigned magnitude (matches fixture values); an explicit `applying: bool` field carries the applying/separating sign separately.
- Every function takes `ComputationConfig` explicitly — nothing reads `data/computation.toml` itself (AD-18).
- All instants are UTC, timezone-aware; no `datetime.now()`, no default timezone.
- `tests/test_conformance.py::compute_output_for()` is rewritten to call the new function and shape its result into the fixture's dict format.

**Ask First:** None — the one open question (Chiron, below) was resolved with the human before this spec was written.

**Never:**
- No Kerykeion dependency — only `pyswisseph`, already vendored.
- No Client/persistence wiring (Story 2.3), no Ruler resolution (Story 2.4), no Domain Profiles (Story 2.5).
- No new ephemeris file or manifest change: Chiron is out of scope (see Design Notes) — the vendored ephemeris stays `sepl_18.se1`/`semo_18.se1` only.
- No mean-node computation — the fixtures use the True Node.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Standard natal computation | UTC birth instant, resolved lat/lon, `ComputationConfig` | Full chart: 10 planets + True/South Node with sign, degree, house; ASC/MC; 12 cusps; Aspects within orb | N/A |
| Natal fixture conformance | Story 1.7's 4 birth-instant fixtures (Chiron entry removed) | Every `planets`/`houses`/`aspects` field matches Astro.com | N/A |
| Determinism | Identical birth data + config, computed twice | Byte-identical `Decimal` results both times | N/A |
| Config-driven orb | `ComputationConfig.orbs.natal` changed from default | Aspect detection uses the passed orb, not a hardcoded 7.0 | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/types/computation.py:89` -- `ComputationConfig` (`.orbs.natal`, `.house_system.name`) is the config this story's function must take explicitly, never read ambiently.
- `core/types/place.py` -- `ResolvedPlace` (Decimal lat/lon, `utc_offset`) is this story's upstream input shape from Story 2.1.
- `core/ephemeris/identity.py:152` -- `verify_ephemeris_identity()` already runs at app import time (`shell/http/app.py`); this story's code assumes it already ran and does not re-verify.
- `shell/adapters/nominatim/geocoder.py:178` -- `_to_decimal()`, the float→Decimal pattern to mirror.
- `data/computation.toml` -- `orbs.natal = "7.0"`, `house_system.name = "placidus"`.
- `data/ephemeris/SHA256SUMS` -- confirms only `sepl_18.se1`/`semo_18.se1` are vendored; no asteroid file, hence the Chiron scope decision below.
- `tests/test_conformance.py:36` -- `compute_output_for()`, the exact call site to wire in; currently `raise NotImplementedError`, wrapped in `pytest.mark.xfail(raises=NotImplementedError)`.

**To create:**
- `core/types/chart.py` -- frozen dataclasses: `NatalChart`, `PlanetPosition` (name/longitude/sign/degree/house, plus `retrograde: bool` -- see Spec Change Log), `HouseCusp` (number/longitude), `Aspect` (body1/body2/aspect/orb/applying). Mirrors `core/types/place.py`'s pattern.
- `core/ephemeris/chart.py` -- `compute_natal_chart(birth_instant_utc, latitude, longitude, config) -> NatalChart`.
- `tests/test_natal_chart.py` -- unit coverage for the I/O matrix rows.

**To modify:**
- `tests/test_conformance.py` -- `compute_output_for()` calls `compute_natal_chart()` and shapes its dict; the blanket `xfail` marker is scoped down to only the three still-unimplemented month/transit fixtures.
- `tests/conformance/fixtures/leap-day-birth.toml`, `dst-fallback-before.toml`, `dst-fallback-after.toml`, `near-midnight-birth.toml` -- remove the `chiron` entry from `expected.planets` (Chiron scope decision); `dst-fallback-before.toml` and `near-midnight-birth.toml` additionally got two further value corrections (see Spec Change Log).
- `tests/conformance/runner.py` -- `compare()` gains a small numeric tolerance for Decimal-parseable fields (see Spec Change Log) -- moved here from "Read-only references" above.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/chart.py` -- add `NatalChart`/`PlanetPosition`/`HouseCusp`/`Aspect` frozen dataclasses -- prerequisite for AC1
- [x] `core/ephemeris/chart.py` -- `compute_natal_chart()`: planets via `swe.calc_ut(SEFLG_SWIEPH)`, ASC/MC/cusps via `swe.houses(hsys=b'P')`, South Node derived, Decimal quantized to 4dp, Aspects detected within `config.orbs.natal` -- AC1, AC2
- [x] `tests/conformance/fixtures/{leap-day-birth,dst-fallback-before,dst-fallback-after,near-midnight-birth}.toml` -- remove the `chiron` entry -- resolves the Chiron scope gap
- [x] `tests/test_conformance.py` -- wire `compute_output_for()` to `compute_natal_chart()`, remove the blanket stub/`xfail` marker (kept, scoped to the three still-unimplemented month/transit fixtures only) -- AC3
- [x] `tests/test_natal_chart.py` -- test the I/O matrix's four rows, including determinism and config-driven orb -- AC2, AC4
- [x] `tests/conformance/runner.py` -- add a small numeric tolerance (±0.01°) to `compare()` for Decimal-parseable fields -- see Spec Change Log
- [x] `tests/conformance/fixtures/dst-fallback-before.toml`, `near-midnight-birth.toml` -- correct two further fixture values found to be transcription errors -- see Spec Change Log

**Acceptance Criteria:**
- Given timezone-aware birth data, resolved coordinates and a `ComputationConfig`, when `compute_natal_chart()` runs, then it returns the ascendant, midheaven, sign/degree/house for the ten planets, the North and South Lunar Node, all twelve Placidus cusps, and natal Aspects within Orb.
- Given the computation, when it runs, then it consults no clock, default timezone, network or database, every angle is `Decimal`, longitudes normalize to `[0, 360)`, and orb sign is carried by an explicit `applying` flag.
- Given the four trimmed natal conformance fixtures, when the conformance runner executes, then computed positions, cusps and Aspects match Astro.com for every fixture.
- Given identical birth data and configuration computed twice, when compared, then the results are identical.

## Spec Change Log

- **Finding:** the fixtures record `retrograde = true/false` per planet, a field not named in this spec's original `PlanetPosition` shape. **Amendment:** `PlanetPosition` gained a `retrograde: bool` field (derived from the body's daily speed sign, already computed via `SEFLG_SPEED`). **Avoids:** every natal fixture's `planets[].retrograde` field reporting as permanently missing. **KEEP:** the field derives from speed sign at the same call that already fetches longitude, no extra ephemeris call.
- **Finding:** once wired in, exact-equality conformance failed on all four natal fixtures -- ~0.0001° noise on planet longitudes/aspect orbs (Decimal-quantization last-digit rounding) and ~0.003-0.009° noise on house cusps (Placidus's known greater sensitivity to engine/DeltaT differences between this vendored Swiss Ephemeris build and Astro.com's own), confirmed by independently recomputing several fixture aspect orbs from the fixtures' own transcribed longitudes and matching exactly. **Human decision:** add a numeric tolerance to `tests/conformance/runner.py`'s `compare()` (±0.01°, string-Decimal-parseable fields only) rather than touch fixture data for this class of mismatch -- moves `runner.py` from this spec's "Read-only references" to modified. **Avoids:** hiding a real regression by loosening the AC itself, or corrupting fixture data to paper over engine noise. **KEEP:** the tolerance is well above both observed noise bands and ~6x below the smallest confirmed transcription-error magnitude found (below), so a real defect of that size still fails loudly.
- **Finding:** after the tolerance was applied, two remaining mismatches held up under independent verification as fixture transcription errors, not code defects: (1) `dst-fallback-before` house cusps 3/9 (a mirrored pair) were 0.06° off -- 7-20x every sibling cusp's noise in the same fixture -- while every other `.0833`-suffixed cusp in the same file matched within tolerance; (2) `near-midnight-birth`'s Neptune `retrograde = true` did not hold up against a ±10-day daily-speed scan (consistently +0.007 to +0.018°/day, no sign change, no station). **Human decision:** correct both values directly in the fixture files (documented inline via each fixture's own `correction_2026_08_16` metadata field) rather than leave them open, given the strength of the internal-consistency evidence and without an available live Astro.com session to re-check against. **Avoids:** a permanently red conformance suite for two isolated, well-evidenced transcription slips. Flagged in each fixture's metadata for a future live re-check if desired.
- **Finding (step-04 review, three parallel layers -- blind-hunter, edge-case-hunter, verification-gap):** seven real, trivially-fixable issues surfaced, none rising to intent_gap/bad_spec (no loopback triggered): (1) the new `_within_numeric_tolerance()` compared longitudes with a plain `abs()` difference, which would misreport a true near-0°/360° match as a ~360° mismatch; (2) `_normalize_decimal()` could quantize a value just under 360 up to exactly `360.0000`, violating the `[0, 360)` invariant `_sign_and_degree()`'s house/sign indexing relies on; (3) `_calc_body()`'s `SEFLG_SWIEPH` bitwise check could pass on a negative (error) `retflag` from `swe.calc_ut()`; (4) `_is_natal_fixture()`'s 5-key duck-typing was fragile against a hypothetical future fixture carrying both shapes' keys; (5) the ephemeris-repinning autouse fixture was duplicated verbatim across two test modules; (6) `compute_natal_chart()`'s docstring overstated the `SEFLG_SWIEPH` integrity check as covering house cusps, which have no equivalent per-call flag; (7) no direct unit test exercised `_within_numeric_tolerance()`'s tolerance boundary or wraparound case. **Amendment:** all seven patched directly (`tests/conformance/runner.py`, `core/ephemeris/chart.py`, `tests/test_conformance.py`, `tests/conftest.py`, `tests/test_natal_chart.py`, `tests/test_conformance_runner.py`) and re-verified (`uv run pytest`: 317 passed, 3 xfailed; `uv run ruff check .`: clean). **Avoids:** a false-negative conformance failure at the 0°/360° boundary, an unreachable `IndexError` on a boundary longitude, a silently-accepted failed ephemeris computation, and an inaccurate docstring. Four further findings (Placidus's undefined behavior near the poles; three untouched Epic-3 fixtures possibly still carrying stray `chiron` entries; the two self-validated fixture corrections above; `PlanetPosition.house`/`sign` and `Aspect.applying` being shape-checked but not value-checked against real data) were judged real but out of this story's scope and logged to `deferred-work.md` rather than blocking here. Four findings (unenforced-but-upstream-guarded orb range; a transient sprint-status/spec-status mismatch mid-workflow; one subjectively-weak unit test; an unreachable pre-1582-date assumption) were rejected as noise.

## Design Notes

**Chiron is out of scope.** All four Story-1.7 birth fixtures include a `chiron` entry (Astro.com's default chart wheel shows it), but no planning artifact (PRD, epics, architecture) ever asked for Chiron, and the vendored ephemeris only ships `sepl_18.se1`/`semo_18.se1` — no asteroid file. Computing it would mean vendoring a new `.se1` file, extending `SHA256SUMS`, and touching `test_ephemeris_identity.py`'s real-file tests: real infrastructure work with no requirement behind it. Resolved with the human: trim the `chiron` entry from the four fixtures rather than expand scope to support it. `true_node` (not separate node fixture entries) is the node naming the fixtures already use, so South Node isn't separately fixture-checked — it's still computed and returned per AC1, just not exercised by conformance.

**Ascendant/midheaven are cusps 1 and 10, not separate lookups.** For Placidus, `swe.houses()`'s `ascmc` output and its `cusps[0]`/`cusps[9]` are definitionally the same values; the fixtures never record them as separate fields, only as `houses[0]`/`houses[9]`.

**Orb is unsigned with a separate `applying` flag.** The AC says orbs are "signed with an explicit applying/separating flag," but the fixtures record positive orb magnitudes (e.g. `"6.7836"`). Reading "signed" as *carried via* the flag (not a negative number) satisfies both: `orb` stays an unsigned magnitude matching the fixture, `applying: bool` is an extra field the conformance comparison ignores (only `expected`'s keys are checked).

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including the now-real (non-xfail) conformance tests and new `tests/test_natal_chart.py`
- `uv run ruff check .` -- clean

## Suggested Review Order

**The computation itself**

- Entry point: pure function signature, the pipeline (planets, houses, South Node, Aspects) it assembles.
  [`chart.py:97`](../../core/ephemeris/chart.py#L97)

- Ascendant/midheaven are cusps 1 and 10 from `swe.houses()`, not a separate lookup.
  [`chart.py:127`](../../core/ephemeris/chart.py#L127)

**Ephemeris-integrity guard (Moshier fallback must never pass silently)**

- `SEFLG_SWIEPH` bit check, now also rejecting a negative `retflag` (two's-complement could otherwise mask an error as truthy) -- review-round patch.
  [`chart.py:179`](../../core/ephemeris/chart.py#L179)

**Decimal normalization and the [0, 360) boundary**

- Quantizing to 4dp can round a value just under 360 up to exactly `360.0000`; re-wrapped to stay in `[0, 360)` -- review-round patch, closes a possible `IndexError` in sign lookup.
  [`chart.py:207`](../../core/ephemeris/chart.py#L207)

- Which Placidus house span a longitude falls in, including the one span crossing 0 degrees.
  [`chart.py:226`](../../core/ephemeris/chart.py#L226)

**Aspect detection and the applying/separating sign**

- First-match-in-fixed-order aspect selection, relying on the configured orb staying well under half the 30-degree gap between aspect angles.
  [`chart.py:267`](../../core/ephemeris/chart.py#L267)

- Applying vs. separating derived from signed relative speed -- the sign convention worth checking by hand.
  [`chart.py:276`](../../core/ephemeris/chart.py#L276)

- Where the two above combine into the emitted `Aspect` list, in fixed body-pair order.
  [`chart.py:302`](../../core/ephemeris/chart.py#L302)

**Conformance harness wiring**

- The one call site real computation plugs into; Chiron and the South Node are deliberately shaped out of the emitted dict.
  [`test_conformance.py:89`](../../tests/test_conformance.py#L89)

- `compute_output_for()` itself -- birth-instant construction, then the call into `compute_natal_chart()`.
  [`test_conformance.py:121`](../../tests/test_conformance.py#L121)

- Natal-vs-month fixture routing, tightened during review to key off the month fixture's own marker key rather than a duck-typed key superset.
  [`test_conformance.py:75`](../../tests/test_conformance.py#L75)

**Numeric tolerance in the conformance runner**

- Circular (mod 360) tolerance comparison -- a plain `abs()` diff would misreport a true near-boundary match as a ~360-degree mismatch; fixed during review.
  [`runner.py:204`](../../tests/conformance/runner.py#L204)

**Fixture data changes**

- Two values corrected against this story's own computation rather than an independent Astro.com re-check -- flagged as open in Design Notes and deferred-work.md.
  [`dst-fallback-before.toml:6`](../../tests/conformance/fixtures/dst-fallback-before.toml#L6)

- Same caveat, Neptune's retrograde flag.
  [`near-midnight-birth.toml:6`](../../tests/conformance/fixtures/near-midnight-birth.toml#L6)

**Peripherals**

- New `NatalChart`/`PlanetPosition`/`HouseCusp`/`Aspect` types, including the `retrograde` field added mid-implementation.
  [`chart.py:1`](../../core/types/chart.py#L1)

- Unit coverage for the I/O matrix's four rows.
  [`test_natal_chart.py:1`](../../tests/test_natal_chart.py#L1)

- New tolerance-boundary and wraparound tests added during review.
  [`test_conformance_runner.py:247`](../../tests/test_conformance_runner.py#L247)

- Ephemeris-repinning fixture deduplicated here from two test modules during review.
  [`conftest.py:38`](../../tests/conftest.py#L38)
