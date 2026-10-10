# Latency measurement (Stories 8.3 and 10.7)

NFR-5 puts one Report from "Client selected" to "Report on screen" — transit
scan, Payload assembly, generation, Groundedness Gate and any bounded
regeneration — at **under 3 minutes at p90**, and NFR-10 puts a full-month
transit scan for one Client at **under 10 seconds**. Epic 10 (parallel
per-Section generation, a stored-PDF cache) adds three targets of its own:
**draft p90 ≤ 90 s** (revised from 60 s by Francesco on 2026-10-02), **PDF first export ≤ 6 s**, **repeat download < 1 s**.
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
ratified_by = "Francesco"
ratified_on = 2026-10-02
environment = "local docker (app image built from the repo, one uvicorn worker, local Postgres 18), real paid gemini-2.5-flash with a 1024 thinking budget; not production"
report_budget_seconds = 180
draft_budget_seconds = 90
pdf_first_budget_seconds = 6
pdf_repeat_budget_seconds = 1
runs_ok = 20
draft_p90_seconds = 58.4
section_p90_seconds = 14.8
one_regen_p90_seconds = 52.3
one_regen_basis = "observed"
regen_runs_observed = 4
pdf_first_p90_seconds = 2.7
pdf_repeat_p90_seconds = 0.035
month_scan_budget_seconds = 10
month_scan_p90_seconds = 1
session_reports = 40
sitting_confirmed = true
repetition_reviewed = true
outcome = "pass"
```

## Result (Story 10.7, 2026-10-02)

20 reports were driven through the running local docker app by
`test_measure_epic10_latency` (`RUN_LATENCY_MEASUREMENT=epic10`) on the committed
build; **all 20 reached `gate_passed`** and were exported twice.

| Figure | p90 | Target | Verdict |
|---|---|---|---|
| Draft, start → `gate_passed` (incl. regenerations) | **58.4 s** | ≤ 90 s | met |
| One Section (claim → complete) | 14.8 s | — | — |
| One regeneration (4 runs with exactly one) | 52.3 s | < 180 s (NFR-5) | within |
| PDF first export | 2.7 s | ≤ 6 s | met |
| PDF repeat download | 0.035 s | < 1 s | met |

- Median draft ≈ 27 s. The 12 runs with no regeneration took 23.5–30.0 s
  (median ≈ 25 s); the 8 runs with a regeneration took 42–66 s (four with one,
  four with two). **Regeneration is what sets the p90**, not generation speed.
- The 60 s target first set for this story would also have been met (58.4 s).
- **What changed since the first measurement** (draft p90 137.7 s → 58.4 s):
  Gemini's hidden "thinking" tokens were the latency. A Section wrote ~1,000
  tokens but spent 1,000–13,000 thinking, taking 10–60 s; `GEMINI_THINKING_BUDGET`
  (default 1024) brings a Section to ≈ 10 s, a clean draft to ≈ 25 s. Section time
  p90 fell from 39.3 s to 14.8 s. The PDF work of Story 10.1 is unchanged: 1.4–2.9 s
  first, ~30 ms repeat, against 20–25 s before.
- NFR-5 (3 min, regeneration counted) holds with a wide margin: slowest run
  65.6 s.
- **Gate regeneration is still frequent:** 8 of 20 runs (40 %) needed at least
  one. None exhausted the three-attempt bound (the first measurement lost one
  run in 20 and three in four early samples).
- Generation concurrency (default 11) was not raised: a report has seven
  parallel Sections, so it only matters when several reports run at once.
- Consiglio finale stays sequential: it takes the other seven Sections as
  input and adds ≈ 8–10 s; written blind it would repeat the headline transits.
- Sending each Section only its own Payload slice was trialled and not
  adopted: no effect on time or repetition on whole reports.

### Per-run table

| run | draft s | draft attempts | PDF first s | PDF repeat s |
|---|---|---|---|---|
| 1 | 26.4 | 1 | 2.42 | 0.017 |
| 2 | 25.3 | 1 | 1.41 | 0.032 |
| 3 | 27.4 | 1 | 1.92 | 0.031 |
| 4 | 23.5 | 1 | 2.48 | 0.026 |
| 5 | 27.6 | 1 | 2.36 | 0.032 |
| 6 | 42.3 | 2 | 2.03 | 0.034 |
| 7 | 65.6 | 3 | 1.49 | 0.016 |
| 8 | 25.9 | 1 | 2.61 | 0.035 |
| 9 | 24.1 | 1 | 1.75 | 0.029 |
| 10 | 47.6 | 2 | 1.87 | 0.028 |
| 11 | 58.4 | 3 | 2.89 | 0.038 |
| 12 | 64.6 | 3 | 2.19 | 0.023 |
| 13 | 30.0 | 1 | 2.51 | 0.029 |
| 14 | 24.1 | 1 | 1.82 | 0.031 |
| 15 | 49.9 | 3 | 1.90 | 0.028 |
| 16 | 26.0 | 1 | 2.04 | 0.028 |
| 17 | 46.2 | 2 | 1.51 | 0.033 |
| 18 | 52.3 | 2 | 2.64 | 0.035 |
| 19 | 24.3 | 1 | 1.39 | 0.016 |
| 20 | 24.7 | 1 | 2.52 | 0.035 |

### Caveats

- **Local, not production.** The Netcup VPS is a slower vCPU; PDF times in
  particular will differ, and Gemini latency from the EU VPS may too. Re-run
  against production before treating the targets as demonstrated there.
- **Section time is polled** every 0.2 s from Postgres (claim → seen
  `complete`), so each reads up to 0.2 s high.
- n = 20; a p90 of 20 samples is the 18th-ranked value.
- Gate and prompt changes made while measuring are listed below; they are in the
  measured build.

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
  **Acknowledged by Francesco on 2026-10-02**; recorded as an amendment under AD-8 in `ARCHITECTURE-SPINE.md`.
- Natal profile data grounds claims: a body's natal sign/house/retrograde, a
  house's cusp sign and rulers, uncited natal-only sentences, a natal body
  placed beside a cited entry, a retrograde on a body the Payload records as
  retrograde, and standing-retrograde start/end dates (one day of timezone
  slack).
- Prompt: no perfection date for a `never_perfected` aspect; no date ranges or
  approximations; only exact days from the cited events' fields — for the six
  Sections that may state dates only. A shared version of that rule had made
  `giorni_favorevoli` fail 5 of 12 attempts by contradicting its no-dates rule;
  it now gets a checklist of the ids it must cover (0 of 24 day-list attempts
  failed afterwards, from 6 of 24). Each Section also has a one-paragraph role
  (Energia generale the overview; the topical Sections only what the events mean
  for their area; Consiglio finale practical advice without re-describing
  transits).
- `GEMINI_THINKING_BUDGET` (default 1024) caps the model's hidden thinking.

## Repetition between Sections (AC-2: acted on and reviewed)

Francesco asked for the repetition to be reduced. It was not caused by Payload
size (sending each Section only its own slice changed nothing); it comes from
the Sections being written in parallel from the same events with no role.
Each Section's prompt now states its role. In trials on whole reports, repeated
eight-word phrases across Sections fell by about 40 % (≈ 22 → ≈ 12). In the five
reports saved from this measurement (`cache/latency-reports/after-epic-10-*.md`,
gitignored), Consiglio finale ↔ Energia generale — the largest pair before (17
shared six-word runs in one report) — no longer appears among the top pairs;
what remains is the topical Sections overlapping each other on a shared event
(Denaro/Lavoro, Benessere/Lavoro): 7–24 repeated eight-word phrases in the prose
Sections per report (mean ≈ 16), more on this chart than on the trial chart
because it holds many slow-planet conjunctions. **Francesco reviewed the repetition on 2026-10-02** (`repetition_reviewed = true`),
and the prompt role briefs above were the fix; no new Style Guide version was
required.

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

> **Confirmed by Francesco on 2026-10-02** (`sitting_confirmed = true`): the
> one-sitting produce → review → export of the forty-report target.

## Ratification

**Ratified by Francesco on 2026-10-02:** the measured figures above, the draft
target revision from 60 s to 90 s, and recording the Gate regeneration share
(40 % of runs regenerate at least once, none failed) rather than treating it as a
budget problem. The scope of the ratification is the **local docker stack**, not
production: a production re-run is still worth doing, since the VPS is a slower
vCPU and Gemini latency from it may differ.

## Outcome

**`pass`.** Every measured target is met locally: draft p90 58.4 s (≤ 90 s), PDF
first 2.7 s (≤ 6 s), repeat 0.035 s (< 1 s), NFR-5 with regeneration 52.3 s
(< 180 s). The forty-report sitting and the repetition review are confirmed and
Francesco has ratified the figures. `test_outcome_permits_release` is now an
ordinary test; the strict `xfail` that held it has been removed.

## Chart data API: 12-month transits (Story 11.6) -- NOT MEASURED

> **UNMEASURED. This is a placeholder, not a result, and it is not a pass.** No
> figure below has been taken. It is outside the machine-readable TOML block on
> purpose, so `tests/test_latency_record.py` neither reads nor satisfies it.

| Figure | Target | Measured | Verdict |
|---|---|---|---|
| `POST /api/v1/charts/transits`, 12-month window, p90 over 20 calls, on the Netcup VPS | <= 30 s | **not measured** | **open** |

Francesco measures this on the VPS (the build that wrote this had no access to it).
Recipe, from the WordPress container or any host that can reach the service:

1. Save a request body, for example the transits request in
   `docs/api/chart-data-v1.md` with `"window": {"start_date": "2026-01-01", "end_date": "2027-01-01"}`, as `body.json`.
2. Run one warm-up call, then 20 timed calls, with the token in `ASTRO_API_TOKEN`
   (not on the command line). Each line is `seconds http_status`; every status must be 200:
   `for i in $(seq 20); do curl -s -o /dev/null -w '%{time_total} %{http_code}\n' -X POST -H "Authorization: Bearer $ASTRO_API_TOKEN" -H 'Content-Type: application/json' --data @body.json <base>/api/v1/charts/transits; done | sort -n`
3. Discard the run if any status is not 200. Sorted ascending, the p90 of 20 samples is
   the 18th line. Record it, the date and the environment here, and set the verdict only
   if it is <= 30 s.

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
