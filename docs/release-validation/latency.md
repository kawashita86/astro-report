# Latency measurement (Story 8.3)

NFR-5 puts one Report from "Client selected" to "Report on screen" — transit
scan, Payload assembly, generation, Groundedness Gate and any bounded
regeneration — at **under 3 minutes at p90**, and NFR-10 puts a full-month
transit scan for one Client at **under 10 seconds**. Both are PRD Assumptions 3
and 4: derived from UJ-1 / SM-1 and the forty-reports-in-an-afternoon target,
never measured. This file is the durable, dated record of that measurement. The
machine-readable block below is parsed by `tests/test_latency_record.py`; the
guard suite stays red while a measured p90 sits outside its recorded budget,
while a recorded budget drifts from `epics.md`'s NFR-5 / NFR-10, or while
`outcome` is anything other than `"pass"`. Per epic-8-retro-item-65 the guard
also refuses `outcome = "pass"` unless `sitting_confirmed = true` — AC-4's
human half (Francesco's forty-report one-sitting produce → review → export)
must actually have happened, not just the machine half.

```toml
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
environment = "local in-process harness (SQLite stand-in for Postgres, RecordedResponseGenerator) + live gemini-2.5-flash generation sample"
report_budget_seconds = 180
local_stage_p90_seconds = 1
real_gen_sample_n = 10
real_gen_p90_seconds = 118
report_p90_seconds = 119
month_scan_budget_seconds = 10
month_scan_p90_seconds = 1
session_reports = 40
sitting_confirmed = false
outcome = "blocked"
```

## Result

- **Per-Report p90 = 119 s** against the 180 s (3-minute) budget — **within
  budget**, at ~66 % of it. Composed as `local_stage_p90_seconds` (1 s) +
  `real_gen_p90_seconds` (118 s).
- **Full-month-scan p90 ≈ 0.2 s** (recorded `= 1`, whole seconds) against the
  10 s bound — **within budget by a wide margin**.
- **Throughput**: 40 Reports driven to `gate_passed` in one harness run, zero
  failures.
- PRD Assumptions 3 and 4 are marked `RESOLVED 2026-08-27` with these values in
  `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md`;
  `epics.md` NFR-5 / NFR-10 carry the measured values as a parenthetical. No
  budget number changed — neither measurement exceeded its bound.

### Known limitation — regeneration is not in the composed p90

`report_p90_seconds` is the **single-generation-call** figure: local pipeline +
one `gemini-2.5-flash` call. It does **not** model regeneration, and NFR-5's own
text counts "any bounded regeneration" toward the 3 minutes. Two independent
regeneration triggers exist and were only partially exercised:

- **Citation validation** (`shell/adapters/gemini/generator.py::_validate_citations`).
  In the live sample, **8 of 10** returned drafts passed; 2 cited a Payload
  entry id that was absent (the model hallucinated it). A ~20 % first-try
  failure rate means a real Report has a material chance of needing a second
  ~100 s generation call, pushing that Report to ~220–250 s — **over the 180 s
  budget** even though the median Report (~87 s generation) is comfortably
  under.
- **Groundedness Gate** (`core/gate/run.py::run_gate`, the `gate_passed` stage).
  `run_gate` is deterministic `core/` computation with no model call, so its
  normal cost *is* included in `local_stage_p90_seconds` (the harness drives
  through `gate_passed` every run). What is **not** exercised is a Gate
  *failure* on real generated prose — `RecordedResponseGenerator` drafts always
  pass it, and a real-prose Gate failure is a separate bounded regeneration
  (another ~100 s generation call) that this composition does not model.

**Re-measure against real post-launch traffic** — drive real end-to-end runs
through the actual `GeminiGenerator` path (generation + Gate + real
regenerations) and record the true wall-clock p90 — before treating the
3-minute budget as demonstrated for the regenerating case. The
`ExportRecord.elapsed_seconds` column (Client selection → PDF export, Story 6.3)
is the natural starting point once traffic exists, but read it as a loose
**upper bound**: it also spans Francesco's on-screen review and any edits
before the export click, so it over-reads NFR-5's machine latency.

## What was assumed

- **NFR-5 / PRD §5 — per-Report latency.** Under 3 minutes at p90 from "Client
  selected" to "Report on screen". `[ASSUMPTION: the 3-minute budget is derived
  from UJ-1's "within a couple of minutes" and SM-1's 15-minute total; not
  validated against real generation latency.]` = **Assumptions Index item 3.**
- **NFR-10 / PRD §4.3 — full-month scan latency.** Under 10 seconds for one
  Client's month. `[ASSUMPTION: bounds set by the target of forty-plus reports
  in an afternoon; not measured.]` = **Assumptions Index item 4.**

## How it was measured

**Local stage p90 — `test_measure_latency`, opt-in
(`RUN_LATENCY_MEASUREMENT=1`).** One Client + Natal Chart is seeded (the
known-good Fort Worth, TX input `tests/test_runner_driver.py` uses: 2026-01-01
00:00 America/Chicago), then 40 fresh `ReportRun` rows are each driven with
`shell/runner/driver.py::drive()` to `gate_passed` through
`RecordedResponseGenerator` (the local, no-network Generator adapter), timed
end to end with `time.perf_counter()`. p90 is nearest-rank
(`sorted(d)[math.ceil(0.9 * len(d)) - 1]`). The harness asserts all 40 runs
reach `gate_passed` with `failed_at is None` — the throughput guarantee — but
never asserts on elapsed time: timings are environment-dependent data. Observed
2026-08-27: p90 ≈ 0.19 s (min 0.17, median 0.18, max 0.20), recorded as
`local_stage_p90_seconds = 1` (rounded up to whole seconds).

The measured endpoint is `drive()` reaching `gate_passed`. Rendering the passed
draft to screen (`view_report` — a Jinja template render of the
already-computed `GeneratedDraft` / `Payload`) adds well under 100 ms and is not
separately measured; "Report on screen" in NFR-5 is treated as `gate_passed`
plus that negligible render.

**Full-month scan p90 — same harness, isolated.** The four Story 3.1–3.4 scan
functions (`find_transit_aspects` + `find_stations` + `find_ingresses` +
`find_lunations`) are called directly over the resolved
`[month_start_utc, month_end_utc)` interval, 40 times, each timed with
`time.perf_counter()`; nearest-rank p90. Observed 2026-08-27: p90 ≈ 0.19 s
(min 0.16, median 0.17, max 0.21), recorded as `month_scan_p90_seconds = 1`.

**Real generation p90 — live `gemini-2.5-flash` sample, n = 10.** The same
seeded Client's persisted `ReportPayload` and `ReportTheme` are fed to
`GeminiGenerator` (the production adapter, real API key), and the raw model
round-trip (`_GoogleGenAIClient.generate_content` with the real
`_RESPONSE_SCHEMA`) is timed with `time.perf_counter()` ten times against the
identical prompt, ~6 s apart. Each returned draft was then run through
`_build_draft` / `_validate_citations` / `_validate_no_date_tokens` to record
whether it would have been accepted (see Known limitation). Samples (seconds):

    89.1  106.1  64.9  131.9  85.8  73.5  60.2  101.8  118.0  75.3

- min 60.2 s · median ≈ 87 s (mean of the 5th/6th samples, 85.8 / 89.1) · max 131.9 s
- **nearest-rank p90 = 118.0 s** → `real_gen_p90_seconds = 118`
- drafts passing citation / date-token validation: **8 / 10**

The model is the rolling `gemini-2.5-flash` **alias** — the free-tier API
response exposed no pinned snapshot id — so this sample is not byte-reproducible
and a silent model revision under the alias will not automatically trip the
"Generator model changes" re-measure trigger. Watch the Gemini release notes
manually and re-run this sample when the backing model moves. Only per-call
wall-clock was retained; no per-call timestamps, token counts or response
metadata were kept.

**Composition.** `report_p90_seconds = local_stage_p90_seconds +
real_gen_p90_seconds` = 1 + 118 = **119** (whole seconds) — the conservative
single-call sum. Regeneration is excluded by construction; see Known limitation.

**Environment.** In-process harness mirroring `tests/test_runner_driver.py`: an
in-memory SQLite engine stands in for Postgres (as every store test in this
codebase does), real `core/` computation, the real vendored ephemeris, and
`RecordedResponseGenerator` for the local pipeline timing. The generation
sample alone used the real Gemini API over the network. No Docker.

## Per-Report latency

Against the `report_budget_seconds = 180` (NFR-5's 3 minutes × 60):

| Component | p90 | Recorded as |
|---|---|---|
| Local stages (scan + assembly + Gate + bounded regeneration, no generation) | ≈ 0.19 s wall-clock (min 0.17 s, median 0.18 s, max 0.20 s), 40 runs | `local_stage_p90_seconds = 1` |
| Real generation (`gemini-2.5-flash`, one call, n = 10 live calls) | 118.0 s nearest-rank (min 60.2 s, median ≈ 87 s, max 131.9 s) | `real_gen_p90_seconds = 118` |
| **Composed per-Report p90 (single generation call)** | **119 s** | `report_p90_seconds = 119` |

The local pipeline is ~0.2 s — effectively the entire 180 s budget is available
for generation. A single `gemini-2.5-flash` call on eight Sections lands at
~87 s median / 118 s p90, so the typical and the p90 Report both clear the
budget on the first generation. A Report that needs one regeneration does not —
see Known limitation.

## Full-month scan

40 isolated scans of the Fort Worth Client's 2026-01 month: p90 ≈ 0.19 s
wall-clock (min 0.16 s, median 0.17 s, max 0.21 s). Recorded as
`month_scan_p90_seconds = 1` against `month_scan_budget_seconds = 10`.
**~0.19 s vs a 10 s bound — within budget by a wide margin.** This measurement
has no live-generation component; it is complete, and PRD Assumption 4 is
marked `RESOLVED 2026-08-27`.

## Throughput

The harness produces `session_reports = 40` Reports in one run, every one
reaching `gate_passed` with `failed_at is None` and zero regenerations — the
machine half of the forty-in-one-sitting target. The human half — Francesco
producing, reviewing and exporting forty Reports in one working session through
the UI — is confirmed separately:

> **PENDING** — _(Francesco's one-sitting produce → review → export
> confirmation note goes here. Not yet performed; this is AC-4's human half.)_

## Budget reconciliation

- **NFR-10 / PRD §4.3 (full-month scan, 10 s):** measured p90 ≈ 0.2 s. **Not
  exceeded.** No number changed; `epics.md` NFR-10 carries
  `(measured 2026-08-27: p90 under 1 s)` and PRD Assumptions Index item 4 is
  marked `RESOLVED 2026-08-27`.
- **NFR-5 / PRD §5 (per-Report, 3 min):** composed single-call p90 = 119 s.
  **Not exceeded.** No number changed; `epics.md` NFR-5 carries
  `(measured 2026-08-27: p90 119 s = 118 s generation + 1 s local)` and PRD
  Assumptions Index item 3 is marked `RESOLVED 2026-08-27`. The regenerating
  case is recorded as a Known limitation to re-measure against real traffic,
  not as a budget change (Francesco's call, 2026-08-27).

## Outcome

**`blocked`** — the *measurements* are done and within budget: the
full-month-scan p90 and the single-generation-call per-Report p90 are both
measured and within their NFR budgets, and PRD Assumptions 3 and 4 are resolved
with the measured values. The one open measurement risk — a real Report that
needs a citation- or Gate-driven regeneration can exceed the 3-minute budget —
is recorded above as a Known limitation with a defined re-measurement against
post-launch traffic.

What holds `outcome` at `blocked` is **AC-4's human half**: one real produce →
review → export sitting of forty Reports through the UI (see Throughput, marked
PENDING) has not happened. The machine half (40 `drive()` runs to `gate_passed`,
zero failures) is proven above, but `sitting_confirmed = false` in the block
above until Francesco runs that sitting and signs it off. Per
epic-8-retro-item-65 the guard now refuses `outcome = "pass"` while
`sitting_confirmed` is false, so `test_outcome_permits_release` is a strict
`xfail` until the sitting is done — at which point flip `sitting_confirmed` to
`true`, set `outcome = "pass"`, and remove the `xfail` marker.

Measurements ratified by Francesco on 2026-08-27 (the measured values, the
single-call composition, and the decision to record the regeneration risk
rather than revise the budget); release sign-off waits on the sitting.

## Re-measure trigger

Re-run the harness and the live-Gemini sample, and bump `checked`, whenever any
of these changes:

- the run pipeline (`shell/runner/driver.py`) or its stage set;
- any of the four transit-scan functions (`core/transits/*`);
- the Generator model or tier (AD-9), or `RecordedResponseGenerator`'s shape —
  and, since the model is a rolling alias, any announced `gemini-2.5-flash`
  revision even without a config change;
- the generation prompt (`_build_prompt` / `_build_system_instruction`) or the
  response schema;
- `sections_config` (section count or shape) or the Payload schema /
  serialization / typical Payload size — all drive generation time directly;
- the ephemeris identity or the computation config;
- `ExportRecord.elapsed_seconds`'s definition (Story 6.3).

Additionally, once real post-launch traffic exists, measure the true
end-to-end p90 from `ExportRecord.elapsed_seconds` (including regenerations and
the Gate) and update the Known limitation.

## Governing references

- **NFR-5 / NFR-10** (`_bmad-output/planning-artifacts/epics.md`) — the budgets
  the guard suite binds to; numbers change only on an over-budget measurement.
- **PRD §5, §4.3, Assumptions Index 3 & 4**
  (`_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md`) —
  the assumptions this record resolves.
- **Story 8.3 spec**
  (`_bmad-output/implementation-artifacts/spec-8-3-measure-the-latency-the-prd-only-assumed.md`).
