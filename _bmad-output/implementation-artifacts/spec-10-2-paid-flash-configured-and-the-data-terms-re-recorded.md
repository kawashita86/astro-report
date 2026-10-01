---
title: '10.2 Paid flash, configured, and the data terms re-recorded'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: '591bf30f1bc21ea1d2db0d79db31513f1aa51a6b'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Gemini model is a hard-coded `_MODEL` in `generator.py`, there is no generation-concurrency setting, and the code, docs and data-terms record all still describe a free tier with a 10 RPM ceiling although the account is now paid.

**Approach:** Read `GEMINI_MODEL` and `GENERATION_CONCURRENCY` in `shell/config.py` (mirroring md-report), feed the model to `GeminiGenerator` from `Settings`, strip the free-tier/RPM rationale, and re-record the data-terms check as `tier = "paid"` with a new date.

## Boundaries & Constraints

**Always:** Only `shell/config.py` reads the environment; both new settings are optional with defaults, validated at startup, and added to `Settings` with dataclass defaults (many tests construct `Settings(...)` directly) and to `__repr__`. `GENERATION_CONCURRENCY` is an integer 1–32, ASCII digits only. Every module keeps its why-docstring; all functions fully type-hinted. `GEMINI_DATA_TERMS_VERIFIED_AT` is bumped to the new `checked` date in `.env.example` and `compose.yaml` (the guard test binds both).

**Ask First:** Any change to retry/backoff numbers in `driver.py` beyond rewording the comment; any claim in the data-terms record beyond switching tier and date (the quoted clauses and ratification stay as they are).

**Never:** Add a generator method or use `GENERATION_CONCURRENCY` anywhere (Stories 10.3/10.4 consume it). Touch `data/ephemeris/*`. Put a model name in `driver.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Defaults | both vars unset or blank | `gemini_model == "gemini-2.5-flash"`, `generation_concurrency == 11` | N/A |
| Override | `GEMINI_MODEL=gemini-2.5-pro`, `GENERATION_CONCURRENCY=4` | values carried on `Settings`; generator calls the API with that model | N/A |
| Bad concurrency | `0`, `33`, `abc`, `-1`, `4.5` | startup refused | `ConfigError` naming `GENERATION_CONCURRENCY` and 1–32, reported with other problems |

</frozen-after-approval>

## Code Map

- `shell/config.py` -- `Settings` dataclass (defaults after `use_real_gemini_locally`), `__repr__`, `_read_report_run_mode` (the optional-reader shape to copy), `load_settings` (error list + asserts).
- `../md-report/shell/config.py:42-105,153` -- reference for defaults 11/32, validation and `GEMINI_MODEL` fallback.
- `shell/adapters/gemini/generator.py:44-46,224,245` -- `_MODEL` constant, `_GoogleGenAIClient.__init__`/`generate_content`, `GeminiGenerator.__init__(api_key, *, client=None)`; tests pass `api_key="unused", client=` so keep that call shape working.
- `shell/runner/scheduler.py:100` -- sole production `GeminiGenerator(settings.gemini_api_key)` construction.
- `shell/runner/driver.py:59,146-152,764` -- free-tier/10 RPM prose to reword (comments/docstrings only).
- `docs/release-validation/gemini-data-terms.md` -- toml block (`tier`, `checked`), intro prose, trailing AD-9 reference naming `_MODEL`.
- `tests/test_data_terms_record.py` -- `_MODEL_LITERAL` regex and `tier == "free"` assertion bind to the old shape; `ENV_EXAMPLE`/`COMPOSE_FILE` date check.
- `.env.example`, `compose.yaml:51`, `README.md` (env table ~l.44, cost table l.151), `docs/decisions/README.md` RGD-1 (l.67-80) -- docs to update.
- `tests/test_config.py` (or the existing config test file) -- add setting tests.

## Tasks & Acceptance

**Execution:**
- [ ] `shell/config.py` -- add `gemini_model: str = "gemini-2.5-flash"` and `generation_concurrency: int = 11` with readers, `__repr__`, `load_settings` wiring -- startup validation
- [ ] `shell/adapters/gemini/generator.py` -- drop `_MODEL`; `GeminiGenerator`/`_GoogleGenAIClient` take `model: str`; reword the module comment -- model from Settings
- [ ] `shell/runner/scheduler.py` -- pass `settings.gemini_model` -- wiring
- [ ] `shell/runner/driver.py` -- remove free-tier / 10 RPM rationale from comments and docstrings -- stale
- [ ] `docs/release-validation/gemini-data-terms.md` -- `tier = "paid"`, `checked = 2026-10-01`, prose and AD-9 reference updated, change note appended -- AD-9 gate
- [ ] `tests/test_data_terms_record.py` -- compare record model to the `Settings` default, expect `tier == "paid"`; keep guard tests meaningful -- binding moved
- [ ] `.env.example`, `compose.yaml`, `README.md`, `docs/decisions/README.md` -- document both vars, bump verified date to `2026-10-01`, paid-tier wording
- [ ] `tests/` -- config tests for the matrix rows (defaults, override, each bad value, blank); generator test that the injected model reaches the SDK call

**Acceptance Criteria:**
- Given the environment lacks both new variables, when settings load, then the process starts with the defaults.
- Given `GeminiGenerator` is built with a model, when it calls the SDK, then that model is used and no `_MODEL` constant remains.
- Given `generator.py` and `driver.py`, when searched, then no free-tier or 10-RPM statement remains.
- Given the data-terms record, when the guard suite runs, then it passes with `tier = "paid"` and the bumped date in `.env.example` and `compose.yaml`.

## Spec Change Log

## Design Notes

`checked` is set to today's date on the strength of the user's statement that the account is paid; the quoted clauses and `ratified_on` are left as Francesco ratified them. Paid Services terms are the ones the record already quotes, so no clause changes.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `grep -rniE "free.tier|10 RPM|requests-per-minute" shell/adapters/gemini shell/runner` -- expected: no output

## Suggested Review Order

**Settings**

- Two optional settings with defaults, validated at startup like md-report.
  [`config.py:396`](../../shell/config.py#L396)

- Model now flows from `Settings` into the Generator; `_MODEL` is gone.
  [`scheduler.py:100`](../../shell/runner/scheduler.py#L100)
  [`generator.py:239`](../../shell/adapters/gemini/generator.py#L239)

**Data terms**

- Tier and date re-recorded; the guard test follows the new record.
  [`gemini-data-terms.md:16`](../../docs/release-validation/gemini-data-terms.md#L16)
  [`test_data_terms_record.py:131`](../../tests/test_data_terms_record.py#L131)

**Tests**

- Matrix rows: defaults, override, bad concurrency values.
  [`test_config.py:601`](../../tests/test_config.py#L601)
  [`test_gemini_generator.py:983`](../../tests/test_gemini_generator.py#L983)
