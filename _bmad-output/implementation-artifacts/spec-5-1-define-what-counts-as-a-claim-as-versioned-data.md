---
title: 'Story 5.1 — Define what counts as a Claim, as versioned data'
type: 'feature'
created: '2026-08-22'
status: 'done'
review_loop_iteration: 0
baseline_commit: '27e05d35df9f0aa36607534fa540e1ec2153feba'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing yet draws the line between an astronomical Claim and interpretive prose. Without
one versioned source of truth, the Groundedness Gate (Story 5.2) and any later revision of it could
drift apart, making the Gate's pass rate (SM-5) meaningless.

**Approach:** Add a versioned closed Italian vocabulary as a data file (`core/gate/vocabulary.it.json`,
AD-8), a shell loader that reads/hashes/validates it into a frozen `GateVocabulary`, and a pure
`core/gate/classify.py::is_claim()` that decides, per sentence, whether it is a Claim.

## Boundaries & Constraints

**Always:**
- Vocabulary covers exactly six categories (AD-8): ten Italian planet names, twelve Italian sign
  names, `casa` paired with an ordinal, a day-of-month numeral, `retrogrado`, `stazionario`.
- The file carries its own integer `version`, independent of the Payload schema version and the
  Section-composition (`sections.toml`) version.
- A sentence is a Claim iff it contains at least one vocabulary token; zero tokens = interpretation,
  never a Claim, governed by the Style Guide instead.
- `classify.py` is pure (AD-1): no I/O, receives an already-loaded `GateVocabulary`, never a path.
- Loading happens only in `shell/` (AD-1), mirroring `shell/sections.py`: read bytes → parse →
  validate every field (collect all problems, don't stop at the first) → SHA-256 `content_hash` →
  typed error on failure.
- PRD Open Question 1's gap — a sentence leaning on a fact without naming it — stays intentionally
  unpoliced. Document it in `classify.py`'s docstring; do not build a heuristic to close it.

**Never:**
- No `GateResult`, citation checking, or Payload comparison — that's Story 5.2.
- No attempt to detect fact-leaning interpretation (Open Question 1) — out of scope by design.
- No schema-validation library — hand-written field checks, matching `shell/sections.py`'s style.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid file | Well-formed `vocabulary.it.json` | `load_gate_vocabulary()` returns frozen `GateVocabulary` | N/A |
| Missing file | Path does not exist | N/A | `GateVocabularyError` naming the path |
| Malformed JSON | Truncated/invalid bytes | N/A | `GateVocabularyError` naming the parse failure |
| Missing category key | One of six required keys absent | N/A | `GateVocabularyError` naming the key |
| Wrong-shaped value | Non-string list entry, or `version` not an int | N/A | `GateVocabularyError` naming every offender at once |
| Planet token | `"Marte è nella tua decima casa."` | `is_claim(...) is True` | N/A |
| Sign token | `"Il Leone domina il tuo mese."` | `is_claim(...) is True` | N/A |
| `casa` + ordinal | `"La quinta casa si attiva."` | `is_claim(...) is True` | N/A |
| Day-of-month numeral | `"Il 15 porta un cambiamento."` | `is_claim(...) is True` | N/A |
| `retrogrado`/`stazionario` | `"Mercurio è retrogrado."` | `is_claim(...) is True` | N/A |
| Zero vocabulary tokens | `"Il mese chiede pazienza."` | `is_claim(...) is False` (unpoliced interpretation) | N/A |
| Vocabulary revised | `version` bumped, a token added/removed | New `version`; `content_hash` changes | N/A |

</frozen-after-approval>

## Code Map

- `core/gate/__init__.py` -- Story 1.2 stub; its docstring ("Conformance gate: the release check
  against transcribed benchmark charts") is a stale placeholder predating this package's real
  purpose — replace it.
- `core/types/sections.py` -- precedent frozen-dataclass shape (`version: int`, `content_hash: str`
  + validated payload) to mirror for `GateVocabulary` in `core/types/gate.py`.
- `shell/sections.py` -- precedent loader (`_read_bytes` → parse → collecting validators →
  `DEFAULT_*_PATH` from `Path(__file__)` → SHA-256 `content_hash`). `shell/gate.py` mirrors this,
  swapping `tomllib` for `json`.
- `core/errors.py` -- add `GateVocabularyError` alongside `SectionsConfigError` (same docstring
  convention: what's raised, when, from where, no partial fallback).
- `data/sections.toml` -- precedent for a hand-bumped `version` field; header comment explains the
  convention (JSON has no comments — restate the rule in `shell/gate.py`'s module docstring).
- `tests/test_sections_config.py` -- precedent test structure (one test per I/O-matrix row,
  `_write(tmp_path, content)` helper, `content_hash == hashlib.sha256(...).hexdigest()`) to mirror.
- `ARCHITECTURE-SPINE.md:88-100` (AD-1 purity boundary), `:163-174` (AD-8 vocabulary rule), `:316`
  (schema-versions row), `:413-414` (source tree placement).
- `prd.md:978-984` -- Open Question 1, the fact-leaning gap this story documents, not closes.

## Tasks & Acceptance

**Execution:**
- [x] `core/errors.py` -- add `GateVocabularyError(RuntimeError)` -- typed error, mirrors
  `SectionsConfigError`.
- [x] `core/types/gate.py` (new) -- frozen `GateVocabulary` (`version`, `content_hash`, `planets:
  frozenset[str]`, `signs: frozenset[str]`, `casa_ordinals: frozenset[str]`, `day_of_month_pattern:
  str`, `retrogrado: str`, `stazionario: str`).
- [x] `core/gate/vocabulary.it.json` (new) -- ten planets (sole…plutone), twelve signs
  (ariete…pesci), ordinal words for `casa` (prima…dodicesima), a day-of-month regex, `retrogrado`,
  `stazionario`, `"version": 1`.
- [x] `shell/gate.py` (new) -- `load_gate_vocabulary(path=DEFAULT_VOCABULARY_PATH) ->
  GateVocabulary` -- read/parse/validate/hash, mirroring `shell/sections.py`.
- [x] `core/gate/classify.py` (new) -- `is_claim(sentence, vocabulary) -> bool` -- pure
  token-membership check; no I/O.
- [x] `tests/test_gate_vocabulary.py` (new) -- one test per loader matrix row.
- [x] `tests/test_gate_classify.py` (new) -- one test per classification matrix row, including the
  zero-token and fact-leaning-but-unpoliced cases.

**Acceptance Criteria:**
- Given `vocabulary.it.json`, when created, then it holds the six-category closed vocabulary and
  its own integer version, independent of the Payload and Section-composition versions.
- Given a sentence, when classified, then it is a Claim iff it contains a vocabulary token; no
  token means interpretation — never a Claim, governed by the Style Guide instead.
- Given the vocabulary, when revised, then `version` increments and `content_hash` changes.
- Given a sentence leaning on a fact without naming it, when classified, then it is not policed,
  and this limit is documented rather than papered over.

## Design Notes

`vocabulary.it.json` shape (illustrative):

```json
{"version": 1, "planets": ["sole", "luna", "..."], "signs": ["ariete", "..."],
 "casa_ordinals": ["prima", "seconda", "..."],
 "day_of_month_pattern": "\\b([1-9]|[12][0-9]|3[01])\\b",
 "retrogrado": "retrogrado", "stazionario": "stazionario"}
```

`casa_ordinals` is a Claim token only combined with the literal word `casa` in the same sentence (an
ordinal alone, e.g. "la prima cosa", is not astronomical); every other category is a direct
substring/regex match.

## Verification

**Commands:**
- `uv run pytest tests/test_gate_vocabulary.py tests/test_gate_classify.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Vocabulary data & versioned shape**

- The versioned closed vocabulary itself -- start here to judge the six categories' content.
  [`vocabulary.it.json:2`](../../core/gate/vocabulary.it.json#L2)

- The frozen shape the JSON loads into; mirrors `SectionsConfig`'s `version`/`content_hash` fields.
  [`gate.py:25`](../../core/types/gate.py#L25)

**Loading & validation (shell boundary, AD-1)**

- Entry point: read/parse/validate/hash, mirroring `shell/sections.py`'s collecting-validator shape.
  [`gate.py:130`](../../shell/gate.py#L130)

- Compiles `day_of_month_pattern` at load time so an invalid regex fails at startup, not mid-classification.
  [`gate.py:119`](../../shell/gate.py#L119)

- Collects every missing/unexpected key before raising, so a malformed file names every offender at once.
  [`gate.py:76`](../../shell/gate.py#L76)

- Vocabulary path resolved from this file's own location, not a `shell/config.py` setting.
  [`gate.py:34`](../../shell/gate.py#L34)

**Classification (pure predicate)**

- The Claim predicate itself: token membership across the six categories, `casa`+ordinal co-occurrence.
  [`classify.py:32`](../../core/gate/classify.py#L32)

- Whole-word matching so a token doesn't false-match inside an unrelated longer word.
  [`classify.py:26`](../../core/gate/classify.py#L26)

**Errors & package docs**

- Typed error mirroring `SectionsConfigError`'s docstring convention: what, when, why no fallback.
  [`errors.py:84`](../../core/errors.py#L84)

- Replaces the Story 1.2 stub docstring with the real Groundedness Gate purpose, as a forward reference to Story 5.2.
  [`__init__.py:1`](../../core/gate/__init__.py#L1)

**Tests**

- One test per I/O-matrix classification row, plus the `casa`-without-ordinal and fact-leaning-unpoliced edge cases.
  [`test_gate_classify.py:1`](../../tests/test_gate_classify.py#L1)

- One test per I/O-matrix loader row, plus the non-dict-JSON, invalid-UTF-8 and empty-list patches from review.
  [`test_gate_vocabulary.py:1`](../../tests/test_gate_vocabulary.py#L1)

