---
title: 'Story 8.1 — Pass conformance across the full adversarial fixture set'
type: 'feature'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
baseline_commit: '8c79c3cca9d6b9fe7f615904532529a760007197'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The conformance harness runs real computation for every fixture section except `expected.transit_positions` (transiting body longitudes + retrograde flags at each month fixture's `transit_snapshot_utc`), which is still stubbed behind three `xfail(raises=NotImplementedError)` `*-remainder` cases. Story 8.1 is the release gate that requires the *complete* adversarial fixture set to match Astro.com at 100%, so that last section must run for real — and the discrepancies it exposes must be resolved, not tolerated.

**Approach:** Wire `transit_positions` into `compute_output_for()` using the existing `_calc_body()` / `_PLANET_BODIES` ephemeris helpers, drop the `xfail` marks, and keep `remainder` as a no-`xfail` guard that fails loudly on any future unrecognized `expected.*` section. Wiring it reveals three transcription errors in the fixture data (Jupiter and Uranus retrograde flags in `two-lunations-month`, the Moon longitude in `no-lunations-month`); correct each in place with a dated note, gated on Francesco's live Astro.com re-verification before merge.

## Boundaries & Constraints

**Always:**
- Compute transiting positions from `transit_snapshot_utc` only (geocentric, anchor-chart-independent). Reuse `core/ephemeris/positions._calc_body` + `core/ephemeris/chart._PLANET_BODIES` — the ten bodies sun…pluto, `true_node` filtered out — never a second ephemeris path.
- `retrograde` is `speed < 0`, matching `core/ephemeris/chart._planet_position`. Emit it on every computed row; `compare()` only checks it where the fixture asserts it.
- Emit rows in `_PLANET_BODIES` order, so `compare()`'s positional list walk aligns with each fixture's `transit_positions` order.
- Every fixture correction carries a `correction_2026_08_27` metadata note shaped like the existing `correction_2026_08_18` / `_19` notes: what was wrong, the corroborating astronomical fact, what changed.
- After wiring, the whole conformance suite passes with zero `xfail` / `xpass` (`xfail_strict = true`).

**Ask First:**
- Any fixture discrepancy beyond the three named below (a longitude outside the 0.01° tolerance, another retrograde-flag disagreement) — surface it, do not adjust fixture data to force a pass.
- Changing `_NUMERIC_TOLERANCE` or adding a retrograde neutral-band — the three known cases don't need it (speeds +0.106, +0.023, +14.9 °/day); if one seems to, stop and ask.

**Never:**
- No new `core/` or `shell/` code — `transit_positions` is a conformance cross-check, not a domain concept; it lives in the test-shaping layer like `_transit_events_for_month_fixture`.
- Don't add the Moon to `_TRANSIT_BODY_IDS` in `core/transits/aspects.py` — that exclusion is FR-9 and unrelated.
- Don't merge on dev corroboration alone — Francesco re-verifies the three corrected values against a live Astro.com session first.
- No CI/CD or branch-protection changes — that gap is logged separately (`deferred-work.md`, story 1.6).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| `transit_positions` scope, happy path | `retrograde-station-month` at `2022-12-01T00:00:00Z` | 10 rows `{name, longitude: str, retrograde: bool}` in `_PLANET_BODIES` order; every longitude within 0.01° of fixture | N/A |
| Retrograde body | `two-lunations-month` saturn (`speed < 0`) | `retrograde: true`, matches fixture | N/A |
| Direct body near station | `two-lunations-month` uranus (`+0.023°/day`) | `retrograde: false`; fixture's `retrograde = true` removed by correction | N/A |
| Body with no `retrograde` key in fixture | `retrograde-station-month` neptune (`-0.0017°/day`, pre-station) | computed `retrograde: true` emitted but not compared | N/A |
| `remainder` scope, no unknown sections | any month fixture | `compute_output_for` returns `{}`, `_expected_for_scope` returns `{}` → passes | N/A |
| `remainder` scope, unknown `expected.foo` present | hypothetical fixture | `{foo: …}` vs `{}` → mismatch, test fails naming `expected.foo` | Loud failure |
| Natal fixture unchanged | `leap-day-birth`, `scope=None` | whole `expected` table still checked via `compute_natal_chart()` | N/A |
| `transit_snapshot_utc` missing / naive | malformed month fixture | `FixtureFormatError` naming the fixture (existing `_transit_snapshot_utc`) | Raises |

</frozen-after-approval>

## Code Map

- `tests/test_conformance.py` — every code change lands here. Anchor points (line numbers approximate):
  - import (~L92) `from core.ephemeris.chart import _ASPECTS, compute_natal_chart` — add `_PLANET_BODIES`.
  - `_LUNATIONS_SCOPE` (~L379) — add `_TRANSIT_POSITIONS_SCOPE = "transit_positions"` alongside.
  - `_transit_events_for_month_fixture` (~L302) — add sibling `_transit_positions_for_month_fixture(fixture)`: `jd = _julian_day_ut(_transit_snapshot_utc(fixture))`; for `(name, body_id)` in `_PLANET_BODIES` where `name != "true_node"`, `longitude, speed = _calc_body(jd, body_id)`; row `{"name": name, "longitude": str(longitude), "retrograde": speed < 0}`.
  - `compute_output_for()` (~L436) — add the `transit_positions` scope branch; replace the trailing `raise NotImplementedError` (~L467) with `return {}` (the `remainder` catch-all).
  - `_expected_for_scope()` (~L473) — add a `transit_positions` case; add `_TRANSIT_POSITIONS_SCOPE` to the `remainder` else-branch exclusion tuple (~L487).
  - `_fixture_params()` (~L503) — per month fixture append `pytest.param(path, _TRANSIT_POSITIONS_SCOPE, id=f"{path.stem}-transit_positions")`; strip `marks=pytest.mark.xfail(...)` from the `remainder` param (keep the param).
  - module docstring (~L1–81) — add a Story 8.1 paragraph: `transit_positions` wired for real, `remainder` demoted to a plain guard.
- `core/ephemeris/chart.py:51` — `_PLANET_BODIES`, `(name, swe_id)` pairs sun…pluto then `true_node`. Read-only; filter `true_node`.
- `core/ephemeris/positions.py:67` / `:53` — `_calc_body(jd_ut, body_id) -> (Decimal longitude, Decimal speed)` (longitude already normalized to `[0,360)`, quantized `0.0001`); `_julian_day_ut`. Read-only.
- `tests/conformance/runner.py` — `compare()` walks `expected` keys only; `_within_numeric_tolerance` folds circularly at `_NUMERIC_TOLERANCE = 0.01`. Read-only.
- `tests/conformance/fixtures/two-lunations-month.toml` — remove `retrograde = true` from the jupiter and uranus `[[expected.transit_positions]]` entries; add `correction_2026_08_27`. Corroboration: Jupiter stationed retrograde 2023-09-05, Uranus 2023-08-30 — both still direct on 2023-08-01.
- `tests/conformance/fixtures/no-lunations-month.toml` — moon `[[expected.transit_positions]]` `longitude = "198.1833"` → `"138.1793"`; add `correction_2026_08_27`. Corroboration: 198.1833 is the Moon at 2018-02-05 ~06:00 UT (wrong date); the real 2018-02-01 00:00 UT position is ~18°11′ Leo, the day after the 2018-01-31 total lunar eclipse in Leo.
- `tests/test_conformance_runner.py` — synthetic `compare()` tests, no real fixture; unaffected. `pyproject.toml:40` — `xfail_strict = true`. `.github/workflows/ci.yml` — runs `uv run pytest`; no change.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_conformance.py` — add `_TRANSIT_POSITIONS_SCOPE` and `_transit_positions_for_month_fixture()`; wire the scope through `compute_output_for()` and `_expected_for_scope()`; in `_fixture_params()` emit a real `transit_positions` param per month fixture and remove the `xfail` mark from `remainder`; replace `compute_output_for`'s `raise NotImplementedError` with `return {}`; add `_PLANET_BODIES` to the `core.ephemeris.chart` import; extend the module docstring.
- [x] `tests/conformance/fixtures/two-lunations-month.toml` — delete `retrograde = true` from the jupiter and uranus `transit_positions` entries; add a `correction_2026_08_27` note citing the 2023-09-05 / 2023-08-30 station dates and the still-direct motion on 2023-08-01.
- [x] `tests/conformance/fixtures/no-lunations-month.toml` — set the moon `transit_positions` `longitude` to `"138.1793"`; add a `correction_2026_08_27` note citing the wrong-date transcription (2018-02-05) and the 2018-01-31 Leo lunar eclipse.
- [x] `tests/test_conformance.py` — I/O Matrix rows 1–5 & 7 are exercised by the parametrized `test_computed_output_matches_conformance_fixture[*-transit_positions]` / `[*-remainder]` / natal cases the wiring adds; rows 6 (unknown-section tripwire) and 8 (missing/naive `transit_snapshot_utc`) get focused tests: `test_remainder_scope_trips_on_an_unrecognized_expected_section`, `test_remainder_scope_passes_when_only_recognized_sections_are_present`, `test_transit_positions_rejects_a_missing_or_naive_snapshot[missing|naive]`.

**Acceptance Criteria:**
- Given the seven-fixture adversarial set, when `uv run pytest tests/test_conformance.py tests/test_conformance_runner.py -rX` runs, then every case passes with zero `xfail`, `xpass`, or `fail`.
- Given a month fixture's `expected.transit_positions`, when the `transit_positions` scope runs, then each of the ten bodies' computed longitude is within 0.01° of the transcribed value and every asserted `retrograde` flag matches.
- Given a fixture that gains an `expected.<section>` the harness does not recognize, when the `remainder` case runs, then it fails and names `expected.<section>`.
- Given the three corrected fixture values, when the story is presented for merge, then Francesco has re-verified each against a live Astro.com session and recorded the outcome in its `correction_2026_08_27` note (or replaced the value with what Astro.com shows).
- Given the full suite, when `uv run pytest` runs, then it passes and `uv run ruff check .` is clean.

## Design Notes

`transit_positions` is a conformance cross-check — "does our ephemeris agree with Astro.com at an arbitrary non-birth instant" — not a Report artifact, so it stays in the test-shaping layer exactly like `_transit_events_for_month_fixture` (which already recomputes orbs via `_calc_body`). No `core/transits/positions.py` exists and none is wanted.

The Moon is one of the ten bodies here even though `core/transits/aspects._TRANSIT_BODY_IDS` excludes it: that exclusion is about the transiting Moon never being an *aspect* partner (FR-9); a raw position snapshot legitimately lists it, and `_PLANET_BODIES` already carries it.

Keeping `remainder` as a real (un-`xfail`ed) case comparing `{}` vs `{}` turns it into a release-gate tripwire: a new adversarial fixture section cannot slip in unchecked — the case fails until the harness learns to compute it. Same "make the gap visible" intent the original `xfail` had, without a standing expected-failure.

Example computed row: `{"name": "saturn", "longitude": "335.7128", "retrograde": True}`.

## Verification

**Commands:**
- `uv run pytest tests/test_conformance.py tests/test_conformance_runner.py -q -rX` — expected: all pass; the `-rX` summary lists no XPASS and no XFAIL lines.
- `uv run pytest -q` — expected: full suite green.
- `uv run ruff check .` — expected: clean.

**Manual checks:**
- Francesco: for each corrected value, open Astro.com's "Natal chart and transits" tool at the fixture's `transit_snapshot_utc` (`2023-08-01 00:00 UT` for jupiter/uranus, `2018-02-01 00:00 UT` for the Moon) against the `near-midnight-birth` anchor, confirm the corrected flag / longitude, and record the result in the `correction_2026_08_27` line.

## Suggested Review Order

**The wiring (design intent)**

- Entry point: the new helper that computes the ten transiting bodies at the snapshot instant — reuses `_calc_body`, `_PLANET_BODIES` order, `retrograde = speed < 0`.
  [`test_conformance.py:474`](../../tests/test_conformance.py#L474)

- The scope routing: `transit_positions` returns real output; `remainder` returns `{}`; any other scope now raises instead of silently passing.
  [`test_conformance.py:552`](../../tests/test_conformance.py#L552)

- `_expected_for_scope` mirror — the `transit_positions` slice, the commented two-rationale exclusion tuple, and the matching `raise` for unknown scopes.
  [`test_conformance.py:581`](../../tests/test_conformance.py#L581)

- Parametrization: a real `transit_positions` case per month fixture; `remainder` keeps a case but loses its `xfail` mark.
  [`test_conformance.py:627`](../../tests/test_conformance.py#L627)

- The two new scope constants.
  [`test_conformance.py:407`](../../tests/test_conformance.py#L407)

**Fixture corrections (need Francesco's live Astro.com re-verification before merge)**

- Jupiter & Uranus corrected from `retrograde = true` to `retrograde = false` (positively asserted, not deleted); dated note with the station dates.
  [`two-lunations-month.toml:7`](../../tests/conformance/fixtures/two-lunations-month.toml#L7)

- Moon longitude `198.1833` → `138.1793`; dated note leaves the root cause (two-sign offset vs wrong-date read) open for the re-verify, and bounds the blast radius.
  [`no-lunations-month.toml:28`](../../tests/conformance/fixtures/no-lunations-month.toml#L28)

**Tests (supporting)**

- `remainder` tripwire: an unrecognized `expected.*` section fails the compare and names it.
  [`test_conformance.py:705`](../../tests/test_conformance.py#L705)

- `remainder` pass-through: only-recognized sections leave both sides empty (covers own-scope and bracket-test exclusions).
  [`test_conformance.py:726`](../../tests/test_conformance.py#L726)

- Shape guard for the new helper: ten rows, `_PLANET_BODIES` order, `str` longitude, `bool` retrograde — oracle-independent.
  [`test_conformance.py:788`](../../tests/test_conformance.py#L788)

- Missing / naive `transit_snapshot_utc` raises `FixtureFormatError` (tested at the shared helper).
  [`test_conformance.py:773`](../../tests/test_conformance.py#L773)

- Module docstring: the Story 8.1 paragraph.
  [`test_conformance.py:74`](../../tests/test_conformance.py#L74)
