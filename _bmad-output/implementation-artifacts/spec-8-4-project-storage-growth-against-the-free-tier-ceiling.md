---
title: 'Story 8.4 — Project storage growth against the free-tier ceiling'
type: 'chore'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
baseline_commit: '67289357d94a5619c94312eba5f34efc9d198ecc'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/docs/release-validation/latency.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Report Payloads are stored permanently — NFR-9 makes losing one unacceptable — on
Neon's 0.5 GB free plan, and nothing has measured how long that fits. Epic 8 is the release gate and
requires the retention guarantee projected against real numbers, with a date, before any Report
reaches a paying Client; a projection that reaches half the ceiling must be raised as an explicit
decision rather than absorbed.

**Approach:** Add a dated, ratified record at `docs/release-validation/storage-growth.md` (mirroring
`latency.md` / `gemini-data-terms.md`): a `tomllib`-parsed block plus prose holding the measured
per-Payload serialized size, the projected monthly growth, the date the 0.5 GB ceiling and its
half are reached at 100–200 Reports/month, and a ratified storage-growth policy. Add
`tests/test_storage_growth_record.py` — an always-on guard suite that the record parses, its
projection arithmetic is internally consistent, its ceiling matches README and its volume matches
`epics.md`, and a policy is recorded whenever the half-ceiling date is near; plus one env-gated
harness that drives N end-to-end runs of the known-good fixture, reads each persisted
`report_payload` row back, and prints a paste-ready block. Append a measured parenthetical to the
E11 bullet in `epics.md`. No PRD change — no Assumptions Index item covers storage.

## Boundaries & Constraints

**Always:**
- The record's machine block is a fenced ` ```toml ` block parsed by `tomllib` (stdlib) — no YAML
  dependency exists (matches `test_data_terms_record.py`). Keys: `checked` (bare ISO date →
  `datetime.date`), `ratified_by`, `ratified_on` (bare ISO date), `sample_n`, `payload_p90_bytes`,
  `storage_overhead_factor`, `projected_row_bytes`, `reports_per_month` (`200`), `monthly_growth_bytes`,
  `ceiling_bytes` (`500000000`), `ceiling_reached_on` (bare ISO date), `half_ceiling_reached_on`
  (bare ISO date), `policy_decision` (`"raised"` or `"none"`), `policy_ratified_by`,
  `policy_ratified_on` (bare ISO date), `outcome`.
- `outcome` is exactly `"pass"` (size measured, projection recorded, policy reconciled — release may
  proceed) or `"blocked"`. The guard asserts `== "pass"`.
- Size metric is `len(canonical_json_bytes(row.payload))` of a real persisted `ReportPayload.payload`
  value — the exact text Postgres' `JSON` column (not JSONB) stores verbatim. `payload_p90_bytes` is
  the nearest-rank p90 (`sorted(d)[math.ceil(0.9 * len(d)) - 1]`) over the harness sample;
  `sample_n >= 6`.
- Projection arithmetic, all integer bytes: `projected_row_bytes == math.ceil(payload_p90_bytes *
  storage_overhead_factor)`; `monthly_growth_bytes == projected_row_bytes * reports_per_month`.
  `storage_overhead_factor >= 1.0` (Postgres row header + the two indexes + TOAST + the duplicated
  typed columns; documented in the record's prose).
- `ceiling_bytes` equals `0.5 GB` as written in README's "Running cost" table
  (`0.5 * 1000**3`); the guard parses the `Neon Postgres … Free (0.5 GB)` row. `reports_per_month`
  equals the upper bound of `epics.md`'s "100–200 per month" (NFR-5 line); the guard parses it.
- `ceiling_reached_on` and `half_ceiling_reached_on` are dates strictly after `checked`, each
  consistent with `checked` plus `ceiling_bytes / monthly_growth_bytes` (resp. half) months at
  30.44 days/month, within a ±5-day tolerance in the guard.
- A storage-growth policy is written in the record's prose and `policy_decision = "raised"` with
  `policy_ratified_by` / `policy_ratified_on` set whenever `half_ceiling_reached_on` falls on or
  before `checked` + a 60-month horizon (the guard's `HORIZON`). `policy_decision = "none"` is only
  valid when the half-ceiling date is beyond that horizon.
- The harness seeds one Client + Natal Chart from the known-good Fort Worth, TX fixture
  (`tests/test_runner_driver.py`: 2026-01-01 00:00 America/Chicago) and drives N (>= 6, use 12)
  fresh `ReportRun` rows over consecutive months with `drive()` to `gate_passed` through a local
  minimal fake `Generator` (mirroring `tests/test_runner_driver.py::_FakeGenerator`), then reads
  each persisted `ReportPayload` back. It asserts all N runs persist a `report_payload` row and
  reach `gate_passed` with `failed_at is None`; it never asserts on byte counts — sizes are
  environment/fixture-dependent data.
- The harness is skipped unless `os.environ.get("RUN_STORAGE_MEASUREMENT") == "1"`, so the default
  `uv run pytest` stays fast; the always-on guard tests validate only the record.
- New tests mirror the read-the-file style: `REPO_ROOT` from `Path(__file__)`, no network, no Docker.

**Ask First:**
- The storage-growth policy text and its ratification — Francesco writes or approves the policy and
  ratifies the measured `payload_p90_bytes`, the projected dates and `outcome`. The record cannot go
  `outcome = "pass"` with `policy_decision = "raised"` on an implementer-invented policy (mirrors the
  8.2 / 8.3 ratification requirement). Draft a candidate policy in Design Notes; Francesco owns it.
- A measured p90 payload size more than ~3× the ~57 KiB observed on 2026-08-27 — pause and bring
  Francesco the number; the projection basis has changed.
- Any change to `ReportPayload`, the run pipeline, or a new storage-reclamation mechanism — out of
  scope; this story measures, projects, and records a decision.

**Never:**
- No runtime behaviour change: no new column, migration, or size-tracking instrumentation in
  `shell/`; no UI surface. Enforcement lives in the test suite and the record.
- No new dependency; `tomllib` + stdlib `math` / `statistics` / `datetime` only.
- Do not add `docs/` content beyond this one record file.
- Do not run the harness inside the default suite, and do not assert on measured byte sizes anywhere.
- Do not edit the PRD — no Assumptions Index item covers storage; the storage-growth policy is a
  decision recorded in the release-validation doc, not a PRD change. Do not change any number in
  `epics.md` — there is no documented storage budget to revise; only append the measured parenthetical.
- Do not design or implement pruning, archival, TTL, or export-and-delete — raising the policy is the
  deliverable; implementing it is not.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Record present, projection consistent | valid toml, `outcome = "pass"`, dates consistent, policy ratified | all guard tests pass | N/A |
| Record missing | file absent | `test_record_exists` fails naming the path | Loud failure |
| Toml block malformed / absent | no ` ```toml ` fence, or unparseable | extraction assert / `tomllib` raises → test fails | Loud failure |
| `checked` not an ISO date / in the future | `checked = "soon"` or a future date | `test_checked_is_a_date` fails | Assertion |
| `payload_p90_bytes` implausibly small | `payload_p90_bytes = 10` | `test_payload_bytes_sane` fails (`< 1024`) | Assertion |
| Overhead arithmetic inconsistent | `projected_row_bytes ≠ ceil(payload_p90_bytes * storage_overhead_factor)` | `test_projected_row_bytes_consistent` fails | Assertion |
| Growth arithmetic inconsistent | `monthly_growth_bytes ≠ projected_row_bytes * reports_per_month` | `test_monthly_growth_consistent` fails | Assertion |
| Ceiling drifts from README | `ceiling_bytes = 1_000_000_000` but README says "0.5 GB" | `test_ceiling_matches_readme` fails | Assertion |
| Volume drifts from target | `reports_per_month = 500` vs `epics.md` "100–200 per month" | `test_reports_per_month_matches_target` fails | Assertion |
| Ceiling date inconsistent | `ceiling_reached_on` not ≈ `checked + ceiling_bytes / monthly_growth_bytes` months | `test_ceiling_date_consistent` fails | Assertion |
| Half-ceiling within horizon, no policy | `half_ceiling_reached_on` soon, `policy_decision = "none"` | `test_policy_raised_when_half_ceiling_near` fails | Assertion |
| Un-reconciled block | `outcome = "blocked"` | `test_outcome_permits_release` fails | Assertion |
| Harness run (opt-in) | `RUN_STORAGE_MEASUREMENT=1` | N `report_payload` rows persisted, all to `gate_passed`; prints per-run sizes, nearest-rank p90, per-Report sibling-row footprint, paste-ready toml | fails if any run has `failed_at` or no payload row |
| Harness skipped (default) | env var unset | `test_measure_payload_size` skipped; guard tests still run | N/A |

</frozen-after-approval>

## Code Map

- `docs/release-validation/storage-growth.md` — **new.** The record. Fenced ` ```toml ` block (keys
  per Boundaries) then prose: *What was assumed* (permanent Payload retention on Neon free 0.5 GB;
  NFR-9; no PRD storage budget) · *How it was measured* (harness: N `gate_passed` drives of the
  Fort Worth fixture, `canonical_json_bytes` of each persisted `report_payload.payload`, nearest-rank
  p90; SQLite stand-in; `storage_overhead_factor` rationale; optional production `pg_total_relation_size`
  cross-check) · *Measured size* (p90, spread, full per-Report footprint) · *Projection* (monthly
  growth, `ceiling_reached_on`, `half_ceiling_reached_on`, and the GB-vs-GiB note) · *Storage-growth
  policy (decision)* (Francesco's ratified policy) · *Outcome* · *Re-measure trigger*. Draft prose in
  Design Notes; Francesco ratifies the numbers, the policy and `outcome` before merge.
- `tests/test_storage_growth_record.py` — **new.** `REPO_ROOT = Path(__file__).resolve().parent.parent`.
  Module-scope fixture extracts the ` ```toml `…` ``` ` block and `tomllib.loads()` it. Guard tests:
  `test_record_exists`, `test_toml_block_parses` (exact key set), `test_checked_is_a_date`
  (`isinstance(meta["checked"], datetime.date)` and not in the future — epic-4-retro item 25),
  `test_ratified_is_a_date` (`ratified_on` a date, `ratified_by` non-empty), `test_payload_bytes_sane`
  (`payload_p90_bytes >= 1024`, `sample_n >= 6`), `test_projected_row_bytes_consistent`
  (`== math.ceil(payload_p90_bytes * storage_overhead_factor)`, `storage_overhead_factor >= 1.0`),
  `test_monthly_growth_consistent` (`== projected_row_bytes * reports_per_month`),
  `test_ceiling_matches_readme` (parse `Free (0.5 GB)` from README's Running-cost table,
  `0.5 * 1000**3 == ceiling_bytes`), `test_reports_per_month_matches_target` (regex `100[–-]200`
  … "per month" out of `epics.md`, upper bound `== reports_per_month == 200`),
  `test_ceiling_date_consistent` / `test_half_ceiling_date_consistent`
  (`checked` + `round(ceiling_bytes / monthly_growth_bytes * 30.44)` days, `abs(...) <= 5` days; both
  dates strictly after `checked`), `test_policy_raised_when_half_ceiling_near`
  (`HORIZON = timedelta(days=round(60 * 30.44))`; if `half_ceiling_reached_on <= checked + HORIZON`
  then `policy_decision == "raised"` and `policy_ratified_by` / `policy_ratified_on` valid, else
  `policy_decision == "none"`), `test_outcome_is_valid` (`in {"pass", "blocked"}`),
  `test_outcome_permits_release` (`== "pass"`). Plus `test_measure_payload_size`,
  `@pytest.mark.skipif(os.environ.get("RUN_STORAGE_MEASUREMENT") != "1", …)`: the harness.
- `tests/test_data_terms_record.py` — **pattern source (read-only).** `_TOML_BLOCK` extraction regex,
  the README-section parser, the exact-key-set assertion, the `checked`-date sanity check, and the
  `outcome in {"pass","blocked"}` + `outcome == "pass"` gate — copy the shape.
- `tests/test_latency_record.py` — **pattern source (read-only).** The env-gated harness shape
  (`@pytest.mark.skipif(os.environ.get(...) != "1")`), nearest-rank p90
  (`sorted(d)[math.ceil(0.9 * len(d)) - 1]`), binding a recorded number to a planning doc parsed
  live, the paste-ready block print, and asserting on run success but never on the measured quantity.
- `tests/test_runner_driver.py` — **copy source (read-only).** `_create_client_and_chart`, `_drive`,
  the module setup (`_COMPUTATION_CONFIG` / `_SECTIONS_CONFIG` / `_VOCABULARY` / `_EPHEMERIS_IDENTITY`,
  Fort Worth `_RESOLVED_PLACE` / `_BIRTH_INSTANT_UTC`), and `_FakeGenerator` / `_a_generated_draft`
  (L132-183). The harness rebuilds this: one Client + chart, then 12× fresh
  `ReportRun(client_id=…, month=…)` → `drive(..., generator=<local fake>)` to `"gate_passed"` →
  `select(ReportPayload).where(report_run_id == run.id)` → `len(canonical_json_bytes(row.payload))`.
- `shell/adapters/postgres/report_payload.py:28` `ReportPayload` — the row under measurement.
  `payload: dict = Field(sa_column=Column(JSON, nullable=False))` stores `freeze_payload()`'s dict
  verbatim as canonical JSON; `report_run_id` is `unique` (FR-14: one Payload per Report); the row is
  immutable (`_forbid_update`). Read-only.
- `core/payload/freeze.py:51` `canonical_json_bytes` — `len(canonical_json_bytes(row.payload))` is the
  exact byte count Postgres' `JSON` column persists; the harness's size metric. Read-only.
- `shell/runner/driver.py` `_run_payload_ready` (~:360) — the stage that persists the `report_payload`
  row; the harness drives at least this far (and on to `gate_passed`). Read-only.
- `README.md` — "Running cost" table row `Neon Postgres 18 (Europe/Frankfurt) | Free (0.5 GB) | €0`;
  the ceiling the guard binds to. Read-only.
- `_bmad-output/planning-artifacts/epics.md:119` NFR-5 ("100–200 per month") — the volume the guard
  parses; `:205` E11 bullet — gets the measured parenthetical appended; `:127` NFR-9 — the durability
  requirement the retention guarantee rests on (cited in the record's prose). Read-only except `:205`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_storage_growth_record.py` — the toml-extraction helper, the guard tests named in
      the Code Map covering every I/O & Edge-Case Matrix row, and the env-gated
      `test_measure_payload_size` harness (12 `gate_passed` drives of the Fort Worth fixture, per-run
      `canonical_json_bytes` sizes + nearest-rank p90 + per-Report sibling-row footprint
      (`report_theme` / `report_draft` / `gate_result` / `report_run.transit_events`) + paste-ready
      toml, asserting only that 12 `report_payload` rows exist and all runs reach `gate_passed`).
- [x] `docs/release-validation/storage-growth.md` — created from the harness run and the projection
      arithmetic. `payload_p90_bytes` transcribed from the harness; `storage_overhead_factor`,
      `reports_per_month = 200`, `ceiling_bytes = 500000000` per Boundaries; `projected_row_bytes`,
      `monthly_growth_bytes`, `ceiling_reached_on`, `half_ceiling_reached_on` computed; the
      storage-growth policy written in prose and ratified by Francesco (`policy_decision = "raised"`,
      `policy_ratified_by` / `policy_ratified_on` set); `outcome = "pass"`, `ratified_by = "Francesco"`,
      `ratified_on` set.
- [x] `_bmad-output/planning-artifacts/epics.md` — E11 bullet (`:205`) gets an appended
      `*(measured 2026-08-27: report_payload JSON p90 ≈ N KiB; at 200 Reports/month the 0.5 GB
      ceiling is reached <date>, half <date> — storage-growth policy in
      docs/release-validation/storage-growth.md)*`. No number in `epics.md` changes.

**Acceptance Criteria:**
- Given a real persisted `report_payload` row, when its serialized size is measured, then
  `docs/release-validation/storage-growth.md` records `payload_p90_bytes` with `sample_n` and states
  the method (canonical-JSON byte length of the `payload` column).
- Given the measured size and the 100–200 Reports/month target, when growth is projected, then the
  record holds `monthly_growth_bytes`, `ceiling_bytes` (Neon 0.5 GB, bound to README), and both
  `ceiling_reached_on` and `half_ceiling_reached_on` as dates after `checked`, each consistent with
  the recorded arithmetic and passing `test_ceiling_date_consistent` / `test_half_ceiling_date_consistent`.
- Given `half_ceiling_reached_on` falls within the guard's 60-month horizon, when the record is
  finalised, then a named storage-growth policy is written in the record and ratified by Francesco
  (`policy_decision = "raised"`, `policy_ratified_by` / `policy_ratified_on` set) rather than
  silently absorbed, and `test_policy_raised_when_half_ceiling_near` passes.
- Given the full suite, when `uv run pytest -q` and `uv run ruff check .` run, then both are clean
  and `test_measure_payload_size` is skipped.
- Given `RUN_STORAGE_MEASUREMENT=1`, when the harness runs, then 12 `report_payload` rows are
  persisted and every run reaches `gate_passed` with `failed_at is None`, and it prints the per-run
  byte sizes, the nearest-rank p90, the per-Report sibling-row footprint and a paste-ready toml
  block — asserting only on row count and run success, never on byte counts.

## Design Notes

**Why byte-length of the canonical JSON, not a live Postgres `pg_column_size`.** `ReportPayload.payload`
is `Column(JSON)` — not `JSONB` — so Postgres stores `canonical_json_bytes(freeze_payload(...))` as
text verbatim. `len(canonical_json_bytes(row.payload))` is therefore the on-disk column size on any
engine, and the harness's in-memory SQLite stand-in (as every store test in this codebase uses) does
not distort it. Per-row header, the `client_id` / `report_run_id` indexes, TOAST, and the typed
columns that duplicate fields already inside `payload` are absorbed by `storage_overhead_factor`
(documented in the record, ~1.5). Francesco can drop in a one-off production cross-check once real
data exists — `SELECT pg_total_relation_size('report_payload'), count(*) FROM report_payload;` — and
record it as a check on the factor, not as the primary number (mirrors 8.3's `ExportRecord` cross-check).

**Why project on the Payload alone.** The story's guarantee is Payload traceability (NFR-9); the
Payload is the row that must never be pruned. The other per-Report JSON rows (`report_theme`,
`report_draft`, `gate_result`, `report_run.transit_events`) are printed by the harness and the
record's prose carries a second projection from the full per-Report footprint. The guard binds to
the Payload-only date — the floor set by the one row NFR-9 forbids pruning; it is *not* the whole-DB
figure (that runway is shorter), so the record states both and does not call the Payload-only number
"conservative".

**Why a policy is required, not optional.** The delivered 2026-08-27 harness run (12 consecutive
months of the Fort Worth fixture: ~40–65 KiB per Payload, mean ~51 KiB, nearest-rank p90 ~63 KiB)
projects, at 200 Reports/month with a 1.5× overhead factor, ~18 MiB/month → the 0.5 GB ceiling in
~26 months and half in ~13 months — inside any reasonable planning horizon — so AC-3's "raised as a
decision rather than absorbed" fires. (The frozen "~57 KiB" figure in *Ask First* is a
pre-measurement estimate kept only as the 3× pause threshold; the measured 63 KiB is well inside it,
so no renegotiation.) Draft
policy for Francesco to ratify or replace: *"When Neon storage crosses 50% of the 0.5 GB ceiling,
move the Neon project to its paid tier and renegotiate the €0/month target — do not prune or archive
Report Payloads, because NFR-9 makes Payload loss unacceptable."*

**Illustrative block** (numbers are placeholders — the harness + arithmetic fill them, Francesco
ratifies):

```toml
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
sample_n = 12
payload_p90_bytes = 65536          # nearest-rank p90, canonical_json_bytes of persisted report_payload rows
storage_overhead_factor = 1.5      # Postgres row header + indexes + TOAST + duplicated typed columns
projected_row_bytes = 98304        # ceil(payload_p90_bytes * storage_overhead_factor)
reports_per_month = 200            # upper bound of epics.md's "100–200 per month"
monthly_growth_bytes = 19660800    # projected_row_bytes * reports_per_month
ceiling_bytes = 500000000          # Neon free plan, README "Running cost" table: Free (0.5 GB)
ceiling_reached_on = 2028-10-12    # checked + ceiling_bytes / monthly_growth_bytes months
half_ceiling_reached_on = 2027-09-19
policy_decision = "raised"
policy_ratified_by = "Francesco"
policy_ratified_on = 2026-08-27
outcome = "pass"
```

- *GB vs GiB:* Neon's plan is documented as "0.5 GB"; the guard binds `ceiling_bytes` to
  `0.5 * 1000**3 = 500_000_000` (the smaller, conservative reading vs 0.5 GiB = 536_870_912). State
  this in the prose.
- *Re-measure trigger:* any change to `freeze_payload` / the Payload schema or serialization, the
  `sections_config` (Section count or shape), the transit-scan functions (they drive event counts and
  thus Payload size), the ephemeris identity or computation config, the Neon plan's storage ceiling,
  or the 100–200/month target — re-run the harness and bump `checked`.

## Verification

**Commands:**
- `uv run pytest tests/test_storage_growth_record.py -q` — expected: all guard tests pass,
  `test_measure_payload_size` reported as skipped.
- `RUN_STORAGE_MEASUREMENT=1 uv run pytest tests/test_storage_growth_record.py::test_measure_payload_size -s`
  — expected: 12 runs reach `gate_passed` with a persisted `report_payload` row each; prints the
  per-run size table, the nearest-rank p90, the per-Report sibling-row footprint, and a paste-ready
  toml block.
- `uv run pytest -q` — expected: full suite green.
- `uv run ruff check .` — expected: clean.

**Manual checks:**
- Francesco: review the projected `ceiling_reached_on` / `half_ceiling_reached_on`, write or approve
  the storage-growth policy in `storage-growth.md`, confirm `outcome`, and set `ratified_by` /
  `ratified_on` and `policy_ratified_by` / `policy_ratified_on` to reflect the actual ratification.

## Suggested Review Order

**The recorded projection (the deliverable)**

- Entry point: the 16-key machine block — every value is guard-tested; `outcome = "pass"` + `policy_decision = "raised"` is the release gate.
  [`storage-growth.md:17`](../../docs/release-validation/storage-growth.md#L17)

- The honest measurement claim: `canonical_json_bytes` is the codebase's canonical serialization, not bytes-on-disk — `json.dumps` whitespace up, TOAST compression down, production cross-check settles it.
  [`storage-growth.md:80`](../../docs/release-validation/storage-growth.md#L80)

- Two projections: payload-only (the machine block, an un-prunable-row floor) and the realistic full per-Report footprint that lands ~4 months earlier; arithmetic shown so `round()` reproduces the dates.
  [`storage-growth.md:173`](../../docs/release-validation/storage-growth.md#L173)

- The decision this story exists to force: paid-tier move at 50 %, no Payload pruning (NFR-9), with a cost line and a monthly Neon-gauge monitoring hook.
  [`storage-growth.md:215`](../../docs/release-validation/storage-growth.md#L215)

**The guard suite (enforcement)**

- The gate: `outcome` must be `"pass"` — a `"blocked"` record keeps the suite red.
  [`test_storage_growth_record.py:415`](../../tests/test_storage_growth_record.py#L415)

- Half-ceiling inside the 60-month horizon forces `policy_decision = "raised"` + ratified-by/on; the inverse (`"none"` far out) is exercised too.
  [`test_storage_growth_record.py:386`](../../tests/test_storage_growth_record.py#L386)

- Recorded dates must re-derive from `checked + round(target/growth × 30.44)` within ±5 days — record and arithmetic cannot silently disagree.
  [`test_storage_growth_record.py:315`](../../tests/test_storage_growth_record.py#L315)

- `ceiling_bytes` bound to README's `Free (0.5 GB)` row and `reports_per_month` to `epics.md` NFR-5 — external sources of truth, parsed live.
  [`test_storage_growth_record.py:258`](../../tests/test_storage_growth_record.py#L258)

- Projection arithmetic: `projected_row_bytes == ceil(p90 × factor)`, `monthly_growth == projected_row_bytes × reports_per_month`.
  [`test_storage_growth_record.py:234`](../../tests/test_storage_growth_record.py#L234)

**The measurement harness (peripheral)**

- Opt-in (`RUN_STORAGE_MEASUREMENT=1`): 12 `drive()` runs of the Fort Worth fixture reusing `test_runner_driver.py` helpers; measures each persisted `report_payload`, prints per-run sizes + summary + a 4-row projection table + paste-ready toml. Asserts row count and `gate_passed` only, never bytes.
  [`test_storage_growth_record.py:456`](../../tests/test_storage_growth_record.py#L456)

**Planning reconciliation (peripheral)**

- E11 bullet gets a measured parenthetical pointing at the record as the live source; no epics.md number changed.
  [`epics.md:205`](../planning-artifacts/epics.md#L205)
