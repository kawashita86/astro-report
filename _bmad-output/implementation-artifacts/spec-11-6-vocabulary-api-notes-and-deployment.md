---
title: '11-6 Vocabulary, API notes for the plugin team, and deployment'
type: 'feature'
created: '2026-10-10'
status: 'done'
baseline_commit: '80e9cc764fe36907ad12ed5574ec889c1d0fe0cf'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The five chart endpoints exist but the alerenzi team has no Italian vocabulary endpoint, no written contract or fixture responses, and nothing records the deployment facts, latency or licence stance, so alerenzi Story 7.6 cannot start.

**Approach:** Add `GET /api/v1/vocabulary/it` served from one new shared shell module that the operator UI's label tables also import. Write `docs/api/chart-data-v1.md` with generated, drift-tested example responses, record RGD-7, and prepare the latency record and hand-off checklist for the parts only Francesco can run on the VPS.

## Boundaries & Constraints

**Always:** New `shell/vocabulary.py` is the only copy of the Gate words (loaded via `load_gate_vocabulary`) and of the Italian body, sign, aspect and direction labels; `shell/http/stage_view.py` imports aspect and direction labels from it and deletes its own tables, byte-identical rendering. Endpoint: bearer-authenticated, sync, canonical JSON, no `meta`, body `{vocabulary_version, content_hash, gate{planets,signs,casa_ordinals,retrogrado,stazionario}, bodies{id:label}, signs{id:label}, aspects{id:label}, directions{id:label}}`, ids are the glossary ids verbatim (`sun`…`pluto`, `true_node`, `south_node`, `ascendant`, `midheaven`; `aries`…`pisces`; the five aspects; `direct`, `retrograde`), labels exactly the current operator-UI Italian. Doc sections: endpoints, shapes, error codes, determinism, birth-time and DST rules, unknown-time rules, window and year limits, version policy, network setup with public HTTPS fallback. One example per endpoint (natal, transits, synastry, solar return, places resolve, vocabulary) plus a `time_known: false` natal and a synastry with one unknown time, each the byte-exact response to a pinned request. A test regenerates them in-process (places via a fake geocoder) and fails on any drift. `docs/decisions/` gets RGD-7: the service token is not a principal, and the AGPL source offer goes to the alerenzi operator. `docs/release-validation/latency.md` gets a clearly marked, unmeasured placeholder for the 12-month `charts/transits` p90 (20 calls, target ≤ 30 s) that cannot read as a pass.

**Ask First:** Any change to a label string, an id, or existing endpoint output; changing `test_latency_record.py` semantics.

**Never:** Set `API_TOKEN_HASH`, touch Coolify or the VPS, or message the alerenzi session (Francesco's steps, listed in the doc's hand-off checklist). No fabricated latency figure or hostname. No new table, migration, env var, or thread. No second vocabulary copy.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Vocabulary | valid bearer | 200, body as above, identical bytes on repeat | N/A |
| No token | missing or wrong bearer | JSON 401 | `unauthorized` |
| Parity | operator UI renders an aspect or direction | same Italian string as before | N/A |
| Drift | doc example differs from a regenerated response | `test_api_doc_examples` fails | N/A |
| Guard | an example block edited by hand | guard test fails, with a `test_the_guard_detects_a_*` negative test | N/A |

</frozen-after-approval>

## Code Map

- `shell/gate.py` -- `load_gate_vocabulary`, `DEFAULT_VOCABULARY_PATH`; `core/gate/vocabulary.it.json`.
- `core/gate/run.py` -- `body_sign_label`, `_BODY_MAP`/`_SIGN_MAP`, `_ANGLE_NODE_LABELS_IT` (source of body/sign labels; core stays pure).
- `shell/http/stage_view.py:166` -- `_ASPECT_LABELS_IT`, `_DIRECTION_LABELS_IT` to move.
- `shell/http/api/{places,charts,transits,synastry,solar_return}.py`, `__init__.py` (register) -- endpoints the examples call; `router.py` prefix.
- `tests/test_api_{natal,transits,synastry,solar_return,skeleton}.py` -- app/bearer/FK fixtures and sample subjects to reuse; route-walk list in `test_api_skeleton.py` needs the new route.
- `docs/decisions/README.md` (RGD index, 6 entries), `docs/release-validation/latency.md` + `tests/test_latency_record.py` (parses the TOML block -- keep the placeholder outside it).
- `shell/http/app.py:220,357` -- gate vocabulary on `app.state`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/vocabulary.py`, `shell/http/stage_view.py` -- shared label tables and Gate words; operator UI imports them
- [x] `shell/http/api/vocabulary.py`, `shell/http/api/__init__.py` -- the endpoint
- [x] `tests/test_api_vocabulary.py`, `tests/test_api_skeleton.py` -- matrix rows, id/label parity with `body_sign_label`, route-walk entry
- [x] `docs/api/chart-data-v1.md`, `tests/test_api_doc_examples.py` -- contract doc, generated examples, drift test and guard negative test
- [x] `docs/decisions/README.md` -- RGD-7
- [x] `docs/release-validation/latency.md` -- unmeasured placeholder and measurement recipe
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 11-6 to `review`

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access, concurrency and route-walk guards.
- Given the doc, when its examples are regenerated, then each equals the committed block byte for byte.
- Given the VPS steps (token, shared network, container call, hostname hand-off, latency, RGD ratification), when this story is reviewed, then they appear as an explicit open checklist for Francesco and nothing claims them done.

## Spec Change Log

## Design Notes

The remaining ACs (Coolify variable and shared network, WordPress-container call, hostname hand-off to alerenzi, VPS p90 over 20 calls) need access this build lacks. They are delivered as a checklist and a measurement script recipe, so the story ends in `review`, not `done`, until Francesco runs them.

## Verification

**Commands:**
- `uv run pytest tests/test_api_vocabulary.py tests/test_api_doc_examples.py tests/test_stage_view.py tests/test_latency_record.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**Shared vocabulary**

- One module holds the Italian aspect and direction words; body and sign labels derive from the Gate map.
  [`vocabulary.py:77`](../../shell/vocabulary.py#L77)

- Operator UI now imports the same tables; its own copies are gone.
  [`stage_view.py:27`](../../shell/http/stage_view.py#L27)

**Endpoint**

- Sync GET serving canonical JSON from the vocabulary loaded at startup.
  [`vocabulary.py:23`](../../shell/http/api/vocabulary.py#L23)

**Contract doc and drift guard**

- Pure guard: regenerate each example and compare against the document.
  [`test_api_doc_examples.py:166`](../../tests/test_api_doc_examples.py#L166)

- The plugin team's document, with generated examples and the open hand-off checklist.
  [`chart-data-v1.md:1`](../../docs/api/chart-data-v1.md#L1)

**Latency record**

- Unmeasured placeholder and measurement recipe, outside the TOML block.
  [`latency.md:207`](../../docs/release-validation/latency.md#L207)

**Tests**

- Matrix rows, id/label parity and operator-UI parity.
  [`test_api_vocabulary.py:1`](../../tests/test_api_vocabulary.py#L1)
