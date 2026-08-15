---
title: 'Story 1.5 — One home for every astronomical tuning value'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
baseline_commit: '4997a3516da1c3d087224780368741eb24de63c7'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every astronomical tuning value this application will ever need — orbs, house system, which bodies transit, both Ruler tables, the harmonic/disharmonic rule — currently lives nowhere. Left unplaced, the chart builder and the transit engine would each invent their own copy, drift apart, and make "byte-identical for identical configuration" unverifiable.

**Approach:** `data/computation.toml` becomes the one versioned home, loaded by a new `shell/computation.py` (file I/O is shell's job, per AD-1) into a frozen `ComputationConfig` defined in `core/types/` (so core functions can type-hint on it without importing shell). Loaded eagerly at shell import time, exactly like `ephemeris_identity` and `settings` already are — a malformed value fails loudly before the app can serve. The file drives no computation yet; nothing consumes `ComputationConfig` in this story.

## Boundaries & Constraints

**Always:**
- Angles are `Decimal`, never binary float (binding convention since `epic-1-context.md`) — store orb values in the TOML as quoted strings (e.g. `natal = "7.0"`) and parse with `Decimal(value)`, never `Decimal(float_value)`, which would carry binary-float imprecision into an exact decimal.
- `ComputationConfig` and its nested value types are pure, frozen dataclasses living in `core/types/` — no I/O, so core functions can accept them as arguments without violating AD-1. The dict-shaped fields (Ruler tables, harmonic rule) use `types.MappingProxyType`, not a plain mutable `dict`, to stay genuinely immutable.
- Everything the loader can catch happens at load time: `data/computation.toml`'s absence, malformed TOML, and each orb outside its permitted range are all typed `ComputationConfigError` (new, in `core/errors.py`) naming the offending value — never a raw `FileNotFoundError`/`TOMLDecodeError`/`KeyError` reaching the caller.
- `content_hash` is the SHA-256 of the file's raw bytes, computed by the loader — not a field stored inside the file itself (a file can't hash its own hash without infinite regress). `version` **is** a field inside the file, bumped by hand on a data edit.
- `shell/http/app.py` loads `ComputationConfig` eagerly at import time (`computation_config: ComputationConfig = load_computation_config()`), mirroring `ephemeris_identity`'s wiring exactly — a bad file aborts startup before anything serves, even though nothing reads the value yet.
- The domain data below is transcribed verbatim from the planning artifacts — do not re-derive or approximate it:
  - **Orbs:** natal default `7.0`, permitted `6.0`–`8.0`; transit-to-natal default `2.0`, permitted `1.5`–`2.5`.
  - **House system:** `placidus` (the only value that exists; nothing else is defined anywhere in the planning artifacts).
  - **Fast transiting bodies:** sun, mercury, venus, mars. **Slow transiting bodies:** jupiter, saturn, uranus, neptune, pluto. (Source: PRD FR-9 — this is the *transiting-body* set, not FR-13's separate "personal planets" list; the transiting Moon is deliberately excluded everywhere, per FR-9.)
  - **Ruler tables** (brief addendum §3 — traditional/modern differ only for Scorpio, Aquarius, Pisces):
    | Sign | Traditional | Modern |
    |---|---|---|
    | Aries | mars | mars |
    | Taurus | venus | venus |
    | Gemini | mercury | mercury |
    | Cancer | moon | moon |
    | Leo | sun | sun |
    | Virgo | mercury | mercury |
    | Libra | venus | venus |
    | Scorpio | mars | pluto |
    | Sagittarius | jupiter | jupiter |
    | Capricorn | saturn | saturn |
    | Aquarius | saturn | uranus |
    | Pisces | jupiter | neptune |
  - **Harmonic/disharmonic rule** (PRD FR-13, table-driven, confirmed domain fact 2026-08-14): trine, sextile → harmonic; square, opposition → disharmonic; conjunction by transiting venus or jupiter → harmonic; conjunction by transiting mars, saturn or pluto → disharmonic; conjunction by any other transiting body → neutral (present in neither day list — do not force a harmonic/disharmonic value onto it).

**Ask First:** None anticipated — every value above is already confirmed domain fact in the planning artifacts, not a new decision.

**Never:**
- No ruler-resolution function, no orb-comparison function, no aspect classifier, no chart or transit computation of any kind — `ComputationConfig` is data only in this story; Epic 2+ consumes it.
- No new runtime dependency — `tomllib` is stdlib since Python 3.11.
- No change to `data/ephemeris/` or the Dockerfile — `COPY data/ ./data/` already ships everything under `data/`, including this new file.
- No aspect-angle definitions (0°/60°/90°/120°/180°) in this file — those are fixed geometric facts, not tunable values, and the planning artifacts never list them among computation.toml's contents.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid file | All values within range, well-formed TOML | Frozen `ComputationConfig` returned, `version` and `content_hash` populated | N/A |
| Natal orb out of range | `orbs.natal` outside `6.0`–`8.0` | Load fails | `ComputationConfigError` names the field and the offending value |
| Transit orb out of range | `orbs.transit` outside `1.5`–`2.5` | Load fails | `ComputationConfigError` names the field and the offending value |
| File missing or malformed | `data/computation.toml` absent, or invalid TOML syntax | Load fails | `ComputationConfigError` names the problem, not a raw traceback |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `shell/config.py`, `core/ephemeris/identity.py` -- the two patterns to combine: `shell/config.py`'s per-field validation collecting every error before raising one `ConfigError`; `core/ephemeris/identity.py`'s split between a pure `core/` type and a `shell/`-side loader that reads the file and computes a content hash.
- `shell/http/app.py:52-55` -- `ephemeris_identity: EphemerisIdentity = verify_ephemeris_identity()` is the exact wiring shape to repeat for `computation_config`.
- `core/errors.py` -- add `ComputationConfigError` alongside `EphemerisIntegrityError`.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:339-341` (FR-9, fast/slow bodies), `:425-443` (FR-13, harmonic rule) -- verbatim source for the domain data above.
- `_bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/addendum.md:68-88` (§3, Ruler table and orbs) -- verbatim source for the Ruler table above.

**To create:**
- `data/computation.toml` -- version, orbs, house system, fast/slow body sets, both Ruler tables, harmonic rule -- per the transcribed data above
- `core/types/computation.py` -- `ComputationConfig` and its nested frozen value types
- `shell/computation.py` -- `load_computation_config() -> ComputationConfig`: reads the file, computes the content hash, validates orb ranges, raises `ComputationConfigError` on any problem
- `tests/test_computation_config.py` -- the I/O matrix, plus a frozen/immutability check and a check that the shipped file's own default orbs (`7.0`, `2.0`) load without error

**To modify:**
- `core/errors.py` -- add `ComputationConfigError`
- `shell/http/app.py` -- eager-load `computation_config` at import time, exported in `__all__`
- `tests/test_http_app.py` -- extend for the new eager-loaded value, mirroring the existing `ephemeris_identity` test

## Tasks & Acceptance

**Execution:**
- [x] `data/computation.toml` -- create with the exact transcribed domain data -- AC1
- [x] `core/types/computation.py` -- `ComputationConfig` and nested frozen types, `Decimal` orbs, `MappingProxyType` tables -- AC2
- [x] `core/errors.py` -- `ComputationConfigError` -- AC3
- [x] `shell/computation.py` -- `load_computation_config()`: read, hash, validate, raise on failure -- AC2, AC3
- [x] `shell/http/app.py` -- eager-load at import time, mirroring `ephemeris_identity` -- AC2
- [x] `tests/test_computation_config.py`, `tests/test_http_app.py` -- cover the I/O matrix and the eager-load wiring

**Acceptance Criteria:**
- Given `data/computation.toml`, when it is created, then it holds the natal orb (default ±7.0°, range ±6.0°–±8.0°), the transit-to-natal orb (default ±2.0°, range ±1.5°–±2.5°), the house system (Placidus), the fast and slow transiting body sets, the traditional and modern Ruler tables for all twelve signs, and the FR-13 harmonic/disharmonic table -- and it carries an integer version and a content hash.
- Given the file, when it is loaded, then it produces a frozen `ComputationConfig`, passed explicitly wherever it's needed -- never read ambiently from a module global, the environment, or a file at call time.
- Given an orb value outside its permitted range, when the configuration is loaded, then loading fails with a typed domain error naming the offending value.
- Given this story, when it is complete, then the file holds no logic and drives no computation -- it exists so nothing downstream invents a second home for these values.

## Spec Change Log

- **2026-08-15 (review round 1) — one crash bug fixed, plus a validation-consistency
  sweep.** Two of three reviewers independently found and verified the same real bug:
  `Decimal("nan")` (and `"snan"`/`"inf"`/`"-inf"`) constructs successfully in `_read_orb`,
  so the range check `minimum <= value <= maximum` was the only thing that could reject
  it — and for NaN specifically, that comparison raises `decimal.InvalidOperation`
  instead of returning `False`, crashing startup with a raw traceback instead of the
  promised `ComputationConfigError`. Fixed with an explicit `value.is_finite()` guard
  before the range comparison. Also closed, as the same mechanical sweep: `[rulers.*]`
  already rejected an unexpected key in its 12-sign tables, but `[orbs]`, `[house_system]`,
  `[bodies]`, `[harmonic]` and the top-level `[rulers]` table did not — a misspelled key
  in any of those four+one tables was silently ignored rather than flagged, now closed
  via a shared `_check_unexpected_keys()` helper. Fixed the redundant/overlapping error
  messages `_read_orb`/`_read_house_system` produced when their whole table was already
  missing, by giving orbs and house_system the same short-circuit-on-missing-table shape
  `_read_bodies`/`_read_rulers`/`_read_harmonic` already used. Also added the one
  regression class none of the unit tests covered: a subprocess-reimport test proving
  `from shell.http import app` actually aborts non-zero when `data/computation.toml`
  is missing — mirroring the two sibling tests (`test_ephemeris_identity.py`,
  `test_config.py`) that already prove this for the other two eager-loaded startup
  guards. **KEEP:** the per-field-collect-all-errors-then-raise-once shape (mirroring
  `shell/config.py`'s `load_settings()`) — extending it to short-circuit consistently
  across all six tables required no structural change, just applying the pattern
  uniformly. Not applied, and logged in `deferred-work.md` instead: cross-field/semantic
  validation (body-set overlaps, aspect-list overlaps, conjunction-body cross-checks),
  `house_system.name` locked to a `"placidus"`-only enum, and `version` given a lower
  bound — all real but requiring a design call beyond this story's frozen scope
  (orb-range validation only).

## Design Notes

`ComputationConfig`'s exact field/type names are an implementation choice, not a spec requirement — group by TOML table (an orbs value, a house-system value, a bodies value, a rulers value, a harmonic value) rather than flattening everything onto one dataclass, since that mirrors the file's own structure and keeps a future consumer's argument list readable.

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including the new computation-config tests
- `uv run ruff check .` -- clean
- `python -c "import tomllib; tomllib.load(open('data/computation.toml', 'rb'))"` -- the file itself is syntactically valid TOML

## Suggested Review Order

**Loading — the entry point**

- Start here: every field validated and collected before one error is raised, mirroring `shell/config.py`'s `load_settings()`.
  [`computation.py:318`](../../shell/computation.py#L318)

- The domain data this all validates against — transcribed from the PRD/brief, not re-derived.
  [`computation.toml`](../../data/computation.toml)

**Hardening added after review — a crash bug, and a consistency sweep**

- The bug two reviewers found independently: `Decimal("nan")` used to reach an unguarded range comparison that raises instead of failing cleanly.
  [`computation.py:117`](../../shell/computation.py#L117)
  [`test_computation_config.py:161`](../../tests/test_computation_config.py#L161)

- `[rulers.*]` already rejected an unexpected key; the other five tables now do too, via one shared helper.
  [`computation.py:105`](../../shell/computation.py#L105)
  [`test_computation_config.py:195`](../../tests/test_computation_config.py#L195)

- `orbs`/`house_system` now short-circuit on a missing table the same way `bodies`/`rulers`/`harmonic` already did — no more duplicated error lines.
  [`computation.py:162`](../../shell/computation.py#L162)

**The gap none of the unit tests would have caught — the actual startup-abort path**

- Every existing test calls the loader directly; nothing proved a broken file actually aborts `from shell.http import app`, until now.
  [`test_computation_config.py:304`](../../tests/test_computation_config.py#L304)
