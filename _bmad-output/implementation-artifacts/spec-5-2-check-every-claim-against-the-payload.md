---
title: 'Story 5.2 — Check every Claim against the Payload'
type: 'feature'
created: '2026-08-22'
status: 'done'
review_loop_iteration: 0
baseline_commit: '64e40424916818f390dafb21353a29b9a65a1c84'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing checks whether a generated sentence's content agrees with the Payload fact it
cites. The Generator's own `_validate_citations`/`_validate_no_date_tokens`
(`shell/adapters/gemini/generator.py`) only check that a cited `entry_id` exists and that Sections 6/7
carry no date token — neither checks *what* a Claim asserts (which planet, house, day, retrograde or
not) against what its cited entry says, so a hallucinated or contradicted fact can still reach export.

**Approach:** Add `run_gate(draft, payload, vocabulary) -> GateResult` in `core/gate/run.py` — pure, no
I/O, no model call. It classifies every `Sentence` via Story 5.1's `is_claim()`, and for each Claim
checks citation presence and factual agreement across the four dimensions the vocabulary classifies
(planet/sign, `casa`+house, day-of-month, `retrogrado`/`stazionario`), plus an unconditional
Sections-6/7 date-token check.

## Boundaries & Constraints

**Always:**
- Pure and deterministic: no I/O, no model call; identical `(draft, payload, vocabulary)` always
  produces a `GateResult` whose `violations` tuple is byte-for-byte identical (fixed order: Section
  field order, then sentence index, then check order below).
- A Claim (`is_claim()` true) with `entry_ids == ()` -> `"empty_citation"` violation (AD-6), independent
  of the checks below.
- For each Claim's checkable category, gather the facts its *cited* entries expose (see Design Notes'
  category table). Category asserted by zero cited entries -> `"invented_fact"`; asserted but matching
  no cited entry's value -> `"contradicted_fact"`. Planet/sign words compare via a small new
  Italian->English map (Payload bodies/signs are English, e.g. `"mars"`/`"aries"`); day-of-month
  compares against the UTC calendar day of the entry's own date field; retrograde is asserted only by
  `station.direction == "retrograde"` or any `standing_retrograde` entry.
- Any date-shaped token (mirror `generator.py`'s `_DATE_TOKEN_PATTERN`: ISO date, day+Italian month,
  `DD/MM`) inside `giorni_favorevoli`/`giorni_di_attenzione` -> `"date_token_in_day_list"`, regardless
  of citation (AD-5) — reimplemented locally, never imported from `shell/` (AD-1).
- `GateResult.passed` is `True` iff `violations` is empty; `GateResult.vocabulary_version` carries
  `vocabulary.version` through for later persistence (Story 5.6).

**Never:**
- No re-derivation of ephemeris astronomy (no recomputing aspects, longitudes or houses) — checks only
  presence/agreement with facts already in `payload`.
- No "aspect name" (trigono/quadrato/...) or "degree" checking — out of scope by design, inherited from
  Story 5.1: `is_claim()`'s six categories never classify those tokens as Claims, so the Gate cannot
  check what it structurally never recognizes.
- No wiring into `ReportRun`/export (Story 5.3) and no `GATE_RESULT` persistence (Story 5.6) — this
  story only builds and tests `run_gate()` itself.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Invented body | Claim names a planet whose entries' bodies never mention it | `"invented_fact"` | N/A |
| Wrong date | Claim day-of-month doesn't match its cited Aspect's `perfected_at` day | `"contradicted_fact"` | N/A |
| Wrong house | Claim `"quinta casa"` doesn't match cited Lunation's `natal_house` | `"contradicted_fact"` | N/A |
| False retrograde | Claim `"retrogrado"` cites a Station with `direction="direct"` | `"contradicted_fact"` | N/A |
| Empty citation | Claim sentence, `entry_ids=()` | `"empty_citation"` | N/A |
| Date token in day list | `giorni_favorevoli` sentence contains `"il 15 gennaio"` | `"date_token_in_day_list"`, even if cited correctly | N/A |
| Well-grounded Claim | Claim's every checkable category matches its cited entries | No violation | N/A |
| Non-Claim sentence | Zero vocabulary tokens, `entry_ids=()` | No violation (never policed) | N/A |
| Deliberately corrupted draft | Each of the four classes injected at once | One violation per injected class | N/A |
| Same inputs, run twice | Identical `draft`/`payload`/`vocabulary` | Identical `GateResult` | N/A |

</frozen-after-approval>

## Code Map

- `core/gate/run.py` (new) -- `run_gate()`, per-entry fact extraction, the Italian->English body/sign
  map, and a locally reimplemented date-token pattern (AD-1: never imported from `shell/`).
- `core/types/gate.py` -- add `GateViolation`/`GateResult` frozen dataclasses alongside `GateVocabulary`.
- `core/gate/classify.py::is_claim()` -- reused as-is for classification.
- `core/gate/__init__.py` -- docstring already forward-references this story; update once both halves exist.
- `shell/adapters/gemini/generator.py:42-75,406-454` -- precedent for `_SECTION_FIELD_NAMES`,
  `_DATE_TOKEN_SECTIONS`, `_DATE_TOKEN_PATTERN`, `_collect_known_entry_ids`, `_validate_citations` --
  mirror the shape, do not import (core/ never imports shell/).
- `core/payload/freeze.py` -- the frozen `payload` dict shape `run_gate()` receives:
  `{"sections": {name: {field: [{"id", "kind", ...fields}]}}, "day_lists": {...}}`.
- `core/types/transits.py` -- the five event dataclasses' field names per kind, frozen into the payload.
- `core/ephemeris/chart.py:51-78` -- canonical English body/sign spelling for the new Italian map.
- `tests/test_gemini_generator.py:432-489` -- precedent for building a real frozen-payload fixture via
  `freeze_payload()` rather than a hand-rolled stand-in shape.
- `tests/test_gate_classify.py`, `tests/test_gate_vocabulary.py` -- test-file conventions to mirror.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/gate.py` -- add `GateViolation` (`kind`, `section`, `sentence`, `entry_ids`, `detail`)
  and `GateResult` (`passed`, `vocabulary_version`, `violations: tuple[GateViolation, ...]`).
- [x] `core/gate/run.py` (new) -- `run_gate(draft: GeneratedDraft, payload: dict[str, Any], vocabulary: GateVocabulary) -> GateResult`.
- [x] `core/gate/__init__.py` -- update docstring now Story 5.1 and 5.2 both live here.
- [x] `tests/test_gate_run.py` (new) -- one test per I/O matrix row, including a deliberately corrupted
  draft covering all four injected classes at once and the run-twice determinism check.

**Acceptance Criteria:**
- Given a cited draft and its Payload, when `run_gate()` executes, then it calls no model, performs no
  I/O, and is a pure function of its arguments.
- Given a Claim naming a planet, sign, house, day-of-month or retrograde condition absent from its
  cited entries, when the Gate runs, then it fails as `"invented_fact"`.
- Given a Claim contradicting its cited entry -- wrong date, wrong house, false retrograde -- when the
  Gate runs, then it fails as `"contradicted_fact"`.
- Given a vocabulary token with an empty citation list, when the Gate runs, then it is an
  `"empty_citation"` violation.
- Given a date token anywhere in Section 6 or 7, when the Gate runs, then it is a
  `"date_token_in_day_list"` violation.
- Given a deliberately corrupted draft, when the Gate runs, then it fails on every injected class.
- Given the same inputs, when the Gate runs twice, then the result is identical.

## Design Notes

`vocabulary` is an explicit third argument, mirroring `is_claim(sentence, vocabulary)` (Story 5.1) --
AD-7's `run_gate(draft, payload)` names the two data-flow inputs; the already-loaded config is passed
the same way `is_claim` already requires, never re-loaded inside `core/` (AD-1).

Per-category fact extraction, keyed by cited entry `"kind"`:

| Category | Entry kind(s) that assert it | Field(s) |
|---|---|---|
| body/sign | aspect, station, standing_retrograde, ingress | `transiting_body`/`natal_point`, `body` |
| house | ingress, lunation | `house_departed`/`house_entered`, `natal_house` |
| date | aspect, station, ingress, lunation | `perfected_at`, `station_at`, `crossed_at`, `occurred_at` |
| retrograde | station, standing_retrograde | `direction == "retrograde"`, presence |

Golden example — wrong house:

```python
# Cited Lunation entry: {"kind": "lunation", "natal_house": 7, ...}
sentence = Sentence(text="La luna piena illumina la tua quinta casa.", entry_ids=("abc123",))
# is_claim(...) is True (casa+ordinal); cited entry's natal_house=7 != quinta(5)
# -> GateViolation(kind="contradicted_fact", section="amore", sentence=..., entry_ids=("abc123",), detail=...)
```

## Verification

**Commands:**
- `uv run pytest tests/test_gate_run.py tests/test_gate_classify.py tests/test_gate_vocabulary.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Entry point**

- `run_gate()` loops every sentence, classifying and checking in a fixed, documented order.
  [`run.py:421`](../../core/gate/run.py#L421)

**Grounding correctness (code-review finding #1: a partly-true Claim must still fail)**

- Contradiction check computes the unmatched subset, not disjointness, so one wrong value in a multi-value Claim can't hide behind one true one.
  [`run.py:293`](../../core/gate/run.py#L293)

- Regression test for the fix: two ordinals in one sentence, only one grounded -- the other must still fail.
  [`test_gate_run.py:227`](../../tests/test_gate_run.py#L227)

- Human-worded violation detail, not a raw bool/list repr, since Story 5.5 surfaces this directly to Francesco.
  [`run.py:266`](../../core/gate/run.py#L266)

**Per-category fact extraction (what a Claim asserts vs. what its citations back)**

- Body/sign extraction: Italian words -> English Payload values via a hand-written map (Payload bodies are English).
  [`run.py:173`](../../core/gate/run.py#L173)

- Fact side: only aspect/station/standing_retrograde/ingress kinds expose a body -- Lunations never do.
  [`run.py:211`](../../core/gate/run.py#L211)

- House assertion requires "casa" and an ordinal to co-occur in the same sentence, mirroring Story 5.1's own rule.
  [`run.py:186`](../../core/gate/run.py#L186)

- Date facts collapse an ISO timestamp to its UTC day-of-month, matching the vocabulary's bare-numeral Claim shape.
  [`run.py:243`](../../core/gate/run.py#L243)

- Retrograde is asserted only by a Station turning retrograde or a standing-retrograde entry.
  [`run.py:255`](../../core/gate/run.py#L255)

**Section 6/7 date-token check (AD-5, independent of citation)**

- Runs unconditionally alongside the Claim check -- those dates are code-projected, never model-written.
  [`run.py:404`](../../core/gate/run.py#L404)

- Reimplemented byte-for-byte from the Generator's own pattern, since `core/` may never import `shell/` (AD-1).
  [`run.py:59`](../../core/gate/run.py#L59)

- Test guarding the two hand-duplicated copies against silent drift.
  [`test_gate_run.py:653`](../../tests/test_gate_run.py#L653)

**Result shape**

- `GateViolation`/`GateResult`: the verdict shape `run_gate()` returns, added alongside `GateVocabulary`.
  [`gate.py:52`](../../core/types/gate.py#L52)

**Peripherals**

- Package docstring reworded to a future/conditional claim -- Story 5.3, not this one, wires the export gate.
  [`__init__.py:1`](../../core/gate/__init__.py#L1)

- One test per I/O-matrix row, plus the check-order and combined-violation tests added in review.
  [`test_gate_run.py:1`](../../tests/test_gate_run.py#L1)
