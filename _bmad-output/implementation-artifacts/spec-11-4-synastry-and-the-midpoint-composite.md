---
title: '11-4 Synastry and the midpoint composite'
type: 'feature'
created: '2026-10-10'
status: 'done'
baseline_commit: 'c062aee493c53fcf73cce56fcd2542092133554d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A couple consultation needs computed facts for two people together, and the API offers only single-subject endpoints.

**Approach:** Add `POST /api/v1/charts/synastry` on two 11.2 subjects: both natal charts, inter-aspects, house overlays both ways and the midpoint composite, from new pure functions in `core/synastry/`. `ComputationConfig` goes to `version = 2` with `orbs.synastry` and `[composite] houses`.

## Boundaries & Constraints

**Always:** Request `{subject_a, subject_b}`, each a `SubjectModel`; parse errors name `subject_a.…` / `subject_b.…`. Response per change request §4.6: `meta` (now with `orbs.synastry`), `subjects`, `natal_a`, `natal_b` (11.2 chart shapes, known or unknown), `inter_aspects`, `overlays`, `composite`; body `canonical_json_bytes`, byte-identical on repeat. Inter-aspects: every (A point, B point) over the ten planets, both nodes, ascendant, midheaven; five majors; `orbs.synastry`; `{body_a, body_b, aspect, orb}` with no applying flag. A time-unknown subject contributes no angles and no Moon. Overlays: `a_in_b` / `b_in_a` list `{body, house}` for the ten planets and nodes; an overlay into an unknown-time subject's houses is `null`. Composite: planets and nodes are shorter-arc midpoints; exact opposition (arc 180°) gives A's longitude + 90° normalized; ascendant and midheaven are midpoints of the two angles; aspects within `orbs.natal`, planets and nodes only, `applying: null`. Either time unknown ⇒ composite `ascendant`, `midheaven`, `houses` and planet `house` are `null` and composite Moon aspects are excluded. Houses follow `[composite] houses`: `midpoint_cusps` (shorter-arc midpoint of each cusp pair) or `derived_from_mc` (Placidus from the composite MC at the mean of the two birth latitudes). `orbs.synastry` is loaded as a 6.0–8.0 decimal. Composite house derivation that calls Swiss Ephemeris lives in `core/ephemeris/` and binds the verified path first. Sync handler; nothing stored or logged about the subjects.

**Ask First:** Any change to existing orbs or to natal/transit output. (Resolved 2026-10-10 with Francesco's Astro.com session: ship `[composite] houses = "midpoint_cusps"`, see Design Notes; `derived_from_mc` stays implemented and tested as the data-edit alternative.)

**Never:** Touch the `RunDriver`, add a table or migration, feed results into Payload/Generator/Gate, add an applying flag, make the method request-selectable.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Both known | two valid subjects | all blocks populated | N/A |
| One unknown | B `time_known: false` | no B angles/Moon in inter-aspects; `a_in_b` null, `b_in_a` populated; composite angles/houses/house null, no composite Moon aspect | N/A |
| Both unknown | both false | overlays both null, composite angles/houses null | N/A |
| Exact opposition | A 10°, B 190° | composite longitude 100° | N/A |
| Near opposition | arc 179.9999° vs 180.0001° | shorter-arc midpoint vs the +90° rule, deterministic | N/A |
| Wrap across 0° | 350° and 20° | composite 5° | N/A |
| Orb edge | pair at exactly `orbs.synastry` | included; just beyond excluded | N/A |
| Bad subject | DST gap in B | none | `invalid_request`, `subject_b.birth_time` |
| Config | `orbs.synastry` 5.9 / 8.1, unknown `houses` | startup rejects | loader error |
| Repeat | identical request | identical bytes, no row written | N/A |

</frozen-after-approval>

## Code Map

- `data/computation.toml`, `shell/computation.py:162` (`_read_orbs`, `_ORBS_KEYS`), `core/types/computation.py` (`Orbs`; add `synastry`, a `Composite` table) -- version 2; loader validation; every test TOML (`tests/test_computation_config.py`, `_VALID_TOML`, version/hash pins) updated.
- `core/ephemeris/chart.py` -- reuse `detect_aspects`, `sign_and_degree`, `_house_for_longitude` (make public as needed), `_ASPECTS`/`_match_aspect`; `positions.py` -- `_angular_separation`, `_normalize_decimal`.
- `core/ephemeris/time_unknown.py` -- noon-chart planets as unknown-subject points.
- `core/synastry/` (new: `inter_aspects.py`, `overlays.py`, `composite.py`), `core/types/synastry.py` -- pure functions and result types; `core/ephemeris/composite_houses.py` -- `derived_from_mc` (ARMC from the composite MC, `swe.houses_armc`).
- `shell/http/api/synastry.py` (new), `__init__.py`, `meta.py` (add `synastry` orb), `charts.py` (`jsonable`, `subject_json`, chart serialisers shared), `subject.py` (`parse_subject` field prefix).
- `tests/test_api_natal.py` -- app/bearer fixtures; `tests/conformance/` -- fixture layout; `tests/test_import_boundary.py`.

## Tasks & Acceptance

**Execution:**
- [x] `data/computation.toml`, `shell/computation.py`, `core/types/computation.py` -- `version = 2`, `orbs.synastry = "7.0"`, `[composite] houses`; loader ranges and enum; update pinned hash/version tests
- [x] `core/types/synastry.py`, `core/synastry/*` -- inter-aspects, overlays, midpoint with opposition rule, composite chart for both house methods
- [x] `core/ephemeris/composite_houses.py` -- Placidus cusps from a composite MC and mean latitude
- [x] `shell/http/api/synastry.py`, `meta.py`, `charts.py`, `subject.py` -- endpoint, unknown-time nulls, field prefixes
- [x] `tests/test_synastry_core.py`, `tests/test_api_synastry.py` -- every matrix row, repeat bytes, row count, sync route, boundary guard negatives if new guards are added
- [x] `tests/conformance/fixtures/` -- composite fixture from the transcribed values in Design Notes; synastry and near-opposition composite fixtures transcribed from Astro.com during the build
- [x] `sprint-status.yaml` -- 11-4 to `review`

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access and route-walk guards.
- Given Francesco's transcribed Astro.com composite fixture, when it is added, then the shipped `houses` value matches it (flip the data value and bump the version if not).

## Spec Change Log

## Design Notes

**House method, decided by Astro.com (2026-10-10).** Composite (Midpoint-method, `btyp=621`) of Case1 LeapDay + Case3 Midnight: every cusp and the ascendant equals the shorter-arc midpoint of the two natal cusps within 0.0008°; `derived_from_mc` misses by 2–7° (cusps 11/12, 2/3, asc). Astro.com's separate "ref.place method" is the MC-derived variant. Transcribed values (Placidus, composite): Asc 4°36'42" Sagittarius, 2 = 10°21'23" Capricorn, 3 = 14°14'6" Aquarius, MC 14°13'11" Virgo, 11 = 11°40'51" Libra, 12 = 7°53'4" Scorpio; Sun 10°34'4" Aquarius; planet houses on the sheet: Sun 2, Moon 9, Jupiter 7, Saturn 4. The conformance tolerance for composite angles is 0.002°. Remaining fixtures, taken from the same session during the build: the Astro.com Synastry chart for a pair (inter-aspects, both overlays) and a composite pair with a near-opposition body.

## Verification

**Commands:**
- `uv run pytest tests/test_synastry_core.py tests/test_api_synastry.py tests/test_computation_config.py tests/test_import_boundary.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**Endpoint**

- Entry point: two sides, inter-aspects, overlays, composite, canonical bytes.
  [`synastry.py:141`](../../shell/http/api/synastry.py#L141)

- Known/unknown branch per subject, with `subject_a.`/`subject_b.` error fields.
  [`synastry.py:71`](../../shell/http/api/synastry.py#L71)

**Composite and the house method Astro.com decided**

- Shorter-arc midpoint with the A+90° rule at exact opposition.
  [`composite.py:39`](../../core/synastry/composite.py#L39)

- `midpoint_cusps` is what Astro.com does; fixture-pinned.
  [`composite.py:53`](../../core/synastry/composite.py#L53)

- Alternative method kept as a data edit, never shipped.
  [`composite_houses.py:33`](../../core/ephemeris/composite_houses.py#L33)

**Inter-aspects and overlays**

- Which points each subject contributes; unknown time drops angles and Moon.
  [`inter_aspects.py:26`](../../core/synastry/inter_aspects.py#L26)

- Overlay into houses, or null without them.
  [`overlays.py:21`](../../core/synastry/overlays.py#L21)

**Config version 2**

- `orbs.synastry` and `[composite] houses` in the one tuning home.
  [`computation.toml:21`](../../data/computation.toml#L21)

- Loader range check for the synastry orb and the closed house-method set.
  [`computation.py:164`](../../shell/computation.py#L164)

**Tests**

- Both Astro.com composite fixtures against the shipped method.
  [`test_synastry_core.py:261`](../../tests/test_synastry_core.py#L261)

- Synastry fixture: inter-aspects and overlays both ways.
  [`test_synastry_core.py:322`](../../tests/test_synastry_core.py#L322)

- API matrix: every block, unknown-time nulls, statelessness.
  [`test_api_synastry.py:101`](../../tests/test_api_synastry.py#L101)
