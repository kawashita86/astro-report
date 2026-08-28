---
title: 'Retro bundle D: shared-helper extractions (items 13, 19, 24, 51, 52, 54, 58, 62)'
type: 'refactor'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
baseline_revision: 'abc0736f03026893f1c0fbc2a07b970370127c53'
baseline_commit: 'abc0736f03026893f1c0fbc2a07b970370127c53'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/sprint-status.yaml'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Eight open retro action items all name the same smell — a helper, constant
cluster, or construction block copied verbatim across two or more modules, with the retro
authors themselves cross-referencing them as one bundle ("Bundle with epic-2-retro-item-13",
"Fold into epic-6-retro-item-52"):

- **13** — the `StoredNatalChart(...)` construction block is byte-identical in
  `create_client_with_chart()` and `correct_client_and_chart()`.
- **19** — `_GRID_STEP` / `_BISECTION_ITERATIONS` / `_ZERO_OFFSET` / `_require_utc_interval` /
  `_build_grid` / `_bisect` are byte-identical (AST-normalized) in all four
  `core/transits/{aspects,stations,ingresses,lunations}.py`, "mirrored rather than imported"
  by deliberate note — a note the retro now overrides.
- **24** — `shell/adapters/local/generator.py` reaches into the Gemini adapter's namespace for
  `_collect_known_entry_ids` / `_validate_citations` / `_validate_no_date_tokens` /
  `_DATE_TOKEN_SECTIONS` / `_SECTION_FIELD_NAMES`; importing that module executes
  `import google.genai`, so the local-only generator transitively needs the Gemini SDK.
- **51** — the Report→ReportRun→ReportDraft→ReportPayload→Client lookup + `render_draft`
  block is duplicated across `view_report` / `download_report_pdf` (verbatim) and
  partially in `view_report_draft` in `shell/http/routes/report_runs.py`.
- **52 + 54** — SQLite FK enforcement (`PRAGMA foreign_keys=ON`) is on for exactly one
  cascade test (`test_client_store.py::test_delete_client_and_derived_succeeds_with_a_report_run_referencing_a_natal_chart`)
  via a hand-rolled connect listener; every other `delete_client_and_derived` test in
  `test_client_store.py` and `test_corpus_store.py` runs with FK enforcement off. Separately,
  `shell/adapters/postgres/report_run.py::_UTCDateTime` is imported by 9 sibling adapter
  modules from a module that also defines an unrelated table.
- **58** — `_parse_form` + `_FormTooLarge` + `_FormNotUtf8` + a per-route
  `_MAX_*_FORM_BODY_BYTES` ceiling are copied verbatim across `clients.py`,
  `style_guide.py`, and `corpus.py`.
- **62** — `_TOML_BLOCK` / `_extract_toml_block` / `REPO_ROOT` / the `meta` module-fixture
  body are copied across `test_data_terms_record.py` / `test_latency_record.py` /
  `test_storage_growth_record.py` / `test_restore.py`.

**Approach:** Pure mechanical extraction, one shared home per cluster, no behaviour change to
any production path. New modules: `core/transits/_month_grid.py` (item 19),
`shell/http/form.py` (item 58), `shell/adapters/generation/validation.py` (item 24),
`shell/adapters/postgres/columns.py` (item 52's `_UTCDateTime`), `tests/_fk.py` (item 52/54),
`tests/_release_validation.py` (item 62). Items 13 and 51 stay in-file — a new private helper
in the module that already holds the duplication. Item 62 also adds one genuinely new thing
the retro asks for: a shared `assert_not_stale(...)` staleness assertion, wired into each
release-validation record's always-on guard tests.

## Boundaries & Constraints

**Always:**
- Behaviour-preserving. Every production code path computes and returns exactly what it does
  today. The full suite (`uv run pytest`) and `uv run ruff check .` pass at the end.
- Respect the import boundary (`tests/test_import_boundary.py`): `core/` never imports
  `shell/`; `core/transits/_month_grid.py` imports stdlib only (datetime, decimal, typing);
  no new module may be named `utils`, `helpers`, or `common`.
- Item 19: the four `core/transits` modules keep byte-identical *results*. Move the constant
  cluster and the three helpers to `_month_grid.py`; replace each module's local copies with
  an import; trim the now-stale "mirrored rather than imported" docstring paragraphs to point
  at the shared module. `_TRANSIT_BODY_IDS` stays in `aspects.py` (out of scope).
- Item 24: `shell/adapters/generation/validation.py` imports from `core.*` only — never
  `google`, never `shell.adapters.gemini`, never `sqlalchemy`/`sqlmodel`. Both
  `gemini/generator.py` and `local/generator.py` import the five moved symbols (plus the
  pattern's own deps `_ITALIAN_MONTHS` / `_ITALIAN_MONTH_ABBREVIATIONS` / `_DATE_TOKEN_PATTERN`)
  from it. `gemini/generator.py` keeps `_RESPONSE_SCHEMA`, `_MODEL`, the continuity/prompt
  builders, `_parse_response` / `_parse_sentences` / `_build_draft`.
- Item 24: update `tests/test_gate_run.py:28` (`_DATE_TOKEN_PATTERN` import path) and
  strengthen `tests/test_recorded_generator.py::test_never_imports_google_genai` to also
  assert `shell.adapters.local.generator` imports nothing from `shell.adapters.gemini` and
  that `shell/adapters/generation/validation.py` imports no `google` root.
- Item 51: the extracted helper serves `view_report` and `download_report_pdf` (verbatim
  Report-gated 404 + downstream `RuntimeError` guards + `render_draft`). `view_report` keeps
  its own passing-`StoredGateResult` lookup. `view_report_draft` and `view_report_payload`
  keep their distinct not-ready 404 semantics (draft-missing / payload-missing = not ready,
  not a data bug) — fold them in only for the shared "deserialize + `render_draft`" tail if
  it stays a clean read; a second small helper is acceptable; do not force one signature.
- Item 52/54: keep the FK-regression test
  `test_delete_client_and_derived_succeeds_with_a_report_run_referencing_a_natal_chart` (it
  may drop its bespoke listener once the shared fixture provides one). `_UTCDateTime` keeps
  its exact `TypeDecorator` behaviour; all 9 importers resolve after the move (update the
  imports, or re-export from `report_run.py`).
- Item 58: `shell/http/app.py::login_submit` stays untouched (inline, 401 semantics, own
  4096-byte ceiling — not a fourth `_parse_form`). The per-route `_MAX_*_FORM_BODY_BYTES`
  constant + its rationale comment stay in each route; `parse_form(request, *, max_bytes)`
  takes the ceiling as an argument.
- Item 62: each record test module keeps its own `RECORD_FILE` path and a thin `meta`
  fixture delegating to the shared loader. `assert_not_stale` is wired into each module's
  always-on guard block (not the opt-in measurement harnesses).

**Ask First:**
- Item 62 staleness bounds: the concrete `max_age_days` per record (data-terms, latency,
  storage-growth, restore-rehearsal). Proposed default 550 days for all four — generous
  enough not to flip CI red now, bounded enough to surface a year-plus-stale record. Confirm
  the numbers, or opt a record out, before wiring.
- Item 52/54: if enabling `PRAGMA foreign_keys=ON` in a module-wide `session` fixture breaks
  sibling non-cascade tests (rows inserted in FK-violating order), fall back to a dedicated
  `fk_session` fixture used only by the `delete_client_and_derived` tests — flag which was
  needed.

**Never:**
- No new behaviour on any production route, generator, or store beyond item 62's added test
  assertion.
- Do not deduplicate `core/gate/run.py::_DATE_TOKEN_PATTERN` into the shell validation module
  (`core/` cannot import `shell/`). Its cross-check test
  (`test_gate_run.py` — compares `.pattern` / `.flags`) keeps working unchanged.
- No signature or return-type changes to any public store/route/generator function.
- Do not touch `core/transits/aspects.py::_TRANSIT_BODY_IDS`, `_signed_offset`,
  `_normalize_signed`, or any root-finding target function — only the generic grid/bisection
  scaffolding is shared.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `parse_form` oversized body | `content-length` absent or > `max_bytes` | raises `FormTooLarge` before reading body | caller maps to 422, exactly as today per route |
| `parse_form` non-UTF-8 body | body bytes not decodable as UTF-8 | raises `FormNotUtf8` | caller maps to 422, exactly as today per route |
| `parse_form` valid body | well-formed urlencoded body ≤ `max_bytes` | `dict(parse_qsl(body))` | N/A |
| `_build_stored_chart` | `client_id`, `natal_chart`, `computation_config`, `ephemeris_identity` | `StoredNatalChart` with the same 8 fields both call sites build today (planets/houses/aspects serialized via `_serialize`) | N/A |
| shared `bisect` | `f` with `f(lo)`/`f(hi)` zero or opposite sign | identical result to each module's former local `_bisect` (40 halvings) | N/A |
| shared `require_utc_interval` | naive datetime, non-zero utcoffset, or `start >= end` | same `ValueError` messages as today | raises `ValueError` |
| `_load_passed_report_bundle` no `Report` row | `run_id` with no `Report` | `HTTPException(404)` | 404 (unchanged) |
| `_load_passed_report_bundle` `Report` present, downstream row missing | `Report` exists but `ReportDraft`/`ReportPayload`/`Client` absent | `RuntimeError` with the same message shape as today | raises `RuntimeError` |
| cascade test with FK on | `delete_client_and_derived` on a client with derived rows, `PRAGMA foreign_keys=ON` | deletion succeeds, no `IntegrityError`; wrong delete order would now fail | test fails loudly on ordering regression |
| `assert_not_stale` fresh record | `checked` within `max_age_days` of today | passes | N/A |
| `assert_not_stale` stale record | `checked` older than `max_age_days` | `AssertionError` naming the record and its age | raises `AssertionError` |

</frozen-after-approval>

## Code Map

### Item 13 — `_build_stored_chart` (in-file)
- `shell/adapters/postgres/client.py`
  - `create_client_with_chart()` L203–246 — `StoredNatalChart(...)` block L230–240
  - `correct_client_and_chart()` L249–303 — identical block as `new_chart` L282–292
  - `_serialize()` L144; `StoredNatalChart` model L96; `__all__` L34
  - Add module-private `_build_stored_chart(*, client_id, natal_chart, computation_config, ephemeris_identity) -> StoredNatalChart`; call from both sites. No test imports these internals (tests use `_create` helpers).

### Item 19 — `core/transits/_month_grid.py` (new, pure)
- Identical clusters (AST-normalized) to lift:
  - `core/transits/aspects.py` — `_GRID_STEP` L83, `_BISECTION_ITERATIONS` L89, `_ZERO_OFFSET` L91, `_require_utc_interval` L189, `_build_grid` L212, `_bisect` L260 (before `_events_for_pair`)
  - `core/transits/stations.py` — L55 / L59 / L61 / `_require_utc_interval` L171 / `_build_grid` L183 / `_bisect` L201
  - `core/transits/ingresses.py` — L61 / L66 / L68 / `_require_utc_interval` L198 / `_build_grid` L210 / `_bisect` L248
  - `core/transits/lunations.py` — L67 / L72 / L74 / `_require_utc_interval` L173 / `_build_grid` L185 / `_bisect` L229
- New module exports `GRID_STEP`, `BISECTION_ITERATIONS`, `require_utc_interval`, `build_grid`, `bisect` (names may keep leading underscore if preferred — no external contract). Each of the four modules: import from `_month_grid`, delete local copies, retire the "mirrored rather than imported" docstring paragraph (replace with a one-line "shared via `core/transits/_month_grid.py`").
- Tests reference `_build_grid` / `_require_utc_interval` only in **docstrings/comments** (`test_ingresses.py`, `test_lunations.py`, `test_stations.py`) — no import to update. `test_import_boundary.py` will scan the new file (pure — OK).

### Item 24 — `shell/adapters/generation/validation.py` (new package + module)
- `shell/adapters/gemini/generator.py` — move: `_SECTION_FIELD_NAMES` L42, `_DATE_TOKEN_SECTIONS` L48, `_ITALIAN_MONTHS` L50, `_ITALIAN_MONTH_ABBREVIATIONS` L69, `_DATE_TOKEN_PATTERN` L93, `_collect_known_entry_ids`, `_validate_citations`, `_validate_no_date_tokens` (bodies near EOF). Keep `_RESPONSE_SCHEMA` L115 (import `_SECTION_FIELD_NAMES` into it), `_SENTENCE_SCHEMA`, `_MODEL`, `_GoogleGenAIClient`, `GeminiGenerator`, continuity/prompt builders, `_parse_response`/`_parse_sentences`/`_build_draft`.
- `shell/adapters/local/generator.py` L25–31 — repoint the five-name import at `shell.adapters.generation.validation`.
- `shell/adapters/generation/__init__.py` — new, empty.
- `tests/test_gate_run.py:28` — repoint `_DATE_TOKEN_PATTERN` import at the new module (L772 `.pattern`/`.flags` assertion unchanged).
- `tests/test_recorded_generator.py::test_never_imports_google_genai` L216 — strengthen (see Boundaries).
- `tests/test_gemini_generator.py:24` imports only `_CONTINUITY_HEADER`, `_FIRST_REPORT_STATEMENT`, `_MODEL`, `_NOTHING_SIGNIFICANT_CHANGED_STATEMENT`, `_RESPONSE_SCHEMA`, `GeminiGenerator` — none moved, no change. L763 postgres/sqlalchemy import guard still holds.

### Item 51 — `_load_passed_report_bundle` (in-file)
- `shell/http/routes/report_runs.py`
  - `view_report_payload()` L198–222 — `ReportPayload`+`Client` only, `localize_payload` (NOT part of the render bundle)
  - `view_report_draft()` L225–298 — draft(404) / payload(`RuntimeError`) / client(`RuntimeError`) + `render_draft` L278–279; conditional `run` + failing-`StoredGateResult` L286–296
  - `view_report()` L301–386 — `Report`(404) / run / draft / payload / client / passing-`StoredGateResult` (all `RuntimeError`) + `render_draft` L370–371
  - `download_report_pdf()` L389–475 — `Report`(404) / run / draft / payload / client (all `RuntimeError`) + `render_draft` L449–450
  - Verbatim-duplicated block: L343–359 ≈ L431–447; render L370–371 ≈ L449–450
  - `_current_chart` L82, `_latest_export_record` L91, `render_draft` import L51
- Add `_load_passed_report_bundle(session, run_id) -> _PassedReportBundle` (NamedTuple/dataclass: `report`, `run`, `stored_draft`, `stored_payload`, `client`, `rendered`). Used by `view_report` + `download_report_pdf`.

### Item 52 + 54 — FK enforcement + `_UTCDateTime` shared module
- `shell/adapters/postgres/report_run.py` L32–53 — `_UTCDateTime(TypeDecorator)` → new `shell/adapters/postgres/columns.py`. Importers to update (or re-export from `report_run.py`): `backup_record.py:31`, `corpus_entry.py:42`, `export_record.py:40`, `gate_result.py:38`, `report.py:24`, `report_draft.py:32`, `report_payload.py:23`, `report_theme.py:28`, `style_guide.py:24`. `shell/restore.py:24` is a docstring mention only.
- `tests/_fk.py` — new. A `sqlite://` engine (or `create_all` + `Session`) with a `PRAGMA foreign_keys=ON` `"connect"` listener registered before first connect. Mirror the body at `test_client_store.py` L388–393.
- `tests/test_client_store.py` — `session` fixture L48–53 → use `tests/_fk.py`; FK-regression test L374–412 keeps its assertions, drops the inline listener.
- `tests/test_corpus_store.py` — `session` fixture L32–37 → use `tests/_fk.py`.
- Run full `pytest`; if FK-on breaks non-cascade siblings, use a dedicated `fk_session` fixture for the cascade tests only (Ask First).

### Item 62 — `tests/_release_validation.py` (new)
- Duplicated: `test_data_terms_record.py` (`REPO_ROOT` L21, `_TOML_BLOCK` L52, `_extract_toml_block` L61, `meta` fixture L77), `test_latency_record.py` (L37 / L72 / L75 / L95), `test_storage_growth_record.py` (L48 / L103 / L106 / L135), `test_restore.py` (L67 / L805 / L821 / L830).
- New module: `REPO_ROOT`, `TOML_BLOCK`, `extract_toml_block(text, *, record_label)`, `load_record_meta(record_file, *, record_label) -> dict`, and new `assert_not_stale(checked, *, max_age_days, record_label, today=None)`.
- Each test module: drop the locals, import from `tests._release_validation`, keep `RECORD_FILE` + a 2-line `meta` fixture, add a `test_record_is_not_stale(meta)` guard using a module `_MAX_RECORD_AGE_DAYS` constant.
- Baseline confirmed green today (`uv run pytest` on all four record files + both cascade files: pass, 2 skips).

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/client.py` — add `_build_stored_chart(...)`, call from `create_client_with_chart` and `correct_client_and_chart` (item 13).
- [x] `core/transits/_month_grid.py` — new pure module: `GRID_STEP`, `BISECTION_ITERATIONS`, `require_utc_interval`, `build_grid`, `bisect` (item 19).
- [x] `core/transits/aspects.py`, `stations.py`, `ingresses.py`, `lunations.py` — import from `_month_grid`, delete the local constant cluster + three helpers, trim the "mirrored rather than imported" docstrings (item 19).
- [x] `shell/adapters/generation/__init__.py` + `shell/adapters/generation/validation.py` — new; move the five validation symbols + `_ITALIAN_MONTHS` / `_ITALIAN_MONTH_ABBREVIATIONS` / `_DATE_TOKEN_PATTERN` out of `gemini/generator.py` (item 24).
- [x] `shell/adapters/gemini/generator.py` — import the moved symbols from `generation.validation`; keep `_RESPONSE_SCHEMA` et al (item 24).
- [x] `shell/adapters/local/generator.py` — repoint imports at `generation.validation` (item 24).
- [x] `tests/test_gate_run.py` — repoint `_DATE_TOKEN_PATTERN` import (item 24).
- [x] `tests/test_recorded_generator.py` — strengthen `test_never_imports_google_genai` (item 24).
- [x] `shell/http/form.py` — new: `FormTooLarge`, `FormNotUtf8`, `async parse_form(request, *, max_bytes)` (item 58).
- [x] `shell/http/routes/clients.py`, `style_guide.py`, `corpus.py` — delete the local trio, import from `shell.http.form`, pass the per-route `_MAX_*_FORM_BODY_BYTES` as `max_bytes`; update `except` clauses to the new exception names (item 58).
- [x] `shell/http/routes/report_runs.py` — add `_load_passed_report_bundle(session, run_id)` + `_PassedReportBundle`; use in `view_report` and `download_report_pdf`; reuse for the render tail of `view_report_draft` where clean (item 51).
- [x] `shell/adapters/postgres/columns.py` — new: `_UTCDateTime`; `report_run.py` imports/re-exports it; update the 9 sibling importers (item 52).
- [x] `tests/_fk.py` — new: sqlite engine/session with `PRAGMA foreign_keys=ON` connect listener (item 52/54).
- [x] `tests/test_client_store.py`, `tests/test_corpus_store.py` — point cascade-test fixtures at `tests/_fk.py`; drop the inline listener in the 6.4 regression test (item 52/54).
- [x] `tests/_release_validation.py` — new: `REPO_ROOT`, `TOML_BLOCK`, `extract_toml_block`, `load_record_meta`, `assert_not_stale` (item 62).
- [x] `tests/test_data_terms_record.py`, `test_latency_record.py`, `test_storage_growth_record.py`, `test_restore.py` — import the shared scaffolding, add `test_record_is_not_stale` with a `_MAX_RECORD_AGE_DAYS` constant (item 62).
- [x] `tests/test_month_grid.py` (or extend an existing transits test) — unit-test `bisect` / `build_grid` / `require_utc_interval` edge cases from the Matrix (item 19).
- [x] `tests/test_http_form.py` (or extend a route test) — unit-test `parse_form`'s oversized / non-UTF-8 / valid paths (item 58).

**Acceptance Criteria:**
- Given the full suite before this change is green, when all extractions land, then `uv run pytest` and `uv run ruff check .` are both green with no test deleted (only added/moved).
- Given `import shell.adapters.local.generator`, when Python resolves its imports, then no module under `shell/adapters/gemini/` and no `google` package is imported as a side effect (asserted by `test_never_imports_google_genai`).
- Given a `core/` purity scan (`tests/test_import_boundary.py`), when it parses `core/transits/_month_grid.py`, then it finds no `shell` import and no network/clock/filesystem/env access.
- Given every `delete_client_and_derived` test in `test_client_store.py` and `test_corpus_store.py`, when it runs, then `PRAGMA foreign_keys=ON` is in force (a wrong delete order fails the test).
- Given each of the four release-validation records with its current `checked` date, when `test_record_is_not_stale` runs today, then it passes at the agreed `max_age_days`.
- Given `find_transit_aspects` / `find_stations` / `find_ingresses` / `find_lunations` on the conformance fixture set, when run after item 19, then every fixture result is byte-identical to before (`tests/test_conformance.py` unchanged and green).

## Design Notes

**Item 19 — the "mirrored rather than imported" note is what the retro overrides.** Each
module's docstring argues the mirroring was deliberate because the four bisection *target
functions* differ. True — but the extracted pieces (`bisect` taking `f: Callable`,
`build_grid`, `require_utc_interval`, the two constants) are generic and provably identical.
Only the scaffolding is shared; every module keeps its own `offset_at` / `speed_fn` /
target logic.

**Item 24 — the boundary is transitive-import, not a name lookup.** Today's
`test_never_imports_google_genai` only checks `"genai" not in vars(local.generator)`, which
passes by luck (the module imports names, not `genai`). The real leak is that
`from shell.adapters.gemini.generator import ...` *executes* that module, which does
`from google import genai` at top level. The new provider-neutral module cuts the chain;
the strengthened test asserts the chain is cut.

**Item 51 — do not over-fuse.** `view_report` / `download_report_pdf` share ~25 lines
verbatim and gate on a `Report` row (404). `view_report_draft` gates on a `ReportDraft` row
and serves *failed* runs — a different not-ready contract. `view_report_payload` shares only
the `Client` lookup. Forcing all four through one signature risks a subtle 404-vs-500
regression; the helper targets the two that are actually identical.

**Item 62 — `assert_not_stale` is the one new behaviour.** Signature sketch:

```python
def assert_not_stale(checked, *, max_age_days, record_label, today=None):
    today = today or datetime.date.today()
    age = (today - checked).days
    assert age <= max_age_days, (
        f"{record_label} record `checked` = {checked.isoformat()} is {age} days old "
        f"(> {max_age_days}) — re-run the measurement/verification and update the record"
    )
```

## Verification

**Commands:**
- `uv run ruff check .` -- expected: clean.
- `uv run pytest` -- expected: all pass, same skip/xfail counts as the pre-change baseline, zero deletions.
- `uv run pytest tests/test_conformance.py tests/test_transit_aspects.py tests/test_stations.py tests/test_ingresses.py tests/test_lunations.py` -- expected: green (item 19 behaviour-preservation).
- `uv run pytest tests/test_recorded_generator.py tests/test_gemini_generator.py tests/test_gate_run.py` -- expected: green (item 24).
- `uv run pytest tests/test_client_store.py tests/test_corpus_store.py` -- expected: green with FK enforcement on.
- `uv run pytest tests/test_http_clients.py tests/test_http_client_correction.py tests/test_http_style_guide.py tests/test_http_corpus.py tests/test_http_report_runs.py` -- expected: green (items 13, 51, 58).
- `uv run python -c "import shell.adapters.local.generator, sys; assert not any('gemini' in m or m == 'google' for m in sys.modules)"` -- expected: no error.

## Suggested Review Order

**Pattern — one shared home per duplicated cluster (start here)**

- New pure module; the 5 grid/bisection symbols the four `core/transits` scans copied verbatim, now defined once.
  [`_month_grid.py:41`](../../core/transits/_month_grid.py#L41)

- Representative consumer: a single clean import replaces ~67 deleted lines; `stations.py:41` / `ingresses.py:46` / `lunations.py:56` follow the same shape.
  [`aspects.py:57`](../../core/transits/aspects.py#L57)

**Generation validation boundary (item 24 — the one behaviour-relevant seam)**

- New provider-neutral module: `core.*`/stdlib only, no `google` import.
  [`validation.py:27`](../../shell/adapters/generation/validation.py#L27)

- The actual fix: local generator repoints here instead of reaching into the Gemini adapter (whose import pulls in the SDK).
  [`generator.py:25`](../../shell/adapters/local/generator.py#L25)

- Gemini adapter imports back only what it uses; −117 lines.
  [`generator.py:29`](../../shell/adapters/gemini/generator.py#L29)

- Boundary test strengthened: AST-asserts the local adapter reaches nothing under `shell.adapters.gemini`.
  [`test_recorded_generator.py:216`](../../tests/test_recorded_generator.py#L216)

**HTTP shell helpers (items 13, 51, 58)**

- `_load_passed_report_bundle` + `_PassedReportBundle`: the Report-gated 5-lookup + render block shared by `view_report` / `download_report_pdf`; `view_report_draft` reuses only the render tail.
  [`report_runs.py:132`](../../shell/http/routes/report_runs.py#L132)

- `parse_form(request, *, max_bytes)`: the hand-rolled urlencoded parser, ceiling passed in per route.
  [`form.py:35`](../../shell/http/form.py#L35)

- `_build_stored_chart`: the `StoredNatalChart` row both create and correct paths build identically.
  [`client.py:149`](../../shell/adapters/postgres/client.py#L149)

- Representative call-site update (style_guide / corpus identical): local trio deleted, import + `max_bytes=` arg.
  [`clients.py:60`](../../shell/http/routes/clients.py#L60)

**Postgres column type + FK enforcement (items 52, 54)**

- `_UTCDateTime` moved to its own module (9 importers, was sharing a file with an unrelated table).
  [`columns.py:20`](../../shell/adapters/postgres/columns.py#L20)

- Re-export dropped: `__all__ = ["ReportRun"]`, import kept only for `ReportRun`'s own columns.
  [`report_run.py:30`](../../shell/adapters/postgres/report_run.py#L30)

- Shared FK-enforcing engine/session; `PRAGMA foreign_keys=ON` on a connect listener.
  [`_fk.py:22`](../../tests/_fk.py#L22)

- Cascade-test `session` fixtures repoint here; the Story 6.4 regression test drops its inline listener (`test_corpus_store.py:34` mirrors this).
  [`test_client_store.py:49`](../../tests/test_client_store.py#L49)

**Release-validation test scaffolding (item 62)**

- New shared module: `REPO_ROOT`, toml-block extractor, `load_record_meta`, and the new `assert_record_not_stale` (type-guards `checked`, rejects future dates, UTC `today`).
  [`_release_validation.py:75`](../../tests/_release_validation.py#L75)

- Representative record module: locals deleted, `meta` thinned to a delegate, one-line staleness guard (latency / storage-growth / restore mirror this).
  [`test_data_terms_record.py:98`](../../tests/test_data_terms_record.py#L98)

**Peripherals — new unit tests**

- Grid/bisection edge cases incl. partial-remainder and sub-step intervals.
  [`test_month_grid.py:1`](../../tests/test_month_grid.py#L1)

- `parse_form` oversized / absent / non-integer content-length, non-UTF-8, valid.
  [`test_http_form.py:1`](../../tests/test_http_form.py#L1)

- `assert_not_stale` / `assert_record_not_stale` failure paths and `today` injection.
  [`test_release_validation.py:1`](../../tests/test_release_validation.py#L1)
