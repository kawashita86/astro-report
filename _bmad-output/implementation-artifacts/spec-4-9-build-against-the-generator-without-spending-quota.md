---
title: 'Story 4.9 — Build against the Generator without spending quota'
type: 'feature'
created: '2026-08-22'
status: 'done'
review_loop_iteration: 0
baseline_commit: '28aa350b07b257a16db0ecac92bfde503d8c49b8'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `get_generator()` (`shell/http/routes/report_runs.py`) always builds a real `GeminiGenerator`, in every environment — so running the app under `compose.yaml` (local Docker Compose + Postgres) would spend real Gemini quota on every `draft_ready` stage, and `compose.yaml`'s `app` service doesn't even set `GEMINI_API_KEY`/`GEMINI_DATA_TERMS_VERIFIED_AT`, so `docker compose up` fails `load_settings()` validation before the server can start at all.

**Approach:** Add a local-only `Generator` port adapter, `RecordedResponseGenerator`, that never calls a network, a model or the filesystem — it builds every Section's cited sentences directly from the entry ids already present in the `payload` it is given, so it is always citation-valid for whatever Client/month is under test (unlike a fixed recorded fixture, whose citations would only match the one Payload it was captured against — AD-4). Wire `get_generator()` to return it whenever `Environment.LOCAL`, mirroring the `settings.environment is Environment.LOCAL` idiom `shell/http/app.py` already uses twice. Give `compose.yaml`'s `app` service the two missing Gemini variables (unused values, since the recorded adapter never reads them) so `docker compose up` boots clean.

## Boundaries & Constraints

**Always:**
- `RecordedResponseGenerator` never performs network I/O, never reads the filesystem, and never imports `google.genai`.
- `RecordedResponseGenerator.generate()` reuses `shell/adapters/gemini/generator.py`'s own `_validate_citations`/`_validate_no_date_tokens` (imported directly, mirroring how `tests/test_gemini_generator.py` already imports that module's private constants) before returning, so a bug in the synthesis logic surfaces as the same `GenerationError` a real Gemini response would raise, never a silent, invalid draft.
- `get_generator()` returns `RecordedResponseGenerator()` when `request.app.state.settings.environment is Environment.LOCAL`, and an unchanged `GeminiGenerator(settings.gemini_api_key)` otherwise — production behavior is byte-for-byte unchanged.
- `GEMINI_API_KEY`/`GEMINI_DATA_TERMS_VERIFIED_AT` stay required, unconditionally, by `shell/config.py::load_settings()` in every environment (no change there) — `compose.yaml` supplies placeholder values for local use only, documented as unused.

**Ask First:** none identified — every value/placement decision below is pinned by an existing convention (AD-4's own content-derived ids, `shell/http/app.py`'s `Environment.LOCAL` idiom, the adapters-per-directory layout).

**Never:** No change to `GeminiGenerator`, `_RESPONSE_SCHEMA`, or any other stage's behavior. No new Generator port argument or method. No caching of the constructed generator on `app.state`. No real Gemini call from `RecordedResponseGenerator`, ever, under any input.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `get_generator()` under `Environment.LOCAL` | `request.app.state.settings.environment == Environment.LOCAL` | Returns a `RecordedResponseGenerator` instance; no `GeminiGenerator`/`genai.Client` constructed | N/A |
| `get_generator()` under `Environment.PRODUCTION` | `request.app.state.settings.environment == Environment.PRODUCTION` | Returns a `GeminiGenerator` built from `settings.gemini_api_key`, unchanged from today | N/A |
| A realistic multi-Section, multi-day-list payload | A `freeze_payload()`-shaped dict with entries under several Sections and both day-lists | `generate()` returns a `GeneratedDraft` whose every `Sentence.entry_ids` are all present in `payload`; `giorni_favorevoli`/`giorni_di_attenzione` sentences contain no date-shaped token | N/A |
| A Section/day-list with zero entries | That field's payload sub-tree is empty (`[]`/absent) | `generate()` still returns a `Sentence` for that field, with `entry_ids == ()` — never a citation error | N/A |
| `compose.yaml`'s `app` service | `docker compose up`-style env block | Declares `GEMINI_API_KEY` and `GEMINI_DATA_TERMS_VERIFIED_AT`, so `load_settings()` no longer refuses to start | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/local/__init__.py` -- new empty package init, mirroring `shell/adapters/gemini/__init__.py`.
- `shell/adapters/local/generator.py` -- new `RecordedResponseGenerator` class implementing `shell/ports/generator.py::Generator`. Iterates `_SECTION_FIELD_NAMES` (imported from `shell/adapters/gemini/generator.py`); for each name, reads `payload["day_lists"][name]` (if `name in _DATE_TOKEN_SECTIONS`) or `payload["sections"][name]`, collects entry ids via `_collect_known_entry_ids` (also imported), and emits one generic Italian placeholder `Sentence` per Section citing every id found there. Calls `_validate_citations`/`_validate_no_date_tokens` (imported) before returning.
- `shell/http/routes/report_runs.py:70-81` (`get_generator`) -- import `Environment` (`shell/config.py`) and `RecordedResponseGenerator`; branch on `request.app.state.settings.environment is Environment.LOCAL`.
- `compose.yaml:27-38` (`app.environment`) -- add `GEMINI_API_KEY: local-dev-unused` and `GEMINI_DATA_TERMS_VERIFIED_AT: "2026-01-01"`, each with a one-line comment noting they're unused by `RecordedResponseGenerator`.
- `.env.example:31-38` -- one-line note that `ENVIRONMENT=local` uses the recorded-response adapter and never sends these to Gemini, without changing either variable's required/validated status.
- `tests/test_recorded_generator.py` -- new file, mirrors `tests/test_gemini_generator.py`'s structure: builds `freeze_payload()`-shaped payloads (reusing `_payload_with_ids`-style helpers) and asserts the Matrix's citation/date-token/empty-Section rows.
- `tests/test_http_report_runs.py:58-66,610-634` -- add a `PRODUCTION` `Settings` const (mirrors `LOCAL`, `environment=Environment.PRODUCTION`); repoint `test_get_generator_builds_a_real_gemini_generator_from_the_apps_configured_key` at `PRODUCTION`; add a new test asserting `get_generator(_StubRequest(LOCAL))` returns a `RecordedResponseGenerator`.
- `tests/test_compose_local_generator.py` -- new file, one structural test (mirrors `tests/test_dockerfile_ephemeris_build.py`'s "read the file, no Docker invoked" approach): `compose.yaml`'s `app` service block contains both `GEMINI_API_KEY` and `GEMINI_DATA_TERMS_VERIFIED_AT`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/local/__init__.py` -- create empty package init.
- [x] `shell/adapters/local/generator.py` -- implement `RecordedResponseGenerator` per the Code Map.
- [x] `shell/http/routes/report_runs.py` -- branch `get_generator()` on `Environment.LOCAL`.
- [x] `compose.yaml` -- add the two missing Gemini env vars to the `app` service.
- [x] `.env.example` -- note that local mode never sends these values to Gemini.
- [x] `tests/test_recorded_generator.py` -- cover the I/O & Edge-Case Matrix's synthesis rows.
- [x] `tests/test_http_report_runs.py` -- cover the Matrix's `get_generator()`/environment rows.
- [x] `tests/test_compose_local_generator.py` -- cover the Matrix's `compose.yaml` row.

**Acceptance Criteria:**
- Given the local environment, when the application runs under Docker Compose against a local Postgres, then the configured Generator adapter replays recorded responses instead of calling the provider.
- Given the recorded-response adapter, when it is used in tests, then the shell is tested at the port boundary with fakes, and the same tests exercise the real port contract.

## Design Notes

- **Payload-derived, not a static fixture:** a literal recorded Gemini response (a JSON file checked into the repo) would only be citation-valid against the one Payload it was captured from — AD-4 makes entry ids content-derived, so every Client/month produces different ids. Building sentences from whatever ids the given `payload` actually contains keeps `RecordedResponseGenerator` valid for any input, in both real local dev and tests, without ever guessing at astronomical content.
- **Reusing `_validate_citations`/`_validate_no_date_tokens` rather than duplicating them:** this is what makes AC2's "the same tests exercise the real port contract" literally true — the recorded adapter is held to the exact same validators a real `GeminiGenerator` response must pass, not a parallel, potentially-drifting copy.
- **No `__init__` needed:** `RecordedResponseGenerator` holds no state and no injectable client (unlike `GeminiGenerator`'s `client` parameter) — there is nothing to fake because there is no network call to make.

## Verification

**Commands:**
- `uv run pytest tests/test_recorded_generator.py tests/test_http_report_runs.py tests/test_compose_local_generator.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.
- `docker compose config >/dev/null` -- expected: valid compose file (fast syntax/env-interpolation check, no containers started).

## Suggested Review Order

**Environment-based selection**

- Entry point: the design intent -- local development never spends real Gemini quota, production is untouched.
  [`report_runs.py:72`](../../shell/http/routes/report_runs.py#L72)

- The branch itself: `Environment.LOCAL` returns the recorded adapter; every other environment is the unchanged Gemini path.
  [`report_runs.py:89`](../../shell/http/routes/report_runs.py#L89)

**The recorded-response adapter**

- `generate()`: builds every Section's `Sentence`s from the payload's own entry ids, then runs the exact same citation/date-token validators a real Gemini response must pass.
  [`generator.py:65`](../../shell/adapters/local/generator.py#L65)

- `_section_subtree()`: why a fixed recorded fixture would have been wrong -- entry ids are content-derived (AD-4), so citations must be built from whatever payload is actually given.
  [`generator.py:46`](../../shell/adapters/local/generator.py#L46)

- Reusing `_validate_citations`/`_validate_no_date_tokens` rather than duplicating them -- the port contract this adapter is held to is identical to `GeminiGenerator`'s.
  [`generator.py:79`](../../shell/adapters/local/generator.py#L79)

**Local dev boots without a real Gemini key**

- `compose.yaml`'s `app` service now supplies both variables `load_settings()` requires unconditionally -- previously missing, so `docker compose up` failed before the server could start.
  [`compose.yaml:45`](../../compose.yaml#L45)

- `.env.example`'s note that these two values are never sent to Gemini under `ENVIRONMENT=local`.
  [`.env.example:33`](../../.env.example#L33)

**Tests**

- `get_generator()` returns the recorded adapter under `Environment.LOCAL` -- the core regression this story guards against.
  [`test_http_report_runs.py:649`](../../tests/test_http_report_runs.py#L649)

- The pre-existing test repointed at `Environment.PRODUCTION`, proving the real `GeminiGenerator` path is unchanged.
  [`test_http_report_runs.py:635`](../../tests/test_http_report_runs.py#L635)

- Every cited entry id traces back to the payload actually given, across several Sections and both day-lists.
  [`test_recorded_generator.py:130`](../../tests/test_recorded_generator.py#L130)

- Each Section cites exactly its own subtree's ids -- proves citations aren't cross-contaminated between Sections.
  [`test_recorded_generator.py:155`](../../tests/test_recorded_generator.py#L155)

- A Section/day-list with zero entries still returns a valid, uncited `Sentence` rather than erroring.
  [`test_recorded_generator.py:186`](../../tests/test_recorded_generator.py#L186)

- `compose.yaml`'s `app` service is checked by reading the file, not by invoking Docker -- mirrors the Dockerfile test's own approach.
  [`test_compose_local_generator.py:40`](../../tests/test_compose_local_generator.py#L40)

