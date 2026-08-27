---
title: 'Story 8.3 — Measure the latency the PRD only assumed'
type: 'chore'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'f12c3d1a4cbd7dfc8df8287a00b65db17259fd7c'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** NFR-5's 3-minute per-Report p90 and NFR-10's 10-second full-month-scan bound are
PRD Assumptions 3 and 4 — derived from UJ-1 / SM-1 and the forty-reports-in-an-afternoon target,
never measured. Epic 8 is the release gate and requires both settled by measurement, recorded with
a date, before any Report reaches a paying Client; where reality exceeds a documented budget the
budget is loosened to match rather than left standing unmet.

**Approach:** Add a dated, ratified record at `docs/release-validation/latency.md` (mirroring
`gemini-data-terms.md`): a `tomllib`-parsed block plus prose holding the measured per-Report p90,
the full-month-scan p90, the 40-in-one-sitting throughput result, and the composition method.
Add `tests/test_latency_record.py` — an always-on guard suite that the record parses, its measured
p90s sit within their recorded budgets, and those budgets equal the numbers in `epics.md`; plus one
env-gated measurement harness that drives 40 end-to-end runs through `RecordedResponseGenerator`,
times each and a standalone month scan, and prints a paste-ready block. Real generation latency is
supplied by a small separate live-Gemini sample Francesco records; the per-Report p90 = local-stage
p90 + real-generation p90. Mark PRD Assumptions 3 and 4 resolved with the measured values; revise the
numeric bounds only where a measurement exceeds one.

## Boundaries & Constraints

**Always:**
- The record's machine block is a fenced ` ```toml ` block parsed by `tomllib` (stdlib) — no YAML
  dependency exists (matches `test_data_terms_record.py`). Keys: `checked` (bare ISO date →
  `datetime.date`), `ratified_by`, `ratified_on`, `environment`, `report_p90_seconds`,
  `report_budget_seconds` (`180`), `local_stage_p90_seconds`, `real_gen_sample_n`,
  `real_gen_p90_seconds`, `month_scan_p90_seconds`, `month_scan_budget_seconds` (`10`),
  `session_reports`, `outcome`.
- `outcome` is exactly `"pass"` (measurements taken, budgets reconciled, release may proceed) or
  `"blocked"`. The guard asserts `== "pass"`, so an un-reconciled over-budget measurement keeps the
  suite red.
- `report_p90_seconds` == `local_stage_p90_seconds` + `real_gen_p90_seconds` (whole seconds, the
  documented composition). `real_gen_sample_n` >= 5.
- `report_budget_seconds` equals NFR-5's minutes × 60 as written in `epics.md`; `month_scan_budget_seconds`
  equals NFR-10's "under N seconds" in `epics.md`. Guard tests parse both lines and bind to them.
- The measurement harness uses `RecordedResponseGenerator` (the local-env adapter) and the same
  known-good Fort Worth Client input `tests/test_runner_driver.py` uses; it drives each run with
  `drive()` to `gate_passed`, timing with `time.perf_counter()`; p90 is nearest-rank
  (`sorted(d)[math.ceil(0.9 * len(d)) - 1]`). It asserts all 40 runs reach `gate_passed` with
  `failed_at is None` (the throughput guarantee) but never asserts on elapsed time — timings are
  environment-dependent data, not pass/fail.
- The harness is skipped unless `os.environ.get("RUN_LATENCY_MEASUREMENT") == "1"`, so the default
  `uv run pytest` stays fast; the always-on guard tests validate only the record.
- Assumptions Index items 3 and 4 in `prd.md` get `RESOLVED 2026-08-27` plus the measured value,
  regardless of outcome. NFR-5/NFR-10 numbers (in `epics.md` and PRD §5 / §4.3) change **only** if
  the corresponding measured p90 exceeds them.
- New tests mirror the read-the-file style: `REPO_ROOT` from `Path(__file__)`, no network, no Docker.

**Ask First:**
- A measured p90 that exceeds its budget by more than ~15% — record `outcome = "blocked"`, stop, and
  bring Francesco the number so he sets the revised budget rather than the implementer picking one.
- Real-Gemini sample p90 unavailable at implementation time — pause; the record cannot be ratified
  `"pass"` without `real_gen_sample_n`/`real_gen_p90_seconds` filled from a live reading.
- Any change to the run pipeline, the Generator adapters, or `ExportRecord.elapsed_seconds` — out of
  scope; this story measures and records, it does not re-architect.

**Never:**
- No runtime behaviour change: no new timing instrumentation in `shell/`, no UI surface. Enforcement
  lives in the test suite.
- No new dependency; `tomllib` + stdlib `statistics`/`math` only.
- Do not add `docs/` content beyond this one record file.
- Do not run the 40-run harness inside the default suite, and do not assert timing thresholds anywhere.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Record present, within budget | `latency.md` with valid toml, `outcome = "pass"`, both p90s ≤ budgets | all guard tests pass | N/A |
| Record missing | file absent | `test_record_exists` fails naming the path | Loud failure |
| Toml block malformed / absent | no ` ```toml ` fence, or unparseable | extraction / `tomllib` raises → test fails | Loud failure |
| `checked` not an ISO date / in the future | `checked = "soon"` or a future date | `test_checked_is_a_date` fails | Assertion |
| Measured p90 over budget, un-reconciled | `report_p90_seconds = 200`, `report_budget_seconds = 180`, `outcome = "pass"` | `test_report_p90_within_budget` fails | Assertion |
| Over-budget, reconciled | budget revised to `210`, `epics.md` NFR-5 updated, `outcome = "pass"` | all pass (budget now matches reality and `epics.md`) | N/A |
| Recorded budget drifts from `epics.md` | `report_budget_seconds = 180` but NFR-5 says "under 4 minutes" | `test_report_budget_matches_epics` fails | Assertion |
| Composition inconsistent | `report_p90_seconds ≠ local_stage_p90_seconds + real_gen_p90_seconds` | `test_composed_p90_consistent` fails | Assertion |
| Real-gen sample too small | `real_gen_sample_n = 2` | `test_real_gen_sample_present` fails | Assertion |
| Throughput short | `session_reports = 30` | `test_session_reports_meets_target` fails | Assertion |
| Harness run (opt-in) | `RUN_LATENCY_MEASUREMENT=1` | 40 runs reach `gate_passed`, `failed_at is None`; prints paste-ready toml + per-run table | fails if any run has `failed_at` |
| Harness skipped (default) | env var unset | `test_measure_latency` skipped; guard tests still run | N/A |

</frozen-after-approval>

## Code Map

- `docs/release-validation/latency.md` — **new.** The record. Fenced ` ```toml ` block (keys per
  Boundaries) then prose: *What was assumed* (NFR-5/NFR-10, Assumptions 3-4) · *How it was measured*
  (local harness + live-Gemini sample, the composition formula, `environment` string) · *Per-Report
  latency* (local-stage p90, real-gen p90, composed p90 vs 3-min budget) · *Full-month scan* (p90 vs
  10-s bound) · *Throughput* (40 runs, one sitting, wall-clock, zero failures + Francesco's UI
  confirmation note) · *Budget reconciliation* (which bounds changed, if any; Assumptions 3-4 marked
  resolved) · *Outcome* · *Re-measure trigger*. Draft prose in Design Notes; Francesco ratifies the
  numbers and `outcome` before merge.
- `tests/test_latency_record.py` — **new.** `REPO_ROOT = Path(__file__).resolve().parent.parent`.
  Module-scope fixture extracts the ` ```toml `…` ``` ` block and `tomllib.loads()` it. Guard tests:
  `test_record_exists`, `test_toml_block_parses`, `test_checked_is_a_date`
  (`isinstance(meta["checked"], datetime.date)` and not in the future — epic-4-retro item 25),
  `test_outcome_permits_release` (`== "pass"`), `test_report_p90_within_budget`
  (`report_p90_seconds <= report_budget_seconds`), `test_month_scan_p90_within_budget`,
  `test_report_budget_matches_epics` (regex NFR-5's "under N minute(s)" out of `epics.md`,
  `N*60 == report_budget_seconds == 180`), `test_month_scan_budget_matches_epics` (NFR-10's
  "under N seconds", `== month_scan_budget_seconds == 10`), `test_composed_p90_consistent`,
  `test_real_gen_sample_present` (`real_gen_sample_n >= 5`, `real_gen_p90_seconds > 0`),
  `test_session_reports_meets_target` (`session_reports >= 40`). Plus `test_measure_latency`,
  `@pytest.mark.skipif(os.environ.get("RUN_LATENCY_MEASUREMENT") != "1", …)`: the harness.
- `tests/test_runner_driver.py` — **copy source (read-only).** `_create_client_and_chart`,
  `_drive`, and the module setup `_COMPUTATION_CONFIG` / `_SECTIONS_CONFIG` / `_VOCABULARY` /
  `_EPHEMERIS_IDENTITY` (L60-92); `ReportRun(client_id=…, month="2026-01")` then `drive(...)` to
  `"gate_passed"` (L189-195). The harness rebuilds this: one Client+chart, then 40× fresh
  `ReportRun` → `perf_counter()` → `drive(..., generator=RecordedResponseGenerator())` →
  `perf_counter()`; assert `result.stage == "gate_passed"` and `result.failed_at is None`.
- `shell/runner/driver.py:196` `_run_transits_ready` — the full-month scan under measurement:
  `find_transit_aspects` + `find_stations` + `find_ingresses` + `find_lunations` over
  `[run.month_start_utc, run.month_end_utc)`. The harness times this block in isolation (call the
  four functions directly with a resolved interval) for `month_scan_p90_seconds`.
- `shell/adapters/local/generator.py:59` `RecordedResponseGenerator` — no-network Generator the
  harness drives through `draft_ready`; its placeholder generation is why real-gen latency must be
  sampled separately.
- `shell/adapters/postgres/export_record.py` — read-only context: `elapsed_seconds` is
  `ReportRun.created_at` → PDF export, the closest existing production instrumentation; the record's
  prose cites it as the real-traffic cross-check but the story adds nothing here.
- `_bmad-output/planning-artifacts/epics.md:119` NFR-5, `:129` NFR-10 — budget source of truth the
  guard tests bind to; numbers change only on an over-budget measurement.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:383` (§4.3 scan bound),
  `:701-706` (§5 throughput/latency + Assumption 3 inline), `:1039-1042` (Assumptions Index 3 & 4).
  Items 3 and 4 get `RESOLVED 2026-08-27` + measured value; §5/§4.3 numbers change only if exceeded.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_latency_record.py` — the toml-extraction helper, the 11 guard tests named in the
      Code Map covering every I/O & Edge-Case Matrix row, and the env-gated `test_measure_latency`
      harness (40 end-to-end runs + isolated month scan, paste-ready output, no timing assertions).
- [x] `docs/release-validation/latency.md` — created; harness run (local-stage + month-scan p90
      ≈ 0.2 s) and a live `gemini-2.5-flash` sample (n=10, p90 118 s) transcribed. `report_p90_seconds
      = 119` (1 + 118), `outcome = "pass"`, `ratified_by = "Francesco"` / `ratified_on = 2026-08-27`.
      Regeneration risk (8/10 drafts valid; Gate path unexercised) recorded as a Known limitation per
      Francesco's 2026-08-27 decision.
- [x] `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md` — Assumptions Index
      items 3 and 4 struck through and marked `RESOLVED 2026-08-27` with the measured values and the
      regeneration caveat. Neither p90 exceeded its bound, so §5 / §4.3 numbers left verbatim.
- [x] `_bmad-output/planning-artifacts/epics.md` — NFR-5 / NFR-10 bounds left verbatim (neither
      exceeded); each carries an appended `*(measured 2026-08-27: …)*` parenthetical.

**Acceptance Criteria:**
- Given real end-to-end Reports, when latency is measured, then `docs/release-validation/latency.md`
  records the per-Report p90 ("Client selected" → Report on screen, scan + assembly + generation +
  Gate + bounded regeneration) against the 3-minute budget, with the local-stage / real-generation
  composition stated.
- Given a full-month transit scan for one Client, when measured, then the record holds
  `month_scan_p90_seconds` against the 10-second bound.
- Given a measurement that exceeds its documented budget, when recorded, then the budget in
  `epics.md` and the PRD is revised to the ratified value rather than left unmet, and
  `test_*_p90_within_budget` passes because the recorded budget now matches reality.
- Given the measurements are taken, when the record is finalised, then PRD Assumptions 3 and 4 are
  marked `RESOLVED 2026-08-27` with the measured values, whether or not a bound changed.
- Given a working session, when throughput is exercised, then the harness produces 40 Reports to
  `gate_passed` with zero `failed_at`, `session_reports >= 40` is recorded, and Francesco's one-sitting
  produce/review/export confirmation is noted.
- Given the full suite, when `uv run pytest -q` and `uv run ruff check .` run, then both are clean and
  `test_measure_latency` is skipped.

## Design Notes

**Why the harness is opt-in, not always-on.** 40 full `drive()` calls each run a real month-long
ephemeris scan (aspects, stations, ingresses, lunations) — tens of seconds to minutes of wall time.
`pyproject.toml` has no `slow` marker and `addopts = -q` runs everything, so an always-on 40-run test
would tax every CI run for a number that is environment-dependent and already captured in the record.
The env gate (`RUN_LATENCY_MEASUREMENT=1`) keeps it a deliberate release action; the always-on tests
guard the *record*, exactly as `test_data_terms_record.py` guards `gemini-data-terms.md`.

**Why the p90 is composed, not measured whole.** `RecordedResponseGenerator` returns placeholder
prose with no network call, so a local `drive()` measures scan + assembly + Gate + regeneration but
zero generation time — which is the one component PRD Assumption 3 flags as never validated. The
record therefore states `report_p90_seconds = local_stage_p90_seconds + real_gen_p90_seconds`, where
`real_gen_p90_seconds` is the p90 of a small (n ≥ 5) live-Gemini sample Francesco records (from a
one-off timed `GeminiGenerator` call or production logs). This is the conservative sum, not a
best-effort estimate.

**Drafted record content (numbers are placeholders — the harness + sample fill them, Francesco
ratifies):**

```toml
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
environment = "local Docker Compose harness (RecordedResponseGenerator) + live-Gemini sample"
report_budget_seconds = 180
local_stage_p90_seconds = 0    # from test_measure_latency, 40 runs, nearest-rank p90
real_gen_sample_n = 0
real_gen_p90_seconds = 0       # p90 of n live gemini-2.5-flash calls
report_p90_seconds = 0         # = local_stage_p90_seconds + real_gen_p90_seconds
month_scan_budget_seconds = 10
month_scan_p90_seconds = 0     # isolated four-function scan, nearest-rank p90
session_reports = 40
outcome = "pass"
```

- *Budget reconciliation:* if `report_p90_seconds <= 180` and `month_scan_p90_seconds <= 10`, leave
  NFR-5 / NFR-10 / §5 / §4.3 numbers unchanged and only append the measured value; Assumptions 3 & 4
  still move to RESOLVED. If either is exceeded by ≤ 15%, revise the bound to the measured value
  (rounded up to a clean number) with a dated note; if by more than 15%, stop and ask Francesco.
- *Re-measure trigger:* any change to the run pipeline (`shell/runner/driver.py`), the transit-scan
  functions, the Generator model/tier (AD-9), or the ephemeris identity; re-run the harness + sample
  and bump `checked`.

## Verification

**Commands:**
- `uv run pytest tests/test_latency_record.py -q` — expected: all guard tests pass, `test_measure_latency`
  reported as skipped.
- `RUN_LATENCY_MEASUREMENT=1 uv run pytest tests/test_latency_record.py::test_measure_latency -s` —
  expected: 40 runs reach `gate_passed` with no `failed_at`; prints the per-run table and a
  paste-ready toml block.
- `uv run pytest -q` — expected: full suite green.
- `uv run ruff check .` — expected: clean.

**Manual checks:**
- Francesco: run the harness and a live-Gemini sample (n ≥ 5), transcribe the four measured numbers
  and `real_gen_sample_n` into `latency.md`, confirm `outcome`, and do one real produce → review →
  export sitting to confirm the throughput AC end-to-end in the UI. Correct `ratified_by` /
  `ratified_on` if ratification did not happen.

## Suggested Review Order

**The recorded measurement (the deliverable)**

- Entry point: the 13-key machine block — every value is guard-tested; `outcome = "pass"` is the release gate.
  [`latency.md:14`](../../docs/release-validation/latency.md#L14)

- The one real finding: single generation call fits 180 s, but a ~20 % citation/Gate regeneration rate can push a Report over — recorded, not budget-revised (Francesco's call).
  [`latency.md:44`](../../docs/release-validation/latency.md#L44)

- Live `gemini-2.5-flash` sample (n=10, p90 118 s), the rolling-alias caveat, and the local-stage + real-gen composition.
  [`latency.md:103`](../../docs/release-validation/latency.md#L103)

- Outcome `pass`, and the explicit note that AC-4's UI sitting is still outstanding.
  [`latency.md:195`](../../docs/release-validation/latency.md#L195)

**The guard suite (enforcement)**

- The gate: `outcome` must be `"pass"` — a `"blocked"` record keeps the suite red.
  [`test_latency_record.py:171`](../../tests/test_latency_record.py#L171)

- Measured p90 strictly under budget (`<`, matching NFR "under"), for both per-Report and month-scan.
  [`test_latency_record.py:178`](../../tests/test_latency_record.py#L178)

- Recorded budgets bound to the numbers parsed live out of `epics.md` NFR-5 / NFR-10 — record, epic and suite cannot silently disagree.
  [`test_latency_record.py:199`](../../tests/test_latency_record.py#L199)

- Composition consistency: `report_p90 == local_stage_p90 + real_gen_p90`.
  [`test_latency_record.py:229`](../../tests/test_latency_record.py#L229)

- The live-sample floor: `real_gen_sample_n >= 5`, `real_gen_p90_seconds > 0` — the composed p90 can't rest on a placeholder.
  [`test_latency_record.py:239`](../../tests/test_latency_record.py#L239)

**The measurement harness (peripheral)**

- Opt-in (`RUN_LATENCY_MEASUREMENT=1`): 40 end-to-end `drive()` runs + 40 isolated month scans, timed, never asserting on time; only that all 40 reach `gate_passed`. Also satisfies the 40-in-one-sitting machine half.
  [`test_latency_record.py:275`](../../tests/test_latency_record.py#L275)

**Planning reconciliation (peripheral)**

- NFR-5 / NFR-10 bounds unchanged; measured-value parenthetical appended to each.
  [`epics.md:119`](../planning-artifacts/epics.md#L119)

- Assumptions Index items 3 & 4 struck through and marked `RESOLVED 2026-08-27` with the measured values and the regeneration caveat.
  [`prd.md:1039`](../planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md#L1039)
