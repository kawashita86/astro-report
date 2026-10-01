---
title: '10.3 Generate one Section at a time'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: '3de867f7668f6c404bddb0e038e220ad6d824083'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The `Generator` port can only write all eight Sections in one ~118 s call, so Sections cannot be written in parallel or rewritten individually.

**Approach:** Add `generate_section(section, payload, style_guide, theme_previous, theme_current, written_sections=None) -> tuple[Sentence, ...]` to the port and to both adapters, reusing the existing aliasing, schema-tightening and validation machinery scoped to one Section. `generate()` stays until Story 10.4 removes it (the driver still calls it).

## Boundaries & Constraints

**Always:** `section` is one of the eight `_SECTION_FIELD_NAMES`. One-Section response schema: narrative shape (any length, many ids) or day-list shape (array length pinned to the Payload's day-list count, exactly one id per sentence), `entry_ids` an `enum` of the shared short aliases. Alias-leak, citation, no-date-token (Sections 6/7 only) and day-list-coverage (Sections 6/7 only) validations run on that Section alone, raising the same `GenerationError` steps as today. Prompt order: system instruction, then user prompt = Payload + continuity block (byte-identical across all eight calls for implicit caching), then the Section-specific instruction last. Consiglio finale additionally receives Sections 1–7's sentence texts (never their ids) and still cites only Payload ids. Every module keeps its why-docstring; all functions fully type-hinted.

**Ask First:** Any change to the existing `generate()` prompt or schema wording; any new `GenerationError` step name.

**Never:** Remove `generate()` or touch `driver.py`/`scheduler.py` (Story 10.4). No DB, filesystem or tool use in adapters. No new env var.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Narrative Section | `amore`, valid response | tuple of `Sentence`, aliases translated to real ids | N/A |
| Day-list Section | `giorni_favorevoli`, N entries | N sentences, one id each, all N covered | missing coverage → `day_list_coverage_validation` |
| Consiglio finale | `consiglio_finale` + `written_sections` | prompt carries 1–7 texts, no ids from them; output cites Payload ids | N/A |
| Alias in text | text contains `e12` | rejected | `alias_token_in_text` |
| Unknown id | id absent from Payload | rejected | `citation_validation` |
| Date in 6/7 | "15 gennaio" in text | rejected | `date_token_validation` |
| Bad response | None / non-JSON / no `sentences` list | rejected | `parsing`; client failure → `request` |
| Unknown section | `"foo"` | rejected before any call | `ValueError` |

</frozen-after-approval>

## Code Map

- `shell/ports/generator.py` -- Protocol; add `generate_section` beside `generate`, document Consiglio's `written_sections`.
- `shell/adapters/generation/validation.py` -- draft-wide validators; extract per-Section variants (`_validate_section_*`) and make the draft validators delegate, messages unchanged.
- `shell/adapters/gemini/generator.py` -- `_build_id_aliases`, `_aliased_payload_json`, `_build_system_instruction`, `_render_continuity`, `_parse_sentences`, `_day_list_count` are reused as-is; `_validate_no_alias_tokens_in_text` becomes per-sentences; add `_build_section_response_schema`, shared-prefix and section-instruction builders, `GeminiGenerator.generate_section`. Existing `_build_prompt` stays for `generate()`.
- `shell/adapters/local/generator.py` -- `RecordedResponseGenerator`; add `generate_section` using `_section_subtree` and per-Section validators.
- `tests/test_gemini_generator.py`, `tests/test_recorded_generator.py` -- helpers `_payload_with_ids`, `_FakeGeminiClient`, `_theme`; add Section tests here.
- `tests/conformance/fixtures/` -- chart fixtures only; there is no recorded generator response to re-record (the local generator derives sentences from the Payload).

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/generation/validation.py` -- per-Section citation/date/coverage validators; draft validators delegate -- scope validation to one Section
- [x] `shell/ports/generator.py` -- add `generate_section` to the Protocol with docstring -- the port
- [x] `shell/adapters/gemini/generator.py` -- one-Section schema (object with a `sentences` array), shared prefix + trailing Section instruction, Consiglio continuity of 1–7 texts, `generate_section` -- core of the story
- [x] `shell/adapters/local/generator.py` -- `generate_section` -- local parity
- [x] `tests/test_gemini_generator.py` -- one test per matrix row; the schema (enum aliases, day-list count/one id); prompt prefix identical across two Sections and Section instruction last; Consiglio prompt holds texts but no 1–7 ids
- [x] `tests/test_recorded_generator.py` -- per-Section output validated, day-list coverage, unknown section

**Acceptance Criteria:**
- Given two `generate_section` calls for different Sections on one Payload, when the prompts are compared, then the system instruction and the text before the Section-specific instruction are identical.
- Given a Gemini response for one Section, when it is returned, then no short alias remains in `entry_ids`.
- Given `generate()`, when the existing suite runs, then it still passes unchanged.

## Spec Change Log

## Design Notes

Response is `{"sentences": [...]}` rather than a bare array so Gemini's structured output stays an object at the top level. `written_sections` maps Section name → its `Sentence`s; only `consiglio_finale` reads it, and only `.text` is rendered, so ids from Sections 1–7 cannot leak into Consiglio's citations.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean

## Suggested Review Order

**The port and its entry point**

- New port method; only `consiglio_finale` reads `written_sections`.
  [`generator.py:71`](../../shell/ports/generator.py#L71)

- Gemini `generate_section`: schema, prompt, then per-Section validation.
  [`generator.py:340`](../../shell/adapters/gemini/generator.py#L340)

**Prompt and schema**

- One-Section schema: alias enum, day-list count and one-id pinning.
  [`generator.py:205`](../../shell/adapters/gemini/generator.py#L205)

- Section instruction last, so the Payload prefix stays cacheable.
  [`generator.py:615`](../../shell/adapters/gemini/generator.py#L615)
  [`generator.py:648`](../../shell/adapters/gemini/generator.py#L648)

**Validation scoped to a Section**

- Draft validators now delegate to these; error messages unchanged.
  [`validation.py:131`](../../shell/adapters/generation/validation.py#L131)

**Local adapter and tests**

- Recorded generator parity.
  [`generator.py:89`](../../shell/adapters/local/generator.py#L89)

- Matrix rows, prefix identity, Consiglio texts without ids.
  [`test_gemini_generator.py`](../../tests/test_gemini_generator.py)
  [`test_recorded_generator.py`](../../tests/test_recorded_generator.py)
