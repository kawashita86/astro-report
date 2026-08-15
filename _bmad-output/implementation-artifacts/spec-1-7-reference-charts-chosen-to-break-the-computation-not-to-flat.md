---
title: 'Story 1.7 — Reference charts chosen to break the computation, not to flatter it'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 1
baseline_commit: 'bac4bb8677f6c2329cb4ee0efdc68e0b986ffa8c'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `tests/conformance/fixtures/` ships empty (Story 1.6). No real, independently-verifiable reference chart exists yet for any future Epic 2/3 computation to be checked against, and the epic's own cross-story notes flag this story as needing Francesco's domain judgement, not an AI-invented dataset — fabricating plausible-looking astronomical data here would defeat the entire purpose of a conformance harness.

**Approach:** Source real, publicly-documented birth data for the six required adversarial cases (leap-day birth, a birth pair either side of a historical DST switch, a near-midnight birth, a month containing a retrograde planetary station, a month with two lunations of one kind, a month with none), compute their charts via Astro.com's own free chart tool logged into a real Astro.com account (not fabricated, not Astrodatabank — that tool turned out to withhold all results from unauthenticated guests), and transcribe the results into `tests/conformance/fixtures/*.toml` following the Story 1.6 schema. Natal and transit-to-natal aspects are derived from the transcribed real positions using *this project's own* orb/aspect rules (`data/computation.toml`), not Astro.com's own aspect grid, since conformance must mean "our rules applied to real positions," not "Astro.com's aspect opinions."

## Boundaries & Constraints

**Always:**
- Every fixture's birth data (date, time, place) is real and independently traceable — either a real documented birth (news-reported, hospital-confirmed) or a real, verifiable astronomical calendar fact (a real month's lunation timestamps, a real bracketed planetary station). Real person names are replaced with placeholder profile labels in the fixture (`metadata.note` discloses this); the astronomical facts are never fabricated.
- Aspects recorded in `expected` are computed from the transcribed real longitudes using `data/computation.toml`'s own orb values (natal 7.0°, transit 2.0°) and the standard five aspects — never copied from Astro.com's own aspect grid, which uses different default orbs.
- Every fixture's `[metadata].source` names where the data came from and how it was computed, at the precision actually achieved (e.g. the retrograde-station fixture records a bracketing range, not a fabricated exact station instant).
- The fixture schema follows `tests/conformance/fixtures/README.md` exactly: `[metadata]` / `[birth_data]` / `[expected]`, loose/free-form `expected` shape.
- The three month fixtures share one anchor natal chart (`near-midnight-birth.toml`) for their transit-to-natal snapshots, for internal consistency across the set.

**Ask First:**
- Which real birth-data candidates to use for the person-based adversarial cases — presented to Francesco for confirmation before any Astro.com computation was performed.
- Whether to proceed with an Astro.com login at all, since the free chart tool's full output (houses, exact degrees) is gated behind account registration — Francesco logged into his own account and authorized driving it; no credentials were ever seen or entered by the assistant.

**Never:**
- No fabricated astronomical data — every date/time/place is real, and every computed position was actually read from Astro.com's own output, not invented to look plausible.
- No entering of Astro.com credentials, and no account creation, by the assistant.
- No change to Epic 2/3 domain types or `compute_output_for()`'s `NotImplementedError` body — that remains Epic 2/3's job. This story only had to keep the existing test suite green now that fixtures are non-empty, which required narrowly-scoped fixes to two Story 1.6 test assertions that had baked in "the directory is empty" as their subject (see Design Notes).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Leap-day birth | Real Feb 29 2024 birth, Durham NC | Full natal chart (12 planets, 12 houses, natal aspects) transcribed | N/A — reference fixture only |
| DST fall-back, before switch | Real Nov 6 2016 birth, 1:39am, forced EDT | Full natal chart, timezone explicitly forced (not left on "automatic") since the local hour repeats | N/A |
| DST fall-back, after switch | Real Nov 6 2016 birth, 1:10am, forced EST, same location/event as above | Full natal chart; positions plausibly ~31 minutes' motion from the "before" fixture, not a full sign off | N/A |
| Near-midnight birth | Real Jan 1 2026 birth, exactly 12:00am | Full natal chart; also serves as the anchor for the three month fixtures | N/A |
| Two-lunations month | August 2023 (two real full moons) | `expected.lunations` has 2 entries with real UTC timestamps; transit snapshot + transit-to-natal aspects at month start | N/A |
| No-lunations month | February 2018 (zero real full moons) | `expected.lunations = []` explicitly — an empty list is itself the fact under test | A computation that always finds ≥1 full moon/month should fail this fixture once wired in |
| Retrograde-station month | December 2022 (real Mercury station) | Station recorded as a bracketing range (last confirmed direct, first confirmed retrograde), not a fabricated exact instant | N/A |
| Fixtures directory no longer empty | `discover_fixtures()` on the real directory | Now returns 7 paths; the Story 1.6 test asserting `== []` had to be inverted to assert non-emptiness | Covered by `test_reports_zero_fixtures_without_failing` (renamed meaning, same name) |
| Parametrized conformance test now reaches real fixtures | `compute_output_for()` still raises `NotImplementedError` (Epic 2/3 don't exist) | Each fixture ID is marked `xfail(raises=NotImplementedError)` so CI stays green; the day Epic 2/3 lands, a newly-passing fixture XPASSes, which is the visible signal to remove its xfail | `xfail_strict` confirmed in `pyproject.toml` so an unexpected pass is *not* silently absorbed |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `tests/conformance/fixtures/README.md` — the schema every fixture below follows
- `data/computation.toml` — orb values (natal 7.0°, transit 2.0°) and fast/slow transiting body sets used to derive every `[[expected.aspects]]` / `[[expected.transit_events]]` entry
- `tests/conformance/runner.py` — `discover_fixtures()` / `load_fixture()` / `compare()`, unchanged in behavior (only two stale comments updated)

**Created:**
- `tests/conformance/fixtures/leap-day-birth.toml`
- `tests/conformance/fixtures/dst-fallback-before.toml`
- `tests/conformance/fixtures/dst-fallback-after.toml`
- `tests/conformance/fixtures/near-midnight-birth.toml`
- `tests/conformance/fixtures/two-lunations-month.toml`
- `tests/conformance/fixtures/no-lunations-month.toml`
- `tests/conformance/fixtures/retrograde-station-month.toml`

**Modified:**
- `tests/test_conformance.py` — `test_reports_zero_fixtures_without_failing` inverted to assert non-emptiness; `test_computed_output_matches_conformance_fixture` gained `@pytest.mark.xfail(raises=NotImplementedError, ...)`; module docstring updated to explain both.
- `tests/test_conformance_runner.py` — `test_the_default_fixtures_directory_reports_zero_fixtures` renamed to `test_the_default_fixtures_directory_is_discoverable_without_raising`, no longer asserts a specific count.
- `tests/conformance/runner.py` — two comments ("ships empty" / "until Story 1.7") updated to stop being stale now that this story has landed.

## Tasks & Acceptance

- [x] Source real candidate birth data for all six adversarial cases; confirm candidates with Francesco before computing charts.
- [x] Compute full natal output (planets, houses, aspects) for four real natal charts via Astro.com, logged into Francesco's account, driven by the assistant without ever seeing or entering credentials.
- [x] Independently verify a retrograde-station month by bracketing a real station with two Astro.com snapshots (before/after), rather than trusting an unverified third-party "exact time" claim.
- [x] Corroborate the two lunation-count months (Aug 2023 two full moons, Feb 2018 zero) against multiple independent external sources, not Astro.com alone.
- [x] Derive every natal and transit-to-natal aspect from the real transcribed positions using this project's own orb/aspect rules (`data/computation.toml`), not Astro.com's own aspect grid — verified programmatically against a throwaway script, catching one transcription error (a Sun longitude typo) before it shipped.
- [x] Transcribe all seven fixtures into TOML per the Story 1.6 schema; confirm every fixture loads via `discover_fixtures()` / `load_fixture()`.
- [x] Fix the two Story 1.6 test assertions that broke once the fixtures directory was no longer empty, keeping the full suite green.
- [x] Full suite green: `.venv/bin/python -m pytest` → 259 passed, 7 xfailed; `.venv/bin/python -m ruff check .` clean.

## Design Notes

**Astrodatabank was a dead end.** The user's first suggestion was to use `astro.com/cgi/aq.cgi/adb-search` (Astrodatabank) to research real birth-data candidates directly. That tool's search form works for a guest visitor, but silently withholds all results — confirmed empirically by submitting the same leap-day search three times, including after clearing a validation-blocking empty filter row. "Guest visitor, no access" turned out to mean exactly what it says: query-building is free, results are not.

**Astro.com's free chart tool also gates on registration — resolved by Francesco logging in himself.** Entering birth data without an account gives only Sun/Moon sign — house cusps and exact degrees require `[correct birth data] → Step 2: Registration` with an email and password. The assistant does not create accounts or handle passwords under any circumstance, including with user authorization. Francesco logged into his own Astro.com account in the browser; the assistant continued driving data entry and reading results, never touching the login fields.

**Real "first baby of the year" / DST-twins / leap-day-baby news stories turned out to be a better source than celebrity Astrodatabank entries.** Hospitals and news outlets report exact, hospital-confirmed birth times specifically *because* they straddle a clock event — this sidesteps the problem that celebrity birth times are usually only reliably known through Astrodatabank's own paid research (which was unavailable here), and avoids attributing a possibly-wrong time to a real named public figure. The Cape Cod DST-twins story in particular gave two real, precisely-timed charts from a single well-documented event for the price of one.

**A privacy-minimizing choice: Astro.com profile labels, not real names.** The underlying birth data (date/time/place) is real and publicly reported; the children's real names were deliberately not entered into Astro.com's own stored-profile system or committed to this repository, since the astronomical computation doesn't depend on the name field at all. Each fixture's `metadata.note` discloses this substitution.

**Aspects are computed from real positions using our own rules, not copied from Astro.com's aspect grid.** Astro.com's on-screen aspect grid uses Astro.com's own default per-planet orbs (visible on the Astrodatabank search page: `10°, 6°, 10°, 10°, 10°, 3°, 3°, 2°, 3°, 2°, 3°, 1°, 1°`), which do not match this project's `data/computation.toml` orb values (natal 7.0°, transit 2.0°). Reading Astro.com's grid pixel-by-pixel would also have been unreliable at the resolution available. Instead, every `[[expected.aspects]]` / `[[expected.transit_events]]` entry was computed by a throwaway script from the transcribed real longitudes, applying this project's own orb and standard-five-aspect rules — which is also the more correct design, since conformance fixtures exist to check *our* computation pipeline, not to reproduce Astro.com's own aspect opinions.

**Month fixtures record a single snapshot moment, not a whole-month walk.** `two-lunations-month.toml` and `no-lunations-month.toml` record transit-to-natal aspects at 00:00 UT on the 1st of the month; `retrograde-station-month.toml` does the same plus a bracketed station range. This is a deliberate scope reduction from "every aspect that forms and separates across the month" — Epic 3 hasn't defined a `TransitEvent` walk yet, and a single real, independently-checkable moment is more valuable than a large multi-body transcription attempted at a zoom level where transcription errors become likely. The two lunation timestamps and the station bracket — the actual adversarial facts under test — are the parts transcribed at full precision and cross-checked externally.

**Populating the fixtures directory broke two Story 1.6 test assertions that had baked in "the directory is empty" as their subject.** `test_reports_zero_fixtures_without_failing` asserted `discover_fixtures() == []` against the *real* directory (not a synthetic one) — accurate when Story 1.6 shipped it, false the moment this story landed real fixtures. More seriously, `test_computed_output_matches_conformance_fixture`'s parametrize was written when zero fixtures meant zero test IDs and the test body was *never reached*; the module's own docstring said as much. With 7 real fixtures now discovered, the test body executes for real and calls `compute_output_for()`, which still legitimately raises `NotImplementedError` (Epic 2/3 don't exist) — an unguarded regression the moment this story landed, not a pre-existing one. Fixed with `xfail(raises=NotImplementedError)` per fixture, confirmed to fail loudly (not silently pass) if `compute_output_for` is ever changed to raise something else or return data, since `pyproject.toml` has `xfail_strict = true` — the day Epic 2/3 wires in real computation, a fixture that now matches will XPASS and the build will go red until its xfail marker is removed, which is exactly the visible signal wanted.

## Verification

- `.venv/bin/python -m pytest` → 259 passed, 7 xfailed, 0 failed.
- `.venv/bin/python -m ruff check .` → clean.
- Every fixture confirmed to load via `discover_fixtures()` / `load_fixture()` with the expected `[metadata]`/`[birth_data]`/`[expected]` shape.
- Every planetary longitude and house cusp cross-checked programmatically against the throwaway conversion script's output (zero mismatches after fixing one manually-introduced Sun-longitude typo in the retrograde-station-month transit snapshot).
- Independent review pass covering TOML schema conformance, DST-pair internal consistency, aspect-orb spot-checks, the xfail/inverted-assertion changes' actual regression-catching behavior, and metadata honesty about transcription precision.

## Spec Change Log

- **Review round 1**: found `pyproject.toml` had no `xfail_strict = true`, so the exact regression-hiding gap this story's own Design Notes warned about (an XPASS silently passing once Epic 2/3 lands) would actually have happened. Patched: added `xfail_strict = true` to `[tool.pytest.ini_options]`. Full suite re-verified green after the change (259 passed, 7 xfailed).

## Suggested Review Order

1. `tests/conformance/fixtures/README.md` (schema recap)
2. `data/computation.toml` (orb/aspect rules every fixture's aspects are derived from)
3. The four natal fixtures (`leap-day-birth.toml`, `dst-fallback-before.toml`, `dst-fallback-after.toml`, `near-midnight-birth.toml`)
4. The three month fixtures (`two-lunations-month.toml`, `no-lunations-month.toml`, `retrograde-station-month.toml`)
5. `tests/test_conformance.py`, `tests/test_conformance_runner.py`, `tests/conformance/runner.py` (the narrowly-scoped fixes required to keep the suite green)
