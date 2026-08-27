---
title: 'Batch B: small mechanical retro fixes (items 3/16, 7, 25, 27, 28+48, 33, 42, 43, 56, 67)'
type: 'chore'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: 'b6649ccab7b8035895f3d9db0f0773163f2037ef'
context: []
warnings: ['multiple-goals', 'oversized']
deferred:
  - summary: >-
      Item 27's ISO date branch still does no field-range validation, so a
      malformed ISO-shaped token such as "2026-13-99" matches.
    evidence: |-
      `_DATE_TOKEN_PATTERN`'s first alternate is `\b\d{4}-\d{2}-\d{2}\b` in
      both `core/gate/run.py` and `shell/adapters/gemini/generator.py`. This
      pre-dates the batch (only the numeric `DD.MM` branch was touched, and it
      now range-checks the month). Over-matching here only ever produces a
      false `date_token_in_day_list` / GenerationError on a token that is
      already date-shaped, so real-world impact is minor.
    location: >-
      core/gate/run.py + shell/adapters/gemini/generator.py (_DATE_TOKEN_PATTERN, ISO branch)
    severity: low
  - summary: >-
      Item 43 removed in-process retry for transient DB / deserialize errors in
      the gate_passed stage, not just for the deterministic gate check it was
      justified by.
    evidence: |-
      `with_backoff` wraps `_run_gate_passed`, which reads `ReportDraft` /
      `ReportPayload` back, deserializes, and writes `Report` +
      `StoredGateResult` before/after the pure `run_gate` call. With
      `max_attempts: 1` a transient Postgres blip (free-tier pooled connection
      reset, lock timeout) on those reads/writes now propagates on first
      occurrence and counts toward `_MAX_STAGE_FAILURES`. The cross-`drive()`-call
      budget still bounds it, but a persistence-only bounded retry (distinct
      from the deterministic gate check) would restore the absorbed-blip
      behaviour. Comment now states this tradeoff; decide whether to act on it.
    location: >-
      shell/runner/driver.py (_STAGE_BACKOFF_OVERRIDES["gate_passed"], _run_gate_passed)
    severity: medium
  - summary: >-
      The `YYYY-MM` month regex is now triplicated across `corpus.py`,
      `report_runs.py`, and effectively `shell/runner/month.py` (strptime).
    evidence: |-
      Item 56's retro text offered "optionally lift the shared YYYY-MM regex
      into one module"; the batch corrected only the provenance comment.
      `shell/http/routes/corpus.py` and `shell/http/routes/report_runs.py`
      carry the byte-identical `re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")`, with
      no lockstep test (unlike item 27's `_DATE_TOKEN_PATTERN`). Consolidating
      into one module, or adding a `.pattern` equality test, would close the
      drift risk the new comment only describes.
    location: >-
      shell/http/routes/corpus.py:55 + shell/http/routes/report_runs.py:69
    severity: low
  - summary: >-
      sprint-status.yaml action_items 3, 7, 16, 25, 27, 28, 33, 42, 43, 48, 56,
      67 remain `status: open` although this run completed them.
    evidence: |-
      `_bmad-output/implementation-artifacts/sprint-status.yaml` still lists
      each of these twelve entries as `open`. They should be marked `done`
      with a `ref` pointing at this spec / the batch commit, so the tracker
      reflects reality after this build-auto run.
    location: >-
      _bmad-output/implementation-artifacts/sprint-status.yaml (action_items)
    severity: low
---

<intent-contract>

## Intent

**Problem:** Ten unrelated `open` retrospective action items (`sprint-status.yaml` `action_items`) are each a few lines of purely mechanical code or documentation change — a guard-list addition, four determinism tiebreaks, a defensive `try/except`, a config bound, a regex tightening, a backoff override, and two doc/comment corrections. They are batched here because each alone is too small for its own plan/review cycle.

**Approach:** Apply each item as a self-contained edit against the file(s) its `action_items` entry names, with a focused test for every behavioral change and a docstring/comment edit for the documentation-only items. No new abstractions, no cross-item refactors, no schema/migration changes.

## Boundaries & Constraints

**Always:**
- Each item touches only the file(s) named in its row of the table below (plus that file's test).
- `core/` stays pure (AD-1): no new I/O, clock, network, or `shell/` import in a `core/` file. Item 25's `date.today()` call lives in `shell/config.py`, which already reads the environment and is not purity-bound.
- Item 27 edits `_DATE_TOKEN_PATTERN` in **both** `shell/adapters/gemini/generator.py` and `core/gate/run.py` to the **byte-identical** new pattern+flags — `tests/test_gate_run.py::test_the_local_date_token_pattern_stays_in_lockstep_with_the_generators` asserts `.pattern` and `.flags` equality and must stay green.
- Determinism tiebreaks (items 28, 33, 48) append a total-order key over stable identity/columns; they never change which rows/events are selected, only the order of ties.
- Existing passing tests stay green. `VALID_ENVIRONMENT` in `tests/test_config.py` uses `2026-01-15`, which is in the past relative to the current date and must remain accepted after item 25.

**Block If:**
- Item 48's `action_items` row also asks to "decide on `(client_id, month)` uniqueness in `start_report_run`". That is a schema/policy decision (allow / dedupe / reject) requiring a migration — **out of scope here**, left `open`. Only the ordering tiebreak is in scope. Do not add a uniqueness constraint or migration.
- Any item turning out to need a schema change, a migration, or a change to a public function signature: HALT with status `blocked`.

**Never:**
- No new shared module, no lifting the duplicated `YYYY-MM` regex into one place (item 56's "optionally" clause is declined — comment-only fix).
- Item 67: do **not** install an engine-level `json_serializer` (the retro's alternative option B); take option A (correct the docstrings).
- No reformat of untouched lines; no unrelated lint churn.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 25 future date | `GEMINI_DATA_TERMS_VERIFIED_AT` = a date after today | `load_settings` raises `ConfigError` naming the var and "future" | n/a — this is the error path |
| 25 today / past | value == today or earlier, well-formed ISO | accepted unchanged | No error |
| 27 dotted date | draft Section 6/7 sentence contains `15.01` or `15.01.2026` | `_DATE_TOKEN_PATTERN.search` matches → `date_token_validation` / `date_token_in_day_list` violation | GenerationError / GateViolation as today |
| 27 abbreviated month | sentence contains `15 gen` / `15 gen.` / `1° feb` | pattern matches | as above |
| 27 non-date lookalike | `3 mare`, `3 set di dati` | pattern does **not** match (word-boundary terminated) | No violation |
| 42 malformed payload date | cited entry's date field is `"not-a-date"` / `""` | `_date_facts` skips that entry, returns the other days; `run_gate` does not raise | `ValueError` from `fromisoformat` caught, entry skipped |
| 33 aspect tie | two `TransitAspectEvent`s with identical group/`perfected_at`/`orb_exit_at` | ordered by `(transiting_body, natal_point, aspect)` ascending — stable across input reorderings | n/a |
| 28 / 48 same-month tie | two `StoredReportTheme` / passed `Report` rows for one client & month | ordered by `created_at` desc then `id` desc — deterministic | n/a |
| 3/16 guard | a source file does `import environs` / `from environs import Env` | `test_env_access_is_centralized` flags it | n/a — this is the guard firing |

</intent-contract>

## Code Map

- `tests/test_env_access_is_centralized.py` — **item 3/16**. `_ENVIRONMENT_MODULES` frozenset, line 35 (`{"dotenv", "environ", "decouple", "pydantic_settings"}`) → add `"environs"`. `test_the_guard_detects_a_new_reader` (line ~144) `offenders` dict → add an `environs.py` entry. `visit_Import`/`visit_ImportFrom` already key on `root in _ENVIRONMENT_MODULES`, so the frozenset add is the whole behavior change.
- `core/ephemeris/identity.py` — **item 7**. `_check_for_unlisted_files` (line 134). `ephemeris_dir.iterdir()` is non-recursive and filters `path.is_file()`; a subdirectory is silently ignored. Document (not change): pyswisseph reads only files directly in the ephe path it is given, so a subdirectory is not a file it can load; the flat-directory assumption is deliberate.
- `shell/config.py` — **item 25**. `_read_gemini_data_terms_verified_at` (line 280). After the existing `date.fromisoformat(raw)` succeeds, compare the parsed `date` to `date.today()` (`date` already imported, line 22); a value strictly after today returns `(None, "<var> is invalid: <raw> is a future date; ...")`.
- `shell/adapters/gemini/generator.py` — **item 27**. `_ITALIAN_MONTHS` (line 50), `_DATE_TOKEN_PATTERN` (line 70) + its comment (lines 65–75). Add abbreviated-month alternates and a `.` separator.
- `core/gate/run.py` — **items 27 + 42**. `_DATE_TOKEN_PATTERN` (line 59) + comment (55–64): must end byte-identical to the generator's. `_date_facts` (line 243): wrap `datetime.fromisoformat(value).day` in `try/except ValueError`.
- `shell/adapters/postgres/report_theme.py` — **item 28**. `most_recent_prior_report_theme` (line 102), `.order_by(ReportRun.month.desc())` (line 122) → append `StoredReportTheme.created_at.desc(), StoredReportTheme.id.desc()`. Update the docstring's "Ordered by `ReportRun.month`" paragraph.
- `shell/http/routes/clients.py` — **item 48**. `list_client_reports` (line 643), `.order_by(ReportRun.month.desc())` (line 679) → append `Report.created_at.desc(), Report.id.desc()`. `Report` already imported and in the `select`. Update the docstring's "by month, most recent first" line to note the tiebreak.
- `core/memory/derive.py` — **item 33**. `_aspect_tightness_key` (line 49). Return-type annotation `tuple[int, bool, float]` → `tuple[int, bool, float, str, str, str]`; append `event.transiting_body, event.natal_point, event.aspect` to both `return` tuples. Update docstring.
- `shell/runner/driver.py` — **item 43**. `_STAGE_BACKOFF_OVERRIDES` (line 122) → add `"gate_passed": {"max_attempts": 1}`. Reword the comment (112–121): `run_gate()` is deterministic (`core/gate/run.py` docstring), so retrying an already-failed check gains nothing; `draft_ready` remains the only rate-limited-network override. `with_backoff` default is `max_attempts=3` (`shell/runner/backoff.py:31`); `stage_failure_count` counts exhausted `drive()` calls, not attempts, so behavioral tests in `tests/test_runner_driver.py` (e.g. line 1168, 1223, 1112) are unaffected.
- `shell/http/routes/corpus.py` — **item 56**. `_MONTH_PATTERN` comment, lines 51–54. It currently claims the shape matches `shell/runner/month.py`; that module uses `datetime.strptime(month, "%Y-%m")` (`_MONTH_FORMAT`, line 26), which also accepts an unpadded month (`2026-1`). Correct the comment: the regex was copied from `shell/http/routes/report_runs.py`'s `_MONTH_PATTERN` (line 69) and is deliberately stricter (zero-padding required) than `month.py`'s parse.
- `core/payload/freeze.py` — **item 67**. `canonical_json_bytes` docstring (line 51). It claims this serialization is what "every persisted `ReportPayload` is written as" — false: the DB `JSON` column is serialized by SQLAlchemy's default `json_serializer`, not this function. Reword to: the serialization every entry `id` is hashed from and the Generator prompt is built from; on-disk key order is not guaranteed and reproducibility does not depend on it (the content-hashed ids are computed here, before persistence).
- `shell/adapters/postgres/report_payload.py` — **item 67**. `ReportPayload` class docstring (lines 35–39), "canonical JSON: sorted keys, no insignificant whitespace" → correct: the dict is stored verbatim through the `JSON` column's serializer; `Decimal`s are already fixed-precision strings because `freeze_payload`'s `_json_safe` converts them; key order on disk is not canonical.

## Tasks & Acceptance

**Execution:**
- `tests/test_env_access_is_centralized.py` — add `"environs"` to `_ENVIRONMENT_MODULES`; add an `"environs.py": "from environs import Env\nenv = Env()\n"` offender to `test_the_guard_detects_a_new_reader` — item 3/16.
- `core/ephemeris/identity.py` — extend `_check_for_unlisted_files`'s docstring with the non-recursive / files-only rationale — item 7.
- `shell/config.py` — reject a future-dated `GEMINI_DATA_TERMS_VERIFIED_AT` in `_read_gemini_data_terms_verified_at` — item 25.
- `shell/adapters/gemini/generator.py` — tighten `_DATE_TOKEN_PATTERN` (abbreviated Italian months; `.` as a `DD.MM` separator) and its comment — item 27.
- `core/gate/run.py` — mirror the identical `_DATE_TOKEN_PATTERN` change (item 27); wrap `_date_facts`'s `datetime.fromisoformat` in `try/except ValueError` (item 42).
- `shell/adapters/postgres/report_theme.py` — add `created_at`/`id` desc tiebreak to `most_recent_prior_report_theme` — item 28.
- `shell/http/routes/clients.py` — add `Report.created_at`/`Report.id` desc tiebreak to `list_client_reports` — item 48.
- `core/memory/derive.py` — append the aspect identity triple to `_aspect_tightness_key`'s sort key + annotation + docstring — item 33.
- `shell/runner/driver.py` — add `"gate_passed": {"max_attempts": 1}` to `_STAGE_BACKOFF_OVERRIDES` and reword the comment — item 43.
- `shell/http/routes/corpus.py` — correct the `_MONTH_PATTERN` provenance comment — item 56.
- `core/payload/freeze.py` + `shell/adapters/postgres/report_payload.py` — correct the two canonical-JSON docstrings — item 67.
- Tests: add/extend focused tests for items 25, 27 (both modules + lockstep still green), 28, 33, 42, 48 in their existing test files (`test_config.py`, `test_gemini_generator.py`, `test_gate_run.py`, `test_report_theme_store.py`, `test_derive_theme.py`, `test_http_clients.py`). Items 3/16 gets its offender-case assertion; items 7, 43, 56, 67 are covered by the full suite staying green (43) or are doc-only (7, 56, 67).

**Acceptance Criteria:**
- Given a source file under `core/`/`shell/`/`migrations` that imports `environs`, when `tests/test_env_access_is_centralized.py` runs, then it is reported as an environment reader (guard fails for that file).
- Given `GEMINI_DATA_TERMS_VERIFIED_AT` set to a well-formed ISO date after the current date, when `load_settings` runs, then it raises `ConfigError` whose message names the variable and that the date is in the future; given the date equal to today or earlier, then `load_settings` succeeds.
- Given a Section 6/7 draft sentence containing `15.01`, `15.01.2026`, `15 gen`, `15 gen.`, or `1° feb`, when `run_gate` / `GeminiGenerator.generate` validates it, then a date-token violation/error is raised; given `3 mare` or `3 set di dati`, then no date-token violation is raised.
- Given `_GATE_DATE_TOKEN_PATTERN` and `_GENERATOR_DATE_TOKEN_PATTERN`, when compared, then `.pattern` and `.flags` are equal.
- Given a cited Payload entry whose date field is not a valid ISO datetime, when `run_gate` runs, then it returns a `GateResult` (no exception) and that entry contributes no day fact.
- Given two aspect events that tie on the existing tightness key, when `derive_theme` sorts `dominant_aspects`, then their relative order is determined by `(transiting_body, natal_point, aspect)` and is identical regardless of the order the events were collected in.
- Given two `StoredReportTheme` rows (item 28) / two passed `Report` rows (item 48) for one client and the same month, when `most_recent_prior_report_theme` / `list_client_reports` orders them, then the row with the later `created_at` (then the greater `id`) comes first, deterministically.
- Given the full test suite, when run after all edits, then it passes with no new failures, and `ruff`/type checks are clean on every touched file.

## Design Notes

Item 27 pattern shape (apply identically in both modules). Add a sibling abbreviation tuple and extend the two alternates:

```python
_ITALIAN_MONTH_ABBREVIATIONS = (
    "gen", "feb", "mar", "apr", "mag", "giu",
    "lug", "ago", "set", "sett", "ott", "nov", "dic",
)
_DATE_TOKEN_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}°?\s+(?:" + "|".join(_ITALIAN_MONTHS + _ITALIAN_MONTH_ABBREVIATIONS) + r")\b"
    r"|\b\d{1,2}[/.\-]\d{1,2}\b",
    re.IGNORECASE,
)
```

`\b` after the month alternation terminates an abbreviation (`3 mar` matches, `3 mare` does not — `r` then `e` is no boundary); a trailing `.` is simply left unconsumed by `.search()`. `[/.\-]` adds the dot; `.` inside a class is literal, `-` is escaped for clarity.

Item 33 key:

```python
def _aspect_tightness_key(event: TransitAspectEvent) -> tuple[int, bool, float, str, str, str]:
    identity = (event.transiting_body, event.natal_point, event.aspect)
    if event.orb_exit_at is None:
        missing = event.perfected_at is None
        ts = 0.0 if missing else -event.perfected_at.timestamp()
        return (0, missing, ts, *identity)
    return (1, False, -event.orb_exit_at.timestamp(), *identity)
```

## Verification

**Commands:**
- `uv run pytest tests/test_env_access_is_centralized.py tests/test_config.py tests/test_gemini_generator.py tests/test_gate_run.py tests/test_derive_theme.py tests/test_report_theme_store.py tests/test_http_clients.py tests/test_runner_driver.py tests/test_payload_freeze.py tests/test_report_payload_store.py tests/test_ephemeris_identity.py tests/test_http_corpus.py` — expected: all pass.
- `uv run pytest` — expected: full suite green, no new failures.
- `uv run ruff check core shell tests` — expected: clean.
- Type check per the repo's configured checker on the touched files — expected: clean (note item 33's widened return annotation).

## Review Triage Log

### 2026-08-28 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 2, low 7)
- defer: 4: (high 0, medium 1, low 3)
- reject: 23
- addressed_findings:
  - `[medium]` `[patch]` Item 27: the `.` added to the numeric date separator made `\d{1,2}[/.\-]\d{1,2}` match Italian clock times ("15.30", "9.45") and decimals ("1.5"), spuriously failing the day-list date-token check. Tightened the numeric branch in both `core/gate/run.py` and `shell/adapters/gemini/generator.py` (byte-identical, lockstep test green) so the second group must be a month `1`–`12` and a single-digit day requires a zero-padded month; `15.01`/`15.1`/`15.01.2026` still match, `15.30`/`9.45`/`1.5`/`13/45`/`99.99` no longer do. Added negative test cases in `test_gate_run.py` and `test_gemini_generator.py`.
  - `[medium]` `[patch]` Item 43: the `_STAGE_BACKOFF_OVERRIDES` comment justified `max_attempts=1` on `run_gate()` purity, but `with_backoff` wraps `_run_gate_passed` (DB read-backs + `Report`/`StoredGateResult` writes). Reworked the comment to rest on the deterministic `GateFailedError` regeneration path and to state the tradeoff (a transient DB error in the stage is no longer retried in-process, counts toward `_MAX_STAGE_FAILURES` from first occurrence). Fixed `_run_gate_passed`'s stale "retries … up to 3 times" docstring.
  - `[low]` `[patch]` Item 3/16: guard test only covered `from environs import Env`; added a bare `import environs` offender case (the `visit_Import` path).
  - `[low]` `[patch]` Item 33: tiebreak test exercised only the `orb_exit_at is None` branch and varied only `natal_point`. Added `test_derive_theme.py` cases for the separated branch (equal non-None `orb_exit_at`) and for ties broken by `aspect` / `transiting_body`, each asserted stable across input-order reversal.
  - `[low]` `[patch]` Item 33: `_aspect_tightness_key` docstring said "total-order tiebreak"; softened to "deterministic tiebreak" and noted two events sharing body/point/aspect that also tie on the timestamp key are not further separated; prose reconciled with the 6-tuple arity.
  - `[low]` `[patch]` Item 42: malformed-date skip was tested with only one cited entry. Added a `test_gate_run.py` case where a claim cites one malformed-date entry alongside a valid-date entry on the asserted day; the valid entry still grounds the claim.
  - `[low]` `[patch]` Item 43: added `test_runner_driver.py::test_a_failing_gate_passed_stage_runs_exactly_once_per_drive_call`.
  - `[low]` `[patch]` Item 67: docstrings implied on-disk payload JSON is non-reproducible; reworded to "`json.dumps` default output — unsorted keys, default `", "`/`": "` whitespace, deterministic for a stably-built dict", contrasted with `canonical_json_bytes`.
  - `[low]` `[patch]` Item 7: `_check_for_unlisted_files` docstring now notes `path.is_file()` follows symlinks, so a symlink to a directory is skipped like a real subdirectory.

## Auto Run Result

Status: done
Blocking condition: none

**Implemented change.** Ten batched `open` retrospective action items (`sprint-status.yaml` `action_items` 3/16, 7, 25, 27, 28, 33, 42, 43, 48, 56, 67), each a small self-contained code or documentation fix. No schema, migration, or public-signature change. Branch `retro-batch-b-mechanical-fixes` from `b6649cc`.

**Files changed:**
- `tests/test_env_access_is_centralized.py` — item 3/16: `"environs"` added to `_ENVIRONMENT_MODULES`; `from environs import Env` and bare `import environs` offender cases added to the guard's self-test.
- `core/ephemeris/identity.py` — item 7: `_check_for_unlisted_files` docstring documents the deliberate non-recursive / files-only (and symlink-following) scan; no behaviour change.
- `shell/config.py` — item 25: `_read_gemini_data_terms_verified_at` now rejects a well-formed ISO date after `date.today()`.
- `shell/adapters/gemini/generator.py` + `core/gate/run.py` — item 27: `_DATE_TOKEN_PATTERN` (kept byte-identical, lockstep test green) gains abbreviated Italian months (`gen`…`dic`, `set` deliberately excluded, `sett` kept) and a `.` date separator, with the numeric branch range-limited to a real month so clock times / decimals are not flagged.
- `core/gate/run.py` — item 42: `_date_facts` wraps `datetime.fromisoformat` in `try/except ValueError` so a malformed cited date is skipped, not raised.
- `shell/adapters/postgres/report_theme.py` — item 28: `most_recent_prior_report_theme` ORDER BY gains `created_at.desc(), id.desc()`.
- `shell/http/routes/clients.py` — item 48: `list_client_reports` ORDER BY gains `Report.created_at.desc(), Report.id.desc()` (the `(client_id, month)` uniqueness question is out of scope — see deferred).
- `core/memory/derive.py` — item 33: `_aspect_tightness_key` appends `(transiting_body, natal_point, aspect)` to its sort key (annotation widened to a 6-tuple).
- `shell/runner/driver.py` — item 43: `_STAGE_BACKOFF_OVERRIDES` gains `"gate_passed": {"max_attempts": 1}`; comment and `_run_gate_passed` docstring corrected.
- `shell/http/routes/corpus.py` — item 56: `_MONTH_PATTERN` provenance comment corrected (copied from `report_runs.py`, stricter than `month.py`'s `strptime`).
- `core/payload/freeze.py` + `shell/adapters/postgres/report_payload.py` — item 67: `canonical_json_bytes` / `ReportPayload` docstrings corrected — the sorted-key form is used for entry-id hashing and the Generator prompt, not for on-disk storage.
- Tests added/extended: `test_config.py`, `test_gemini_generator.py`, `test_gate_run.py`, `test_derive_theme.py`, `test_report_theme_store.py`, `test_http_clients.py`, `test_runner_driver.py`.

**Review findings breakdown:** 9 patches applied (2 medium, 7 low — see Review Triage Log); 4 items deferred (1 medium: item 43's in-process retry loss for transient DB errors in `gate_passed`; 3 low: item 27 ISO-branch range validation, item 56 `YYYY-MM` regex triplication, `sprint-status.yaml` `action_items` status not updated); 23 findings rejected (pre-existing design, out of scope per the "a few lines" intent, or reviewer misreads verified against the code — e.g. abbreviation-homograph expansion, `created_at` vs `id`-only tiebreak, `date.fromisoformat` accepting datetime strings, the two-write "inconsistent state" already covered by a shared uncommitted transaction).

**Follow-up review recommended:** true. This pass's patched findings: high 0, medium 2, low 7; score = 3×2 + 1×7 = 13 (≥ 5).

**Verification performed:**
- `uv run ruff check core shell tests` → `All checks passed!` (exit 0), before and after the review patches.
- `uv run pytest` full suite → exit 0, 1309 passed, 4 skipped (pre-existing), 1 pre-existing kerykeion `utcnow` DeprecationWarning. (The interactive terminal shows a spurious "Pytest: No tests collected"; redirecting stdout to a file shows the real result.)
- Targeted run of the 12 relevant test files → 438 passed.
- `_DATE_TOKEN_PATTERN` byte-identity re-checked in a Python shell, plus the full positive/negative match table (`15.01`/`15.1`/`15.01.2026` match; `15.30`/`9.45`/`1.5`/`13/45`/`99.99`/`3 set di dati` do not).
- I/O & Edge-Case Matrix: every row covered by a test that ran and passed.
- No type checker is configured in the repo (`pyproject.toml` has no mypy/pyright); the only type-surface change (item 33's 6-tuple return annotation) matches both return statements.

**Residual risks:**
- Item 27 trades a little recall for precision: single-digit-day + single-digit-month slashed dates (`3/3`) and a bare `15 set` (September) are no longer caught. The model is instructed not to write any date in those sections, and the month-name / ISO / `DD.MM(.YYYY)` forms are still covered.
- Item 43 reduces `gate_passed`'s in-process resilience to a transient DB blip (deferred, medium).
- Items 7, 56, 67 ship as documentation-only corrections; the behavioural facts they now assert (pyswisseph non-recursion, `strptime` leniency, SQLAlchemy's default serializer) are not pinned by a test.
