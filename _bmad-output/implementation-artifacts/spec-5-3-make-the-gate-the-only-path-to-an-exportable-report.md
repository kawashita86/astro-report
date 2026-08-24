---
title: 'Story 5.3 — Make the Gate the only path to an exportable Report'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'bef525ca7613553e4532c2908677aed64cce10fd'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `run_gate()` (Story 5.2) exists but is wired nowhere: `ReportRun` only advances through
`natal_ready → transits_ready → payload_ready → draft_ready` (`shell/runner/driver.py`), no `REPORT`
table exists, and no export function exists anywhere -- so today nothing stops a draft from being
treated as exportable without ever passing the Gate.

**Approach:** Register `gate_passed` as `driver.py`'s fifth stage: it re-derives the persisted
`GeneratedDraft` and `Payload`, runs `run_gate()` against the app's already-loaded `GateVocabulary`,
and on a pass persists a new immutable `REPORT` row (never on failure). Add the single
`export_report()` function -- it reads a `REPORT` row by ID or refuses; no other function anywhere
accepts a draft and produces an exportable artifact, enforced by a new static test.

## Boundaries & Constraints

**Always:**
- `gate_passed`'s stage function reads back `ReportDraft`/`ReportPayload` for `run` (never
  recomputed), mirroring every other stage function's own read-back pattern.
- `GateVocabulary` loads once at import time in `shell/http/app.py` via `load_gate_vocabulary()`
  (mirrors `sections_config`/`ephemeris_identity`), stashed on `app.state.gate_vocabulary`, threaded
  into `drive()`/`StageFn` as a new uniform parameter (mirrors how `generator` joined in Story 4.6).
- On `GateResult.passed`, a `Report` row is persisted (immutable once written, like `ReportDraft`),
  recording `client_id`, `report_run_id` (unique), `style_guide_version` (from the stored
  `ReportDraft`), `payload_schema_version` (from the stored `ReportPayload`), and
  `gate_vocabulary_version` (`GateResult.vocabulary_version`) -- never before a pass.
- `Report` joins the FR-29 Client-deletion cascade (`shell/adapters/postgres/client.py`), deleted
  before `ReportRun` rows (it FKs to `report_run.id`, same ordering as `ReportDraft`/`ReportPayload`).
- On `GateResult.passed is False`, the stage function raises a new `GateFailedError` (core/errors.py,
  mirrors `GenerationError`) so `drive()`'s existing stage-failure/backoff bookkeeping handles it
  uniformly -- `run.stage` stays at `draft_ready`. (Bounded, controlled regeneration is Story 5.4; this
  story only makes a failure visible as a stage failure, not silent.)
- `export_report(session, report_id)` is the only function anywhere that reads a `Report` row to
  produce an exportable result; it raises if no `Report` row exists for `report_id` -- which is also
  how "Gate not passed" refuses export, since a `Report` row exists only on a pass. Actual PDF/Markdown
  rendering is Story 6.2's job; this function is the structural gate, not the renderer.
- New Alembic migration `0011_report.py` (forward-only, mirrors `0009_report_draft.py`).

**Ask First:** None.

**Never:**
- No regeneration logic, no `GATE_RESULT` audit table, no persisted violations list -- Stories 5.4/5.6.
- No HTTP route for export or for viewing a `Report` -- Epic 6.
- `export_report()` does not render PDF/Markdown; it only enforces the single-path invariant.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Gate passes | `draft_ready` run, clean draft | `run.stage == "gate_passed"`, one `Report` row persisted | N/A |
| Gate fails | `draft_ready` run, a violation present | `run.stage` stays `draft_ready`, `stage_failure_count` increments | `GateFailedError` raised, caught by `drive()` |
| Export a passed Report | Valid `report_id` | `export_report()` returns the `Report` row | N/A |
| Export with no Report row | Unknown or never-passed `report_id` | Refused | Raises, naming the reason |
| Client deletion | Client with a `Report` row | `Report` row deleted before its `ReportRun` | N/A |
| Codebase scan | Whole `shell/`/`core/` tree | Exactly one export-shaped function found | Test fails naming the second one |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py` -- add `vocabulary: GateVocabulary` to `StageFn`; new `_run_gate_passed`;
  new `_deserialize_generated_draft` (mirrors `_deserialize_theme:384`); register in `_STAGE_FUNCTIONS`
  and `_STAGE_SEQUENCE` (already lists `"gate_passed"` at line 99).
- `shell/adapters/postgres/report.py` (new) -- `Report` model + `store_report()`, mirror
  `shell/adapters/postgres/report_draft.py` exactly (immutable `before_update` listener included).
- `shell/adapters/postgres/client.py:46-49,266-321` -- add `Report` import, `"report"` to
  `_CLIENT_CASCADE_TABLES`, delete `Report` rows before the `ReportRun` block.
- `shell/http/app.py:35-58,196-207` -- import `load_gate_vocabulary`/`GateVocabulary`; module-level
  `gate_vocabulary = load_gate_vocabulary()`; `application.state.gate_vocabulary = gate_vocabulary`.
- `shell/http/routes/report_runs.py:_drive_run` -- pass `vocabulary=request.app.state.gate_vocabulary`.
- `shell/export.py` (new) -- `export_report(session, report_id) -> Report`.
- `core/errors.py:120` -- new `GateFailedError(RuntimeError)`, mirrors `GenerationError`.
- `migrations/versions/0011_report.py` (new) -- mirror `0009_report_draft.py`; `down_revision =
  "0010_report_run_failure"`.
- `tests/test_import_boundary.py:328-357` -- AST-visitor pattern to mirror for the export-invariant test.
- `core/gate/run.py:421`, `core/types/gate.py:73` -- `run_gate()`/`GateResult` signature this consumes.

## Tasks & Acceptance

**Execution:**
- [x] `core/errors.py` -- add `GateFailedError`.
- [x] `shell/adapters/postgres/report.py` (new) -- `Report` table + `store_report()`.
- [x] `migrations/versions/0011_report.py` (new) -- create `report` table.
- [x] `shell/adapters/postgres/client.py` -- join `Report` to the deletion cascade.
- [x] `shell/http/app.py` -- load `gate_vocabulary`, attach to `app.state`.
- [x] `shell/runner/driver.py` -- `_run_gate_passed`, `_deserialize_generated_draft`, registry updates.
- [x] `shell/http/routes/report_runs.py` -- thread `vocabulary` through `_drive_run`.
- [x] `shell/export.py` (new) -- `export_report()`.
- [x] `tests/test_report_store.py` (new) -- mirror `tests/test_report_draft_store.py`.
- [x] `tests/test_runner_driver.py` -- gate-pass and gate-fail stage tests (I/O matrix rows 1-2).
- [x] `tests/test_export_boundary.py` (new) -- I/O matrix rows 3-6, plus the static single-export-path test.
- [x] `tests/test_client_store.py` -- extend the existing cascade-invariant test coverage to `Report`.

**Acceptance Criteria:**
- Given a run at `draft_ready`, when it advances, then the Gate runs before any exportable state, and
  the run reaches `gate_passed` only on a passing `GateResult`.
- Given a passing `GateResult`, when the run advances, then the `Report` row is written, recording the
  Style Guide, Payload schema and Gate vocabulary versions, and joins the Client deletion cascade.
- Given a `Report` that does not exist (no pass yet), when export is attempted, then it is refused.
- Given the codebase, when export functions are counted, then exactly one exists, taking a stored
  Report ID, and no function accepting a draft produces an exportable artifact.

## Design Notes

`_deserialize_generated_draft` is the mirror of `_deserialize_theme` (driver.py:384): `ReportDraft.draft`
is a dict of 8 keys, each a list of `{"text", "entry_ids"}` -- rebuild each as
`tuple(Sentence(text=s["text"], entry_ids=tuple(s["entry_ids"])) for s in ...)`, then
`GeneratedDraft(**fields)`.

`export_report()`'s static-invariant test scans `shell/` and `core/` (excluding `tests/`) for: (a) every
function named with an `export` prefix -- asserting exactly one, `export_report` in `shell/export.py`;
(b) every function with a parameter annotated `GeneratedDraft` -- asserting none of them also has
`export` in its name. Both checks are name/annotation-based AST scans, mirroring
`test_core_never_imports_shell`'s `ast.parse` + visitor shape (`tests/test_import_boundary.py:328`).

## Verification

**Commands:**
- `uv run pytest tests/test_report_store.py tests/test_runner_driver.py tests/test_export_boundary.py tests/test_client_store.py tests/test_migration_chain.py -q` -- expected: all pass.
- `uv run alembic upgrade head` (against a local/test DB) -- expected: `0011_report` applies cleanly.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Gate wiring — the new `gate_passed` stage**

- Entry point: re-derives the persisted draft and Payload, runs the Gate, and only advances on a pass.
  [`driver.py:516`](../../shell/runner/driver.py#L516)

- On a failure, raises rather than silently stalling, so `drive()`'s existing backoff/terminal-failure bookkeeping applies uniformly.
  [`driver.py:556`](../../shell/runner/driver.py#L556)

- Round-trips `ReportDraft.draft`'s JSON back into a real `GeneratedDraft`, mirroring the theme deserializer already in this file.
  [`driver.py:437`](../../shell/runner/driver.py#L437)

- Registered as the fifth stage; `StageFn` gains `vocabulary` as a new uniform parameter across every stage function.
  [`driver.py:574`](../../shell/runner/driver.py#L574)

**The `Report` row — written only on a Gate pass**

- Immutable once persisted, mirroring `ReportDraft`'s own `before_update` guard.
  [`report.py:60`](../../shell/adapters/postgres/report.py#L60)

- `store_report()` records the three producing versions; called only after `run_gate()` passes.
  [`report.py:72`](../../shell/adapters/postgres/report.py#L72)

- New table's DDL: unique index on `report_run_id` enforces "exactly one Report per ReportRun" at the schema layer.
  [`0011_report.py:33`](../../migrations/versions/0011_report.py#L33)

**The single export path — structurally enforced, not by convention**

- `export_report()` refuses whenever no `Report` row exists — which is also how "Gate not passed" refuses.
  [`export.py:30`](../../shell/export.py#L30)

- The AST visitor backing the invariant: finds every `export`-prefixed function and every `GeneratedDraft`-accepting one.
  [`test_export_boundary.py:176`](../../tests/test_export_boundary.py#L176)

- Asserts exactly one export-shaped function exists in `shell/`+`core/`, named and located correctly.
  [`test_export_boundary.py:208`](../../tests/test_export_boundary.py#L208)

**Typed failures**

- `GateFailedError` carries the failing violations through for a future story (5.5) to surface.
  [`errors.py:146`](../../core/errors.py#L146)

- `ReportNotFoundError` replaces a bare `LookupError`, matching how every other domain failure here is typed (review finding, patched).
  [`errors.py:171`](../../core/errors.py#L171)

**Peripherals**

- `Report` joins the FR-29 Client-deletion cascade, deleted before its owning `ReportRun`.
  [`client.py:320`](../../shell/adapters/postgres/client.py#L320)

- `GateVocabulary` loads once at import time, mirroring `sections_config`/`ephemeris_identity`.
  [`app.py:215`](../../shell/http/app.py#L215)

- Terminal-failure parity test for `gate_passed`, mirroring Story 4.8's `draft_ready` coverage (review finding, patched).
  [`test_runner_driver.py:1022`](../../tests/test_runner_driver.py#L1022)
