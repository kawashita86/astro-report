---
title: 'Bucket G dev-loop follow-ups (sprint-change-proposal 2026-08-28, Section 5)'
type: 'chore'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context:
  - '_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-28.md'
  - '_bmad-output/implementation-artifacts/spec-6-2b-markdown-export.md'
  - '_bmad-output/implementation-artifacts/sprint-status.yaml'
baseline_commit: '05540936936c0bd4ea5e7e82d455d55225d492ce'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `sprint-change-proposal-2026-08-28.md` Section 5 routes eight retrospective
bucket-G items to the dev loop, each with a recorded decision but no code yet: a stale
`Rulers` docstring (17), no stale-config warning on the chart wheel (11), no link from a
client create/correct to its chart (14), no Markdown export route (47, spec'd in
`spec-6-2b`), no shared `snake_case → Italian-title` heading map for the report templates
(50), an undocumented GET-with-side-effects deviation on the PDF route (49), and a
release-validation `outcome=="pass"` guard that passes on partial evidence (65). Item 45
(persist `GateVocabulary.content_hash` on `StoredGateResult`) is explicitly opportunistic
and is **not** in scope here — no task below touches `StoredGateResult` or the Gate write
path, so it stays `open` in the tracker with its recorded decision.

**Approach:** Implement items 50 → 47 → 17 → 11 → 14 → 49 → 65 in that order (50 before 47:
47's Markdown headings consume 50's title map). Each is a small, self-contained change
against an already-ratified decision; none is architectural. Close the tracker: flip
items 11/14/17/47/49/65 and `spec-6-2b` to `done`, leave 45 `open`.

## Boundaries & Constraints

**Always:**
- Item 50's `snake_case → Italian-title` map is the single source of truth for section
  headings across `report.html`, `report_draft.html`, `report_export.html`, and item 47's
  Markdown. It lives beside `SECTION_ORDER` in `shell/http/draft_view.py` as an explicit
  dict (`SECTION_TITLES`), not a generated title-case transform (Italian casing:
  "Giorni di attenzione", not "Giorni Di Attenzione"). It must have exactly one entry per
  `SECTION_ORDER` name; a missing key is a `KeyError` at render time, and a unit test
  binds the two together so a future `GeneratedDraft` field cannot silently ship without
  an Italian heading.
- Item 47 follows `spec-6-2b-markdown-export.md` verbatim — the same
  `_load_passed_report_bundle` gate, the same eight-Sections-plus-Client-name content
  model, first-export-advances-`run.stage`-once / every-export-writes-one-`ExportRecord`
  (`format="markdown"`), no schema change, no migration. New symbols must not start with
  `export` and must not take a `GeneratedDraft` parameter
  (`tests/test_export_boundary.py`): use `download_report_markdown` (handler) and
  `render_report_markdown` (serializer).
- Item 11 warns, never refuses: on
  `stored_chart.computation_config_content_hash != request.app.state.computation_config.content_hash`
  the wheel still renders 200 with a non-blocking banner. The equal-hash path renders
  byte-identically to today (no banner element).
- Item 14 keeps both success responses at HTTP 200 with the existing confirmation text
  ("Client {id} created." / "corrected.") and adds an `<a href="/clients/{id}/chart">`
  link — `tests/test_http_clients.py` and `tests/test_http_client_correction.py` assert
  `status_code == 200` and the word "created"/"corrected" in the body. No redirect.
- Items 17 and 49 are documentation-only: no behavior, no signature, no test-observable
  change beyond the docstring text itself.
- Item 65: add a shared `assert_outcome_permits_release(meta, *, evidence_field,
  evidence_value, record_label)` helper in `tests/_release_validation.py`; it fails when
  `outcome == "pass"` while `meta.get(evidence_field) != evidence_value`, naming the
  pending step. Wire it into `test_latency_record.py::test_outcome_permits_release`
  (`evidence_field="sitting_confirmed"`, `evidence_value=True`) and
  `test_restore.py::test_outcome_permits_release`
  (`evidence_field="rehearsed_against"`, `evidence_value="real-postgres"`). Add the new
  key to each module's `_EXPECTED_KEYS`. In the two record files set the honest values
  (`sitting_confirmed = false`; `rehearsed_against = "in-process-sqlite"`) and
  `outcome = "blocked"`. Mark both `test_outcome_permits_release` bodies
  `@pytest.mark.xfail(strict=True, reason=...)` pointing at the pending operator step —
  the project's `xfail_strict = true` then turns the eventual real pass into an XPASS
  signal to remove the marker. `test_data_terms_record.py` and
  `test_storage_growth_record.py` are untouched.

**Ask First:**
- If implementing item 47 reveals the Markdown handler and `download_report_pdf` are
  >80% identical, `spec-6-2b` Design Notes call for extracting a shared
  `_finalize_export(...)` helper rather than a third copy of the `ExportRecord` + `stage`
  block. Flag it in review; do not extract pre-emptively.
- If item 65's honest record edits would make any guard test *other than* the two named
  `test_outcome_permits_release` go red, stop and report — only those two are expected to
  become xfail.

**Never:**
- No `core/` changes except item 17's `core/types/computation.py` docstring.
- No hashability added to `ComputationConfig` / `Rulers` (item 6 decision).
- No migration. No `ExportRecord` / `StoredGateResult` schema change. Item 45 is not
  implemented here.
- No change to `download_report_pdf`'s behavior (item 49 is its docstring only).
- No new domain error type for item 11; no refusal path.
- Item 65: do not add a generic `external_evidence` field — bespoke named fields per
  record, as ratified.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chart wheel, config unchanged | `stored_chart` hash == `app.state` hash | 200, wheel SVG, no warning banner element (byte-identical to pre-change) | N/A |
| Chart wheel, config drifted | `stored_chart` hash != `app.state` hash | 200, wheel SVG **plus** a non-blocking warning banner naming the stale-config condition | N/A |
| Client created | valid `POST /clients` | 200, body contains "created." **and** an anchor to `/clients/{id}/chart` | existing 422 paths unchanged |
| Client corrected (confirmed) | `POST /clients/{id}/edit` with `confirmed=1` | 200, body contains "corrected." **and** an anchor to `/clients/{id}/chart` | existing 422 / warning-gate paths unchanged |
| Markdown export, passed Report | `run_id` with a `Report` row | 200, `text/markdown; charset=utf-8`, `attachment; filename="report-{run_id}.md"`; body = the eight Italian-titled Sections + Client name; `ExportRecord(format="markdown")` written; `run.stage` → `exported` if not already | N/A |
| Markdown export, no/again | unknown `run_id` / non-passed run | 404 (same gate as `download_report_pdf`) | — |
| Markdown export repeat | 2nd+ call, same `run_id` | 200; new `ExportRecord`; `run.stage` stays `exported` | — |
| Section heading lookup | any `SECTION_ORDER` name | `SECTION_TITLES[name]` returns its Italian title | missing key → `KeyError` (impossible-state; unit test forbids it) |
| Release guard, pass + evidence present | `outcome="pass"`, evidence field == required value | `assert_outcome_permits_release` passes | — |
| Release guard, pass + evidence absent/wrong | `outcome="pass"`, evidence field missing or != required value | assertion fails, message names the pending step | — |
| Release guard, current records | `outcome="blocked"`, honest evidence values | `test_outcome_permits_release` fails → recorded as `xfail(strict)` | — |

</frozen-after-approval>

## Code Map

- `core/types/computation.py:60-68` — `Rulers` docstring (item 17). Rewrite: state the type
  is deliberately **not** hashable (`MappingProxyType` fields make `hash()` raise
  `TypeError` despite `frozen=True`) and point readers at `ComputationConfig.content_hash`
  as the identity/cache key. No code change.
- `shell/http/draft_view.py:26-58` — add `SECTION_TITLES: dict[str, str]` beside
  `SECTION_ORDER` / `LIST_SECTION_NAMES` and to `__all__` (item 50). Keys: `energia_generale`
  "Energia generale", `amore` "Amore", `lavoro` "Lavoro", `denaro` "Denaro", `benessere`
  "Benessere", `giorni_favorevoli` "Giorni favorevoli", `giorni_di_attenzione`
  "Giorni di attenzione", `consiglio_finale` "Consiglio finale" — i.e. `GeneratedDraft`'s
  dataclass field order (`core/types/generation.py:43-50`), which is what `SECTION_ORDER`
  introspects.
- `shell/http/routes/chart.py:44-69` — `chart_wheel_view` (item 11): compare
  `stored_chart.computation_config_content_hash` with
  `request.app.state.computation_config.content_hash`, pass a `config_stale: bool` into the
  `chart_wheel.html` context.
- `shell/http/templates/chart_wheel.html:11-13` — add a `{% if config_stale %}` non-blocking
  banner above/below the `{{ svg | safe }}` block (item 11).
- `shell/http/routes/clients.py:323` and `:510` — `create_client` / `correct_client` success
  `Response` (item 14): change body from plain text to a minimal HTML fragment keeping the
  "created."/"corrected." wording plus `<a href="/clients/{id}/chart">View chart</a>`; set
  `media_type="text/html"`.
- `shell/http/routes/report_runs.py:435-494` — `download_report_pdf` (item 49): add a
  docstring paragraph recording the accepted GET-with-side-effects deviation (writes an
  `ExportRecord`, advances `run.stage`, commits on every GET), same rationale ratified for
  `GET /backup` (plain-link download; POST declined); to be folded into `docs/decisions/`
  once retro item 66 lands. No code change.
- `shell/http/routes/report_runs.py` — new `download_report_markdown` handler (item 47),
  sibling of `download_report_pdf`;
  `@router.get("/report-runs/{run_id}/export/markdown", include_in_schema=False)`. Also
  thread `section_titles=SECTION_TITLES` into the `view_report` (`:419`),
  `view_report_draft` (`:352`), and `report_export.html` render (`:471`) contexts (item 50).
- `shell/http/report_markdown.py` *(new)* — `render_report_markdown(rendered, *,
  client_name, section_order, list_section_names, section_titles) -> str`. Pure string
  assembly, no I/O. List sections → one `-` bullet per day entry, date-prefixed.
- `shell/http/templates/report.html:40`, `report_draft.html:34`, `report_export.html:13` —
  `<h2>{{ section_name }}</h2>` → `<h2>{{ section_titles[section_name] }}</h2>` (item 50).
- `shell/http/templates/report_export.html` — add minimal print CSS in `<head>` (item 50);
  add nothing else.
- `shell/http/templates/report.html:17` — add a "Download Markdown" link next to the
  existing "Export PDF" link (item 47).
- `tests/_release_validation.py:75-86` — add `assert_outcome_permits_release(...)` beside
  `assert_record_not_stale` (item 65).
- `tests/test_latency_record.py:57-72,164-168` — `_EXPECTED_KEYS += {"sitting_confirmed"}`;
  rewrite `test_outcome_permits_release` to call the helper; add `@pytest.mark.xfail`.
- `tests/test_restore.py:805-817,938-941` — `_EXPECTED_KEYS += {"rehearsed_against"}`;
  same rewrite + `xfail`.
- `docs/release-validation/latency.md:14-28` — add `sitting_confirmed = false`, set
  `outcome = "blocked"`; note the pending sitting in prose (item 65).
- `docs/release-validation/restore-rehearsal.md:31-42` — add
  `rehearsed_against = "in-process-sqlite"`, set `outcome = "blocked"`; the guard prose
  block already mentions `outcome`; extend it for `rehearsed_against` (item 65).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — items 11/14/17/47/49/65 →
  `done`; item 45 stays `open`.
- `_bmad-output/implementation-artifacts/spec-6-2b-markdown-export.md` — `status: done`
  once item 47 lands.
- **Read-only reference** (do not edit): `tests/test_export_boundary.py` (the
  `export`-prefix / `GeneratedDraft`-param static scan — must stay green),
  `tests/test_http_report_runs.py:1388-1520` (the PDF route tests item 47 mirrors),
  `tests/test_http_chart_wheel.py`, `shell/adapters/postgres/export_record.py:98`
  (`store_export_record` signature), `shell/adapters/postgres/client.py:96-124`
  (`StoredNatalChart.computation_config_content_hash`).

## Tasks & Acceptance

**Execution (in order):**
- [x] `shell/http/draft_view.py` — add `SECTION_TITLES` dict + `__all__` entry (item 50).
- [x] `shell/http/routes/report_runs.py` — pass `section_titles=SECTION_TITLES` into the
  `view_report`, `view_report_draft`, and `report_export.html` render contexts (item 50).
- [x] `shell/http/templates/report.html`, `report_draft.html`, `report_export.html` —
  headings use `section_titles[section_name]`; add print CSS to `report_export.html`
  `<head>` (item 50).
- [x] `shell/http/report_markdown.py` *(new)* — `render_report_markdown(...)` (item 47).
- [x] `shell/http/routes/report_runs.py` — `download_report_markdown` handler with the
  `_load_passed_report_bundle` gate, `ExportRecord(format="markdown")` write, one-time
  `stage` advance (item 47).
- [x] `shell/http/templates/report.html` — "Download Markdown" link by the PDF link (47).
- [x] `core/types/computation.py` — rewrite the `Rulers` docstring (item 17).
- [x] `shell/http/routes/chart.py` — hash compare → `config_stale` in context (item 11).
- [x] `shell/http/templates/chart_wheel.html` — non-blocking warning banner (item 11).
- [x] `shell/http/routes/clients.py` — `create_client` / `correct_client` success bodies →
  HTML with a `/clients/{id}/chart` link, still 200, still say "created"/"corrected" (14).
- [x] `shell/http/routes/report_runs.py` — `download_report_pdf` docstring: accepted
  GET-with-side-effects deviation note (item 49).
- [x] `tests/_release_validation.py` — `assert_outcome_permits_release(...)` helper (65).
- [x] `tests/test_latency_record.py`, `tests/test_restore.py` — `_EXPECTED_KEYS`, helper
  call, `xfail(strict)` on `test_outcome_permits_release` (item 65).
- [x] `docs/release-validation/latency.md`, `restore-rehearsal.md` — new evidence field,
  `outcome = "blocked"`, prose (item 65).
- [x] `tests/test_http_report_runs.py` (or `tests/test_http_export_markdown.py` new,
  mirroring `spec-6-2b`) — Markdown route cases: gate 404s, content model, first-vs-repeat
  `ExportRecord`, `stage` advance (item 47).
- [x] `tests/test_draft_view.py` (or nearest) — `SECTION_TITLES` has exactly one entry per
  `SECTION_ORDER` name (item 50).
- [x] `tests/test_http_chart_wheel.py` — banner present on hash mismatch, absent on match
  (item 11).
- [x] `tests/test_http_clients.py` / `tests/test_http_client_correction.py` — success body
  carries the chart link, status still 200 (item 14).
- [x] `render_report_markdown` unit test — eight Italian-titled Sections + Client name,
  list sections as bullets, built from a `render_draft` output not a hand fixture (47).
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` +
  `spec-6-2b-markdown-export.md` — status updates.

**Acceptance Criteria:**
- Given a stored chart whose `computation_config_content_hash` differs from the running
  config, when `GET /clients/{id}/chart` is requested, then the response is 200 and
  contains a warning banner; when the hashes match, the response has no banner.
- Given a successful client create or confirmed correction, when the success page renders,
  then it is HTTP 200, still names the outcome ("created"/"corrected"), and links to
  `GET /clients/{id}/chart`.
- Given a Gate-passed Report, when `GET /report-runs/{run_id}/export/markdown` is
  requested, then a `.md` attachment downloads containing exactly the eight Italian-titled
  Sections and the Client's name; a second request writes a second
  `ExportRecord(format="markdown")` without re-advancing `run.stage`; a non-passed run
  404s.
- Given the report templates, when any of `report.html` / `report_draft.html` /
  `report_export.html` renders, then section headings show Italian titles from the shared
  `SECTION_TITLES` map, and `report_export.html` carries print CSS.
- Given `tests/test_export_boundary.py`, when the suite runs, then it still passes
  unchanged (no new `export`-prefixed symbol, no `export`-named `GeneratedDraft` consumer).
- Given `docs/release-validation/latency.md` or `restore-rehearsal.md` with `outcome =
  "pass"` but its bespoke evidence field missing or wrong, when the guard suite runs, then
  `test_outcome_permits_release` fails naming the pending step; given the records' current
  honest state (`outcome = "blocked"`), that test is a strict `xfail`.
- Given the `Rulers` docstring, when read, then it states the type is not hashable and
  names `content_hash`; given `download_report_pdf`'s docstring, when read, then it records
  the accepted GET-with-side-effects deviation.
- Item 45 is untouched; `sprint-status.yaml` still lists it `open` with its decision.

## Spec Change Log

## Design Notes

- **Ordering matters only for 50 → 47.** 47's `render_report_markdown` takes
  `section_titles` and its headings must match the HTML routes'. Every other item is
  independent; the given order just groups the presentational work first.
- **Item 14 — why a link, not a redirect.** The two success tests assert `status_code ==
  200` and a word in the body. A `303` to `/clients/{id}/chart` would be followed by
  `TestClient` and land on the SVG page, dropping "created"/"corrected" and changing the
  effective response. An inline anchor keeps both invariants and is the literal reading of
  the decision ("trivial UX link").
- **Item 65 — why xfail(strict).** The hardened guard correctly rejects today's
  `outcome = "pass"` on both records because the real operator steps (a `python -m
  shell.restore` dry-run against a real Neon branch; Francesco's 40-report one-sitting)
  have not happened — that is the retro's finding. `xfail(strict=True)` records this as a
  known-not-yet-satisfiable release gate; when the real step is done and the evidence
  field flips, the test passes → `xfail_strict` fires an XPASS → the marker is removed.
  This mirrors the conformance-fixture xfail pattern in `pyproject.toml`.
- **Item 50 — explicit map, not `.replace('_',' ').title()`.** Italian title casing keeps
  prepositions/articles lowercase ("Giorni di attenzione"); a generic transform gets it
  wrong. The dict is eight lines and future-proofed by the `SECTION_ORDER`-parity test.

## Verification

**Commands:**
- `.venv/bin/python -m pytest -q` — expected: full suite green; the two
  `test_outcome_permits_release` report as `xfail` (not `fail`, not `xpass`).
  (Note: `uv run pytest` is intercepted in this environment and collects nothing — use
  the venv interpreter directly.)
- `.venv/bin/python -m pytest tests/test_export_boundary.py -q` — expected: all pass
  (static export-shape invariant intact).
- `.venv/bin/python -m pytest tests/test_http_report_runs.py tests/test_http_chart_wheel.py tests/test_http_clients.py tests/test_http_client_correction.py -q`
  — expected: all pass, including the new Markdown-route and chart-banner cases.
- `.venv/bin/ruff check .` — expected: clean.

**Manual checks:**
- `GET /report-runs/{run_id}/export/markdown` for a passed run downloads a `.md` file
  whose headings read "Energia generale", "Amore", … "Consiglio finale".
- `docs/release-validation/latency.md` and `restore-rehearsal.md` `outcome` is `blocked`
  and each carries its new evidence field.

## Suggested Review Order

**Shared heading map (item 50) — the piece everything else consumes**

- The single source of truth: explicit Italian dict, one entry per `SECTION_ORDER` name.
  [`draft_view.py:72`](../../shell/http/draft_view.py#L72)
- Threaded into all three view contexts + the PDF render; the new key is `section_titles`.
  [`report_runs.py:473`](../../shell/http/routes/report_runs.py#L473)
- Templates now render `section_titles[section_name]`; print CSS lives only in the export template.
  [`report_export.html:7`](../../shell/http/templates/report_export.html#L7)

**Markdown export (item 47)**

- New route: same `_load_passed_report_bundle` gate, same stage-advance / `ExportRecord` semantics as PDF, only body + `format` differ.
  [`report_runs.py:516`](../../shell/http/routes/report_runs.py#L516)
- Pure string assembly, no I/O; named `render_report_markdown` (not `export_*`) to keep the boundary scan green.
  [`report_markdown.py:25`](../../shell/http/report_markdown.py#L25)

**Stale-config warning (item 11)**

- Whole-file `content_hash` compare → `config_stale`; warn, never refuse; equal-hash path byte-identical.
  [`chart.py:69`](../../shell/http/routes/chart.py#L69)
- Non-blocking banner, `{%- ` whitespace control so the no-drift render is unchanged.
  [`chart_wheel.html:12`](../../shell/http/templates/chart_wheel.html#L12)

**Client → chart link (item 14)**

- Success body becomes a minimal HTML fragment: keeps "created."/"corrected.", adds an inline anchor, stays 200 (no redirect).
  [`clients.py:331`](../../shell/http/routes/clients.py#L331)

**Docstring-only (items 17, 49)**

- `Rulers` is deliberately non-hashable; point readers at `content_hash`.
  [`computation.py:67`](../../core/types/computation.py#L67)
- `download_report_pdf` records the accepted GET-with-side-effects deviation (applies to the Markdown route too).
  [`report_runs.py:473`](../../shell/http/routes/report_runs.py#L473)

**Release-gate hardening (item 65)**

- New helper: `outcome == "pass"` requires a bespoke per-record evidence field, else it fails naming the pending step.
  [`_release_validation.py:89`](../../tests/_release_validation.py#L89)
- The two records now honestly say `outcome = "blocked"` + carry the evidence field; the two `test_outcome_permits_release` are `xfail(strict)`.
  [`latency.md:30`](../../docs/release-validation/latency.md#L30)
  [`restore-rehearsal.md:31`](../../docs/release-validation/restore-rehearsal.md#L31)
