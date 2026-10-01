---
title: '10-7 Measure it'
type: 'chore'
created: '2026-10-01'
status: 'in-progress'
baseline_commit: '8bcb31f59d8e51eebbabf3b3baa74e00a3e9e000'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
  - '{project-root}/docs/release-validation/latency.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `latency.md` records the pre-Epic-10 single-call generation (p90 118 s) and no PDF timing, so the new latency is unproven against NFR-5 and the Epic 10 targets (draft p90 ≤ 60 s, PDF first ≤ 6 s, repeat < 1 s).

**Approach:** An opt-in harness drives the running local docker app (real `gemini-2.5-flash`, local Postgres, one uvicorn worker) over HTTP, timing draft, per-Section, regeneration and PDF export; its figures replace the stale ones in `latency.md`, and `tests/test_latency_record.py` checks them against the budgets. Five generated reports are saved for Francesco's side-by-side read for repetition.

## Boundaries & Constraints

**Always:** Environment is recorded honestly as local docker, not production; the record keeps `outcome = "blocked"` until Francesco sets `sitting_confirmed` and `repetition_reviewed` himself. Nearest-rank p90 as today. Draft time = `POST /clients/{id}/report-runs` to `gate_passed`; Section time = `claimed_at` to the status flip to `complete`, polled from Postgres at ≤0.25 s. PDF first = cache-miss GET of `/export/pdf`; repeat = second GET. The harness only creates its own throwaway Client (named `Latency Harness *`) and deletes it afterwards. Real-API cost is bounded: N = 20 runs.

**Ask First:** Publishing a new Style Guide version — only Francesco decides whether repetition warrants one; the harness never writes a Style Guide. Revising any budget.

**Never:** Fabricate or round down a figure; edit `core/`; read secrets other than the committed local-dev session secret in `compose.yaml`; touch real Clients; run on production.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal sample | 20 runs reach `gate_passed` | Printed toml block + per-run table | N/A |
| No regeneration observed | all 20 pass first Gate | `one_regen_basis = "bound"`: draft p90 + 2 × per-Section p90 | Never recorded as `observed` |
| Run fails | `failed_at` set / 10 min timeout | Reported in output, excluded from p90, count recorded | Harness fails if <15 runs succeed |
| App not up / no real Gemini | healthz fails or `USE_REAL_GEMINI_LOCALLY` off | Skip with reason | No silent fallback to recorded generator |
| Over budget | measured p90 above target | Guard test red | Reconcile budget with Francesco, never edit silently |

</frozen-after-approval>

## Code Map

- `tests/test_latency_record.py` -- existing guard (`_EXPECTED_KEYS`, `test_composed_p90_consistent`, `test_real_gen_sample_present`) and 8-3 opt-in harness; extend both.
- `docs/release-validation/latency.md` -- toml block + prose; add Epic 10 section, supersede the single-call composition and its regeneration limitation.
- `tests/_release_validation.py` -- `load_record_meta`, `assert_outcome_permits_release` reuse.
- `shell/http/routes/report_runs.py:501,1491` -- start route and PDF export (cache hit by `pdf_fingerprint`); `ExportedPdf` in `shell/adapters/postgres/exported_pdf.py`.
- `shell/adapters/postgres/report_draft_section.py` -- `claimed_at`, `status`, `attempt`, `ordinal` for Section timing.
- `shell/http/auth.py:79` -- `sign_session` for a cookie from the compose local-dev secret.
- `tests/test_runner_advance.py` -- `_a_natal_chart`, resolved place and config helpers; `create_client_with_chart` seeds the Client.
- `compose.yaml` -- DB `postgresql://astro:astro@localhost:5432/astro_report`, app on :8000.

## Tasks & Acceptance

**Execution:**
- [ ] `tests/test_latency_record.py` -- add `test_measure_epic10_latency` (skip unless `RUN_LATENCY_MEASUREMENT=epic10` and app healthy): seed Client, 20 runs over HTTP + DB polling, two PDF GETs each, save five report texts under `cache/latency-reports/`, print toml block and a naive cross-Section repeated-sentence count
- [ ] `tests/test_latency_record.py` -- new keys `draft_p90_seconds`, `section_p90_seconds`, `one_regen_p90_seconds`, `one_regen_basis`, `pdf_first_p90_seconds`, `pdf_repeat_p90_seconds` (repeat as float, whole seconds is too coarse), `runs_ok`, `repetition_reviewed`; budget tests (60 / 6 / <1, NFR-5 180 on `one_regen_p90`); drop the single-call composition tests; negative tests `test_the_guard_detects_a_*` for over-budget draft, PDF, and `bound` presented as `observed`
- [ ] `docs/release-validation/latency.md` -- run the harness, record measured values, Epic 10 section, side-by-side reading instructions, repetition-review PENDING marker
- [ ] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 10-7 to `review`

**Acceptance Criteria:**
- Given the local stack with real Gemini, when the harness runs, then `latency.md` holds draft, per-Section, one-regeneration p90 and PDF first/repeat times from that run.
- Given the record, when `uv run pytest tests/test_latency_record.py` runs, then it checks them against the targets and fails if any is over.
- Given five saved reports, when Francesco reads them, then any repetition is addressed by a new Style Guide version he publishes and records in the file.

## Spec Change Log

## Design Notes

Per-Section time is read from Postgres rather than the HTML poll: the rail only shows state at poll granularity and `claimed_at` has no completion twin, so the DB flip observed at ≤0.25 s is the cheapest honest signal without a migration. The "bound" regeneration basis exists because the Gate may never reject in 20 runs; a regenerated Section plus Consiglio finale run in sequence, hence 2 × per-Section p90.

## Verification

**Commands:**
- `RUN_LATENCY_MEASUREMENT=epic10 uv run pytest tests/test_latency_record.py -k epic10 -s` -- expected: toml block printed, ≥15 runs ok
- `uv run pytest` -- expected: green (guard may stay xfail on `outcome`)
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
