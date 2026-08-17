---
title: 'Assemble the four Domain Profiles'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'de9f6225833d3456322c8d853fcd6daf71f7091f'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A computed `NatalChart` (Story 2.2) with Rulers resolved (Story 2.4) is still shaped the
way an ephemeris emits it -- flat lists of planets, cusps and aspects -- not the way an astrologer
reads it, so nothing downstream (the Report Payload, Epic 3-4) has the four life-area groupings to
read from.

**Approach:** A new pure `core/domains/profiles.py` function takes the `NatalChart` and its resolved
`HouseRuler` tuple and regroups them by fixed rule into `amore`, `lavoro`, `denaro` and `benessere` --
each assembled from planets/houses already present in the inputs, with no new lookup, config or
computation introduced.

## Boundaries & Constraints

**Always:**
- Assembly is a pure function of `NatalChart` and `tuple[HouseRuler, ...]` only -- no I/O, clock,
  network, randomness, or import from `shell/` (AD-1). No `ComputationConfig` parameter: every value
  this story needs (sign, Aspects, Rulers) is already resolved upstream.
- The four Profiles' fields are literally named `amore`, `lavoro`, `denaro`, `benessere` -- Italian,
  lowercase, never translated (PRD glossary rule).
- Domain content follows FR-7 exactly: `amore` = Venus, Mars, 5th house, 7th house, Moon; `lavoro` =
  10th, 6th, 2nd houses (10th also stands for the midheaven); `denaro` = 2nd, 8th houses, Venus,
  Jupiter, Saturn; `benessere` = ascendant (house 1), 6th house, Mars, Saturn, Moon.
- A house's "planets in it" = `chart.planets` filtered by `.house == cusp number`. A planet's/house's
  Aspects = `chart.aspects` filtered to entries naming that planet, or naming any planet in that house.
  `chart.aspects` already holds only the five major Ptolemaic aspects within configured Orb (Story
  2.2), so no further "principal" narrowing applies -- the matching set is the principal set.
- A house's sign is read from the matching `HouseRuler.sign` (already resolved, Story 2.4); a planet's
  sign is read from `PlanetPosition.sign`. No new sign-from-longitude derivation.
- Calling assembly twice on the same `NatalChart`/rulers produces byte-identical results (implied by
  purity).

**Ask First:** none anticipated.

**Never:**
- No persistence -- this story returns a value; storing `DomainProfiles` is a later story's concern
  (Story 2.4 precedent).
- No new error type -- both inputs are already validated by `compute_natal_chart()` and
  `resolve_house_rulers()`; there is no failure mode for this function to raise.
- No calling `resolve_house_rulers()` itself -- rulers are received as an already-resolved parameter.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full chart | A `NatalChart` + its 12 resolved `HouseRuler` entries | `DomainProfiles` with all four domains populated per FR-7 | N/A |
| Planet in a domain | e.g. Venus's position + its Aspects | `DomainPlanet(name="venus", sign=.., house=.., aspects=<Aspects naming venus>)` | N/A |
| House in a domain | e.g. the 5th house's cusp, planets in it, its Ruler | `DomainHouse(number=5, sign=<rulers[4].sign>, planets=<planets with house==5>, ruler=rulers[4], aspects=<Aspects naming those planets>)` | N/A |
| Empty house | No planet falls in a domain house | `DomainHouse.planets == ()` and `.aspects == ()` | N/A |
| Purity | Same `NatalChart` + rulers, assembled twice | Byte-identical `DomainProfiles`; no clock/network/db consulted | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/types/chart.py:87,21,52,70` -- `NatalChart` (`planets`, `houses`, `aspects`),
  `PlanetPosition` (`name`, `sign`, `house`), `HouseRuler` (`house`, `sign`, ...), `Aspect` (`body1`,
  `body2`) -- the inputs this story reads; no field changes needed.
- `core/domains/rulers.py:40` (`resolve_house_rulers`) -- produces the `tuple[HouseRuler, ...]` this
  story consumes as a parameter; not called by this story.
- `core/domains/__init__.py` -- existing empty package docstring; this story adds the second module.
- `tests/test_house_rulers.py:39,19` -- pattern for a minimal `NatalChart` fixture and for loading the
  real `ComputationConfig` via `shell.computation.load_computation_config()` in a `core/` test.
- `ARCHITECTURE-SPINE.md` `domains/` entry -- confirms `core/domains/` as this capability's home
  (4.2 Domain Profiles, FR-6/FR-7).

**To create:**
- `core/types/domains.py` -- frozen dataclasses: `DomainPlanet(name, sign, house, aspects)`;
  `DomainHouse(number, sign, planets, ruler, aspects)`; `AmoreProfile(venus, mars, house_5, house_7,
  moon)`; `LavoroProfile(house_10, house_6, house_2)`; `DenaroProfile(house_2, house_8, venus, jupiter,
  saturn)`; `BenessereProfile(ascendant, house_6, mars, saturn, moon)`; `DomainProfiles(amore, lavoro,
  denaro, benessere)`.
- `core/domains/profiles.py` -- `assemble_domain_profiles(chart: NatalChart, rulers: tuple[HouseRuler,
  ...]) -> DomainProfiles`; private helpers to build one `DomainPlanet` by name and one `DomainHouse`
  by cusp number, reused across all four domains.
- `tests/test_domain_profiles.py` -- one test per I/O matrix row, plus: field names are
  `amore`/`lavoro`/`denaro`/`benessere`; `lavoro.house_10`/`benessere.ascendant` equal the house
  10/house 1 `DomainHouse`; purity.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/domains.py` -- add `DomainPlanet`, `DomainHouse`, `AmoreProfile`, `LavoroProfile`,
  `DenaroProfile`, `BenessereProfile`, `DomainProfiles` frozen dataclasses -- required result shapes
- [x] `core/domains/profiles.py` -- `assemble_domain_profiles()` -- AC1-AC3
- [x] `tests/test_domain_profiles.py` -- unit-test the I/O matrix rows plus naming and purity -- AC1-AC3

**Acceptance Criteria:**
- Given a `NatalChart` with Rulers resolved, when `core/domains/` assembles the Profiles, then
  `amore` contains Venus (sign, house, Aspects), Mars (sign, house, Aspects), the 5th house (sign,
  planets in it, Ruler), the 7th house (sign, planets in it, Ruler), and the Moon (sign, house,
  Aspects); `lavoro` contains the 10th, 6th and 2nd houses (10th standing also for the midheaven),
  each with sign, planets in it, Ruler and Aspects; `denaro` contains the 2nd and 8th houses, and
  Venus, Jupiter and Saturn with their Aspects; `benessere` contains the ascendant (house 1) with its
  Ruler, the 6th house, Mars, Saturn and the Moon.
- Given the four Profiles, when they are named in code, then they are `amore`, `lavoro`, `denaro` and
  `benessere` -- Italian, lowercase, never translated.
- Given the same `NatalChart`, when the Profiles are assembled twice, then the results are
  byte-identical, asserted by test, and assembly consulted no clock, network or database.

## Spec Change Log

## Design Notes

**One shared shape per kind, not one bespoke shape per domain row.** `DomainHouse`/`DomainPlanet` are
used identically in all four Profiles, even where an AC row doesn't spell out every field (e.g.
`amore`'s 5th/7th houses don't mention Aspects) -- a superset of the required fields satisfies every
row without contradicting it, and the Aspects-filtering logic is needed for `lavoro` regardless, so
reusing it everywhere is less code than two near-duplicate types.

**Ascendant/midheaven are not separate lookups**, mirroring Story 2.2 ("house 1's cusp is the
ascendant, house 10's is the midheaven") -- `benessere.ascendant`/`lavoro.house_10` are just cusp 1's
and cusp 10's `DomainHouse`.

**No third copy of sign-from-longitude.** Story 2.4 already resolved every cusp's sign onto
`HouseRuler.sign`; this story reads that instead of re-deriving it from `HouseCusp.longitude`.

## Verification

**Commands:**
- `uv run pytest tests/test_domain_profiles.py` -- new tests green
- `uv run pytest` -- full suite green
- `uv run ruff check .` -- clean

## Suggested Review Order

**Assembly: the pure regrouping function**

- Entry point: regroups one `NatalChart`/`rulers` pair into the four Profiles by fixed rule -- the whole story's contract in one function.
  [`profiles.py:27`](../../core/domains/profiles.py#L27)

- Shared house-builder: sign from `HouseRuler.sign`, planets by `.house == number`, Aspects filtered to those planets -- reused for all seven cusps this story reads.
  [`profiles.py:77`](../../core/domains/profiles.py#L77)

- Shared planet-builder: sign/house from `PlanetPosition`, Aspects filtered to that one name -- reused across all five planet mentions.
  [`profiles.py:64`](../../core/domains/profiles.py#L64)

- Where a hardcoded "principal Aspects" rule would have gone: one filter over `chart.aspects` by body name, since the chart already holds only the five major aspects.
  [`profiles.py:94`](../../core/domains/profiles.py#L94)

**New result types**

- `DomainHouse`/`DomainPlanet`: the one shared shape per kind used identically in all four Profiles (see this spec's Design Notes).
  [`domains.py:35`](../../core/types/domains.py#L35)
  [`domains.py:46`](../../core/types/domains.py#L46)

- The four domain-specific Profiles plus the `amore`/`lavoro`/`denaro`/`benessere` container -- field names are the literal Italian words, never translated.
  [`domains.py:59`](../../core/types/domains.py#L59)
  [`domains.py:103`](../../core/types/domains.py#L103)

**Peripherals**

- The multi-planet-house test proving `_build_house()` collects every planet in a cusp, not just the first match -- added during review to close a verification gap.
  [`test_domain_profiles.py:180`](../../tests/test_domain_profiles.py#L180)

- Coverage of every I/O matrix row: full chart, a planet in a domain, a house in a domain, an empty house, and purity.
  [`test_domain_profiles.py:111`](../../tests/test_domain_profiles.py#L111)

- Cross-domain reuse proof: the same house/planet, independently assembled from two different Profiles, is byte-identical.
  [`test_domain_profiles.py:225`](../../tests/test_domain_profiles.py#L225)
