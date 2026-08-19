---
title: "Assemble the Report Payload each Section needs"
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'c34fc39f9e907044c507e8a0e60a2f77dab0da3b'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing today organizes a Natal Chart, its Domain Profiles and a month's Transit Events
(Stories 3.1-3.5) into what each of the eight report Sections actually needs. Without it, a future
Generator would have to go hunting through raw event lists per Section, and nothing stops it inventing
a fact.

**Approach:** A new pure `core/payload/assemble.py::assemble_payload()` builds a `Payload`
(`core/types/payload.py`) with one `SectionPayload` per Section (Energia generale, Amore, Lavoro,
Denaro, Benessere, Consiglio finale — Sections 6/7's day-lists are a Story 3.7 projection, not part of
this mapping). Which events/profile each Section receives is declarative data in new `data/sections.toml`
(AD-13), loaded by `shell/sections.py::load_sections_config()` mirroring `shell/computation.py`'s
validate-and-hash shape. `assemble_payload()` applies one generic filter per Section spec — no
`if section == "amore"` branching anywhere.

## Boundaries & Constraints

**Always:**
- `core/types/sections.py::SectionSpec` fields: `domain_profile: str | None`, `houses: tuple[int, ...]`,
  `house_bodies: str | None` (`"fast"`/`"slow"`/`None`=any), `aspect_natal_points: tuple[str, ...]`,
  `aspect_bodies: str | None`, `retrogrades: bool`, `include_all_events: bool`.
  `SectionsConfig`: `version: int`, `content_hash: str`, `sections: MappingProxyType[str, SectionSpec]`.
- `shell/sections.py::load_sections_config(path=DEFAULT_SECTIONS_PATH) -> SectionsConfig` validates every
  field before reporting (mirror `shell/computation.py`'s per-field readers), requires `sections` to
  contain exactly the six names below (no more, no fewer), raises new `core.errors.SectionsConfigError`
  naming every offender at once.
- `data/sections.toml` (`version = 1`): `energia_generale` = `houses=[1,4,7,10]`, `house_bodies="slow"`,
  `aspect_natal_points=["sun","moon","mercury","venus","mars"]`, `aspect_bodies="slow"`,
  `retrogrades=true`; `amore` = `domain_profile="amore"`, `houses=[5,7]`,
  `aspect_natal_points=["venus","mars"]`; `lavoro` = `domain_profile="lavoro"`, `houses=[10,6]`,
  `aspect_natal_points=["mercury","mars","saturn"]`; `denaro` = `domain_profile="denaro"`,
  `houses=[2,8]`, `aspect_natal_points=["jupiter","saturn"]`; `benessere` = `domain_profile="benessere"`,
  `houses=[1,6]`, `aspect_natal_points=["mars","saturn","moon"]`; `consiglio_finale` =
  `include_all_events=true` (every Aspect/Station/StandingRetrograde/Ingress/Lunation, unfiltered —
  Lunations already carry `natal_house`, satisfying "the natal houses the month's Lunations fall in").
- `core/types/payload.py::SectionPayload` (`profile`, `aspects`, `stations`, `standing_retrogrades`,
  `ingresses`, `lunations`) and `Payload` (six named `SectionPayload` fields, one per Section above).
- `core/payload/assemble.py::assemble_payload(chart, profiles, aspects, stations, ingresses, lunations,
  config, sections_config) -> Payload`: `stations` is the mixed `Station | StandingRetrograde` tuple
  `find_stations()` returns (split by `isinstance`, mirroring `shell/runner/driver.py`). Per spec: an
  Ingress matches when `spec.houses` is non-empty and (`house_departed` or `house_entered`) is in it and
  `body` is in the resolved `house_bodies` set (`config.bodies.fast`/`.slow`/both when `None`); an Aspect
  matches when `spec.aspect_natal_points` is non-empty and `natal_point` is in it and `transiting_body` is
  in the resolved `aspect_bodies` set; a Station matches when `spec.retrogrades` and
  `direction == "retrograde"`; a StandingRetrograde matches when `spec.retrogrades`; every Lunation
  matches only under `include_all_events`. `include_all_events` short-circuits every filter to "match
  all" for that Section. No I/O, clock, network or randomness (core/, AD-1); identical inputs produce a
  byte-identical `Payload` every call.

**Ask First:** None identified.

**Never:**
- No entry IDs, no canonical-JSON serialization, no persistence, no `REPORT_PAYLOAD` table — Story 3.8's
  job.
- No wiring into `shell/runner/driver.py`'s `_STAGE_FUNCTIONS` or `shell/http/app.py`'s state —
  registering a `payload_ready` stage with nothing to persist the result into is premature; that lands
  with 3.8's storage.
- No Sections 6/7 day-list classification (harmonic/disharmonic) — Story 3.7.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Full month, all event kinds present | One of each: Aspect (fast+slow), Station, StandingRetrograde, Ingress, Lunation | Each Section's `SectionPayload` holds exactly the events its spec matches | N/A |
| Ingress crossing counted from either side | `house_departed=4, house_entered=5` | Counted toward a Section listing house 4 **or** house 5 | N/A |
| Event matching no Section's filter | Fast-body Aspect to a non-listed natal point, non-angular house | Absent from every `SectionPayload` except `consiglio_finale` (`include_all_events`) | N/A |
| `sections.toml` missing a required Section key | File lacking `[sections.lavoro]` | `SectionsConfigError` naming the missing key | Raised, not swallowed |
| `sections.toml` names an unsupported `house_bodies`/`aspect_bodies` value | `house_bodies = "medium"` | `SectionsConfigError` naming the field and value | Raised, not swallowed |
| Same inputs, two calls | Identical arguments | Byte-identical `Payload` (dataclass equality) both times | N/A |

</frozen-after-approval>

## Code Map

- `shell/computation.py` -- mirror this module's `_read_table`/`_check_unexpected_keys`/
  `_read_string_list`/error-collection shape for `load_sections_config`.
- `core/types/computation.py` -- `ComputationConfig:89` -- mirror `version`/`content_hash` fields.
- `core/errors.py` -- add `SectionsConfigError(RuntimeError)` beside `ComputationConfigError:38`.
- `core/types/domains.py` -- `DomainProfiles:103`, `AmoreProfile:59`/`LavoroProfile:70`/
  `DenaroProfile:80`/`BenessereProfile:91` -- `domain_profile` resolves via `getattr(profiles, name)`.
- `core/types/transits.py` -- `TransitAspectEvent:22`, `Station:55`, `StandingRetrograde:76`,
  `Ingress:96`, `Lunation:123` -- exact fields the filters read.
- `core/types/chart.py` -- `NatalChart:87` -- passed through unfiltered (each `SectionPayload` need not
  duplicate it).
- `core/domains/rulers.py::resolve_house_rulers:40`, `core/domains/profiles.py::assemble_domain_profiles:27`
  -- how a test builds `DomainProfiles` from a `NatalChart` fixture.
- `core/transits/ingresses.py::find_ingresses:73` -- confirms `house_departed`/`house_entered` semantics
  (direct crossing enters the cusp's own house; retrograde departs it).
- `shell/runner/driver.py::_run_transits_ready:110` -- the mixed `Station | StandingRetrograde` tuple
  shape this story's `stations` parameter matches, and the `isinstance` split pattern to mirror.
- `tests/test_computation_config.py`, `tests/test_domain_profiles.py` -- fixture-building and
  error-collection test-pattern precedent.

## Tasks & Acceptance

**Execution:**
- [x] `data/sections.toml` -- new versioned Section-to-Payload mapping per Boundaries.
- [x] `core/types/sections.py` -- `SectionSpec`, `SectionsConfig` frozen dataclasses.
- [x] `core/errors.py` -- `SectionsConfigError`.
- [x] `shell/sections.py` -- `load_sections_config()`, mirroring `shell/computation.py`.
- [x] `core/types/payload.py` -- `SectionPayload`, `Payload` frozen dataclasses.
- [x] `core/payload/__init__.py`, `core/payload/assemble.py` -- `assemble_payload()`.
- [x] `tests/test_sections_config.py` -- load/validation matrix rows.
- [x] `tests/test_payload_assembly.py` -- assembly matrix rows plus purity/determinism.

**Acceptance Criteria:**
- Given a Natal Chart, Domain Profiles, a month's Transit Events (3.1-3.4 output) and a
  `ComputationConfig`, when `assemble_payload()` runs, then each Section receives exactly the slice
  Boundaries describes, with no per-Section branch in the implementation.
- Given the Section-to-Payload mapping, when it changes, then only `data/sections.toml` is edited — no
  code change is needed to add or adjust a Section's filter.
- Given identical inputs, when `assemble_payload()` is called twice, then the two `Payload` results are
  equal and no clock/network/database/randomness was consulted.

## Design Notes

**"Against the overall transit picture" (Consiglio finale) read as unfiltered.** The AC names no houses
or natal points for this Section, unlike the other five — `include_all_events=true` gives it every
computed event for the month, which is the only reading that doesn't silently invent a narrower filter
the AC never states. Flagged here for the human checkpoint to correct if wrong.

**Ingress house-match checks both `house_departed` and `house_entered`.** A crossing's "cusp" side
depends on direction (see `find_ingresses`'s docstring); checking both sides is the simplest rule that
never misses a transit touching the named house, at the cost of also counting the house being left.

## Verification

**Commands:**
- `uv run pytest tests/test_sections_config.py tests/test_payload_assembly.py -q` -- expected: all pass.
- `uv run pytest tests/test_import_boundary.py -q` -- expected: `core/payload/` and `core/types/payload.py`/
  `core/types/sections.py` import nothing from `shell/`.

## Suggested Review Order

**Assembly — the generic, branch-free filter**

- Entry point: builds the six-field `Payload` from `sections_config.sections`, splitting the mixed `Station | StandingRetrograde` tuple by `isinstance`.
  [`assemble.py:37`](../../core/payload/assemble.py#L37)

- One Section's slice: the same generic call shape applied to every Section, regardless of name.
  [`assemble.py:81`](../../core/payload/assemble.py#L81)

- The four match predicates: each reads only `SectionSpec` fields, never a Section's name.
  [`assemble.py:115`](../../core/payload/assemble.py#L115)

- `house_bodies`/`aspect_bodies` resolve to `config.bodies.fast`/`.slow`/their union -- never a hardcoded body list.
  [`assemble.py:104`](../../core/payload/assemble.py#L104)

**Section-to-Payload mapping — the versioned data (AD-13)**

- One domain Section's filter, entirely data: houses, aspected natal points, its own Domain Profile.
  [`sections.toml:23`](../../data/sections.toml#L23)

- `consiglio_finale`'s unfiltered read of the whole month -- the Design Notes' flagged interpretation.
  [`sections.toml:43`](../../data/sections.toml#L43)

**Config loading & validation — fail visibly, mirroring `shell/computation.py`**

- `domain_profile` cross-checked against its own Section's name -- a patch-review fix closing a silent-mismatch gap.
  [`sections.py:176`](../../shell/sections.py#L176)

- `_DOMAIN_SECTION_NAMES`: the closed set a Section's `domain_profile` is validated against.
  [`sections.py:68`](../../shell/sections.py#L68)

- `SectionsConfigError`: the typed failure `shell/sections.py` raises instead of a raw parse/`KeyError`.
  [`errors.py:54`](../../core/errors.py#L54)

**Types — pure data, no logic beyond the dataclass machinery**

- `SectionSpec`: one Section's declarative filter, the shape every match predicate reads.
  [`sections.py:23`](../../core/types/sections.py#L23)

- `SectionPayload`/`Payload`: the six named Sections a `Payload` is fixed to.
  [`payload.py:24`](../../core/types/payload.py#L24)

**Peripherals — tests**

- The full-month matrix row: every Section's exact slice asserted at once, including the multi-domain and either-side-Ingress fixtures.
  [`test_payload_assembly.py:248`](../../tests/test_payload_assembly.py#L248)

- The patch-review addition: an Ingress whose house matches but whose body doesn't, proving the body filter isn't dead code.
  [`test_payload_assembly.py:334`](../../tests/test_payload_assembly.py#L334)

- Purity/determinism: two calls with identical inputs produce equal `Payload`s.
  [`test_payload_assembly.py:376`](../../tests/test_payload_assembly.py#L376)

- The two patch-review additions proving a mismatched `domain_profile` is caught at load time, not silently accepted.
  [`test_sections_config.py:220`](../../tests/test_sections_config.py#L220)

- The shipped `data/sections.toml` itself loads without error -- the test that would catch a real config regression.
  [`test_sections_config.py:325`](../../tests/test_sections_config.py#L325)
