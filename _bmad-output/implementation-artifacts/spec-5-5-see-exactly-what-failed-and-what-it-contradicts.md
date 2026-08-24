---
title: 'Story 5.5 — See exactly what failed and what it contradicts'
type: 'feature'
created: '2026-08-24'
status: 'done'
review_loop_iteration: 0
baseline_commit: '5e333ef7b3386f12e65b81a41c5941003b872a4f'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When a Report exhausts its regeneration bound (Story 5.4), `run.failed_at`/
`failure_reason` are set and the last `ReportDraft` stays reachable, but the Gate's own violations —
computed once inside `GateFailedError` when `drive()` caught it — are never persisted or shown;
Francesco has no way to see which Claims failed or what they contradict, only a one-line summary in
the poll fragment.

**Approach:** `run_gate()` is pure and deterministic (Story 5.2, AD-1), so recompute it on demand in
`view_report_draft` from the run's already-persisted latest `ReportDraft` + `ReportPayload` whenever
`run.failed_at` is set, and render each `GateViolation`'s section/sentence/detail alongside the draft
— no new persistence, no `GATE_RESULT` table (that belongs to Story 5.6).

## Boundaries & Constraints

**Always:**
- `view_report_draft` (`shell/http/routes/report_runs.py`) fetches the `ReportRun` itself (not just the
  `ReportDraft`), 404ing if it doesn't exist, so it can branch on `run.failed_at`.
- When `run.failed_at is not None`: call `run_gate(draft, stored_payload.payload,
  request.app.state.gate_vocabulary)` and pass its `violations` plus `run` to the template context.
- When `run.failed_at is None`: behavior is byte-for-byte unchanged — no recomputation, no new context
  keys.
- `report_draft.html` renders a "Gate failures" block (kind, section, sentence, detail per violation)
  and `run.failure_reason`, only when violations are non-empty.
- The poll fragment's existing "View Draft" link (`report_run_poll.html`, gated on
  `run.stage == "draft_ready"`) needs no change — Story 5.4 already leaves `run.stage` at `draft_ready`
  on bound-exhaustion, so the link already reaches this page for a persistently-failing run.
- A new test proves `export_report()` refuses a `ReportRun` shaped exactly like Story 5.4's
  bound-exhaustion terminal state (`stage="draft_ready"`, `failed_at` set, a persisted `ReportDraft`,
  no `Report` row) with `ReportNotFoundError` — closing AC3 against the real shape, not just the
  generic "never reached `gate_passed`" case already covered.

**Ask First:** None.

**Never:**
- No new column or table to persist violations — `run_gate()`'s purity makes recomputation free and
  keeps Story 5.6's `GATE_RESULT` table the sole audit-history concern.
- No change to `drive()`, `GateFailedError`, or `run_gate()` themselves.
- No export HTTP route — that's Epic 6, Story 6.2; this story only proves the existing
  `export_report()` boundary already refuses.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Persistently failing run, draft viewed | `run.failed_at` set (regeneration bound exhausted), latest `ReportDraft` + `ReportPayload` exist | 200; page shows draft text, each violation's section/sentence/detail, and `failure_reason` | N/A |
| Passing run, draft viewed | `run.failed_at` is `None` | 200; unchanged — no violations block, no Gate recomputation | N/A |
| Export attempted on a persistently failing run | `ReportRun` in Story 5.4's exact bound-exhausted shape, no `Report` row | `export_report()` raises `ReportNotFoundError` naming the id | Refused; reason stated in the exception message |
| Run failed before any draft exists (generic stage failure) | no `ReportDraft` row for the run | draft view still 404s (existing behavior) | 404 |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py:188-234` (`view_report_draft`) -- fetch `ReportRun`; when
  `failed_at is not None`, recompute `run_gate()` and add `violations`/`run` to the template context.
- `shell/http/templates/report_draft.html` -- add the Gate-failures block, conditioned on violations.
- `core/gate/run.py:421` (`run_gate`) -- reused as-is, read-only; already pure/deterministic.
- `core/types/gate.py:52-90` (`GateViolation`/`GateResult`) -- reused as-is; `GateViolation.detail`
  already renders "what was claimed vs. what the cited Payload entries say" in prose (Story 5.2's own
  docstring names Story 5.5 as its consumer) -- no extra Payload-entry lookup needed in the view layer.
- `shell/runner/driver.py:701` (`drive()`'s `except GateFailedError` branch) -- reference only: confirms
  `run.stage` stays `draft_ready` and the last `ReportDraft` stays reachable on bound-exhaustion.
- `shell/export.py:30` (`export_report`) -- reused as-is, read-only reference for the new test.
- `tests/test_http_report_runs.py` -- new tests for the failed-run draft view (violations rendered) and
  the passing-run draft view (unchanged).
- `tests/test_export_boundary.py` -- new test using Story 5.4's exact bound-exhausted `ReportRun` shape.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/report_runs.py` -- fetch `ReportRun` in `view_report_draft`, recompute
  `run_gate()` when `run.failed_at is not None`, pass `violations`/`run` to the template -- surfaces
  failing Claims without persisting anything new.
- [x] `shell/http/templates/report_draft.html` -- render a Gate-failures block (kind/section/sentence/
  detail) plus `failure_reason` when violations are present -- AC1.
- [x] `tests/test_http_report_runs.py` -- add a bound-exhausted-run draft-view test (violations +
  failure_reason rendered) and a passing-run draft-view test proving no regression (I/O matrix rows 1-2,
  4).
- [x] `tests/test_export_boundary.py` -- add a test asserting `export_report()` refuses Story 5.4's
  exact bound-exhausted `ReportRun` shape with `ReportNotFoundError` (I/O matrix row 3).

**Acceptance Criteria:**
- Given a Report that has exhausted its regeneration bound, when Francesco opens its draft view, then
  he sees the Report text, each failing Claim's section/sentence/detail, and the run's failure reason.
- Given such a Report, when the database is inspected after failure, then its `ReportRun` and
  `ReportDraft` rows remain present and queryable -- nothing discards them.
- Given such a Report, when export is attempted via `export_report()`, then it raises
  `ReportNotFoundError` naming the id, stating the refusal reason.

## Spec Change Log

## Design Notes

AC2 ("never silently discarded") needs no new production code: no code path anywhere deletes a
`ReportRun`/`ReportDraft` on terminal failure (`drive()`'s `except` branches only set
`failed_at`/`failure_reason` and commit) -- this story's task list only adds a test making that
already-true invariant explicit, not a new guard.

Why recompute rather than persist: `run_gate()`'s purity (Story 5.2, AD-1; reaffirmed in this epic's
Technical Decisions) means recomputing at view time from the already-stored `ReportDraft` +
`ReportPayload` costs nothing extra, avoids inventing a second persisted violations shape ahead of
Story 5.6's `GATE_RESULT` table, and can never drift from what a fresh `run_gate()` call would say.

## Verification

**Commands:**
- `uv run pytest tests/test_http_report_runs.py tests/test_export_boundary.py -q` -- expected: all
  pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Recomputing the Gate on demand**

- Entry point: fetches the `ReportRun` itself so the handler can branch on `failed_at`, then recomputes `run_gate()` only for a failed run.
  [`report_runs.py:219`](../../shell/http/routes/report_runs.py#L219)

- The recomputation itself -- pure, against the currently loaded vocabulary, with the drift caveat now stated rather than overclaimed.
  [`report_runs.py:249`](../../shell/http/routes/report_runs.py#L249)

**Never letting a failure render as an ordinary pass**

- `run.failure_reason` renders whenever `run` is in context; the violations list is a separate, narrower guard nested inside -- a generic terminal failure with a coincidentally-grounded draft still shows the reason.
  [`report_draft.html:13`](../../shell/http/templates/report_draft.html#L13)

- Each violation's cited entry ids are surfaced, matching `GateViolation`'s own stated intent for this story.
  [`report_draft.html:24`](../../shell/http/templates/report_draft.html#L24)

**Peripherals**

- Fixture mirrors Story 5.4's exact bound-exhausted terminal shape (`stage` stays `draft_ready`, a `ReportDraft` already exists).
  [`test_http_report_runs.py:768`](../../tests/test_http_report_runs.py#L768)

- Coverage for the corner case the review caught: a terminal failure whose recomputed Gate is grounded still shows the reason.
  [`test_http_report_runs.py:837`](../../tests/test_http_report_runs.py#L837)

- Coverage for the ordinary pass path staying byte-for-byte unchanged.
  [`test_http_report_runs.py:887`](../../tests/test_http_report_runs.py#L887)

- Closes AC3 against the real bound-exhaustion shape, not just the generic "never reached `gate_passed`" case already covered.
  [`test_export_boundary.py:146`](../../tests/test_export_boundary.py#L146)
