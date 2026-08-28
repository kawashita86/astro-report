---
id: SPEC-astro-report
# Path convention: entries under `companions:` with no directory part are spec-authored
# siblings of this file. Every other path here — adopted companions and all sources —
# resolves from the project root, matching the convention the architecture spine uses.
companions:
  # Spec-authored (siblings of this file)
  - computation-tables.md
  - sections.md
  # Adopted (project-root-relative)
  - _bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/BUILD-ORDER.md
  - _bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md
sources:
  - _bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/brief.md
  - _bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/addendum.md
  - product_research.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# astro-report

## Why

A pain to solve, and with it a ceiling to remove. Francesco is a working astrologer with paying clients; producing one monthly report takes him one to three hours, and almost none of that is astrology. It is transcription — loading a chart on Astro.com, sampling the month by hand on four dates, annotating retrogrades, ingresses and aspect orbs, then cross-referencing all of it against the natal positions before a sentence gets written. At the thirty to fifty reports a month he produces now that is roughly eighty hours of clerical labor; at the one to two hundred he is aiming for it exceeds what a full-time month contains. His own hands are the ceiling on his practice and he has nearly reached it. astro-report takes five facts — name, birth date, birth time, birthplace, month — and returns eight sections of finished Italian prose in his register, ready to send. What makes that safe is a hard separation: **the system computes, the language model narrates.** Every astronomical fact in a delivered report is calculated locally and handed to the model as a fixed payload; the model may produce no claim that is not in it, and generated output is checked against it before anyone sees it. Reports ship unedited under Francesco's professional name, so that check is the product, not a nicety.

## Capabilities

- **CAP-1** — Create a Client
  - **intent:** Francesco can register a Client from five inputs — name, birth date, birth time, birthplace, and the month to analyze — so the chart behind every future report exists once.
  - **success:** A Client persists only when all five inputs are present and the birthplace has resolved; a Client with a missing or approximate birth time cannot be created by any path, and two Clients may share a name and stay distinct.

- **CAP-2** — Resolve birthplace to coordinates and historical timezone
  - **intent:** A free-text birthplace becomes a latitude, a longitude, and the UTC offset that was actually in force at the birth instant.
  - **success:** Coordinates resolve to at least four decimal places; a 1975-06-15 Italian birth resolves to +02:00, not +01:00; ambiguous names present candidates and require an explicit choice; a repeat of the same place does not re-query the geocoder; failure leaves no Client row and names the step that failed.

- **CAP-3** — Compute and store the Natal Chart
  - **intent:** Each Client's birth chart is computed once and read from storage thereafter, so no month re-derives it.
  - **success:** The stored chart carries ascendant, midheaven, all ten planets with sign/degree/house, both Lunar Nodes, twelve Placidus cusps and every natal Aspect within Orb; a second read returns the stored chart rather than recomputing.

- **CAP-4** — Correct birth data
  - **intent:** Francesco can fix wrong birth data and get a corrected chart without losing the record of what earlier reports were built on.
  - **success:** The correction warns that prior Reports were generated against the previous chart before it applies; those Reports and their Report Payloads survive unchanged and stay marked as belonging to the superseded chart.

- **CAP-5** — Render the chart wheel for verification
  - **intent:** Francesco can eyeball the computed chart against what he would have seen on Astro.com.
  - **success:** The wheel shows positions, cusps and natal Aspects, and no export or Client-facing artifact can reach it.

- **CAP-6** — Resolve house Rulers
  - **intent:** Every house cusp carries its governing planet in both the traditional and the modern system, so Domain Profiles can be assembled from rulership.
  - **success:** All twelve cusps carry both Rulers; Scorpio, Aquarius and Pisces additionally record the traditional co-ruler; assignment matches the table in `computation-tables.md` exactly.

- **CAP-7** — Assemble the four Domain Profiles
  - **intent:** The chart is regrouped from the way an ephemeris emits it into the way an astrologer reads it — `amore`, `lavoro`, `denaro`, `benessere`.
  - **success:** Each Profile contains exactly the placements listed in `sections.md`, and the same Natal Chart yields byte-identical Profiles on every run.

- **CAP-8** — Scan the month continuously
  - **intent:** The requested month is scanned finely enough to locate every Transit Event at its exact instant, replacing the four-date hand sample outright.
  - **success:** Every Transit Event carries an exact date and UTC time rather than a sample-date approximation; the event set for a given Natal Chart and month is identical on every run; an event at 23:30 local on the last day belongs to exactly one Report, never two and never none.

- **CAP-9** — Detect transit-to-natal Aspects and their perfection
  - **intent:** Every Aspect between a transiting body and a natal point during the month is found, with the moment it becomes exact.
  - **success:** Each detection records transiting body, natal point, aspect type, exact perfection instant and the in-orb entry and exit dates; Aspects in orb but never perfecting within the month are recorded and flagged; bodies, targets and Orb follow `computation-tables.md`, with the transiting Moon absent from this set.

- **CAP-10** — Detect retrogrades and Stations
  - **intent:** Francesco gets the month's retrograde picture and every turning point in it, dated.
  - **success:** Each Station records body, direction of turn, exact instant and zodiacal degree; a body retrograde for the whole month with no Station inside it is recorded as a standing condition with its span.

- **CAP-11** — Detect Ingresses into natal houses
  - **intent:** Each crossing of a natal house cusp by a transiting body is caught and dated.
  - **success:** Each Ingress records body, house departed, house entered and the exact crossing instant; crossings caused by retrograde motion are detected identically, including repeated crossings of the same cusp inside one month.

- **CAP-12** — Locate Lunations
  - **intent:** The month's new and full moons are placed exactly and located in the Client's natal chart.
  - **success:** Each Lunation records kind, exact instant, zodiacal degree and the natal house it falls in; a month with none of a kind, or two of one kind, needs no intervention from Francesco.

- **CAP-13** — Assemble the Report Payload per Section
  - **intent:** Everything the Generator will ever know about a Client's month is assembled into one structure, so nothing downstream can introduce an astronomical fact.
  - **success:** Each of the eight Sections receives exactly the material listed in `sections.md`; the dated day-lists for *Giorni favorevoli* and *Giorni di attenzione* are produced by applying the classification table in `computation-tables.md`; identical Natal Chart, month and ComputationConfig produce a byte-identical Payload across two machines.

- **CAP-14** — Version and persist the Report Payload
  - **intent:** A Report's facts remain readable and reproducible for as long as the Report is retained.
  - **success:** Every stored Report has exactly one stored Payload, immutable once the Report exists, recording its schema version, its ComputationConfig version and hash, and the identity of the ephemeris files that produced it.

- **CAP-15** — Generate the eight Sections in Italian
  - **intent:** A Report Payload becomes eight sections of finished Italian prose a client can read, or Francesco can read aloud.
  - **success:** Section order is always the fixed order in `sections.md`; output is Italian under every configuration; Sections 1–5 and 8 are continuous prose rather than bullet fragments; register is professional and non-fatalistic; no Section predicts a fixed outcome.

- **CAP-16** — Author and condition on the Style Guide
  - **intent:** Francesco's register is captured in a written guide he can revise himself, and every generation is conditioned on it.
  - **success:** The Style Guide exists as versioned, in-application editable text covering register and address, sentence rhythm, vocabulary used and avoided, how a claim is anchored to its transit and date, and each Section's interpretive territory; generation refuses to run when no version exists; revising it changes subsequent output with no code change and no redeploy; every Report records the version that produced it.

- **CAP-17** — Write a recurring Client's Report as a continuation
  - **intent:** March does not restate February — a returning Client reads the next chapter, not a reprint.
  - **success:** Where a transit covered in a prior Report is still active, the Report treats it as continuing — moved, tightened or resolved; where nothing significant has changed, the Report says so plainly rather than manufacturing novelty, and that judgement is computed by comparison rather than left to the Generator; a Client's first Report carries no history and no reference to prior months.

- **CAP-18** — Absorb transient generation failures
  - **intent:** Provider rate limits and transient errors do not become Francesco's problem mid-batch.
  - **success:** Transient failures trigger bounded automatic retry; after retries are exhausted the Report is marked failed and surfaced with its reason; no partial Report is ever produced that could be exported.

- **CAP-19** — Validate every Claim against the Report Payload
  - **intent:** No astronomical statement reaches Francesco — and therefore no client — that the computed facts do not support.
  - **success:** A Claim naming a body, sign, house, degree, date, aspect or retrograde condition absent from the Payload fails; a Claim contradicting the Payload fails; a sentence asserting no astronomical fact is never a Claim and never fails; a Report with one failing Claim does not reach the review screen in an exportable state.

- **CAP-20** — Regenerate or surface on Gate failure
  - **intent:** A failing Report is retried automatically, and a persistently failing one is shown to Francesco with the evidence rather than discarded.
  - **success:** Regeneration is automatic, bounded, and replaces the whole Report rather than a single Section; on persistent failure Francesco sees the Report, the failing Claims and the Payload entries they contradict; no Report reaches export without a passed Gate result.

- **CAP-21** — Retain and report Gate outcomes
  - **intent:** A drift in generation quality is visible from stored data before it becomes a client-visible problem.
  - **success:** Each Report records pass/fail, regeneration count and flagged Claims; those counts are queryable across Reports so a rising rate is observable.

- **CAP-22** — Collect the Corpus and report its composition
  - **intent:** Francesco's existing hand-written reports get gathered into one place, and their volume becomes a measured number rather than a guess.
  - **success:** A past report can be added as text regardless of origin; each entry is marked paired (matched to birth data and month, linked to a Client) or unpaired; paired and unpaired counts are visible at any time and are the decision input for phase-2 conditioning.

- **CAP-23** — Restrict the application to a single principal
  - **intent:** Only Francesco can reach Client data, and the system is shaped so a second account cannot be added as a convenience.
  - **success:** No Client data, Report, Payload or chart wheel is reachable unauthenticated, including via error messages; a session survives a working batch without re-authentication; there is no users table, no invitation flow and no password-reset flow.

- **CAP-24** — Delete a Client and everything derived from them
  - **intent:** A Client can be removed outright — the operational path for a corrected or abandoned record, and the deletion capability the hosted deployment requires.
  - **success:** Deletion removes the Client, the Natal Chart, every Report, every Payload and every Corpus pairing referencing them; it is confirmed first and states what will be removed; nothing deleted remains readable through the application.

- **CAP-25** — Review a Report with its facts alongside
  - **intent:** Francesco reads the finished Report next to the computed facts that produced it, months later as easily as the same day — so any sentence can be defended live.
  - **success:** All eight Sections display in order with the Gate result visible; the Payload entries behind any Section are reachable within one interaction, each showing body, natal point, aspect type, exact date and time, and orb.

- **CAP-26** — Export a passed Report
  - **intent:** The finished Report leaves the system as a file Francesco can send, and the act of exporting captures the two measurements the product is judged by.
  - **success:** PDF and Markdown are both available; exports contain the eight Sections and the Client's name only — no wheel, no Payload, no internal metadata; a Report that has not passed the Gate cannot be exported; send disposition (*sent as generated* / *edited before sending*) is recorded in one interaction, and elapsed time from Client selection to export is recorded automatically.

- **CAP-27** — Produce an operator-held backup
  - **intent:** Francesco holds a complete copy of his own data, because the hosting tier's restore window is shorter than the interval in which a corruption would be noticed.
  - **success:** One authenticated route produces a complete logical export — Clients, Natal Charts, Reports, Payloads, Gate results, Themes and Corpus entries — downloaded to his machine; the UI warns whenever the newest Report postdates the last export; a restore from that export has been exercised before release, not assumed.

- **CAP-28** — Browse Report History
  - **intent:** Every Report ever produced for a Client stays reachable, in order.
  - **success:** Reports list by Client and month; any prior Report reopens with its Payload and Gate result intact.

- **CAP-29** — Verify computed output against Astro.com
  - **intent:** The astronomy is checked against the benchmark Francesco's professional judgement is calibrated to, systematically rather than by eye.
  - **success:** A fixture set of transcribed Astro.com reference charts runs on every change, covering positions, cusps, Aspects, Stations, Ingresses and Lunations, and chosen adversarially — a leap-day birth, births either side of a historical DST switch, a near-midnight birth, a month with a retrograde station, a month with two lunations of one kind and one with none.

- **CAP-30** — Watch a report run progress
  - **intent:** Francesco can start a report run and watch it move through its stages, and can leave the view or close the tab and come back without the run being lost or restarted.
  - **success:** Starting a run returns to the run view immediately without waiting for any stage; the view shows the run's current stage and reflects each advance as it happens; a run left or closed mid-flight resumes from its last completed stage when the view is reopened; a terminally failed run shows which stage failed and why — distinct from a Gate failure, which routes to the review surface of CAP-20. Mechanism in `ARCHITECTURE-SPINE.md` AD-10/AD-20 and `EXPERIENCE.md` (*Report Run Lifecycle*).

## Constraints

- The Generator narrates and never computes: it receives the Report Payload, the Style Guide version and the two ReportThemes, and nothing else — no tools, no database handle, no prior Report prose.
- No astronomical fact may appear in a Report that is not in its Report Payload, and the Groundedness Gate is the only path to export.
- Claim-level determinism is the bar, not byte-identical prose. Wording may vary between runs; Claims may never vary, exceed the Payload, or contradict each other.
- Identical Client birth data, month and ComputationConfig produce a byte-identical Report Payload, on every run and every deployment.
- Reports ship unedited under Francesco's professional name. Every guardrail must hold without a human catching the failure.
- Everything the operator sees is Italian: report content under every configuration (CAP-15), and the entire operator UI — navigation, labels, helper text, errors, empty states, toasts, stage labels, and the native date/time pickers (`lang="it"`; dates `dd/MM/yyyy`, times `HH:mm`). Only identifiers — `YYYY-MM` month codes, hashes, UUIDs — stay Latin-alphanumeric.
- The operator-facing web UI conforms to the adopted `EXPERIENCE.md` (information architecture, voice, component / state / interaction patterns, key flows, WCAG 2.1 AA floor) and `DESIGN.md` (visual identity: `#42297A` on white, Inter, light and dark themes). Both companions are binding, not reference.
- Exact birth time to the minute is mandatory. No noon chart, solar-house fallback or house-less path exists anywhere in the system.
- Placidus houses; the five major aspects only; natal Orb ±7.0° default (tunable 6.0–8.0); transit-to-natal Orb ±2.0° default (tunable 1.5–2.5); the transiting Moon excluded from Aspects, entering only through Lunations. Values in `computation-tables.md`.
- Every astronomical tuning value lives in one versioned ComputationConfig, passed explicitly and recorded with its hash on each Payload. Changing the harmonic/disharmonic rule is a data edit and a version bump, never a code change.
- All computation and storage is UTC. The analyzed month is one half-open UTC interval derived from the Client's local calendar month, so every Transit Event belongs to exactly one Report.
- Ephemeris files are vendored, pinned by SHA-256 and asserted at boot; the Moshier fallback is never an accepted runtime state.
- All durable state lives in Postgres. Nothing written to the compute host's filesystem at runtime is ever read back after a restart.
- Running cost stays at zero at 30–200 Reports per month. A design requiring paid infrastructure at target volume must be raised rather than absorbed.
- Hosting and storage are EU/EEA. Exactly one Generator adapter is configured with no runtime failover, and its data terms are verified before real Client data is sent and again on any provider change.
- Exactly one principal, enforced structurally. Adding a second is a revision of this contract, not a feature — it would also trigger the AGPL source-offer obligation the current shape avoids.
- Reports are non-fatalistic: no fixed outcome, medical event, death or financial result is ever predicted.
- The dated entries of Sections 6 and 7 are projected from the Payload by code. A date token written by the Generator inside those two Sections is a Gate violation.
- The glossary vocabulary is used verbatim across code, database and configuration, and the four domains stay Italian and lowercase (`amore`, `lavoro`, `denaro`, `benessere`). Introducing a synonym is a defect.
- No Report reaches a Client before Astro.com conformance passes across the full reference set.
- Losing a Report Payload permanently breaks the traceability guarantee for its Report and is not acceptable. Losing a Natal Chart is recoverable by recomputation.
- One Report goes from Client selected to Report on screen in under 3 minutes at p90, and total operator involvement per Report stays under 15 minutes.

## Non-goals

- No client-facing surface: no accounts, logins, portal or interface any Client touches. Clients receive an exported file.
- No multi-astrologer or multi-tenant operation. Permanently out, not deferred.
- No native mobile application. The hosted web app is reachable from a phone browser.
- No astrological techniques beyond natal chart and monthly transits — synastry, compatibility, solar returns and progressions are out.
- No chart pattern detection: stelliums, grand trines, dispositor chains and similar configurations. Each would be a new class of Claim the Gate must learn to verify.
- No billing, payments, scheduling or CRM. The Client record exists to produce Reports.
- No output language other than Italian.
- No support for Clients with an unknown birth time. Rectification, noon charts, solar houses and house-less readings are all out.
- No delivery mechanics. The product produces a file; sending it stays manual.
- No Corpus-based voice conditioning, exemplar retrieval or fine-tuning in v1 — phase 2, gated on the count from CAP-22.
- No multi-year narrative memory and no alternative report formats (quarterly, annual, per-domain) in v1.
- No capacity planning beyond 200 Reports per month; no horizontal scale, multi-region, queue broker or background worker process. A report run is advanced only by the operator's own polling of the run view (`ARCHITECTURE-SPINE.md` AD-20).
- No observability stack beyond structured logs — no metrics backend, no alerting, no tracing.
- The system does not teach astrology. It assumes a professional operator and explains nothing about its own reasoning beyond exposing the facts.

## Success signal

Francesco produces forty Reports in a single afternoon without opening Astro.com once, and sends the majority of them without changing a word — his involvement per Report having fallen from one-to-three hours to under fifteen minutes, with computed output matching Astro.com on every reference chart. The counter-signal that would falsify it: an unedited-send rate that rises while the reports get vaguer, shorter, or stop naming the transit and the date behind a claim.

## Assumptions

- Sections 6 and 7 may use list form while Sections 1–5 and 8 must be continuous prose.
- The 3-minute p90 latency budget and the 10-second full-month scan bound are derived from the throughput target, not measured. Release validation measures both and loosens the documented numbers if reality disagrees.
- The chart wheel adequately replaces the four-date snapshot as Francesco's verification habit.
- Availability is best-effort with no SLA, inferred from the batch working pattern.
- Report delivery to Clients stays manual.
- The PRD addendum states a data processing agreement is required before real Client data is entered; PRD §6.2 consciously defers the DPA as accepted risk. The PRD is taken as the later decision of record and supersedes — but the two currently-live sources disagree, so the divergence is recorded rather than silently resolved.

## Open Questions

- Where does the Groundedness Gate draw the line for an interpretive statement that leans on a fact without naming it? The closed-vocabulary rule answers it structurally and states its limit explicitly; the empirical calibration against real generated Reports is still open.
- What is the anonymization position for Corpus content? Required before phase-2 conditioning, not before v1, but it shapes how the Corpus is collected now.

*Closed by Francesco on 2026-08-14:* the harmonic/disharmonic classification rule is confirmed correct as stated (see `computation-tables.md`), and the *Benessere* Section is determined not to produce GDPR Article 9 special category data. Neither relaxes any constraint above — the ban on predicting medical events and the single-owner rule for the classification table both stand on their own grounds.
