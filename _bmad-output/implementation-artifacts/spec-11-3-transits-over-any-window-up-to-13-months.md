---
title: '11-3 Transits over any window up to 13 months'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '58a6c357e2f5fdd57ee7ee25abef766ebdc8a677'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The alerenzi plugin can get a natal chart but not the transit events that a consultation's forecast (next three months, or twelve from a birthday) should rest on; the existing scans only run over one calendar month inside a Report run.

**Approach:** Add `POST /api/v1/charts/transits` on the 11.2 subject, converting a half-open local-date window to one UTC interval and calling the existing four `core/transits` scans over it, serialised from the core types. Time-unknown subjects get the house-free subset.

## Boundaries & Constraints

**Always:** Request is `{subject, window:{start_date,end_date}}` (ISO local dates, half-open, in the subject place's zone), converted once to one UTC interval (local 00:00 of each date, gap-lenient like `unknown_time_instants`). `end_date <= start_date` is `invalid_request` on `window.end_date`; longer than 13 calendar months (`end_date` after `start_date` plus 13 months, month-end clamped) is `window_too_long` on `window.end_date`; a window date outside the vendored ephemeris span is `ephemeris_out_of_range` on that field. The maximum is a code constant, not config. Response is `meta`, `subject` (as 11.2), `window_utc:{start,end}`, `aspects`, `stations`, `standing_retrogrades`, `ingresses`, `lunations`; instants ISO-8601 `Z`, Decimals as strings, field names those of the core dataclasses, body `canonical_json_bytes`. Boundary rule is the existing one (`computation-tables.md` "API transit windows"): an aspect in orb at the start has `orb_entry_at` = window start, one still in orb at the end has `orb_exit_at: null`, a standing retrograde is clamped to the window. Known time: natal chart from `compute_natal_chart` at the birth instant. `time_known: false`: the noon chart supplies the targets; the ten planets and nodes except the natal Moon are targets, angles are not; `ingresses` is `null` and every lunation's `natal_house` is `null` (11.2's null-not-omitted convention). Sync handler; compute only through `core/` entry points that bind the verified ephemeris path; nothing stored or logged about the subject.

**Ask First:** Any change to what the four scans compute or to `ComputationConfig`. A different reading of "omitted" than null.

**Never:** Touch the `RunDriver`, add a table or migration, feed the result into Payload/Generator/Gate, make the window limit configurable, scan the transiting Moon.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 12-month window | known time, window crossing a Mercury station | all five lists; each event equals the union of the monthly scans | N/A |
| Window opens in orb | aspect in orb at start | `orb_entry_at` = `window_utc.start` | N/A |
| Window closes in orb | aspect in orb at end | `orb_exit_at: null` | N/A |
| Short window, retrograde throughout | 1 month, no turn | `standing_retrogrades` entry clamped to the window | N/A |
| Unknown time | `time_known: false` | no angle or natal-Moon targets; `ingresses: null`; lunation `natal_house: null` | N/A |
| Exactly 13 months | Jan 31 to Feb 28 next year | accepted | N/A |
| Over 13 months | one day longer | none | `window_too_long`, `window.end_date` |
| Empty or inverted | `end_date <= start_date` | none | `invalid_request`, `window.end_date` |
| Bad date / out of span | malformed, or year 1700 | none | `invalid_request` / `ephemeris_out_of_range` |
| Repeat | identical request | identical bytes, no row written | N/A |

</frozen-after-approval>

## Code Map

- `core/transits/aspects.py:82,177` -- `find_transit_aspects(natal_chart, …)` builds targets via `_natal_targets(NatalChart)`; extract a targets-taking public function it delegates to, so an unknown-time chart can pass its own targets (behavior of the existing function unchanged).
- `core/transits/lunations.py:74` -- `find_lunations` needs `natal_chart.houses` for `natal_house`; add a house-free variant (cusps optional) rather than duplicating the scan. `core/types/transits.py` -- `Lunation.natal_house` is `int`; the house-free path needs its own result or `int | None`.
- `core/transits/stations.py:52`, `ingresses.py:57` -- used as is. `_month_grid.py` -- 6 h grid, 40 halvings; a 13-month window is the same code over a longer interval.
- `core/types/chart.py:135` -- `TimeUnknownChart.planets` (noon longitudes incl. `south_node`, `moon`) is the unknown-time target source.
- `shell/http/api/charts.py` -- `_subject_json`, `_jsonable` (Decimal/dataclass only; add datetime → `format_utc_instant`) to promote and share; `natal_chart` handler is the pattern.
- `shell/http/api/subject.py` -- `parse_subject`, `known_time_instant`, `unknown_time_instants`, `format_utc_instant`; `shell/local_time.py` `local_to_utc(strict=False)`.
- `shell/http/api/errors.py` -- `ApiError`, `ErrorCode.WINDOW_TOO_LONG` already exist. `shell/http/api/__init__.py` -- register the new module in the import line.
- `shell/runner/advance.py:238` -- the monthly consumer of the same four scans; reference for call shapes only.
- `tests/test_api_natal.py` (app/session/bearer fixtures), `tests/test_stations.py`, `test_transit_aspects.py`, `test_lunations.py`, `test_month_grid.py`.

## Tasks & Acceptance

**Execution:**
- [x] `core/transits/aspects.py`, `core/transits/lunations.py`, `core/types/transits.py` -- targets-taking aspects entry point and house-free lunations; existing functions delegate, outputs unchanged -- one scan implementation
- [x] `shell/http/api/window.py` -- window model, parse to UTC interval, 13-month constant and check, span check -- reusable shape, one place
- [x] `shell/http/api/transits.py`, `charts.py`, `__init__.py` -- endpoint, known/unknown branches, serialisers; share the subject serialiser -- the AC response
- [x] `tests/test_api_transits.py` -- every matrix row, repeat-bytes, row-count (nothing grows), no-log check, route is sync
- [x] `tests/test_transit_window_seam.py` -- 12-month window vs twelve monthly scans (partition aligned to the 6 h grid so brackets match): perfections, stations, ingresses, lunations equal with none duplicated or missing; aspect in-orb intervals equal after merging adjacent clamped monthly pieces; standing retrogrades excluded (clamped per interval by design)
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 11-3 to `review`

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access, concurrency and route-walk guards.
- Given a 12-month known-time request, when handled locally, then the elapsed time is recorded in Verification (expected ≈ 3 s); the VPS measurement stays in 11.6.

## Spec Change Log

## Design Notes

Seam equality is exact only when both runs share a grid phase, because bisection brackets are 6 h steps from each interval's start; months starting at UTC midnight keep the phase. The API-level comparison, whose local-midnight months drift by DST, uses a 1 s tolerance. A pair in orb across a seam is two monthly events but one window event, so orb intervals are compared merged, perfections directly.

## Verification

Local timing, 12-month known-time request (including natal chart): about 3 s (module fixture setup 2.8 s).
Approved mid-build (Ask First): `find_transit_aspects(..., split_perfections=True)` emits one event per perfection in an orb interval; default off, monthly output unchanged; the API turns it on.

**Commands:**
- `uv run pytest tests/test_api_transits.py tests/test_transit_window_seam.py tests/test_transit_aspects.py tests/test_lunations.py tests/test_stations.py tests/test_ingresses.py tests/test_runner_advance.py tests/test_import_boundary.py tests/test_concurrency_boundary.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**The Ask-First change: every perfection in a long window**

- Opt-in flag keeps monthly output identical; a loop's later perfections are no longer dropped.
  [`aspects.py:309`](../../core/transits/aspects.py#L309)

- Explicit-target entry point lets an unknown-time chart pass targets without angles.
  [`aspects.py:120`](../../core/transits/aspects.py#L120)

- House-free lunations; `find_lunations` now adds the house on top.
  [`lunations.py:114`](../../core/transits/lunations.py#L114)

- Result type for a lunation with no house.
  [`transits.py:158`](../../core/types/transits.py#L158)

**Endpoint**

- Entry point: known/unknown branches, five event lists, canonical bytes.
  [`transits.py:64`](../../shell/http/api/transits.py#L64)

- Window to one UTC interval; 13-month ceiling and span checks.
  [`window.py:64`](../../shell/http/api/window.py#L64)

**Tests**

- Window equals the union of monthly scans, exactly, on a shared grid phase.
  [`test_transit_window_seam.py:52`](../../tests/test_transit_window_seam.py#L52)

- API-level matrix, statelessness, and monthly-union check with quantization tolerance.
  [`test_api_transits.py:159`](../../tests/test_api_transits.py#L159)
