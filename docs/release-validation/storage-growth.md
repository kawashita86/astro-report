# Storage-growth projection (Story 8.4)

Report Payloads are stored permanently — NFR-9 makes losing one unacceptable,
because a lost Payload permanently breaks the traceability guarantee for its
Report — on Neon's **0.5 GB** free plan. The PRD carries no storage budget and
no Assumptions Index item covers storage; nothing had measured how long a real
`report_payload` row is or how long the free tier fits. This file is the
durable, dated record of that measurement and the growth projection built from
it. The machine-readable block below is parsed by
`tests/test_storage_growth_record.py`; the guard suite stays red while the
projection arithmetic is internally inconsistent, while `ceiling_bytes` drifts
from README's Running-cost table, while `reports_per_month` drifts from
`epics.md`'s NFR-5 line, while the projected half-ceiling date falls inside the
guard's 60-month planning horizon without a ratified storage-growth policy, or
while `outcome` is anything other than `"pass"`.

```toml
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
sample_n = 12
payload_p90_bytes = 64259          # nearest-rank p90, canonical_json_bytes of persisted report_payload rows
storage_overhead_factor = 1.5      # additive on-disk overhead: Postgres row header + the two indexes + duplicated typed columns (TOAST compression works the other way — see prose)
projected_row_bytes = 96389        # ceil(payload_p90_bytes * storage_overhead_factor)
reports_per_month = 200            # upper bound shared by NFR-5 ("100–200/month") and NFR-7 ("30–200/month")
monthly_growth_bytes = 19277800    # projected_row_bytes * reports_per_month
ceiling_bytes = 500000000          # Neon free plan, README "Running cost" table: Free (0.5 GB) = 0.5 * 1000**3
ceiling_reached_on = 2028-10-25    # checked + round(ceiling_bytes / monthly_growth_bytes * 30.44) days
half_ceiling_reached_on = 2027-09-26
policy_decision = "raised"
policy_ratified_by = "Francesco"
policy_ratified_on = 2026-08-27
outcome = "pass"
```

The machine block is the **payload-only, 200-Reports/month** projection — the
one the guard binds to. A realistic full-per-Report-footprint projection is
given in prose below; it lands earlier, and the storage-growth policy is written
against it, not just the machine block.

## What was assumed

- **Permanent Payload retention.** A `report_payload` row is written exactly
  once per Report (`shell/adapters/postgres/report_payload.py`, `unique`
  `report_run_id`, immutable via `_forbid_update`) and is never pruned — only
  the FR-29 Client-deletion cascade ever removes one. Every Report kept means
  its Payload kept, for as long as the Report is retained.
- **NFR-9 — data durability.** "Loss of a Report Payload permanently breaks the
  traceability guarantee for that Report and is not acceptable." A Natal Chart
  is recoverable by recomputation; a Payload is not. That is why the machine
  block projects the Payload row alone — it is the row that can never be
  reclaimed.
- **Neon free plan, 0.5 GB.** README's "Running cost" table:
  `Neon Postgres 18 (Europe/Frankfurt) | Free (0.5 GB) | €0`. The zero-cost
  target assumes this whole-database ceiling is not crossed at target volume.
  NFR-5 states the volume range as "100–200 per month"; NFR-7 states it as
  "30–200 per month". The projection uses **200/month**, the upper bound common
  to both; a 100/month variant is given for the lower end.
- **No PRD storage budget.** The PRD's Assumptions Index has no storage item, so
  this record is where the projection and the resulting decision live — not a
  PRD change.

## How it was measured

**Harness — `test_measure_payload_size`, opt-in (`RUN_STORAGE_MEASUREMENT=1`).**
One Client + Natal Chart + Style Guide is seeded from the known-good Fort Worth,
TX fixture (reusing `tests/test_runner_driver.py`'s `_create_client_and_chart`,
its clean-draft `_FakeGenerator` and its `drive()` wrapper — the story's Code
Map "copy source"): 2026-01-01 00:00 America/Chicago. 12 fresh `ReportRun` rows
are then driven over consecutive months (2026-01 … 2026-12) with
`shell/runner/driver.py::drive()` to `gate_passed` (the last registered stage
today; the harness also accepts a later `exported` stage). Each persisted
`report_payload` row is read back and its size taken as
`len(canonical_json_bytes(row.payload))`. p90 is nearest-rank
(`sorted(d)[math.ceil(0.9 * len(d)) - 1]`). The harness asserts all 12 runs
persist a `report_payload` row and reach `gate_passed` with `failed_at is None`
— it never asserts on byte counts: sizes are environment/fixture-dependent
data.

**What `len(canonical_json_bytes(row.payload))` is, and is not.** It is the
**canonical serialization the codebase specifies for a persisted Payload**
(`core/payload/freeze.py`: sorted keys, no insignificant whitespace, `Decimal`
as a fixed-precision string) — the same bytes every entry id is hashed from and
the reproducible number this record is built on. It is **not** claimed to equal
bytes-on-disk. `ReportPayload.payload` is `Column(JSON)` (not `JSONB`), so
Postgres stores the value as text, but:

- the engine's own `json.dumps` when writing the column may add insignificant
  whitespace the canonical form omits — a small *upward* difference;
- Postgres TOASTs and compresses a large `payload` value (pglz or lz4).
  Repetitive JSON — the fixed key names, the 64-hex content-hash ids — compresses
  several-fold; this is a *downward* difference and is **not modelled** here.

`storage_overhead_factor` (below) is additive-only and deliberately pessimistic;
the pending production `pg_total_relation_size` cross-check is what settles the
true on-disk figure.

**`storage_overhead_factor` (1.5).** The canonical `payload` text is not the
whole on-disk cost of a row. Folded into the 1.5× factor: the Postgres per-row
header (~24 B), the two b-tree indexes on `report_payload` (`client_id`, the
unique `report_run_id`), and the typed columns that duplicate fields already
inside `payload` — `schema_version`, `computation_config_version` /
`_content_hash`, `sections_config_version` / `_content_hash`, the UUID keys,
`created_at`, and the second JSON column **`ephemeris_files`** (a short list of
`{filename, sha256}`, not measured separately — it is a few hundred bytes and
rides inside this factor). 1.5× is a loose *upper* estimate: it counts additive
overhead and ignores TOAST compression, which pulls the real ratio down. It is
intentionally on the pessimistic side so the projected dates are early rather
than late.

**Production cross-check (pending real data).** Once Neon holds real rows,
Francesco runs `SELECT pg_total_relation_size('report_payload'), count(*) FROM
report_payload;` and divides — recorded as a check on the 1.5× factor, not as
the primary number (mirrors Story 8.3's `ExportRecord` cross-check). If the real
ratio exceeds 1.5×, raise `storage_overhead_factor`, re-run the arithmetic, and
bump `checked`. If it is well under 1.5× (likely, given compression), the
projection was conservative and the dates move out.

## Measured size

12 runs of the Fort Worth fixture, `report_payload.payload` canonical-JSON byte
length (the harness's `_summary()` line — reproduce with
`RUN_STORAGE_MEASUREMENT=1`):

| Statistic | Bytes | KiB |
|---|---|---|
| min | 40,595 | 39.6 |
| mean | 52,710 | 51.5 |
| median | 53,592 | 52.3 |
| **nearest-rank p90** | **64,259** | **62.8** |
| max | 64,837 | 63.3 |

Spread is driven by how many Transit Events a given month produces — the Payload
embeds every frozen event with its content-hashed id.
`report_run.transit_events` for the same 12 runs ran min 9,970 B / p90 **17,246
B (16.8 KiB)** / max 17,465 B, tracking the Payload's own spread.

**Full per-Report footprint.** The Payload is not the only per-Report JSON row.
p90 of each row in the same 12-run sample:

| Row | p90 bytes |
|---|---|
| `report_payload.payload` | 64,259 |
| `report_run.transit_events` | 17,246 |
| `report_theme.theme` | 2,985 |
| `report_draft.draft` | 205 |
| `gate_result.violations` (clean pass) | 2 |
| **sum** | **84,697** (≈ 82.7 KiB) |

**The machine block projects `report_payload` alone — that is a *floor*, not a
conservative bound.** Projecting only the un-prunable Payload row against the
*whole-database* 0.5 GB ceiling pushes the ceiling date **later** than reality,
because every run also writes the sibling rows above (and, per exported Report,
an `ExportRecord` and a `Report` row, small next to these). The realistic
full-footprint projection below lands earlier and is what the policy is written
against. The machine block stays payload-only because that is the row NFR-9
forbids reclaiming — the number that must hold no matter what else is pruned.

**Caveats on the sample:**

- **One non-adversarial fixture.** Fort Worth over twelve consecutive months is
  a *typical-month* sample, not the adversarial maximum. Real p90 across varied
  clients and high-transit months (cf. the Story 8.1 adversarial fixtures — a
  retrograde-station month, a two-Lunation month) may run higher. Absorbed by
  the overhead factor and by the 50 %-trigger policy, not modelled precisely —
  **accepted as the deliberate basis, see "Measurement basis — accepted
  deviation" below (retro item 64).**
- **Best-case siblings.** `report_draft.draft` (205 B) and
  `gate_result.violations` (2 B) reflect the harness's minimal fake draft and a
  clean first-pass Gate. A real eight-Section generated draft, and any Gate
  regeneration (each adds a `gate_result` row with populated `violations` and
  another `report_draft`), enlarge the sibling tail — another reason the
  full-footprint projection is the one to act on.

## Projection

All integer bytes. `checked = 2026-08-27`; `_DAYS_PER_MONTH = 30.44`. A date is
derived exactly as the guard re-derives it: `checked + round((target_bytes /
monthly_growth_bytes) * 30.44)` days (`abs(recorded − implied) ≤ 5` days
tolerance). The intermediate products below are shown to 3 decimals so the
`round(...)` is unambiguous — do **not** round the months figure first.

### Payload-only (the machine block)

- `projected_row_bytes` = `ceil(64259 × 1.5)` = **96,389 B/row** on disk.
- At **200 Reports/month**: `monthly_growth_bytes` = `96389 × 200` =
  **19,277,800 B/month** ≈ 18.4 MiB/month.
  - ceiling: `round((500000000 / 19277800) × 30.44)` = `round(789.507)` =
    **790 days** → **`ceiling_reached_on = 2028-10-25`**.
  - half: `round((250000000 / 19277800) × 30.44)` = `round(394.754)` =
    **395 days** → **`half_ceiling_reached_on = 2027-09-26`**.
- At **100 Reports/month** (NFR-7's lower end): monthly growth halves to
  **9,638,900 B/month**; the runway roughly doubles — `round(1579.0)` = 1579
  days → ceiling ≈ **2030-12-23**, half ≈ **2028-10-25**.

### Full per-Report footprint (the realistic case)

- footprint p90 = 84,697 B → `ceil(84697 × 1.5)` = **127,046 B/row**.
- At **200 Reports/month**: `127046 × 200` = **25,409,200 B/month** ≈ 24.2
  MiB/month.
  - ceiling: `round((500000000 / 25409200) × 30.44)` = `round(598.990)` =
    **599 days** → ≈ **2028-04-17**.
  - half: `round((250000000 / 25409200) × 30.44)` = `round(299.495)` =
    **299 days** → ≈ **2027-06-22**.
- At **100 Reports/month**: `12,704,600 B/month` — ceiling ≈ **2029-12-07**,
  half ≈ **2028-04-17**.

Every one of these half-ceiling dates (2027-06 … 2028-10) falls well inside the
guard's 60-month planning horizon (≈ 2031-08), so Story 8.4's "raised as an
explicit decision rather than absorbed" fires — see the policy below.

**GB vs GiB.** Neon's plan is documented as "0.5 GB". The guard binds
`ceiling_bytes` to `0.5 × 1000³ = 500,000,000` — the smaller, conservative
decimal reading, not `0.5 GiB = 536,870,912`. The ~7 % difference is inside the
noise of a 1.5× overhead estimate and does not change the decision.

## Storage-growth policy (decision)

Indexed as **RGD-3** in [`docs/decisions/README.md`](../decisions/README.md).


Half the 0.5 GB ceiling is projected to be reached in **~10 months** (full
footprint, 200/month) to ~13 months (payload-only, 200/month) — inside any
reasonable planning horizon — so this is raised as a decision, not absorbed:

> **When Neon storage crosses 50 % of the 0.5 GB free-plan ceiling, move the
> Neon project to its paid tier and renegotiate the €0/month target (NFR-7) as
> an explicit, recorded cost decision. Do not prune, archive, TTL, or
> export-and-delete Report Payloads — NFR-9 makes Payload loss unacceptable, and
> the traceability guarantee has no expiry.**

- **Cost to attach at ratification.** Neon's entry paid-plan monthly price
  (Francesco to confirm the current figure — Neon's pricing page). This is the
  number NFR-7's €0/month renegotiation turns on: the policy trades the
  zero-cost guarantee for that amount rather than trading away Payload
  durability.
- **Monitoring hook.** Check the Neon project dashboard's storage gauge
  **monthly**, or set a Neon usage alert at ~40–50 % of 0.5 GB if the plan
  offers one. Owner: Francesco. The `half_ceiling_reached_on` dates above are a
  heads-up for *when* to expect the threshold, **not** the trigger — the gauge
  reading is.
- **Scope.** Designing or implementing any storage-reclamation mechanism
  (pruning, archival, TTL, export-and-delete) is explicitly **out of scope** for
  this story; raising the decision is the deliverable.

## Measurement basis — accepted deviation (retro item 64)

Epic-8 retrospective F4 flagged the projection's measurement basis as a disclosed
limitation and deferred the choice — **re-measure** `payload_p90_bytes` against
the Story 8.1 adversarial fixtures (retrograde-station month, two-Lunation month)
plus a second birth chart, **or explicitly accept** the current basis.

**Decision (Francesco, 2026-08-28): accept the current basis.** The Fort Worth
typical-month fixture over twelve consecutive months, together with the additive
`storage_overhead_factor = 1.5`, is the deliberate projection basis. It is *not*
re-measured against adversarial fixtures or a second chart for this record.

Rationale:

- **The overhead factor already leans pessimistic.** 1.5× is additive-only and
  ignores TOAST compression on the repetitive `payload` JSON (§"How it was
  measured"), which pulls the true on-disk ratio *down*. Adversarial months
  produce more Transit Events and a larger Payload, but that headroom is what the
  deliberately-high additive factor is absorbing.
- **The trigger is the live gauge, not the projected dates.** RGD-3's policy
  fires on the Neon dashboard storage gauge crossing 50 % (checked monthly), not
  on `half_ceiling_reached_on`. A heavier real p90 shortens the runway but is
  caught by the same monthly gauge reading well before the ceiling — a more
  precise projection would not change the control.
- **Cost/benefit.** Re-measuring needs a reachable Postgres and the opt-in
  harness run; it would refine dates the policy does not key off. Not worth it
  for v1.

The "if the adversarial-fixture Payloads (Story 8.1) turn out materially larger
than this typical-month sample, re-run with those inputs" line under
"Re-measure trigger" stays as a **standing option, not an obligation** — take it
if a future change makes adversarial-month sizing matter to a decision.

## Outcome

**`pass`** — a real persisted `report_payload` row has been measured
(`payload_p90_bytes = 64259` over `sample_n = 12`, canonical-JSON byte length of
the `payload` column), growth is projected against the 0.5 GB ceiling bound to
README — both payload-only (the machine block) and the realistic full per-Report
footprint — and the half-ceiling projection is reconciled by a ratified
storage-growth policy rather than left standing. Release may proceed.

Ratified by Francesco on 2026-08-27 (`ratified_on` / `policy_ratified_on`),
confirming the measured p90, the additive 1.5× overhead factor, the projected
dates, the storage-growth policy (including its cost and monitoring terms), and
the `pass` outcome.

## Re-measure trigger

Re-run the harness and bump `checked` (and the projection, the policy dates and
`outcome` as needed) whenever any of these changes:

- `core/payload/freeze.py::freeze_payload` or the Payload schema /
  serialization (`PAYLOAD_SCHEMA_VERSION`);
- `sections_config` — the Section count or shape (drives how many events a
  Payload embeds);
- the four transit-scan functions (`core/transits/*`) — they drive event counts
  and thus Payload size;
- the ephemeris identity or the computation config;
- Neon's free-plan storage ceiling, or the switch of `ReportPayload.payload`
  from `JSON` to `JSONB` (which would change the on-disk representation);
- the 100–200 (NFR-5) / 30–200 (NFR-7) Reports/month target.

Also: once real production data exists, run the `pg_total_relation_size`
cross-check and re-derive the dates against the measured overhead ratio; and if
the adversarial-fixture Payloads (Story 8.1) turn out materially larger than
this typical-month sample, re-run with those inputs.

## Governing references

- **NFR-9 — Data durability**
  (`_bmad-output/planning-artifacts/epics.md`): loss of a Report Payload is not
  acceptable; the retention guarantee this projection protects.
- **NFR-5 — Throughput and latency**
  (`_bmad-output/planning-artifacts/epics.md`): "100–200 per month" — the line
  the guard parses; the projection uses its **200** upper bound.
- **NFR-7 — Cost** (`_bmad-output/planning-artifacts/epics.md`): "€0/month at
  30–200 Reports per month" — the constraint the paid-tier move renegotiates.
  Its range (30–200) differs from NFR-5's (100–200); the projection uses the
  shared 200 upper bound and gives a 100/month lower-end variant.
- **README "Running cost"** (`README.md`): `Neon Postgres 18 (Europe/Frankfurt)
  | Free (0.5 GB)` — the ceiling the guard binds `ceiling_bytes` to.
- **Story 8.4 spec**
  (`_bmad-output/implementation-artifacts/spec-8-4-project-storage-growth-against-the-free-tier-ceiling.md`).
