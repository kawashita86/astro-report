# Epic 8 Context: Release validation — measure what the PRD assumed

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic 8 is the release gate. It adds no features; it settles the numbers and guarantees the PRD asserted but never verified, by measurement, before any Report reaches a paying client. Five things are pinned down: 100% astronomical conformance across the full adversarial fixture set; the generation provider's data terms re-checked against what is published now and recorded; real end-to-end latency and full-month scan time measured against the budgets that were only derived; permanent Payload retention projected against the database's free-tier ceiling; and a restore-from-backup actually performed rather than assumed. Where measured reality disagrees with a documented budget, the budget is loosened to match rather than left standing as an unmet number. Several of these checks block release outright.

## Stories

- Story 8.1: Pass conformance across the full adversarial fixture set
- Story 8.2: Re-verify the generation provider's data terms and record it
- Story 8.3: Measure the latency the PRD only assumed
- Story 8.4: Project storage growth against the free-tier ceiling
- Story 8.5: Restore from a backup, for real

## Requirements & Constraints

- **Conformance is a hard gate, not a trend.** Computed positions, house cusps, transit-to-natal aspects, stations, ingresses and lunations must all match the Astro.com reference values for every fixture in the complete adversarial set. Pass rate target is 100%; any mismatch stops the release, and the runner must name the fixture, field, expected value and computed value.
- **Provider data-terms re-verification.** Read the configured Generator provider's current published data terms and compare them against the EEA paid-tier terms the zero-cost design depends on (no training on submitted content, no human review of submitted content). Record the check with its date and outcome. A material change blocks release until assessed. Also confirm hosting and data storage sit in the EU/EEA where the free tier offers the choice.
- **Latency measurement.** Record the p90 from "Client selected" to "Report on screen" — transit scan, Payload assembly, generation, Gate and any bounded regeneration included — against the 3-minute budget. Separately record a full-month transit scan for one Client against the 10-second bound. Where a measurement exceeds its documented budget, revise the budget (and mark the corresponding PRD assumptions resolved with the measured values) rather than leave it unmet. Also exercise throughput: forty Reports produced, reviewed and exported in one sitting.
- **Storage projection.** Measure a real stored Report Payload's size. Project growth at the target volume of 100–200 Reports/month against the database's 0.5 GB free-plan ceiling and record the date the ceiling would be reached. If the projection reaches half the ceiling, raise a storage-growth policy as an explicit decision rather than absorbing it.
- **Restore rehearsal.** Restore a complete logical export into an empty database and confirm Clients, Natal Charts, Reports, Report Payloads, Gate results, Themes and Corpus entries all reconstruct. Open a previously exported Report and confirm its Payload and Gate result are intact and its Claims still trace to Payload entries. Record the procedure so it can be followed under pressure. Loss of a Report Payload permanently breaks traceability and is not acceptable — this proves recoverability.
- Deliverables of this epic are recorded artifacts: measurements, a dated terms check, a projection with a date, a written restore procedure.

## Technical Decisions

- **Determinism is the premise conformance rests on.** Identical Client birth data, month and configuration must yield identical Transit Events and a byte-identical Report Payload on every run and every deployment. Conformance is meaningless without it.
- **The conformance runner already exists** from Epic 1: it walks `tests/conformance/fixtures/`, compares computed output to transcribed Astro.com values, and runs on every change. Epic 8 runs it over the *complete* adversarial set (leap-day birth; births minutes either side of a historical DST switch; a near-midnight birth; a month with a retrograde station; a month with two lunations of one kind; a month with none), not a subset.
- **Backup is one authenticated route** producing a complete logical export — Clients, Natal Charts, Reports, Payloads, Gate results, Themes, Corpus entries — downloaded to the operator's machine, with a UI banner shown whenever the newest Report postdates the last export. Restore is a manual operator action. Epic 8 is the first time it is actually executed.
- **Free-tier constraints that shape this epic:** the Postgres free plan gives ~0.5 GB storage, a ~6-hour point-in-time-recovery window and no scheduled backups — which is why the operator export plus a rehearsed restore is the durability mechanism. The Generator is Gemini `gemini-2.5-flash` on the free tier; its acceptability for paying clients' data hinges entirely on the EEA paid-tier data terms, so the re-verification is a manual reading of the published terms, recorded.
- **No staging environment.** Measurement runs against production or the local Docker Compose stack (local Postgres, recorded-response Generator adapter).
- Every Report Payload already records the ephemeris file identity, the computation-config version and hash, and schema versions that produced it — the provenance a conformance or storage investigation needs.

## Cross-Story Dependencies

- **The whole epic runs last.** It needs Epics 1–6 delivered end to end, and Epic 7's Corpus in place for the restore check to be complete.
- Story 8.1 depends on the full transcribed fixture set (Story 1.7) and the conformance runner (Story 1.6), plus natal and transit computation (Epics 2–3).
- Story 8.3 depends on the complete run pipeline (Epics 2–6) and the Client-selection-to-export elapsed-time instrumentation captured at export (Epic 6 / FR-26).
- Story 8.4 depends on real stored Report Payloads (Epic 3, FR-14).
- Story 8.5 depends on the logical export route built in Story 6.5.
- Feedback outward: Story 8.3 writes back to the PRD — Assumptions 3 and 4 marked resolved and the latency/scan budgets (NFR-5, NFR-10) revised to the measured values; Story 8.4 may open a storage-growth decision.
