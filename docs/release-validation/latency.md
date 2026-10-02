# Latency measurement (Stories 8.3 and 10.7)

NFR-5 puts one Report from "Client selected" to "Report on screen" — transit
scan, Payload assembly, generation, Groundedness Gate and any bounded
regeneration — at **under 3 minutes at p90**, and NFR-10 puts a full-month
transit scan for one Client at **under 10 seconds**. Epic 10 (parallel
per-Section generation, a stored-PDF cache) adds three targets of its own:
**draft p90 ≤ 60 s**, **PDF first export ≤ 6 s**, **repeat download < 1 s**.
This file is the durable, dated record. The machine-readable block below is
parsed by `tests/test_latency_record.py`; the guard suite stays red while a
measured figure sits outside its budget, while a budget drifts from
`epics.md`, or while `outcome` is anything other than `"pass"`. The guard also
refuses `outcome = "pass"` unless `sitting_confirmed` (the forty-report
one-sitting) **and** `repetition_reviewed` (Francesco has read the Epic 10
reports side by side) are true.

The ratified "record the regeneration risk, do not revise the budget" decision
is indexed as **RGD-2** in [`docs/decisions/README.md`](../decisions/README.md).

```toml
checked = 2026-10-02
ratified_by = "unratified: measured by Claude on 2026-10-02, pending Francesco"
ratified_on = 2026-10-02
environment = "local docker (app image built from the repo, one uvicorn worker, local Postgres 18), real paid gemini-2.5-flash over the network; not production"
report_budget_seconds = 180
draft_budget_seconds = 60
pdf_first_budget_seconds = 6
pdf_repeat_budget_seconds = 1
runs_ok = 19
draft_p90_seconds = 137.7
section_p90_seconds = 39.3
one_regen_p90_seconds = 137.7
one_regen_basis = "observed"
regen_runs_observed = 4
pdf_first_p90_seconds = 1.7
pdf_repeat_p90_seconds = 0.019
month_scan_budget_seconds = 10
month_scan_p90_seconds = 1
session_reports = 40
sitting_confirmed = false
repetition_reviewed = false
outcome = "blocked"
```

## Result (Story 10.7, 2026-10-02)

20 reports were driven through the running local docker app by
`test_measure_epic10_latency` (`RUN_LATENCY_MEASUREMENT=epic10`); 19 reached
`gate_passed` and were exported twice, one failed the Gate three times.

| Figure | p90 | Target | Verdict |
|---|---|---|---|
| Draft, start → `gate_passed` (incl. regenerations) | **137.7 s** | ≤ 60 s | **missed** |
| One Section (claim → complete) | 39.3 s | — | — |
| One regeneration (4 observed runs) | 137.7 s | < 180 s (NFR-5) | within |
| PDF first export | 1.7 s | ≤ 6 s | met |
| PDF repeat download | 0.019 s | < 1 s | met |

- Median draft ≈ 77 s; fastest 46 s, slowest 215 s (three attempts).
- The **PDF work of Story 10.1 is a clear success**: 1.1–2.0 s first, ~15 ms
  repeat, against 20–25 s before.
- **The 60 s draft target is not met.** Even the 14 runs with no regeneration
  took 46–123 s (median ≈ 70 s). A draft is the slowest of the seven parallel
  Sections (Section p90 39 s, max 77 s — Gemini latency, not the local pipeline)
  **plus** Consiglio finale, which waits for all seven before it starts.
  Regeneration adds one more such round for a rejected Section and Consiglio
  finale. This is a
  finding for Francesco, not a budget to edit: see Open decisions.
- NFR-5 (3 min, regeneration counted) holds at p90 (137.7 s) but one run took
  215 s with three attempts.
- Gate regeneration: 5 of the 19 successful runs needed a regeneration (four
  one, one two) and 1 run exhausted the three-attempt bound. `one_regen` is the
  p90 over the four runs with exactly one regeneration (attempts = 2).

### Per-run table

| run | draft s | draft attempts | PDF first s | PDF repeat s |
|---|---|---|---|---|
| 1 | 94.9 | 2 | 1.13 | 0.014 |
| 2 | 75.5 | 1 | 1.57 | 0.016 |
| 3 | 83.5 | 1 | 1.15 | 0.012 |
| 4 | 50.9 | 1 | 1.48 | 0.015 |
| 5 | 51.5 | 1 | 1.17 | 0.015 |
| 6 | 64.4 | 1 | 1.46 | 0.013 |
| 7 | 106.0 | 2 | 1.16 | 0.011 |
| 8 | 137.7 | 2 | 1.58 | 0.011 |
| 9 | failed (Gate, 3 attempts) | 3 | — | — |
| 10 | 63.5 | 1 | 1.34 | 0.016 |
| 11 | 105.0 | 1 | 1.58 | 0.013 |
| 12 | 68.4 | 1 | 1.56 | 0.012 |
| 13 | 46.2 | 1 | 1.41 | 0.009 |
| 14 | 122.7 | 1 | 1.48 | 0.018 |
| 15 | 70.5 | 1 | 1.48 | 0.017 |
| 16 | 54.3 | 1 | 1.37 | 0.011 |
| 17 | 77.8 | 1 | 1.43 | 0.016 |
| 18 | 109.5 | 1 | 1.98 | 0.022 |
| 19 | 214.7 | 3 | 1.25 | 0.012 |
| 20 | 108.0 | 2 | 1.68 | 0.014 |

### Caveats

- **Local, not production.** The Netcup VPS is a slower vCPU; PDF times in
  particular will differ. Re-run against production before treating the PDF
  targets as demonstrated there.
- **The measured build predates the last Gate and prompt fixes** (a natal body
  placed beside a cited entry, an uncited house and its ruler, the "no date
  ranges or approximations" prompt rule). Those fixes cut Gate rejections, so
  the regeneration share and the draft p90 here are pessimistic; the one failed
  run (9) died on an uncited "tra il 10 e il 15 gennaio" that the new prompt
  rule targets. Re-measure on the committed build.
- **Section time is polled** every 0.2 s from Postgres (claim → seen
  `complete`), so each reads up to 0.2 s high.
- n = 20; a p90 of 20 samples is the 18th-ranked value.
- To get these runs through the Gate, Story 10.7 also loosened the Gate and
  stopped rejecting leaked id aliases (see Gate changes below).

## Gate changes made while measuring

In an earlier sample only 3 of 19 started runs reached export: most drafts were
rejected on false positives. Reading the rejected sentences produced the
following changes (each has tests with negatives):

- Leaked id aliases ("(e54)") are stripped from the text and cited instead of
  failing the draft.
- A house ordinal counts only next to "casa" ("terza settimana" is not a
  house); a number followed by "anni/giorni/volte…" is not a day; the verb
  "bilancia" is not the sign Libra. These narrow AD-8's day-of-month and
  casa-ordinal tokens; two tripwire tests (epic-5 retro item 40) were inverted.
  **Francesco has not yet acknowledged this change to AD-8.**
- Natal profile data grounds claims: a body's natal sign/house/retrograde, a
  house's cusp sign and rulers, uncited natal-only sentences, a natal body
  placed beside a cited entry, a retrograde on a body the Payload records as
  retrograde, and standing-retrograde start/end dates (one day of timezone
  slack).
- Prompt: no perfection date for a `never_perfected` aspect; no date ranges or
  approximations; only exact days from the cited events' fields.

## Repetition between Sections (AC-2, not yet done)

Five Epic 10 reports are saved under `cache/latency-reports/after-epic-10-*.md`
(gitignored). A naive count of six-word runs that appear under more than one
Section: 24, 40, 42, 37, 68. **Francesco still has to read them side by side
against reports generated before Epic 10** and decide whether the repetition
warrants a new Style Guide version (only he publishes one). `repetition_reviewed`
stays `false` until he does.

## Superseded: the Story 8.3 measurement (2026-08-27)

Story 8.3 measured a single eight-Section Gemini call: p90 118 s, composed to
a per-Report p90 of 119 s, with 8 of 10 drafts passing citation validation and
the regenerating case recorded as a known limitation (RGD-2). Epic 10 replaced
that generation path, so those keys (`local_stage_p90_seconds`,
`real_gen_*`, `report_p90_seconds`) are gone; the guards now bind the measured
end-to-end figures instead. The 8-3 local-stage and scan harness
(`test_measure_latency`, `RUN_LATENCY_MEASUREMENT=1`) remains for the scan.

## Full-month scan (unchanged from 8.3)

40 isolated scans of the Fort Worth Client's 2026-01 month: p90 ≈ 0.19 s
wall-clock, recorded as `month_scan_p90_seconds = 1` against
`month_scan_budget_seconds = 10`. NFR-10 is within budget by a wide margin;
PRD Assumption 4 is marked `RESOLVED 2026-08-27`. Nothing in Epic 10 touches
the scan.

## Throughput

`session_reports = 40` is the Story 8.3 harness figure (40 `drive()` runs to
`gate_passed`). The human half — Francesco producing, reviewing and exporting
forty Reports in one working session through the UI — is still:

> **PENDING** — _(Francesco's one-sitting produce → review → export
> confirmation note goes here.)_

## Open decisions for Francesco

1. **The 60 s draft target is missed** (p90 137.7 s; median ≈ 77 s). Options:
   raise `GENERATION_CONCURRENCY` or generate Consiglio finale in parallel with
   a Payload-only brief (it currently waits for the other seven Sections);
   shorten the Payload each Section receives; accept a revised target. The
   guard stays red until a measurement meets the target or he revises it.
2. Acknowledge (or reject) the AD-8 narrowing listed above.
3. Read the five saved reports for repetition and decide on a Style Guide
   version.
4. The forty-report one-sitting.

## Outcome

**`blocked`.** Measured and recorded honestly: the PDF targets are met locally,
NFR-5 holds at p90, the draft target is missed, `sitting_confirmed` and
`repetition_reviewed` are both `false`, and the numbers are unratified.
`test_draft_p90_within_target` is red on purpose until the target is met or
Francesco revises it; `test_outcome_permits_release` stays a strict `xfail`.

## Re-measure trigger

Re-run `test_measure_epic10_latency` and bump `checked` whenever any of these
changes:

- the run pipeline (`shell/runner/driver.py`), `GENERATION_CONCURRENCY`, or its
  stage set;
- the Generator model or tier (AD-9) — the model is a rolling alias, so also
  any announced `gemini-2.5-flash` revision;
- the generation prompt (`_SECTION_FRAMING`, `_build_system_instruction`) or the
  response schema;
- the Gate (`core/gate/`) or the Gate vocabulary — it decides how often drafts
  regenerate;
- `sections_config` or the Payload schema / typical size;
- the export template or `exported_pdf` cache (Story 10.1);
- `ExportRecord.elapsed_seconds`'s definition (Story 6.3).

Once real traffic exists, also read the true end-to-end figure from
`ExportRecord.elapsed_seconds` and the Gate failure rate from `gate_result`.

## Governing references

- **NFR-5 / NFR-10** (`_bmad-output/planning-artifacts/epics.md`) — the budgets
  the guard suite binds to; numbers change only on an over-budget measurement.
- **Story 10.7** in `epics.md` (the Epic 10 targets) and its spec
  `_bmad-output/implementation-artifacts/spec-10-7-measure-it.md`.
- **Story 8.3 spec**
  (`_bmad-output/implementation-artifacts/spec-8-3-measure-the-latency-the-prd-only-assumed.md`).
