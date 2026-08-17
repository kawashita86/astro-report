---
title: 'Resolve the Ruler of every house, traditional and modern'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '59bb6560d06e4768fc839f7a93b7ad04ee48302d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A computed `NatalChart` has twelve house cusps but no governing planet attached to
any of them, so nothing downstream (Story 2.5's Domain Profiles, which need a house's Ruler) can
run yet.

**Approach:** A new pure `core/domains/rulers.py` function takes a `NatalChart` and the passed
`ComputationConfig`, derives each cusp's zodiac sign, and looks up that sign's traditional and
modern Ruler from `config.rulers` -- never a hardcoded sign-to-planet mapping in code.

## Boundaries & Constraints

**Always:**
- Ruler assignment reads only `config.rulers.traditional`/`config.rulers.modern` (from
  `data/computation.toml`, AD-18) -- no sign-to-planet mapping is hardcoded in the function.
- All twelve cusps get a resolved entry, in cusp order 1-12.
- The traditional co-ruler is derived data, not a hardcoded sign list: a cusp's co-ruler is its
  `traditional_ruler` whenever `traditional_ruler != modern_ruler` (true today for Scorpio, Aquarius
  and Pisces per the configured tables), otherwise absent. This keeps "which signs disagree" a fact
  read from configuration, not asserted in code.
- Resolution is a pure function: no I/O, clock, network, randomness or import from `shell/` (AD-1).
- Calling resolution twice on the same `NatalChart`/`ComputationConfig` produces byte-identical
  results (implied by purity; no internal state, no ambient input).

**Ask First:** none anticipated.

**Never:**
- No persistence -- this story returns a value; storing it (if ever needed) is a later story's
  concern, not this one's.
- No Domain Profile assembly (Story 2.5) and no chart-wheel display (Story 2.6) -- resolution only.
- No new error type -- both inputs are already validated (`ComputationConfig` at load time, `NatalChart`
  by `compute_natal_chart()`); there is no failure mode for this function to raise.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Standard cusp | Cusp sign is e.g. Taurus (traditional Ruler == modern Ruler) | `HouseRuler` with `traditional_ruler="venus"`, `modern_ruler="venus"`, `co_ruler=None` | N/A |
| Scorpio/Aquarius/Pisces cusp | Cusp sign is Scorpio | `HouseRuler` with `traditional_ruler="mars"`, `modern_ruler="pluto"`, `co_ruler="mars"` | N/A |
| Full chart | A `NatalChart` with all twelve cusps | Twelve `HouseRuler` entries returned, one per cusp, ordered by `house` 1-12 | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `core/types/chart.py:42` (`HouseCusp` -- `number`, `longitude`; no `sign` field yet) and `:69`
  (`NatalChart.houses`) -- the input this story reads.
- `core/types/computation.py:60` (`Rulers` -- `traditional`/`modern` as `MappingProxyType[str, str]`,
  keyed by lowercase sign name) and `:89` (`ComputationConfig.rulers`) -- the lookup table.
- `core/ephemeris/chart.py:55` (`_ZODIAC_SIGNS`) and `:220` (`_sign_and_degree`) -- the existing
  sign-from-longitude pattern (module-private; not imported across modules, see Design Notes).
- `data/computation.toml` `[rulers.traditional]`/`[rulers.modern]` -- the twelve-sign tables already
  populated with the Scorpio/Aquarius/Pisces divergence (Story 1.5).
- `core/domains/__init__.py` -- existing empty package docstring ("Domain classification: amore,
  lavoro, denaro, benessere"); this story adds the first module inside it, per
  `ARCHITECTURE-SPINE.md`'s `domains/ — ruler resolution, the four Domain Profiles`.
- `tests/test_natal_chart.py:17-33` -- pattern for loading the real `ComputationConfig` via
  `shell.computation.load_computation_config()` in a `core/` test.

**To create:**
- `core/domains/rulers.py` -- `resolve_house_rulers(chart: NatalChart, config: ComputationConfig) ->
  tuple[HouseRuler, ...]`; derives each cusp's sign from its longitude (local helper, not imported
  from `core/ephemeris/chart.py`), looks up `traditional_ruler`/`modern_ruler` from `config.rulers`,
  and sets `co_ruler` when they differ.
- `tests/test_house_rulers.py` -- one test per I/O matrix row, plus: all twelve cusps resolved and
  correctly ordered; every non-divergent sign's `co_ruler` is `None`; the function consults no clock,
  network or database (purity).

**To modify:**
- `core/types/chart.py` -- add `HouseRuler` dataclass (`house: int`, `sign: str`,
  `traditional_ruler: str`, `modern_ruler: str`, `co_ruler: str | None`) alongside the existing chart
  types, and add it to `__all__`.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/chart.py` -- add frozen `HouseRuler` dataclass -- required result shape
- [x] `core/domains/rulers.py` -- `resolve_house_rulers()` -- AC1, AC2, AC3
- [x] `tests/test_house_rulers.py` -- unit-test the I/O matrix rows plus purity -- AC1, AC2, AC3

**Acceptance Criteria:**
- Given a `NatalChart` and a `ComputationConfig`, when Rulers are resolved, then both the
  traditional and the modern Ruler are resolved and stored for all twelve cusps, and assignment
  follows `config.rulers` exactly, with no rulership rule hardcoded in a function.
- Given a cusp falling in Scorpio, Aquarius or Pisces, when its Ruler is resolved, then both the
  modern Ruler and the traditional co-ruler are recorded -- Pluto with co-ruler Mars; Uranus with
  co-ruler Saturn; Neptune with co-ruler Jupiter.
- Given resolution, when it runs, then it is a pure function of the `NatalChart` and the passed
  `ComputationConfig` -- no I/O, clock, network or randomness.

## Spec Change Log

## Design Notes

**Co-ruler is derived, not a hardcoded sign list.** `co_ruler = traditional_ruler if
traditional_ruler != modern_ruler else None` reads the divergence directly from
`config.rulers`, rather than special-casing `{"scorpio", "aquarius", "pisces"}` in code -- if the
tables ever change, the divergence set changes with them for free.

**Sign derivation is duplicated, not imported.** `core/ephemeris/chart.py`'s `_sign_and_degree()`
and `_ZODIAC_SIGNS` are underscore-private to that module. Rather than break that encapsulation,
`core/domains/rulers.py` carries its own small local zodiac-sign lookup (twelve names, a
longitude-to-index calculation) -- the same tiny piece of astronomical vocabulary two pure modules
both need, not a shared dependency.

**No persistence in this story.** Like Story 2.2's `compute_natal_chart()`, this returns a value;
nothing here writes to a database. If a later story needs Rulers stored, that migration is its own
concern.

## Verification

**Commands:**
- `uv run pytest tests/test_house_rulers.py` -- new tests green
- `uv run pytest` -- full suite green
- `uv run ruff check .` -- clean

## Suggested Review Order

**Ruler resolution: the pure function**

- Entry point: derives each cusp's sign, then resolves both Rulers purely from the passed config -- the whole story's contract in one function.
  [`rulers.py:40`](../../core/domains/rulers.py#L40)

- Where a hardcoded rulership table would have gone: both Rulers come from `config.rulers`, and `co_ruler` is a comparison of the two looked-up values, not a Scorpio/Aquarius/Pisces special case.
  [`rulers.py:55`](../../core/domains/rulers.py#L55)

- Sign derivation is a small local helper, deliberately duplicated rather than imported across `core/ephemeris/chart.py`'s private boundary (see this spec's Design Notes).
  [`rulers.py:69`](../../core/domains/rulers.py#L69)

**New result type**

- `HouseRuler` carries the resolved pair plus the derived `co_ruler`, added alongside the existing chart types.
  [`chart.py:51`](../../core/types/chart.py#L51)

**Peripherals**

- The config-swap tests proving `co_ruler` tracks `config.rulers` rather than a hardcoded sign check -- added during review to close a verification gap.
  [`test_house_rulers.py:174`](../../tests/test_house_rulers.py#L174)

- Coverage of every I/O matrix row: standard cusp, the three divergent cusps, and full 12-cusp ordering.
  [`test_house_rulers.py:70`](../../tests/test_house_rulers.py#L70)
