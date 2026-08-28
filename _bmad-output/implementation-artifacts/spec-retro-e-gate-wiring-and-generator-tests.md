---
title: 'retro bundle E — Gate wiring + generator tests (items 38/40/41/29/30/31/32)'
type: 'chore'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd113cf3fc3ccd28c40145fabf1a602fa66ca7a53'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-retro-2026-08-22.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-retro-2026-08-25.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Seven open retrospective action items cluster around two seams — the Groundedness
Gate's wiring/validation and the two `Generator` adapters' test honesty. Item 38 (wire
`view_report_draft` to the persisted `StoredGateResult`) is already implemented and tested in
code (commit `a772ba6`) but its `sprint-status.yaml` entry is still `open`. The other six are
verification-and-hardening tasks the epic-4/epic-5 retros logged as "defer / verify before
fixing": two generator-adapter test gaps, one unverified `try/except` span, one uncaught
`ValueError`, one un-measured Gate false-positive class, and one missing load-time cross-check.

**Approach:** One bundle, mirroring the repo's existing `spec-retro-c-*`/`spec-retro-d-*` /
`spec-batch-b-*` pattern. Item 38: verify the code/tests are complete, then flip its
`sprint-status.yaml` status to `done` (no code change). Items 29/30/40: additive characterization
tests only. Item 41: a pure derived-constant in `core/gate/run.py` plus a load-time cross-check in
`shell/gate.py`. Items 31/32: minimal typed-error guards, each with a covering test.

## Boundaries & Constraints

**Always:**
- Item 38 is code-complete: `shell/http/routes/report_runs.py` already reads `StoredGateResult`
  ordered by `regeneration_count` desc with `.where(passed.is_(False))`, `run_gate` is no longer
  imported there, and `tests/test_http_report_runs.py` already covers it (the bound-exhausted,
  multiple-rows/diverged-vocabulary, and no-row cases). The only change for item 38 is setting its
  `action_items` entry in `sprint-status.yaml` to `status: done`. If verification shows the code
  is NOT complete, HALT (see Ask First).
- Item 41's translation-map exposure lives in `core/gate/run.py` as a module-level dict built
  from the existing `_BODY_MAP`/`_SIGN_MAP`/`_CASA_ORDINAL_TO_HOUSE` constants — a pure
  comprehension, no I/O, `run_gate()` stays byte-for-byte deterministic. `core/` still imports no
  `shell/`.
- Item 41's cross-check runs inside `load_gate_vocabulary()` and folds any mismatch into the
  existing `problems` list, so a bad vocabulary still names every offender at once and raises the
  same `GateVocabularyError` ("Refusing to start: ..."). It compares in both directions: a
  vocabulary word with no map entry AND a map key with no vocabulary word are both reported. With
  today's `vocabulary.it.json` the check passes (word sets equal the map keysets exactly).
- Item 31: widen `GeminiGenerator.generate()`'s protection to cover `_build_system_instruction`
  /`_build_prompt`. Add exactly one new value `"prompt_construction"` to `GenerationStep`
  (`core/errors.py`) and convert any non-`GenerationError` exception raised while building the
  prompt into `GenerationError("prompt_construction", ...)`. A `GenerationError` already raised
  inside that block propagates unwrapped. The existing network-call `try/except` (step
  `"request"`) is unchanged.
- Item 32: `_entry_date` (`shell/http/draft_view.py`) currently raises a bare `ValueError` on an
  unrecognized/missing `kind`; nothing between it and `view_report_draft` catches it. The three
  `kind`s in `_DATE_FIELD_BY_KIND` are the only ones `project_day_lists()` emits, so an
  unrecognized `kind` is a data-integrity impossibility, not user input — raise `RuntimeError`
  with the same descriptive message instead, matching `report_runs.py`'s existing
  `RuntimeError`-on-impossible-state convention (`_load_passed_report_bundle`,
  `view_report_draft`'s own missing-row branches).
- Items 29/30/40 add tests only — no production-code behavior change. Item 40's tests assert the
  *current* (documented, accepted) false-positive behavior; they characterize and lock it, they
  do not "fix" it.
- New tests mirror the fixtures already in their target file: `tests/test_gemini_generator.py
  ::test_citation_validation_finds_ids_in_a_real_freeze_payload_shaped_payload` and
  `tests/test_gate_run.py::_freeze` for real `freeze_payload()` output; `tests/test_gate_classify
  .py`'s one-assertion-per-row style.

**Ask First:**
- If verifying item 38 shows `shell/http/routes/report_runs.py` or `tests/test_http_report_runs.py`
  does NOT already implement the persisted-`StoredGateResult` read as described — HALT and report,
  do not re-implement it inside this bundle.
- If item 30's filesystem assertion (patching `open` around the `generate()` call) proves flaky
  under pytest/coverage — HALT and confirm narrowing item 30 to socket-blocking only.

**Never:**
- No change to `core/gate/run.py`'s classification or extraction logic, `run_gate()`'s signature,
  `GateResult`, `StoredGateResult`, `store_gate_result()`, or `shell/runner/driver.py`.
- No change to `shell/http/routes/report_runs.py` for item 38 (only `sprint-status.yaml`).
- No new `day_of_month_pattern` / `casa`-trigger heuristic for item 40 (AD-8 forbids it; the
  false positives are an accepted design cost).
- No reshaping of `GenerationStep` beyond adding `"prompt_construction"`; no change to the
  `"request"`/`"parsing"`/`"citation_validation"`/`"date_token_validation"` semantics.
- No new dependency (e.g. `pytest-socket`) for item 30 — use `monkeypatch`.
- Items 42–45 (epic-5 retro) and 33–37 (epic-4 retro) are out of scope even where adjacent.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Item 29: RecordedResponseGenerator vs real payload | a `freeze_payload()` output with entries under a Section and both day-lists | `generate()` returns a `GeneratedDraft`; every cited id is present in the payload; each Section cites exactly the ids in its own subtree; `_section_subtree`'s `None`-value branch is never entered (real `freeze_payload()` always writes dicts at `sections`/`day_lists`) | N/A |
| Item 30: no network I/O | `socket.socket` monkeypatched to raise; real payload | `generate()` still succeeds | test fails if any socket is opened |
| Item 30: no filesystem I/O | `builtins.open` monkeypatched to raise, scoped to the `generate()` call; real payload | `generate()` still succeeds | test fails if a file is opened (fallback: socket-only, per Ask First) |
| Item 31: prompt construction raises | fake `_GeminiClient` never reached; `_build_prompt` forced to raise (non-serializable payload passed to `canonical_json_bytes`) | `GenerationError` with `.step == "prompt_construction"`, `from` the original exception | typed error, not a raw `TypeError`/`KeyError` |
| Item 31: network call raises (unchanged) | fake client raises on `generate_content` | `GenerationError` with `.step == "request"` | unchanged from today |
| Item 32: unrecognized day-list `kind` | a day-list entry dict whose `kind` is not `aspect`/`lunation`/`station` | `_entry_date` raises `RuntimeError` naming the entry; surfaces as a 500 (impossible-state), not a bare `ValueError` | `RuntimeError`, message unchanged in substance |
| Item 40: bare 1–31 number, non-astrological | `is_claim("Per i prossimi 3 giorni rallenta.", VOCABULARY)` | `True` — documented false positive (day-of-month trigger fires on any bare 1–31) | N/A |
| Item 40: mundane "casa" + ordinal | `is_claim("Ho preso la mia seconda casa al mare.", VOCABULARY)` | `True` — documented false positive | N/A |
| Item 40: false positive reaches run_gate | a mundane "seconda casa" / "3 giorni" sentence citing an entry with no house/day fact | `run_gate()` returns an `invented_fact` violation — the practical cost is an unnecessary regeneration / bound failure for prose making no astronomical claim | N/A |
| Item 41: vocabulary word with no translation | a `planets`/`signs`/`casa_ordinals` word absent from the matching map (or vice versa) | `load_gate_vocabulary()` raises `GateVocabularyError` naming the unpaired word(s), both directions | folded into the existing `problems` list |
| Item 41: shipped vocabulary | `core/gate/vocabulary.it.json` as-is | loads clean — word sets equal the map keysets | N/A |

</frozen-after-approval>

## Code Map

- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- `action_items` entries by id:
  `epic-5-retro-item-38-wire-view_report_draft-shell-http-routes` → set `status: done`. Leave
  40/41/29/30/31/32 for step-04 / the follow-up "mark done" commit once this bundle lands.
- `shell/http/routes/report_runs.py:39,297-369` -- item 38 evidence only: `StoredGateResult`
  import (L39), `view_report_draft`'s persisted-row read (L357-366), docstring (L315-326). Read
  to confirm completeness; do not edit.
- `tests/test_http_report_runs.py:758-915` -- item 38 evidence: `test_the_draft_view_for_a_failed_run_still_404s`,
  `test_getting_the_draft_for_a_bound_exhausted_run_shows_gate_violations_...` (seeds a real
  `store_gate_result(...)` row), `test_getting_the_draft_for_a_run_with_multiple_gate_results_shows_only_the_...`
  (out-of-order rows + diverged live vocabulary). Read to confirm; do not edit.
- `shell/adapters/local/generator.py:46-56,65-81` -- `_section_subtree` (item 29's `None`-branch
  question), `RecordedResponseGenerator.generate()` (items 29/30 target). No edit.
- `tests/test_recorded_generator.py` -- items 29/30 land here. Existing `_multi_section_payload()`
  is hand-built and carries a `"profile": {"id": ...}` the real pipeline never emits; add a real
  `freeze_payload()`-backed fixture (copy the `Payload`/`SectionPayload`/`DayLists` +
  `load_computation_config`/`load_sections_config`/`verify_ephemeris_identity` setup from
  `tests/test_gemini_generator.py:432-487`).
- `shell/adapters/gemini/generator.py:111-134` -- `GeminiGenerator.generate()`: `_build_system_instruction`
  /`_build_prompt` at L118-119 sit OUTSIDE the L121-128 `try/except` (confirmed). Item 31 wraps
  them.
- `core/errors.py:36,~140-160` -- `GenerationStep` Literal (add `"prompt_construction"`);
  `GenerationError` docstring (mention the new step).
- `tests/test_gemini_generator.py` -- item 31's test lands here (mirror the `_FakeGeminiClient`
  pattern; force `_build_prompt` to raise via a payload value `canonical_json_bytes` can't
  serialize, e.g. `{"unserializable": object()}` merged into an otherwise-real payload, or a
  `theme_current` that breaks `diff_themes`).
- `shell/http/draft_view.py:66-70,105-109,120-142` -- `_DATE_FIELD_BY_KIND`, `_entry_date` (item
  32: `ValueError` → `RuntimeError`), `_render_list` caller.
- `tests/test_draft_view.py` -- item 32's test lands here (179 lines; add one case feeding
  `render_draft`/`_render_list` a day-list entry with a bogus `kind`).
- `shell/http/routes/report_runs.py:122-129,340-369` -- `_render_stored_draft` → `render_draft`
  → `_render_list` → `_entry_date` is the uncaught path through `view_report_draft`; convention
  reference: `_load_passed_report_bundle` (L132-178) raises `RuntimeError` for every
  impossible-state row.
- `core/gate/run.py:95-146` -- `_BODY_MAP` (10), `_SIGN_MAP` (12), `_CASA_ORDINAL_TO_HOUSE` (12).
  Item 41 adds a module-level `TRANSLATABLE_VOCABULARY: dict[str, frozenset[str]]` built from
  these, added to `__all__`.
- `shell/gate.py:38-42,130-175` -- `_STRING_LIST_FIELDS`, `load_gate_vocabulary()`'s
  parse-then-collect-`problems` flow. Item 41: after the `_read_string_list` calls, when
  `planets`/`signs`/`casa_ordinals` all parsed, compare each to `TRANSLATABLE_VOCABULARY[...]`
  both ways and append a `problem` string per mismatch.
- `tests/test_gate_classify.py` (88 lines) / `tests/test_gate_run.py:1-90` -- item 40 tests;
  `_VOCABULARY = load_gate_vocabulary(DEFAULT_VOCABULARY_PATH)` and `_freeze(...)` already there.
- `tests/test_gate.py` or `tests/test_gate_vocabulary*.py` -- item 41's loader test (find the
  existing `load_gate_vocabulary` test module; add a monkeypatched-map or tmp-file case).

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/gemini/generator.py` + `core/errors.py` -- add `"prompt_construction"` to
  `GenerationStep`; wrap `_build_system_instruction`/`_build_prompt` so any non-`GenerationError`
  becomes `GenerationError("prompt_construction", ...)` `from` the original; update the
  `GenerationError` docstring's step list. (item 31)
- [x] `shell/http/draft_view.py` -- `_entry_date`: raise `RuntimeError` (not bare `ValueError`)
  on an unrecognized/missing `kind`, keeping the descriptive message; note in the docstring it is
  an impossible-state guard (`project_day_lists()` emits only the three known kinds). (item 32)
- [x] `core/gate/run.py` -- add `TRANSLATABLE_VOCABULARY: dict[str, frozenset[str]]` (pure,
  built from the three existing maps) and export it in `__all__`. (item 41)
- [x] `shell/gate.py` -- import `TRANSLATABLE_VOCABULARY`; in `load_gate_vocabulary()`, after the
  three `_read_string_list` calls, when all three parsed, append a `problem` for every
  vocabulary-word-without-map-entry and every map-key-without-vocabulary-word, per category. (item 41)
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- set the
  `epic-5-retro-item-38-...` `action_items` entry to `status: done` (after confirming its code +
  tests are complete). (item 38)
- [x] `tests/test_recorded_generator.py` -- add a real-`freeze_payload()` fixture and tests:
  `generate()` returns a valid `GeneratedDraft`, every cited id is in the payload, per-subtree
  citation is exact, and (settling edge-case-hunter #4) `_section_subtree` never meets a `None`
  at `sections`/`day_lists` from real output. (item 29)
- [x] `tests/test_recorded_generator.py` -- add a runtime no-I/O test: `socket.socket`
  monkeypatched to raise (and `builtins.open` scoped to the call, per Ask First), `generate()`
  against a real payload still succeeds. (item 30)
- [x] `tests/test_gemini_generator.py` -- add a test: a forced prompt-construction failure
  surfaces as `GenerationError` with `.step == "prompt_construction"`; keep/confirm the existing
  `.step == "request"` network-failure test. (item 31)
- [x] `tests/test_draft_view.py` -- add a test: a day-list entry with an unrecognized `kind`
  makes `render_draft` raise `RuntimeError` (not `ValueError`). (item 32)
- [x] `tests/test_gate_classify.py` + `tests/test_gate_run.py` -- add characterization tests for
  the two accepted false-positive triggers: a bare 1–31 number used as a duration/count/age, and
  mundane "casa" + ordinal — `is_claim(...) is True` for both, and `run_gate()` returns an
  `invented_fact` violation when such a sentence cites a fact-free entry. (item 40)
- [x] `tests/<gate vocabulary loader test module>` -- add a test: a vocabulary whose word set
  diverges from `TRANSLATABLE_VOCABULARY` (either direction) raises `GateVocabularyError` naming
  the unpaired word; the shipped `vocabulary.it.json` still loads clean. (item 41)

**Acceptance Criteria:**
- Given the shipped repo, when the full suite runs, then every new test passes and no existing
  test regresses.
- Given item 38, when its `sprint-status.yaml` entry is read, then `status: done` — and this was
  set only after confirming `report_runs.py` + `test_http_report_runs.py` already implement the
  persisted-`StoredGateResult` read (no code written for item 38 in this bundle).
- Given a future `vocabulary.it.json` that adds a `planets`/`signs`/`casa_ordinals` word without
  a matching translation-map entry, when the app starts, then it refuses to start with a
  `GateVocabularyError` naming that word — instead of silently under-checking that category.
- Given a `GeminiGenerator` prompt-construction failure, when `generate()` is called, then the
  caller sees a typed `GenerationError(step="prompt_construction")`, never a raw `TypeError`/`KeyError`.
- Given a day-list entry with an unrecognized `kind`, when `view_report_draft` renders it, then a
  `RuntimeError` (impossible-state) is raised, consistent with the route's other data-integrity guards.

## Design Notes

**Item 31 — why a new step, not reuse `"request"`.** `GenerationStep` is deliberately the closed
set of *distinct* failure points so tests/handlers key off a stable label. A prompt that can't be
built is not "the Gemini call failed"; giving it its own `"prompt_construction"` value keeps the
taxonomy honest and lets a test assert precisely. In practice this path is unreachable with the
trusted frozen-payload + real-theme inputs `_run_draft_ready` passes — the guard is for
defence-in-depth and to make the module docstring's "every failure mode surfaces as a typed
`GenerationError`" claim actually true.

**Item 32 — `RuntimeError`, not a caught-and-handled `ValueError`.** The retro asked "add a guard
if [uncaught]". It is uncaught. But the right guard is not a `try/except` in the route — an
unrecognized `kind` means `freeze_payload()`/`project_day_lists()` produced something impossible,
which is exactly what `report_runs.py` already answers with `RuntimeError` elsewhere. Swapping the
bare builtin `ValueError` for `RuntimeError` makes the failure mode match the convention and stops
it reading like a validation error.

**Item 40 — these tests assert a bug-shaped behavior on purpose.** `is_claim(...) is True` for
"per i prossimi 3 giorni" is a false positive, and the test says so in its name/docstring. Its
value is (a) a regression tripwire if someone later narrows the trigger without updating the
retro decision, and (b) a measured record of the false-positive surface before Epic 6 exposed it
to client-facing reports.

**Item 41 — direction matters.** Vocabulary-word-without-map-entry is the dangerous case
(`is_claim` flags it, `run.py` has no translation, the category is checked as an empty asserted
set and can pass ungrounded). Map-key-without-vocabulary-word is only latent drift. Reporting both
keeps the two artifacts provably in lockstep, which is the finding's actual ask.

## Verification

**Commands:**
- `uv run pytest tests/test_recorded_generator.py tests/test_gemini_generator.py tests/test_draft_view.py tests/test_gate_classify.py tests/test_gate_run.py tests/test_http_report_runs.py -q` -- expected: all pass.
- `uv run pytest -q` -- expected: full suite green, no regressions.
- `uv run ruff check .` -- expected: no new violations.
- `grep -n 'status: done' -A0 -B2 _bmad-output/implementation-artifacts/sprint-status.yaml | grep -A2 -B0 'epic-5-retro-item-38'` (or open the file) -- expected: item 38 marked `done`.

**Manual checks:**
- Confirm `run_gate` is not imported in `shell/http/routes/report_runs.py` and `view_report_draft`
  reads `StoredGateResult` ordered by `regeneration_count.desc()` — the precondition for flipping
  item 38 to `done`.

## Suggested Review Order

**Item 31 — every generator failure mode is now a typed `GenerationError`**

- Entry point: `_build_system_instruction`/`_build_prompt` now sit in their own `try`; a `GenerationError` re-raises unwrapped, anything else becomes `GenerationError("prompt_construction", ...)`.
  [`generator.py:118`](../../shell/adapters/gemini/generator.py#L118)
- The new closed-set step value, ordered first; docstring comment reworded.
  [`errors.py:39`](../../core/errors.py#L39)

**Item 41 — vocabulary and translation maps refuse to drift apart**

- The derived constant `run_gate()` exposes so the loader can cross-check it — pure comprehension over the three private maps, no I/O.
  [`run.py:168`](../../core/gate/run.py#L168)
- The load-time cross-check: both directions, per-list, folded into the existing `problems` list so one load names every offender.
  [`gate.py:120`](../../shell/gate.py#L120)
- Call site — `_STRING_LIST_FIELDS`-ordered tuple, field names spelled once.
  [`gate.py:212`](../../shell/gate.py#L212)

**Item 32 — impossible day-list state raises the codebase's impossible-state error**

- Bare `ValueError` → `RuntimeError`, matching `report_runs.py`'s data-integrity convention; docstring explains why.
  [`draft_view.py:105`](../../shell/http/draft_view.py#L105)

**Item 38 — sprint-status flip only (code + tests already landed in `a772ba6`)**

- [`sprint-status.yaml:403`](sprint-status.yaml#L403)

**Tests — new coverage and characterization**

- Prompt-construction failure surfaces as `GenerationError(step="prompt_construction")` with the original cause, provider never called.
  [`test_gemini_generator.py:588`](../../tests/test_gemini_generator.py#L588)
- An untranslated word / an orphan map key each refuse startup; shipped vocab cross-checked against the maps directly (independent of the loader guard).
  [`test_gate_vocabulary.py:266`](../../tests/test_gate_vocabulary.py#L266)
- `RecordedResponseGenerator` against real `freeze_payload()` output: valid cited draft, exact per-subtree citations, and `_section_subtree`'s `None` branch shown unreachable.
  [`test_recorded_generator.py:332`](../../tests/test_recorded_generator.py#L332)
- Runtime no-I/O proof: `socket.socket`/`create_connection`/`getaddrinfo`/`open` all patched to raise; `generate()` still succeeds.
  [`test_recorded_generator.py:384`](../../tests/test_recorded_generator.py#L384)
- Item 40 characterization: the two accepted Claim-trigger false positives, at classify and at `run_gate` (`invented_fact`).
  [`test_gate_classify.py:95`](../../tests/test_gate_classify.py#L95)
  [`test_gate_run.py:787`](../../tests/test_gate_run.py#L787)
- Unknown day-list `kind` raises exactly `RuntimeError`.
  [`test_draft_view.py:172`](../../tests/test_draft_view.py#L172)
