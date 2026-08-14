# Reviewer Gate — astro-report architecture spine

Run at Finalize, 2026-08-14, against `ARCHITECTURE-SPINE.md`.

Lenses were run **inline and sequentially rather than as parallel subagents**, per Francesco's standing
instruction against agent dispatch in this project (the same constraint was recorded during the PRD
run). This is a stated weakening of the gate: an inline reviewer shares the author's context and will
talk past some of the divergences a genuinely fresh reviewer would catch.

**Verdict: pass, after 9 findings applied.** Two were critical — a whole class of stale version claims,
and two independent ways units could obey every AD and still build incompatibly.

---

## Lens 1 — Verification audit (configured reviewer)

*Brief: verify every committed decision was web-researched or reality-checked rather than asserted from
training data.*

**Verdict: FAILED on first pass. The Stack table was largely asserted.** Versions were re-read from the
PyPI JSON API and from vendor documentation on 2026-08-14 and corrected.

| Entry | Written | Actual | Status |
| --- | --- | --- | --- |
| FastAPI | 0.129.1 | **0.141.1** | corrected — a web result naming the February 2026 release was taken as current |
| uv | 0.9 | **0.12.4** | corrected |
| SQLModel | 0.0.27 | **0.0.39** | corrected |
| Alembic | 1.16 | **1.19.1** | corrected |
| WeasyPrint | 66 | **69.0** | corrected |
| geopy | 2.4 | **2.5.0** | corrected |
| timezonefinder | 8.1 | **8.2.5** | corrected |
| Jinja2 | 3.1 | **3.1.6** | refined to a patch pin |
| PostgreSQL on Neon | 17 | **18** | corrected — 18 became the default for new Neon projects on 2026-06-05 |
| HTMX | 2.0 | **2.0.9** | pinned, with the 4.0-beta transport change noted as a deliberate non-upgrade |
| Kerykeion | 5.12.9 | 5.12.9 | confirmed |
| pyswisseph | 2.10.3.2 | 2.10.3.2 | confirmed |
| argon2-cffi | absent | **25.1.0** | added — AD-15 depends on it and it was unlisted |

Decisions confirmed against primary sources rather than memory:

- **Gemini EEA data terms** — quoted verbatim from `ai.google.dev/gemini-api/terms` (effective
  2026-03-23): paid-service data terms apply to unpaid quota in the EEA, Switzerland and the UK. The
  PRD §6.2 premise holds.
- **Gemini free-tier limits** — `gemini-2.5-flash` at 10 RPM / 250k TPM / 500 RPD. 500 RPD clears
  200 reports/month; 10 RPM is the real constraint on a forty-report batch, which AD-10 absorbs.
- **Render free tier** — no persistent disk on free web services; free Postgres expires 30 days after
  creation with a 14-day grace period. This is what broke the addendum's hosting plan.
- **Neon free plan** — permanent, 0.5 GB, 100 compute-hours/month, Europe/Frankfurt available,
  point-in-time restore ~6 hours, no scheduled backups. The restore window is what forced AD-17.
- **AGPL-3.0 chain** — Kerykeion → pyswisseph → Swiss Ephemeris, the last dual-licensed against a
  Professional License (CHF 750 first seat). §13's remote-user source-offer obligation is what gives
  AD-15 its second, legal justification.
- **pyswisseph ephemeris selection** — it switches automatically to the best precision ephemeris it
  finds installed, which is the silent-downgrade risk AD-2 closes.

**Residual, disclosed:** Python 3.13 is a judgement call, not a vendor fact — 3.12, 3.13 and 3.14 are
all supported by FastAPI and all satisfy Kerykeion's ≥ 3.10 floor. The Swiss Ephemeris file *names*
(`sepl_18.se1`, `semo_18.se1`) match Astrodienst's published naming for the 1800–2400 range but the
pinned checksums must be taken from the files actually downloaded, at build time.

---

## Lens 2 — Adversarial: two compliant units that still diverge (configured reviewer)

*Brief: construct two units one level down that each obey every AD to the letter yet still build
incompatibly.*

**Verdict: two genuine holes found and closed, four smaller ambiguities tightened.**

### CRITICAL — Astronomical tuning values had no owner → **AD-18 added**

Construct the Natal Chart unit and the Transit Engine unit. Both obey AD-1 (pure), AD-2 (pinned
ephemeris) and AD-12 (UTC). Nothing in the spine said *where* the natal Orb (±7.0°), the transit Orb
(±2.0°), the house system, the fast/slow body split, the Ruler tables or the FR-13 harmonic table
live. The chart unit reads them from the environment; the transit unit reads them from a constants
module. Both are compliant. They drift the moment one is tuned — and worse, the PRD's "byte-identical
*for identical configuration*" becomes unverifiable, because no stored Payload records what the
configuration was. Compounding it: PRD Open Question 4 leaves the harmonic/disharmonic rule awaiting
Francesco's confirmation, so it *must* be changeable without touching code.

### CRITICAL — FR-30's "without a code change" was contradicted by the source tree → **AD-19 added**

The first draft placed the Style Guide at `data/style-guide.md` in the repository. FR-17 requires that
revising it changes generation without a code change, and FR-30 requires it be versioned so an output
quality change can be traced to a guide change. A repo file means a commit and a redeploy, and git
history is not queryable from the application — so no Report could name the guide version that
produced it, which is exactly the diagnostic SM-2 depends on. Moved to versioned database rows, with
the repo file demoted to a seed for version 1.

### HIGH — Month membership was undefined at the boundary → AD-12 tightened

FR-8 scans "the full calendar month in the Client's local timezone" but records events in UTC. A
lunation at 23:30 local on the last day of the month is in the next month in UTC. One unit filters on
local dates, another on UTC dates; both are compliant, and the event appears in two Reports or in
none. AD-12 now fixes the analyzed month as a single half-open UTC interval derived once from the
local calendar boundaries, with all membership decided against it.

### HIGH — Geocoder cache could retroactively alter a computed chart → AD-16 tightened

`PLACE_CACHE` and `CLIENT` both held place data with no stated authority. One unit denormalizes
coordinates onto the Client; another resolves through the cache at read time. Both compliant — but
under the second, a Nominatim correction to a cached place silently changes a Natal Chart that Reports
were already generated against, with no FR-4 warning and no recomputation. The Client now holds an
immutable snapshot; the cache is an accelerator only.

### MEDIUM — Regeneration unit was ambiguous → AD-10 tightened

FR-21 bounds regeneration but never said what gets regenerated. Whole-Report and per-Section
regeneration are both compliant readings, and they make FR-22's stored regeneration count mean
different things — and under per-Section, a single Report can contain Sections drawn from different
drafts. Fixed to whole-Report.

### MEDIUM — `exported` as a stage collided with repeat export → AD-10 tightened

FR-26 offers both PDF and Markdown, and a Report can be exported more than once, but AD-10 listed
`exported` as a forward-only stage. Now: the stage is reached once; each export writes an
`EXPORT_RECORD`.

### LOW — Draft persistence was implied but unstated → AD-10 tightened

SM-7 requires hand-sampling passed Reports against their Payload, which needs the cited draft
structure, not just the rendered prose. Now explicit.

### LOW — The chart wheel had no home → Capability map row added

FR-5 renders an SVG via Kerykeion, which lives in `core/`. Rendering presentation from the pure core
would breach AD-1's carve-out, which covers ephemeris *computation* only. The wheel is now placed in
the shell, with FR-5's "never in a Report or export" tied to AD-7.

---

## Lens 3 — Rubric walk (good-spine checklist)

| Criterion | Verdict |
| --- | --- |
| Fixes the real divergence points for the level below | **Pass** after AD-18 and AD-19. The four PRD §10 extension seams are each realised by a specific AD (seam 1 → AD-4/AD-2, seam 2 → AD-13, seam 3 → AD-14, seam 4 → AD-10). |
| Every AD's Rule is enforceable and prevents its stated divergence | **Pass.** AD-1 by a CI import test, AD-2 by a boot-time checksum assertion, AD-3 by a port signature, AD-7 by a single export function taking a Report id, AD-15 by an all-routes-authenticated test. |
| Nothing under Deferred could let two units diverge | **Pass.** Every deferred item is a future capability or a preference, not a shared contract. Storage growth carries a measurement trigger rather than being silently dropped. |
| Named tech is verified-current | **Pass only after Lens 1's corrections.** It failed outright on the first pass. |
| Ratifies rather than contradicts existing reality | **N/A for code** (greenfield, no source yet). Against the *documents*: the spine deliberately contradicts the addendum's hosting proposal and the research document's SQLite and 4-date-sampling designs. Each contradiction is recorded in the memlog with the verified reason, and the PRD had already superseded the sampling design. |
| Covers the driving spec's capabilities | **Pass.** All 30 FRs across the 8 PRD features appear in the Capability map; FR-5 and FR-30 were the two that had fallen through and are now placed. |
| No new AD weakens an inherited one | **N/A** — no parent spine. |
| Every dimension the altitude owns is decided, deferred or open | **Pass.** The operational envelope is covered explicitly: deployment topology, two named environments and why there is no staging, provider strategy, backup and restore, migrations, logging, secrets placement, and observability consciously deferred with a revisit trigger. |

**Answered from the PRD's open questions:** OQ-1 by AD-8 (with its limit stated rather than hidden),
OQ-2 by AD-14. OQ-3 (Corpus anonymization) and OQ-4 (the harmonic table) remain the PRD's to close —
AD-18 makes OQ-4 a data edit when Francesco confirms it.

**Carried forward, not resolved here:** PRD Assumption 3 (the 3-minute p90 latency budget) and
Assumption 4 (the 10-second transit scan) remain unmeasured. Neither is an architecture decision; both
are measurements to take on the first real month. AD-10 is what makes exceeding them an inconvenience
rather than a failure.
