---
title: 'Story 4.5 — Generate eight Sections as cited structure'
type: 'feature'
created: '2026-08-21'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'cf45ed49d4448faf496c9434113ccd5cddc28e1c'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** There is no `Generator` port and no adapter — nothing turns a Report Payload into text at all, and any prose a future model produced without a fixed, cited output shape would be unverifiable free text, defeating the Groundedness Gate (Epic 5) before it can even run.

**Approach:** Define the `Generator` port fixed to `(payload, style_guide, theme_previous, theme_current)` (AD-3) and build its one Gemini adapter, returning each of the eight Sections as an ordered list of sentences carrying the Payload entry IDs they rest on (AD-6) — never free prose.

## Boundaries & Constraints

**Always:**
- `Generator` port: `generate(payload: dict, style_guide: StyleGuideVersion, theme_previous: ReportTheme | None, theme_current: ReportTheme) -> GeneratedDraft`. The adapter holds no database handle, no filesystem access, no tool definitions (AD-3). Prior Report prose is never an input.
- `GeneratedDraft` is a frozen dataclass with eight named fields in AD-6's fixed order (`energia_generale`, `amore`, `lavoro`, `denaro`, `benessere`, `giorni_favorevoli`, `giorni_di_attenzione`, `consiglio_finale`), never a string-keyed dict — order is structural, not a runtime check. Each field is `tuple[Sentence, ...]`; `Sentence` carries `text: str` and `entry_ids: tuple[str, ...]`.
- The adapter validates every `entry_id` the model returns against the full set of ids present anywhere in `payload` (every `"sections"` and `"day_lists"` entry) before returning `GeneratedDraft`; an unknown id raises `GenerationError`.
- The adapter validates that no sentence in `giorni_favorevoli`/`giorni_di_attenzione` contains a date-shaped token (day-of-month + month name, or an ISO date); a violation raises `GenerationError` naming the offending sentence. Dates in those two Sections are code-projected upstream (Story 3.7) — the model must never write one.
- `style_guide: StyleGuideVersion` (`version: int`, `content: str`) is a required argument, never optional — the caller supplies it from `current_style_guide()`, so a call with no Style Guide present cannot be constructed.
- `theme_previous: ReportTheme | None` — `None` for a Client's first Report (mirrors `diff_themes`'s own `previous is None` handling, Story 4.4); never a zero-valued `ReportTheme`.
- `shell/config.py` requires `GEMINI_API_KEY` and `GEMINI_DATA_TERMS_VERIFIED_AT` (a non-blank ISO date) at startup, same as every other required Setting — the process refuses to start without both. This is the verified-and-recorded check NFR-17 requires before real Client data is ever sent.

**Ask First:**
- Scope stops at the port + one working adapter. This story does **not** wire `shell/runner/driver.py` (no `draft_ready` stage registered), does not persist a draft table, and does not call `diff_themes` — the epic context assigns the persisted draft table to Story 4.6, which is what actually drives generation from the runner. Confirm this split before implementation starts.
- The data-terms check is enforced as a required Settings field (config refuses to start without it), not a database row or an in-app verification workflow — chosen because this is a single-operator deployment with exactly two environments and no staging, and every other startup-time invariant in this codebase (Argon2 hash, session key) already works this way. Confirm, or redirect to a different mechanism.

**Never:**
- No backoff/retry (Story 4.8), no recorded-response fixture adapter for tests (Story 4.9), no rendering into continuous prose (Story 4.6), no Groundedness Gate (Epic 5).
- No runtime failover to a second provider, ever (AD-9). Exactly one `Generator` adapter is configured.
- No attempt to code-check Italian-language output, register, or non-fatalism structurally — those are Style-Guide-and-prompt-carried and reviewed by Francesco, not verifiable at this layer.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path, returning Client | payload + style guide + both themes present | `GeneratedDraft` with all eight fields populated | N/A |
| First Report for a Client | `theme_previous=None` | Prompt omits prior-month material; `GeneratedDraft` still returned | N/A |
| Model cites an unknown entry id | response references an id absent from `payload` | — | `GenerationError` (citation step), draft never returned |
| Model writes a date in Section 6 or 7 | e.g. a day-of-month token inside `giorni_favorevoli` | — | `GenerationError` (date-token step) |
| Gemini call raises or times out | client call raises | — | `GenerationError` wraps the original; no retry (Story 4.8's job) |
| Malformed / non-JSON model response | response body isn't the expected structure | — | `GenerationError` (parsing step) |

</frozen-after-approval>

## Code Map

- `shell/ports/geocoder.py` -- `Geocoder(Protocol)`: the exact port-definition pattern to mirror for `shell/ports/generator.py` (docstring-as-contract, `Raises:` documented).
- `shell/adapters/nominatim/geocoder.py:37-62` -- `_GeocoderClient(Protocol)` + constructor-injected client pattern (`geolocator: _GeocoderClient | None = None`): mirror this exactly for a `_GeminiClient` Protocol in the new adapter, so tests never hit the network.
- `core/errors.py` -- add `GenerationStep` (`Literal["request", "parsing", "citation_validation", "date_token_validation"]`) and `GenerationError(RuntimeError)` alongside the existing `PlaceResolutionStep`/`PlaceResolutionError` pair — same pattern, same file (typed domain errors live here even though raised from `shell/`).
- `core/types/memory.py:69` -- `ReportTheme` (the `theme_previous`/`theme_current` argument type; `theme_previous` is `| None`).
- `shell/adapters/postgres/style_guide.py:34,82` -- `StyleGuide` row (`.version`, `.content`) and `current_style_guide(session) -> StyleGuide`: the source the caller builds `StyleGuideVersion` from; `StyleGuideMissingError` already exists there for the empty-table case.
- `core/payload/freeze.py` -- the frozen `Payload` dict shape: `{"sections": {6 keys}, "day_lists": {2 keys}}`, every event dict carrying `"id"` (AD-4). This is exactly the `payload: dict` argument shape and what citation validation reads ids from.
- `shell/config.py:65-141,259-306` -- `Settings` dataclass + `_read_required`/`_read_auth_password_hash`-style validators + `load_settings()`: extend with `gemini_api_key`/`gemini_data_terms_verified_at`, redacting the API key in `__repr__` like `redacted_auth_password_hash`.
- `pyproject.toml` -- add the `google-genai` dependency (no Gemini SDK is installed yet).
- `tests/test_geocoder_nominatim.py` -- fixture/fake-client conventions to mirror in the new test file.

## Tasks & Acceptance

**Execution:**
- [x] `core/errors.py` -- add `GenerationStep` Literal and `GenerationError(RuntimeError)` -- typed failure vocabulary for the port, mirroring `PlaceResolutionError`.
- [x] `core/types/generation.py` -- new: `Sentence` (`text: str`, `entry_ids: tuple[str, ...]`) and `GeneratedDraft` (eight named fields per the Boundaries, fixed order) -- pure data, no logic.
- [x] `shell/ports/generator.py` -- new: `Generator(Protocol)` with `generate(...)`; also defines `StyleGuideVersion` (`version: int`, `content: str`) so the port never imports the ORM `StyleGuide` row.
- [x] `shell/config.py` -- add required `gemini_api_key`/`gemini_data_terms_verified_at` fields, their `_read_*` validators, and `redacted_gemini_api_key`.
- [x] `pyproject.toml` -- add `google-genai`.
- [x] `shell/adapters/gemini/__init__.py`, `shell/adapters/gemini/generator.py` -- new: `GeminiGenerator` implementing `Generator`; injectable `_GeminiClient` Protocol; builds the prompt from `payload`/`style_guide`/both themes, requests a structured response matching `GeneratedDraft`'s shape, parses it, runs the citation and date-token validations, raising `GenerationError` (with the failing `GenerationStep`) on any violation.
- [x] `tests/test_gemini_generator.py` -- new, covers the I/O & Edge-Case Matrix in full via an injected fake `_GeminiClient` (no real network call).

**Acceptance Criteria:**
- Given the `Generator` port, when it is defined, then it accepts exactly `(payload, style_guide, theme_previous, theme_current)`, and its adapter holds no database handle, filesystem access, or tool definitions.
- Given a generation request, when it is made, then the Style Guide version in force is a required argument — a call cannot be constructed without one.
- Given `GeneratedDraft`, when returned, then its eight Sections are in fixed field order and every Sentence's `entry_ids` are all present somewhere in `payload`.
- Given Sections `giorni_favorevoli`/`giorni_di_attenzione`, when returned, then no Sentence in either contains a date-shaped token.
- Given the process starting, when `GEMINI_API_KEY` or `GEMINI_DATA_TERMS_VERIFIED_AT` is missing, then startup refuses with a `ConfigError` naming the missing variable.

## Spec Change Log

## Design Notes

- **Why `StyleGuideVersion` instead of passing the ORM `StyleGuide` row:** keeps `shell/ports/generator.py` free of a `shell/adapters/postgres` import, matching how `Geocoder`'s own port takes only `core.types.place` value objects. The caller (Story 4.6's driver wiring) turns `current_style_guide(session)` into this two-field value.
- **Why citation validation checks the whole `payload`, not just the Section being generated:** entry ids are content-derived and global (AD-4); the same Aspect/Lunation/Retrograde legitimately appears in more than one Section's slice (Story 4.3's own dedup note), so restricting validation to one Section's own slice would reject a correct, cross-referenced citation.
- **Why the date-token and citation checks live in this adapter and not `core/gate/`:** the Gate (Epic 5) validates a *persisted draft* against the Payload after the fact and is deliberately model-agnostic; this story's checks are about trusting one response enough to return it at all — a narrower, earlier job the Gate doesn't remove the need for.
- The date-token check is a best-effort regex heuristic (day-of-month + Italian month name, or an ISO date), not a completeness guarantee — final backstop is Francesco's own review before export, same as register and non-fatalism.

## Verification

**Commands:**
- `uv run pytest tests/test_gemini_generator.py -q` -- expected: all pass, no real network call made.
- `uv run ruff check .` -- expected: no new violations.

**Manual checks (if no CLI):**
- Confirm `shell/adapters/gemini/generator.py` imports nothing from `shell/adapters/postgres` and nothing from `sqlmodel`/`sqlalchemy` (holds no DB handle, per AD-3).

## Suggested Review Order

**The port contract (AD-3)**

- Entry point: the fixed four-argument signature and the `StyleGuideVersion` value type that keeps the port ORM-free.
  [`generator.py:39`](../../shell/ports/generator.py#L39)

- The port's return shape — eight named fields in fixed order, never a dict.
  [`generation.py:32`](../../core/types/generation.py#L32)

**The Gemini adapter — request and parse (AD-6)**

- The one call site: builds the prompt, requests structured JSON, then runs both validations before returning.
  [`generator.py:148`](../../shell/adapters/gemini/generator.py#L148)

- The real SDK wrapper, injectable so tests never touch the network.
  [`generator.py:109`](../../shell/adapters/gemini/generator.py#L109)

- Parses the model's JSON into `GeneratedDraft`, rejecting any shape that doesn't match all eight Sections.
  [`generator.py:198`](../../shell/adapters/gemini/generator.py#L198)

**Trust boundary — validating a response before it's ever returned**

- Every cited `entry_id` must resolve against the whole Payload, not just its own Section (AD-4).
  [`generator.py:304`](../../shell/adapters/gemini/generator.py#L304)

- The date-token heuristic for Sections 6/7 — best-effort regex, not a completeness guarantee.
  [`generator.py:72`](../../shell/adapters/gemini/generator.py#L72)

**Typed failure vocabulary**

- `GenerationStep`/`GenerationError`, mirroring `PlaceResolutionError`'s existing pattern.
  [`errors.py:102`](../../core/errors.py#L102)

**Startup-time data-terms gate (NFR-17)**

- The two new required Settings fields and their validators — process refuses to start without both.
  [`config.py:280`](../../shell/config.py#L280)

**Tests — I/O & Edge-Case Matrix coverage**

- Happy path and the real-`ReportTheme` serialization case (Decimal/datetime through the prompt).
  [`test_gemini_generator.py:107`](../../tests/test_gemini_generator.py#L107)

- Citation validation against a real `freeze_payload()`-shaped payload, not just the hand-rolled fixture.
  [`test_gemini_generator.py:231`](../../tests/test_gemini_generator.py#L231)

- The real SDK wrapper's call shape, verified against a monkeypatched `genai.Client`.
  [`test_gemini_generator.py:472`](../../tests/test_gemini_generator.py#L472)

- Date-token rejection across ordinal, numeric, and ISO forms; and the no-false-positive case.
  [`test_gemini_generator.py:300`](../../tests/test_gemini_generator.py#L300)
