---
title: 'Project the two day-lists by code, so a day cannot be misfiled'
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'f83249c3772bce5dcafb79e5345ef32ebfa23d84'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Report Payload (Story 3.6) holds every computed Transit Event but does not yet sort any
into Section 6 (*Giorni favorevoli*) or 7 (*Giorni di attenzione*) — the most client-visible
classification the product makes, which must never rest on a model's judgement.

**Approach:** New pure `core/payload/day_lists.py::project_day_lists()` applies the already-loaded
`ComputationConfig.harmonic` table to `payload.consiglio_finale`'s unfiltered event set (AD-5), returning
a frozen `DayLists`: dated harmonic Aspect Perfections + favorable Lunations, and dated disharmonic Aspect
Perfections + retrograde Stations.

## Boundaries & Constraints

**Always:**
- New `core/payload/day_lists.py`, pure (AD-1): no I/O, clock, network, randomness.
- Reads only `payload.consiglio_finale` (the unfiltered `SectionPayload`) — never re-derives from raw scan
  output, so Sections 6/7 stay downstream of the one assembled Payload like every other Section.
- Conjunction classifies by `transiting_body` against `config.harmonic.harmonic_conjunction_bodies`/
  `disharmonic_conjunction_bodies`; every other aspect by membership in `harmonic_aspects`/
  `disharmonic_aspects`. No match on either list = neutral, added to neither tuple.
- Only `TransitAspectEvent`s with `perfected_at is not None` are eligible — "dated" excludes
  `never_perfected=True`.
- Lunation favorability re-tests `lunation.longitude` against every natal target `core/transits/aspects.py`'s
  `_natal_targets()` returns, via `core/ephemeris/chart.py`'s `_match_aspect()` and `config.orbs.transit`:
  favorable on `trine`/`sextile` to any natal point, or `conjunction` specifically to natal `venus`/`jupiter`.
- Only `Station`s (not `StandingRetrograde`) with `direction == "retrograde"` enter the attention tuple.
- This function only reads `payload`; excluded/neutral events stay reachable through the Payload as-is.
- Deterministic: identical inputs produce an equal `DayLists`; within each tuple, entries keep
  `payload.consiglio_finale`'s own relative order — never re-sorted by date.

**Ask First:** None — classification, orb and eligibility rules are fully specified by
`computation-tables.md`/`sections.md` and the story AC.

**Never:** No `shell/`/runner wiring — `payload_ready` stays unregistered (Story 3.6 left it that way; a
later story wires this in). No new TOML table — `[harmonic]` already ships in `data/computation.toml`,
loaded onto `ComputationConfig.harmonic` but currently unconsumed.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Trine/sextile aspect | Perfected event, `aspect="trine"` | In `giorni_favorevoli` | N/A |
| Square/opposition aspect | Perfected event, `aspect="opposition"` | In `giorni_di_attenzione` | N/A |
| Conjunction, Venus/Jupiter | Perfected event, `transiting_body="venus"`, `aspect="conjunction"` | In `giorni_favorevoli` | N/A |
| Conjunction, Mars/Saturn/Pluto | Perfected event, `transiting_body="saturn"`, `aspect="conjunction"` | In `giorni_di_attenzione` | N/A |
| Conjunction, other body | Perfected event, `transiting_body="mercury"`, `aspect="conjunction"` | In neither tuple | N/A |
| Never-perfected aspect | `never_perfected=True`, harmonic aspect type | In neither tuple (no date) | N/A |
| Lunation trine/sextile a natal point | Longitude 120° from natal Mercury, within `orbs.transit` | In `giorni_favorevoli` | N/A |
| Lunation conjunct natal Venus/Jupiter | Longitude conjunct natal Jupiter, within Orb | In `giorni_favorevoli` | N/A |
| Lunation conjunct other natal point | Longitude conjunct natal Saturn | In neither tuple | N/A |
| Lunation with no qualifying aspect | Longitude square every natal point | In neither tuple | N/A |
| Retrograde Station | `Station(direction="retrograde")` | In `giorni_di_attenzione` | N/A |
| Direct-turn Station | `Station(direction="direct")` | In neither tuple | N/A |
| Standing retrograde (no Station) | `StandingRetrograde` in `consiglio_finale.standing_retrogrades` | In neither tuple | N/A |
| Empty month | Empty `aspects`/`stations`/`lunations` | `DayLists` with two empty tuples | N/A |
| Determinism | Same inputs called twice | Two equal `DayLists`, no clock/I/O/db consulted | N/A |

</frozen-after-approval>

## Code Map

- `core/types/computation.py` -- `HarmonicRule:73`, `ComputationConfig.harmonic:103` (already loaded,
  unconsumed), `Orbs.transit:38`.
- `core/types/payload.py` -- `Payload.consiglio_finale:55`, `SectionPayload:24` (`.aspects`, `.stations`,
  `.lunations` read; `.standing_retrogrades` read only to confirm exclusion).
- `core/types/transits.py` -- `TransitAspectEvent:22` (`transiting_body`, `aspect`, `perfected_at`,
  `never_perfected`), `Station:55` (`body`, `direction`), `Lunation:123` (`longitude`).
- `core/types/chart.py` -- `NatalChart:87`, `PlanetPosition` (`.name`, `.longitude`) -- pass alongside
  `Payload` since `assemble_payload()` discards the chart (`core/payload/assemble.py:60`) and
  `SectionPayload` never stores it.
- `core/ephemeris/chart.py` -- `_match_aspect(lon1, lon2, orb_limit):206`, `_ASPECTS:85` -- reuse for
  Lunation-to-natal-point matching (static longitude check, no bisection). `core/transits/aspects.py`
  already imports `_ASPECTS` from here -- same cross-module `core/` reuse precedent.
- `core/transits/aspects.py` -- `_natal_targets(chart):201` -- the fourteen fixed natal targets (ten
  planets/nodes + ascendant + midheaven); reuse rather than re-deriving.
- `core/payload/assemble.py` -- `assemble_payload:37` -- upstream producer; not modified.
- `data/computation.toml` -- `[harmonic]:60` -- already-shipped table this story first consumes.
- `shell/computation.py` -- `load_computation_config:318` -- load the real shipped config in tests
  (mirrors `tests/test_payload_assembly.py`'s `_CONFIG = load_computation_config()`).
- `tests/test_payload_assembly.py` -- fixture-building technique to mirror for this story's tests.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/day_lists.py` -- new `DayLists` frozen dataclass: `giorni_favorevoli: tuple[TransitAspectEvent | Lunation, ...]`, `giorni_di_attenzione: tuple[TransitAspectEvent | Station, ...]`.
- [x] `core/payload/day_lists.py` -- `project_day_lists(payload, chart, config) -> DayLists`, plus private `_classify_aspect()`/`_is_favorable_lunation()` helpers per Boundaries.
- [x] `tests/test_day_lists.py` -- one test per I/O & Edge-Case Matrix row, plus purity/determinism.

**Acceptance Criteria:**
- Given the month's Transit Events and `config.harmonic`, when `project_day_lists()` runs,
  trines/sextiles classify harmonic, squares/oppositions disharmonic, conjunctions by transiting body.
- Given a Lunation, when it is classified, then it is favorable exactly when it trines/sextiles any natal
  point within `config.orbs.transit`, or is conjunct natal Venus or Jupiter within the same Orb.
- Given a projected `DayLists`, when inspected, then `giorni_favorevoli`/`giorni_di_attenzione` each hold
  exactly the dated events and Lunations/Stations Boundaries describe.
- Given a neutral or undated event, when `project_day_lists()` runs, then it is never added to either
  tuple, and `payload` itself is untouched.
- Given identical inputs, when `project_day_lists()` is called twice, then it returns two equal
  `DayLists` values.

## Design Notes

**"Dated" excludes `never_perfected=True`.** `computation-tables.md` draws this line explicitly: an
in-orb-but-never-perfecting aspect has no instant to file a day under, so it stays out of both lists even
if its aspect type would otherwise classify harmonic/disharmonic. It remains reachable via
`payload.energia_generale`/etc. unchanged. Flagged for the human checkpoint to confirm.

**Entries are not sorted by date.** The AC specifies membership, not order; both tuples keep
`payload.consiglio_finale`'s existing relative order. A later story/view can sort by
`perfected_at`/`occurred_at`/`station_at` if chronological rendering is needed. Flagged for the human
checkpoint to confirm this reading is correct.

## Verification

**Commands:**
- `uv run pytest tests/test_day_lists.py -q` -- expected: all pass.
- `uv run pytest tests/test_import_boundary.py -q` -- expected: `core/payload/day_lists.py`/
  `core/types/day_lists.py` import nothing from `shell/` and touch no forbidden facility.
- `uv run ruff check core/payload/day_lists.py core/types/day_lists.py tests/test_day_lists.py` --
  expected: no findings.

## Suggested Review Order

**Classification logic**

- Entry point: harmonic/disharmonic and conjunction-body classification, the story's core rule.
  [`day_lists.py:38`](../../core/payload/day_lists.py#L38)

- Conjunction branches on transiting body; every other aspect on aspect-type membership.
  [`day_lists.py:80`](../../core/payload/day_lists.py#L80)

- Lunation favorability re-tests longitude against all fourteen natal targets via reused `_match_aspect`.
  [`day_lists.py:102`](../../core/payload/day_lists.py#L102)

**Result shape**

- `DayLists`: two tuples, deliberately typed to exclude `Lunation` from the attention list.
  [`day_lists.py:20`](../../core/types/day_lists.py#L20)

**Tracking**

- Sprint status flips the story to in-progress, lifting the parent epic if needed.
  [`sprint-status.yaml:66`](../../_bmad-output/implementation-artifacts/sprint-status.yaml#L66)

**Tests**

- Matrix coverage starts here: trine/sextile and square/opposition aspect classification.
  [`test_day_lists.py:125`](../../tests/test_day_lists.py#L125)

- Conjunction classification by body: harmonic, disharmonic, and neutral cases.
  [`test_day_lists.py:151`](../../tests/test_day_lists.py#L151)

- Undated aspects (`never_perfected=True`) are excluded even when the aspect type qualifies.
  [`test_day_lists.py:190`](../../tests/test_day_lists.py#L190)

- Lunation favorability: trine/sextile, Venus/Jupiter conjunction, and the negative cases.
  [`test_day_lists.py:205`](../../tests/test_day_lists.py#L205)

- Loop-continuation regression: a non-matching natal target must not short-circuit the scan.
  [`test_day_lists.py:247`](../../tests/test_day_lists.py#L247)

- Station direction filter: retrograde enters the attention list, direct and standing don't.
  [`test_day_lists.py:280`](../../tests/test_day_lists.py#L280)

- Determinism and untouched-`Payload` guarantees across two calls with the same inputs.
  [`test_day_lists.py:332`](../../tests/test_day_lists.py#L332)

- Relative order is preserved within each source kind, never re-sorted by date.
  [`test_day_lists.py:357`](../../tests/test_day_lists.py#L357)

- Cross-kind concatenation order is pinned: aspects precede Lunations/Stations in each tuple.
  [`test_day_lists.py:380`](../../tests/test_day_lists.py#L380)

- `DayLists` is frozen, matching every other `core/types/` result shape.
  [`test_day_lists.py:409`](../../tests/test_day_lists.py#L409)
