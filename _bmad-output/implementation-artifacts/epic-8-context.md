# Epic 8 Context: Release validation — measure what the PRD assumed

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The PRD carries four numbers it derived but never validated (per-Report latency, month-scan latency, storage growth, sustained throughput) and one guarantee it never re-checked (the generation provider's data terms). This epic settles all of them by measurement and rehearsal before any Report reaches a paying client. It ships no feature and covers no functional requirement directly; it is the release gate. Its outputs are recorded measurements, a data-terms verification record, a storage-growth projection, and a proven restore procedure. Where a measurement contradicts a documented budget, the budget is revised to match reality rather than left standing as an unmet number, and the corresponding PRD assumption is marked resolved with the measured value.

## Stories

- Story 8.1: Pass conformance across the full adversarial fixture set
- Story 8.2: Re-verify the generation provider's data terms and record it
- Story 8.3: Measure the latency the PRD only assumed
- Story 8.4: Project storage growth against the free-tier ceiling
- Story 8.5: Restore from a backup, for real

## Requirements & Constraints

- **Conformance is a 100% release gate, not a trend.** Every reference chart in the adversarial fixture set must match Astro.com across planetary positions, house cusps, transit-to-natal Aspects, Stations, Ingresses and Lunations. Any single non-matching fixture stops the release. The runner must name the fixture, field, expected value and computed value on failure.
- **Per-Report latency:** p90 from "Client selected" to "Report on screen" — transit scan, Payload assembly, generation, Gate, and any bounded regeneration included — recorded against a 3-minute budget. A run needing citation- or Gate-driven regeneration may exceed it; that case is a recorded known limitation, not a blocker.
- **Month-scan latency:** full-month transit scan for one Client recorded against a 10-second bound.
- **Throughput:** a single working session must be able to produce, review and export forty Reports in one sitting.
- **A measurement over budget forces the documented budget to be revised**, and PRD Assumptions 3 (per-Report latency) and 4 (month scan) marked resolved with measured values.
- **Data-terms re-verification:** the Generator provider's currently published data terms are read and compared against the EEA paid-tier terms the design relies on (no training on submitted content, no human review). Recorded with date and outcome; materially changed terms stop the release until assessed. Hosting and data storage are confirmed to sit in the EU/EEA wherever the free tier offers the choice.
- **Storage projection:** a real stored Report Payload's size is measured, then projected against 100–200 Reports/month and Neon's 0.5 GB free-plan ceiling, recording the date the ceiling would be reached. A projection reaching half the ceiling is raised as an explicit decision, not absorbed.
- **Restore rehearsal:** a complete logical export is restored into an empty database, reconstructing every entity class (Clients, Natal Charts, Reports, Report Payloads, Gate results, Themes, Corpus entries). A previously exported Report is reopened with its Payload and Gate result intact and its Claims still traceable. The procedure is written down so it can be followed under pressure.

## Technical Decisions

- **Determinism underpins conformance (AD-2).** Identical birth data, month and configuration must yield identical Transit Events and a byte-identical Report Payload on every run and every deployment; conformance measurement assumes this holds.
- **Durability is an operator action with a staleness signal (AD-17).** One authenticated route produces the complete logical export downloaded to the operator's machine; the UI warns whenever the newest Report postdates the last export. Restoring from that export is exercised here, not assumed. Neon's free plan gives only a ~6-hour PITR window and no scheduled backups, which is why the logical export plus a rehearsed restore is the durability mechanism.
- **One Generator adapter, no runtime failover (AD-9).** Changing provider is a deliberate config change gated on a recorded data-terms verification — the record this epic produces is that gate.
- **Every Report Payload records the ephemeris file identity and the ComputationConfig version and content hash** that produced it, so a conformance result or a stored Payload is reproducible.
- **Conformance harness already exists** (built in Epic 1 before the astronomy): a runner walks `tests/conformance/fixtures/`, runs on every change, and reports zero fixtures cleanly on an empty set. This epic asserts the full set passes, not builds the harness.
- Measurement and validation records live under `docs/release-validation/` (latency, data-terms).

## Cross-Story Dependencies

- **Depends on the full pipeline being complete (Epics 1–6).** Latency and throughput measurement need real Reports produced end to end (generation, Gate, export); conformance needs the transit engine and Payload assembly.
- **Story 8.1** consumes the adversarial fixture set transcribed by Francesco in Story 1.7 (leap-day birth, births either side of a historical DST switch, near-midnight birth, a month with a retrograde station, a month with two Lunations of one kind, a month with none).
- **Story 8.5** consumes the complete logical export route delivered by Story 6.5 and its staleness-warning banner.
- **Story 8.4** depends on a real persisted Report Payload from Epic 3's assembly work.
- This epic is the last gate before release (SM-3) and blocks nothing downstream. Epic 7 (Corpus) runs in parallel and gates none of this.
