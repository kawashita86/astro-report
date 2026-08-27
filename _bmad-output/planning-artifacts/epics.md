---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - '_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md'
  - '_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/BUILD-ORDER.md'
  - '_bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/addendum.md'
---

# astro-report - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for astro-report, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

Extracted verbatim in intent from PRD §4. FR numbers are append-only and never reused, so the
numbering is non-consecutive within features by design (PRD §0).

**4.1 Client Record and Natal Chart**

FR-1: Francesco can create a Client from five inputs — name, birth date, birth time, birthplace, and (per report) the month to analyze. All five are required; birth time is mandatory and exact to the minute with no degraded path (no noon chart, no solar houses, no house-less reading); birthplace is resolved before the Client is persisted; names need not be unique.

FR-2: The system resolves a free-text birthplace to latitude, longitude (≥4 decimal places) and the UTC offset **in force at the birth instant**, including historical DST rules. Ambiguous place names require an explicit choice from Francesco — never a silent pick. Resolved places are cached. Failure means the Client is not persisted and Francesco is told which step failed.

FR-3: On Client creation the system computes and stores the Natal Chart: ascendant and midheaven; sign, degree and natal house for all ten planets; North and South Lunar Nodes with sign, degree and house; all twelve Placidus cusps; all natal Aspects within Orb. Natal Aspect Orb default ±7.0°, configurable ±6.0°–±8.0°. Computed exactly once per Client and read from storage thereafter.

FR-4: Francesco can correct a Client's birth data, which invalidates and recomputes the Natal Chart. The system warns that prior Reports were generated against the previous chart before applying the change. Prior Reports and their Report Payloads are retained unchanged and marked as belonging to the superseded chart.

FR-5: The system renders a chart wheel for a Client's Natal Chart showing planetary positions, house cusps and natal Aspects — for Francesco's verification only, never included in a Report or any Client-facing export.

FR-28: The application is reachable only by Francesco. No Client data, Report, Report Payload or chart wheel is reachable without authenticating; unauthenticated requests return no Client data of any kind, including in error messages. A session persists across a working batch. Exactly one account exists — no account creation, invitations, password reset for others, or role distinctions.

FR-29: Francesco can delete a Client outright, removing the Client record, the Natal Chart, every Report, every Report Payload and every Corpus pairing that referenced them. Deletion is confirmed before executing and reports what will be removed. Deletion is complete rather than a soft flag.

**4.2 Domain Profiles**

FR-6: For each of the twelve house cusps, the system resolves the governing planet in both traditional and modern systems. Where the two differ — Scorpio, Aquarius, Pisces — both the modern Ruler and the traditional co-ruler are recorded. Assignment follows the addendum §3 table exactly.

FR-7: The system assembles the four Domain Profiles from the Natal Chart. **Amore**: Venus (sign, house, Aspects); Mars (sign, house, Aspects); 5th house (sign, planets in it, Ruler); 7th house (sign, planets in it, Ruler); Moon (sign, house, Aspects). **Lavoro**: 10th, 6th and 2nd houses and the midheaven — each with sign, planets in it, Rulers, and principal Aspects. **Denaro**: 2nd and 8th houses; Venus, Jupiter, Saturn and their Aspects. **Benessere**: ascendant, Ruler of the ascendant, 6th house, Mars, Saturn, Moon. Assembly is a pure function — the same Natal Chart always yields byte-identical Domain Profiles.

**4.3 Monthly Transit Engine**

FR-8: The system scans the requested month at a resolution fine enough to locate every Transit Event to the exact date and UTC time — not a sample-date approximation. Scanning covers the full calendar month in the Client's local timezone, with events recorded in UTC and presented in local time. The event set for a given Natal Chart and month is identical on every run.

FR-9: The system detects every Aspect between a transiting body and a Natal Chart point during the month and locates the exact moment of perfection. Transiting bodies: **fast** — Sun, Mercury, Venus, Mars; **slow** — Jupiter, Saturn, Uranus, Neptune, Pluto. **The transiting Moon is deliberately excluded** and enters only through Lunations (FR-12). Natal points targeted: the ten planets, the ascendant, the midheaven, and the Lunar Nodes. Five major aspects only. Transit-to-natal Orb default ±2.0°, configurable ±1.5°–±2.5°. Each Aspect records transiting body, natal point, aspect type, exact perfection date and UTC time, and the in-orb window (entry and exit dates). Aspects in orb during the month but never perfecting within it are recorded and flagged as such.

FR-10: The system identifies which bodies are retrograde during the month (dλ/dt < 0) and dates every Station, recording body, direction of turn, exact date and UTC time, and zodiacal degree. Bodies retrograde for the entire month with no Station inside it are recorded as a standing condition with the month's retrograde span.

FR-11: The system detects each crossing of a natal house cusp by a transiting body, recording body, house departed, house entered, and the exact date and UTC time of the crossing. Crossings caused by retrograde motion are detected identically, including repeated crossings of the same cusp within one month.

FR-12: The system locates the new and full moons falling within the month, recording kind, exact date, UTC time, zodiacal degree, and the natal house it falls in. A month containing no Lunation of a given kind, or two of one kind, requires no intervention from Francesco.

**4.4 Report Payload Assembly**

FR-13: The system assembles a Report Payload organizing the Natal Chart, Domain Profiles and Transit Events into the material each of the eight Sections requires — *Energia generale* (slow-planet transits to angular houses 1/4/7/10 and to personal planets Sun/Moon/Mercury/Venus/Mars; all active retrogrades); *Amore* (Amore Profile; transits to 5th and 7th; transit Aspects to natal Venus and Mars); *Lavoro* (Lavoro Profile; transits to midheaven, 10th, 6th; transit Aspects to natal Mercury, Mars, Saturn); *Denaro* (Denaro Profile; transits to 2nd and 8th; transit Aspects to natal Jupiter and Saturn); *Benessere* (Benessere Profile; transits to ascendant and 6th; transit Aspects to natal Mars, Saturn, Moon); *Giorni favorevoli* (dated harmonic Aspect Perfections and favorable Lunations); *Giorni di attenzione* (dated disharmonic Aspect Perfections and retrograde Stations); *Consiglio finale* (natal houses the month's Lunations fall in, against the overall transit picture). Assembly is a pure function — identical Natal Chart, month and configuration always produce a byte-identical Report Payload.

  **Harmonic / disharmonic classification rule** (table-driven, confirmed domain fact 2026-08-14):
  trine and sextile → harmonic; square and opposition → disharmonic; conjunction by transiting Venus
  or Jupiter → harmonic; conjunction by transiting Mars, Saturn or Pluto → disharmonic; conjunction by
  any other transiting body → neutral, appearing in neither day list. A **tense Mars or Saturn passage**
  is a transiting Mars or Saturn in conjunction, square or opposition to any natal point. A **favorable
  Lunation** is one forming a trine or sextile to a natal point within Orb, or conjunct natal Venus or
  Jupiter. Neutral events are never silently dropped — they remain available to Sections 1–5 and 8.

FR-14: Each Report Payload carries a schema version and is stored permanently with its Report. Every stored Report has exactly one stored Report Payload. Payloads produced under older rules remain interpretable. A stored Payload is immutable once its Report is generated.

FR-15: Francesco can view the Report Payload entries underlying any Report, including Reports generated months earlier. For any Section he can see the exact Transit Events and natal placements supplied to it; each entry displays body, natal point, aspect type, exact date and time, and orb. The view is reachable within one interaction from a displayed Report.

**4.5 Italian Report Generation**

FR-16: The system generates a Report of exactly eight Sections in fixed order — Energia generale del mese, Amore, Lavoro, Denaro, Benessere, Giorni favorevoli, Giorni di attenzione, Consiglio astrologico finale. Output language is Italian; no other language under any configuration. Narrative Sections (1–5, 8) are continuous prose, not bullet fragments. Sections 6 and 7 present dated days and may use list form. Register is professional and non-fatalistic; the Report never predicts fixed outcomes.

FR-30: The Style Guide exists as a written artifact before v1 generation is usable, and Francesco can revise it without a code change. **Authored by Francesco** — it describes his register and no one else can supply it; producing the first version is a v1 deliverable, not a configuration step. It covers at minimum: register and address to the reader; sentence rhythm and length habits; vocabulary used and avoided; how a claim is anchored to its transit and date; and the interpretive territory of each Section. Stored as editable text and versioned, so a change in output quality can be traced to a change in the guide.

FR-17: Generation is conditioned on the Style Guide (FR-30) so output reads in Francesco's register. The Style Guide is supplied to every generation request; generation cannot proceed without a Style Guide present; revising it changes subsequent generation without a code change.

FR-18: For a Client with Report History, generation accounts for what prior Reports already said. The Generator receives a summary of the preceding Report's principal themes. Where a transit was covered in a prior Report and is still active, the Report treats it as continuing — what has moved, tightened or resolved — rather than reintroducing it. Where nothing significant has changed, the Report states that plainly rather than manufacturing novelty. A Client's first Report is generated with no history and no reference to prior months.

FR-19: Transient generation failures are retried without Francesco's involvement. Provider rate limits and transient errors trigger bounded automatic retry. After exhausting retries the Report is marked failed and surfaced to Francesco with the reason. A failed generation never produces a partial Report that could be exported.

**4.6 Groundedness Gate**

FR-20: Before a generated Report is shown to Francesco, the system checks each Claim in it against the Report Payload. A Claim naming a planet, sign, house, degree, aspect, date or retrograde condition not present in the Payload fails. A Claim contradicting the Payload — wrong date for a named Aspect Perfection, wrong house for a Lunation, a body described as retrograde that is not — fails. A Report containing at least one failing Claim does not reach the review screen in an exportable state. Interpretive statements asserting no astronomical fact are not treated as Claims.

FR-21: A Report failing the Groundedness Gate is regenerated a bounded number of times automatically. On persistent failure Francesco is shown the Report, the failing Claims, and the Payload entries they contradict — never a silent discard. A Report that has not passed the Gate cannot be exported.

FR-22: The Gate outcome for each Report is stored with the Report — whether it passed, how many regenerations were required, and any Claims flagged. Regeneration counts are reportable across Reports so a rising rate is visible before it becomes a quality problem.

**4.7 Corpus Collection**

FR-23: Francesco can add past reports to the Corpus as text regardless of original source. Each entry records whether it is paired (matched to birth data and month) or unpaired (prose only). Paired entries link to a Client and a month where one exists.

FR-24: The system reports how many Corpus entries exist, split paired and unpaired. Counts are visible at any time and are the decision input for whether phase-2 few-shot conditioning is viable.

**4.8 Review, Export and Report History**

FR-25: Francesco can read a generated Report with its underlying Report Payload accessible alongside. All eight Sections are displayed in order; the Payload view (FR-15) is reachable without leaving the Report; the Gate result (FR-22) is visible.

FR-26: Francesco can export a Report that has passed the Groundedness Gate, to both PDF and Markdown. Exports contain only the eight Sections and the Client's name — no chart wheel, no Payload, no internal metadata. At export Francesco records the Report's **send disposition** in one interaction: *sent as generated* or *edited before sending*. The system records the elapsed time from Client selection to export for each Report.

FR-27: Francesco can see all Reports previously generated for a Client, in order, listed by Client and month. Any prior Report can be reopened with its Payload and Gate result intact. Report History is what FR-18 draws on.

### NonFunctional Requirements

From PRD §5 (cross-cutting), the feature-specific NFRs in §4.3 and §4.6, and the constraints in §6–§7.

NFR-1: **Astronomical conformance.** Computed output — planetary positions, house cusps, transit-to-natal Aspects, Stations, Ingresses and Lunations — matches Astro.com's *Natal chart and transits* for a defined set of reference charts. No Report reaches a Client before conformance passes. Release gate at 100% (SM-3).

NFR-2: **Computational determinism.** Identical Client birth data, month and configuration produce identical Transit Events and a byte-identical Report Payload, on every run and every deployment.

NFR-3: **Claim-level determinism.** Report prose may vary between generations. Claims may not. Two generations from the same Payload may never contradict each other on a fact.

NFR-4: **Traceability.** Every Claim in every delivered Report remains traceable to a stored Report Payload entry for as long as the Report is retained.

NFR-5: **Throughput and latency.** One Report goes from "Client selected" to "Report on screen" — transit scan, Payload assembly, generation, Gate and any bounded regeneration included — in **under 3 minutes at p90**. The system sustains forty Reports in a single working session and 100–200 per month. *(PRD Assumption 3: budget derived, not validated.)* *(measured 2026-08-27: single-generation-call p90 119 s = 118 s gemini-2.5-flash generation + 1 s local; within budget. Regenerating case not modelled — see docs/release-validation/latency.md.)*

NFR-6: **Time budget.** End-to-end Francesco involvement per Report — entering or selecting a Client, generating, reviewing, exporting — stays under 15 minutes (SM-1).

NFR-7: **Cost.** Running cost stays at €0/month at 30–200 Reports per month. Any design requiring paid infrastructure at target volume fails this constraint and must be raised rather than absorbed.

NFR-8: **Availability.** Best-effort. No SLA; an hour of downtime is an inconvenience, not an incident. *(PRD Assumption 6.)*

NFR-9: **Data durability.** Client records, Natal Charts, Reports and Report Payloads survive host restarts and redeploys. Loss of a Natal Chart is recoverable by recomputation; **loss of a Report Payload permanently breaks the traceability guarantee for that Report and is not acceptable.**

NFR-10: **Transit scan latency.** The full month scan for one Client completes in under 10 seconds. *(PRD Assumption 4: inferred from the forty-reports-in-an-afternoon target; not measured.)* *(measured 2026-08-27: p90 under 1 s across 40 scans; within budget. See docs/release-validation/latency.md.)*

NFR-11: **Gate is terminal and unbypassable.** The Gate is the last step before Francesco sees a Report. No path exists from Generator to export that bypasses it.

NFR-12: **The Generator computes nothing.** It receives a Report Payload and produces prose. No tools, no calculation ability, no authority to supply an astronomical fact.

NFR-13: **Non-fatalistic output.** No Report predicts a fixed outcome, a medical event, a death, or a financial result.

NFR-14: **Reports ship unedited.** Every guardrail must hold without a human catching the failure — there is no human review step between generation and the Client.

NFR-15: **Access control.** The application is access-controlled; Francesco is the only person who can reach Client data. (Realized by FR-28.)

NFR-16: **Data residency.** Hosting and data storage are located in the EU/EEA where the chosen free tier offers the choice.

NFR-17: **Provider data terms verified.** The generation provider's data terms are verified once before real Client data is sent, and again if generation ever falls back to another provider. The zero-cost guarantee is jurisdiction-contingent (EEA paid-tier data terms applied to free tiers).

NFR-18: **Speakable prose.** Sentences must survive being read aloud on a call — no nested clauses that lose their thread, no construction that only works on a page.

NFR-19: **Claim specificity.** Claims name the transit and the date. Vagueness is the specific failure mode to guard against; generic horoscope prose that would apply to anyone is an anti-reference (counter-metric SM-C1).

### Additional Requirements

Technical requirements from the Architecture Spine and Build Order that constrain how stories are
implemented. Each is citable by its `AD` number.

**🚨 Starter template: NONE.** The Architecture specifies no starter/greenfield template. The project
is scaffolded from scratch — `uv` packaging, a Docker image, a Render web service (EU region), a Neon
Postgres project (Europe/Frankfurt), and Alembic wired forward-only. **This is Epic 1, Story 1.**

- **AD-1 — The purity boundary.** `core/` contains only pure functions: no I/O, no clock, no network, no randomness, no environment reads, and no import from `shell/`. The shell loads data, calls core functions, and persists what they return. **The single declared exception is the ephemeris**: Kerykeion and pyswisseph read the vendored `.se1` files from disk inside `core/ephemeris/`. An import-boundary test enforces this in CI; a second exception is a spine amendment, not a judgement call.
- **AD-2 — Ephemeris identity pinned, asserted at boot, recorded in every Payload.** `sepl_18.se1` and `semo_18.se1` are vendored. The shell calls `swe.set_ephe_path()` at startup, verifies each file against a pinned SHA-256, and **refuses to start** on a missing file or checksum mismatch. The Moshier fallback is never an accepted runtime state. Every Report Payload records the ephemeris file identity that produced it.
- **AD-3 — The Report Payload is the Generator's only channel.** The `Generator` port accepts exactly `(ReportPayload, StyleGuide, ReportTheme_previous, ReportTheme_current)` and nothing else. Its adapter holds no database handle, no filesystem access and no tool definitions. **Prior Report prose is never sent to the Generator**; continuity travels as `ReportTheme`.
- **AD-4 — Payload entry IDs are content-derived.** An entry's ID is a stable hash of its canonical field tuple — never sequential, never time-derived, never random. Entries are emitted in a total order over those same fields.
- **AD-5 — Dated day-lists are rendered by code, never written by the model.** The dated entries of Sections 6 and 7 are projected from the Payload by a pure function applying the FR-13 harmonic/disharmonic table. The Generator writes only connective prose around them and **emits no date token within those two Sections**; a date token appearing there is a Gate violation.
- **AD-6 — Generation returns cited structure, not prose.** The `Generator` port returns each Section as an ordered list of sentences, each carrying the Payload entry IDs it rests on. A sentence containing a closed-vocabulary token with an empty citation list is a Gate violation. Rendering sentences into continuous prose is the shell's job.
- **AD-7 — The Gate is pure, and is the only path to export.** `run_gate(draft, payload) -> GateResult` lives in `core/gate/`, calls no model and performs no I/O. **Exactly one export function exists**; it takes a stored Report ID and reads only Reports whose persisted `GateResult` is `passed`. No function anywhere accepts a draft and produces an exportable artifact.
- **AD-8 — Claim classification is a versioned closed vocabulary.** A sentence is a **Claim** if and only if it contains a token from the closed Italian astronomical vocabulary — the ten planets, the twelve signs, `casa` with an ordinal, a day-of-month numeral, `retrogrado`, `stazionario`. The vocabulary is a data file versioned alongside the Gate. **Stated limit:** a sentence that leans on a fact without naming it is not policed. *(This is the architecture's answer to PRD Open Question 1.)*
- **AD-9 — One Generator adapter; no runtime failover.** Exactly one `Generator` adapter is configured. Changing provider is a deliberate configuration change gated on a recorded data-terms verification, never an automatic fallback. Rate limits and transient failures are absorbed by bounded backoff and run checkpointing.
- **AD-10 — A report run is a checkpointed row advancing through persisted stages.** A `ReportRun` row advances forward only: `natal_ready → transits_ready → payload_ready → draft_ready → gate_passed → exported`. Each stage persists its output before the next begins, including the cited draft structure. Re-driving a run resumes at the first incomplete stage; every stage function is idempotent on its input. **Regeneration under FR-21 replaces the whole Report, never a single failing Section.** Reaching `exported` happens once; each subsequent export writes an `EXPORT_RECORD` row.
- **AD-11 — No durable state on the compute host's filesystem.** All durable state lives in Postgres. The container filesystem carries only the vendored ephemeris, templates and application code. Nothing written at runtime is ever read back after a restart.
- **AD-12 — UTC in the core; local time exists only at the edges.** Every instant computed or stored is UTC. Core functions take explicit timezone-aware inputs and never consult a system clock or default timezone. Conversion to the Client's local time happens only in `shell/http/`. **The analyzed month is a half-open UTC interval** derived once from the Client's local calendar-month boundaries, so an event at 23:30 local on the last day belongs to exactly one Report.
- **AD-13 — Section composition is data, not code.** The mapping from each of the eight Sections to its Payload selectors is a versioned data file (`data/sections.toml`), loaded by the core as data. Adding a report format adds a mapping, not a branch.
- **AD-14 — ReportTheme is derived purely from the Payload.** `derive_theme(payload) -> ReportTheme` is pure and model-free, yielding dominant slow-planet aspects ordered by tightness, lunation houses, and standing retrogrades. FR-18's "nothing significant has changed" is **computed** by comparing two ReportThemes, not judged by the Generator.
- **AD-15 — Exactly one principal, enforced structurally.** Authentication is a single Argon2 password hash in an environment variable plus a signed session cookie surviving a working batch. No users table, no invitation flow, no password-reset flow. *(Also an AGPL-3.0 consideration: the Kerykeion → pyswisseph → Swiss Ephemeris chain obliges offering Corresponding Source to remote users; a second principal would create that obligation.)*
- **AD-16 — A Client cannot exist in a partial state.** The `Client` type has no optional birth fields and no partial constructor. Birthplace and historical-offset resolution complete before a Client is persisted; failure means no Client row. No noon chart, no solar-house fallback, no house-less path anywhere in the codebase. The Client stores its **own immutable snapshot** of resolved latitude, longitude and IANA zone; `PLACE_CACHE` is a lookup accelerator, never a source of truth afterwards.
- **AD-17 — Durability is an operator action with a visible staleness signal.** One authenticated route produces a complete logical export — Clients, Natal Charts, Reports, Payloads, Gate results, Themes and Corpus entries — downloaded to the operator's machine. The UI displays a warning whenever the newest Report postdates the last export. **Restoring from an export is exercised before release, not assumed.** *(Neon's free plan gives a ~6-hour PITR window and no scheduled backups.)*
- **AD-18 — One ComputationConfig, versioned, passed explicitly, recorded on every Payload.** The natal Orb (±7.0°, tunable 6.0–8.0), the transit-to-natal Orb (±2.0°, tunable 1.5–2.5), the house system, the fast/slow body sets, the traditional and modern Ruler tables, and the FR-13 harmonic/disharmonic table live in one versioned data file (`data/computation.toml`), loaded into a frozen `ComputationConfig` and **passed explicitly as an argument** into every core function that needs one — never read ambiently. Its version and content hash are recorded in every Report Payload.
- **AD-19 — The Style Guide is versioned data in the database, not a file in the repository.** Stored as versioned rows, edited in the application, with prior versions retained. The repository file `data/style-guide.seed.md` seeds version 1 only. Every Report records the Style Guide version that produced it. **Generation refuses to run when no Style Guide version exists.**

**Consistency conventions (binding on every story):**

- Domain vocabulary is the PRD §3 Glossary verbatim and untranslated: `Client`, `NatalChart`, `Aspect`, `TransitEvent`, `AspectPerfection`, `Station`, `Ingress`, `Lunation`, `Ruler`, `DomainProfile`, `ReportPayload`, `Generator`, `Report`, `Section`, `Claim`, `GateResult`, `StyleGuide`, `Corpus`, `ReportTheme`. Introducing a synonym is a defect.
- The four domains are `amore`, `lavoro`, `denaro`, `benessere` — Italian, lowercase, never translated in code, database or configuration.
- `snake_case` modules mirroring the paradigm's directories; a module's name states its stage. **No `utils`, `helpers` or `common` module anywhere.**
- Database rows use UUIDv7 primary keys. Report Payload *entries* use content-derived hashes (AD-4) and are not database identities.
- Instants stored and computed as timezone-aware UTC, serialized ISO-8601 with an explicit `Z`. A naive datetime crossing any boundary is a defect.
- Angles as `Decimal`, never binary float, in every stored or compared value. Longitudes normalized to `[0, 360)`; orbs signed with an explicit applying/separating flag.
- The Payload is canonical JSON: sorted keys, no insignificant whitespace, `Decimal` as a fixed-precision string. Byte-identity is asserted by test, not assumed.
- The Report Payload, the Section composition file (AD-13) and the Gate vocabulary (AD-8) each carry an **independent** integer version, recorded on every Report.
- Core functions raise typed domain errors from a single `core/errors.py` and never return `None` to mean failure. No core module imports an HTTP status code.
- Core values are frozen dataclasses; nothing in `core/` mutates its input. All writes happen in `shell/adapters/postgres/`, and only the runner advances a `ReportRun` stage.
- Environment variables are read in exactly one place, `shell/config.py`, validated into a frozen settings object at startup. No module reads `os.environ` directly. Startup fails loudly on a missing or invalid setting.
- Logging is structured and **never carries Client birth data, names or Report prose** — an identifier only. Every log line for a report run carries its `ReportRun` id.
- Every route is authenticated by default; the small allowlist of unauthenticated routes is declared in one place and covered by a test asserting no other route is reachable anonymously.
- Alembic migrations are forward-only, one per change, applied at deploy before the application accepts traffic.
- Core is tested by example and by conformance fixtures; the shell is tested at the port boundary with fakes. Golden Astro.com fixtures live in `tests/conformance/fixtures/` and run on every change.

**Stack (seed — the lockfile owns these once code exists):** Python 3.13 · uv 0.12.4 · FastAPI 0.141.1 · Kerykeion 5.12.9 · pyswisseph 2.10.3.2 · Swiss Ephemeris data pinned by SHA-256 · SQLModel 0.0.39 · Alembic 1.19.1 · Jinja2 3.1.6 · HTMX 2.0.9 · WeasyPrint 69.0 · geopy (Nominatim) 2.5.0 · timezonefinder 8.2.5 · argon2-cffi 25.1.0 · Google Gemini `gemini-2.5-flash` (free tier, EEA data terms) · PostgreSQL 18 (Neon, Europe/Frankfurt) · Render web service (free plan, EU region). Three are load-bearing rather than incidental: Kerykeion requires Python ≥ 3.10; the Gemini EEA data terms are what make the free tier acceptable for paying clients' data; HTMX is pinned to 2.x deliberately because 4.0 replaces the XHR transport with `fetch` and is not a drop-in upgrade.

**Environments:** two only — **local** (Docker Compose, local Postgres, a recorded-response Generator adapter so development costs no quota) and **production** (one Render service, one Neon project). No staging.

**Build-order requirements not carried by any FR:**

- **Conformance harness before the computation it validates** (Build Order E1, a deliberate deviation from PRD §14 step 8). `tests/conformance/fixtures/` plus a runner that walks them. Francesco transcribes reference charts from Astro.com, chosen **adversarially**: a leap-day birth; births minutes either side of a historical DST switch; a near-midnight birth; a month containing a retrograde station; a month with two lunations of one kind, and one with none. **This chunk needs Francesco, not a developer.**
- **ReportTheme before generation** (Build Order E7, a deliberate deviation from PRD §14 step 5). `ReportTheme` is an *input* to generation under AD-3, so it must exist before E8 or the Generator port signature changes after generation is already built.
- **Bounded backoff sized for Gemini's 10 RPM ceiling** (E5), with an HTMX polling view over run status.
- **Release validation** (E11): 100% conformance across the full adversarial fixture set; re-verify Gemini data terms against the current published terms and record the check; measure real p90 latency against the 3-minute budget (PRD Assumption 3) and the full-month scan against the 10-second bound (Assumption 4), loosening the documented budgets if reality disagrees; measure a real Report Payload against Neon's 0.5 GB ceiling; rehearse restore-from-export.

**Open items carried into story writing:**

- **PRD Open Question 1** (where the Claim/interpretation boundary sits) is answered by **AD-8**'s closed vocabulary, with the limitation stated explicitly.
- **PRD Open Question 2** (how the preceding Report is summarized for FR-18) is answered by **AD-14** — a stored, purely derived `ReportTheme`. The PRD's note that "FR-18 is not buildable until it resolves" is therefore discharged by the architecture.
- **PRD Open Question 3** (Corpus anonymization) remains open and is deferred to phase 2. It gates no v1 story, but shapes how the Corpus is collected now.
- **⚠ Broken cross-reference.** PRD FR-16 and FR-30 both cite `addendum.md` §8 as recording "the interpretive territory of each Section" and as the Style Guide's starting material. **Addendum §8 is "Validation approach"**; the per-Section material is §4 ("Data sourcing per report section"), and §4 describes *which data feeds* each Section rather than what each Section is *for*. The interpretive-territory material FR-30 depends on **does not exist in any input document** and must be written from scratch as part of the Style Guide.

### UX Design Requirements

**Not applicable — no UX design contract exists for this project.** No `ux-designs/` folder, no legacy
UX document. Confirmed with Francesco on 2026-08-14: interface stories are derived from the PRD's FR
consequences (FR-1, FR-5, FR-15, FR-25, FR-26, FR-27, FR-28, plus the Style Guide editor at FR-30, the
Corpus entry surface at FR-23/FR-24 and the backup route at AD-17) and from the architecture's fixed
presentation stack — FastAPI + Jinja2 server-rendered templates with HTMX 2.x, no SPA, no native app.

The UI surface v1 requires, for planning visibility:

- Sign-in (single principal, AD-15) and a session that survives a working batch.
- Client list and Client creation form, with the ambiguous-birthplace disambiguation choice (FR-2).
- Birth-data correction flow with its supersession warning (FR-4).
- Client deletion with a confirmation that reports what will be removed (FR-29).
- Chart wheel view, internal only (FR-5).
- Month selection and report-run launch, with an HTMX polling view over `ReportRun` status (AD-10).
- Report review: eight Sections in order, Gate result visible, Payload reachable in one interaction (FR-15, FR-25).
- Gate-failure view: the Report, the failing Claims, and the Payload entries they contradict (FR-21).
- Export controls for PDF and Markdown, with send disposition captured in one interaction (FR-26).
- Report History per Client (FR-27).
- Style Guide editor over versioned rows, prior versions retained (FR-30, AD-19).
- Corpus entry and the paired/unpaired composition count (FR-23, FR-24).
- Backup/export route with the staleness warning banner (AD-17).

### FR Coverage Map

| FR | Epic | Coverage |
|---|---|---|
| FR-1 | Epic 2 | Create a Client from five inputs |
| FR-2 | Epic 2 | Resolve birthplace to coordinates and historical timezone |
| FR-3 | Epic 2 | Compute and store the Natal Chart |
| FR-4 | Epic 2 | Correct birth data and recompute the chart |
| FR-5 | Epic 2 | Render the chart wheel for verification |
| FR-6 | Epic 2 | Resolve house Rulers, traditional and modern |
| FR-7 | Epic 2 | Assemble the four Domain Profiles |
| FR-8 | Epic 3 | Scan the month continuously |
| FR-9 | Epic 3 | Detect transit-to-natal Aspects and perfection dates |
| FR-10 | Epic 3 | Detect retrogrades and Stations |
| FR-11 | Epic 3 | Detect Ingresses into natal houses |
| FR-12 | Epic 3 | Locate Lunations |
| FR-13 | Epic 3 | Assemble the Report Payload per Section |
| FR-14 | Epic 3 | Version and persist the Report Payload |
| FR-15 | Epic 3 | Expose the Payload behind the Report |
| FR-16 | Epic 4 | Generate the eight Sections in Italian |
| FR-17 | Epic 4 | Condition generation on the Style Guide |
| FR-18 | Epic 4 | Avoid restating prior Reports |
| FR-19 | Epic 4 | Retry on generation failure |
| FR-20 | Epic 5 | Validate every Claim against the Report Payload |
| FR-21 | Epic 5 | Regenerate or surface on gate failure |
| FR-22 | Epic 5 | Retain the Gate result |
| FR-23 | Epic 7 | Ingest and normalize past reports |
| FR-24 | Epic 7 | Report Corpus composition |
| FR-25 | Epic 6 | Review a generated Report |
| FR-26 | Epic 6 | Export to PDF and Markdown |
| FR-27 | Epic 6 | Browse Report History |
| FR-28 | Epic 1 | Restrict access to the application |
| FR-29 | Epic 2 | Delete a Client and their Reports (moved from Epic 1 — see note below) |
| FR-30 | Epic 4 | Author and maintain the Style Guide |

All 30 functional requirements are mapped. Epic 8 covers no FR directly — it realizes NFR-1, NFR-5,
NFR-9, NFR-10 and NFR-17, and is the release gate behind SM-3.

**⚠ FR-29 moved from Epic 1 to Epic 2.** Build Order E0 places Client deletion first, on the reasoning
that everything after it stores identifiable Client data. But no `CLIENT` table exists until Epic 2,
so a deletion cascade written in Epic 1 would have nothing to cascade over, and creating the table
early would violate the entity-creation principle (tables are created by the story that needs them).
The requirement is therefore satisfied at the end of Epic 2 — the first moment Client data exists —
and every later story that creates a table referencing a Client carries an acceptance criterion that
the new table joins the FR-29 cascade. The build order's intent is preserved: no Client data ever
exists without a working delete.

## Epic List

### Epic 1: A private application I can sign into, with correctness guardrails that cannot be retrofitted

Francesco can reach a locked-down application that no one else can, delete a Client and everything
derived from them, and trust that the mechanical guardrails are in place before a single line of
astronomy is written.
**FRs covered:** FR-28, FR-29
**Build Order:** E0 + E1 · **Governed by:** AD-1, AD-2, AD-11, AD-15, AD-18
**Notes:** No starter template exists — this epic scaffolds the project from scratch. Includes the
import-boundary test (AD-1 is a rule only while this test exists), the ephemeris SHA-256 boot
assertion, `data/computation.toml` as the single home for tuning values, and the adversarial
conformance fixture harness built *before* the computation it validates. The fixture transcription
needs Francesco, not a developer, and sits on the critical path.

### Epic 2: Enter a Client once and get a natal chart I can verify

Francesco enters the five inputs, the birthplace resolves to coordinates and the offset in force at
the birth instant, and a complete Natal Chart plus the four Domain Profiles are computed and stored
permanently — with a chart wheel he can eyeball against Astro.com.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7
**Build Order:** E2 + E4 · **Governed by:** AD-1, AD-2, AD-12, AD-16, AD-18
**Notes:** FR-5 is pulled forward from Build Order E10 so this epic stands alone as verifiable — the
PRD records the wheel's value as highest during conformance validation. Domain Profiles (E4) are
independent of the transit engine and parallelize here.

### Epic 3: Every dated fact for a Client's month, inspectable

Francesco picks a Client and a month and gets every Transit Event located to the exact instant,
assembled into a versioned Report Payload he can read entry by entry. Realizes UJ-3 on its own: he
could write reports by hand from these facts and still have removed almost all the transcription
labor.
**FRs covered:** FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15
**Build Order:** E3 + E5 + E6 · **Governed by:** AD-1, AD-2, AD-3, AD-4, AD-5, AD-10, AD-12, AD-13, AD-18
**Notes:** Three build-order chunks merged because none delivers usable value alone. They touch
distinct directories (`core/transits/`, `shell/runner/`, `core/payload/`), so this is a value
boundary rather than file-churn consolidation. The Sections 6 and 7 day-lists are projected by pure
code here (AD-5), which is what makes the misfiled-day error class structurally impossible.

### Epic 4: Eight Sections of Italian prose in my register, that don't repeat last month

Francesco writes the Style Guide, edits it in the application without a deploy, and generation
produces eight Sections conditioned on it — treating still-active transits as continuing rather than
reintroducing them.
**FRs covered:** FR-16, FR-17, FR-18, FR-19, FR-30
**Build Order:** E7 + Track A + E8 · **Governed by:** AD-3, AD-6, AD-9, AD-14, AD-19
**Notes:** `ReportTheme` (E7) leads this epic rather than trailing generation — it is an *input* to
the Generator port under AD-3, so building it after E8 would change the port signature. FR-30 is the
highest-risk deliverable in the whole build (PRD §12) and is writing work, not engineering; it can
start on day one and blocks only this epic.

### Epic 5: A report I can trust enough to send without reading it

Every Claim is checked against the Report Payload before Francesco sees the Report; failures
regenerate automatically and, when persistent, are shown alongside the Payload entries they
contradict. This is the emotional job-to-be-done: send a report without reading it first, and not
worry about what is in it.
**FRs covered:** FR-20, FR-21, FR-22
**Build Order:** E9 · **Governed by:** AD-5, AD-6, AD-7, AD-8
**Notes:** The Gate is pure and is the only path to export (AD-7). AD-8's versioned closed vocabulary
is the architecture's answer to PRD Open Question 1, with its limitation stated: a sentence that
leans on a fact without naming it is not policed.

### Epic 6: Review, export and history — the forty-reports-in-an-afternoon loop

Francesco reads a Report with its Payload alongside and the Gate result visible, exports to PDF and
Markdown recording send disposition in one interaction, browses Report History, and takes a durable
backup with a staleness warning when he has not.
**FRs covered:** FR-25, FR-26, FR-27
**Build Order:** E10 · **Governed by:** AD-7, AD-17
**Notes:** Carries the measurement sources for SM-1 (elapsed time) and SM-2 (send disposition). The
durability requirement is not met until the operator backup route exists and a restore has actually
been exercised.

### Epic 7: Corpus collection (parallel track — gates nothing in v1)

Francesco adds past reports as text, marks each paired or unpaired, and sees the composition count
that decides whether phase-2 conditioning is viable.
**FRs covered:** FR-23, FR-24
**Build Order:** Track B · **Governed by:** AD-11
**Notes:** Deliberately kept separate from Epic 6 despite both being `shell/http/` + Postgres —
merging would imply it is blocked until Epic 6, whereas it runs from day one. Gathering is
Francesco's work and is expected to be slow. PRD Open Question 3 (anonymization) stays open and gates
no v1 story, but shapes how the Corpus is collected now.

### Epic 8: Release validation — measure what the PRD assumed

100% conformance across the full adversarial fixture set, Gemini data terms re-verified and recorded,
real p90 latency and full-month scan time measured against the assumed budgets, Payload size
projected against Neon's ceiling, and a restore-from-export actually rehearsed.
**FRs covered:** none directly — realizes NFR-1, NFR-5, NFR-9, NFR-10, NFR-17 and SM-3
**Build Order:** E11 · **Governed by:** AD-2, AD-17
**Notes:** Where PRD Assumptions 3 and 4 are settled by measurement. If reality disagrees with the
documented budgets, the budgets are loosened rather than left unmet in the PRD.

### Dependency flow

```
Epic 1 → Epic 2 → Epic 3 → Epic 4 → Epic 5 → Epic 6 → Epic 8
                                                 ↑
Epic 7 (parallel from day one) ──────────────────┘
```

Each epic stands alone and enables those after it without requiring them to function. Two epics
contain work only Francesco can do, and both sit on the critical path: Epic 1's transcribed reference
charts and Epic 4's Style Guide.

---

## Epic 1: A private application I can sign into, with correctness guardrails that cannot be retrofitted

Francesco can reach a locked-down application that no one else can, and the three mechanical
guardrails — the purity boundary, the pinned ephemeris, and the conformance harness — are in place
before a single line of astronomy is written. Each is worth nothing if retrofitted.

**FRs covered:** FR-28 · **NFRs:** NFR-7, NFR-8, NFR-15, NFR-16 · **Governed by:** AD-1, AD-2, AD-11, AD-15, AD-18

### Story 1.1: A deployable application skeleton

As Francesco,
I want the application to boot on its production host against its production database,
So that every later story lands in a place that is already running rather than in a repository that has never been deployed.

**Acceptance Criteria:**

**Given** an empty repository
**When** the project is scaffolded
**Then** `uv` manages dependencies with a committed lockfile pinning Python 3.13
**And** a Docker image builds and runs the FastAPI application as a single process
**And** a Render web service in an EU region serves it, and a Neon Postgres project in Europe/Frankfurt backs it
**And** Alembic is wired forward-only, with migrations applied at deploy before the application accepts traffic

**Given** the application starting up
**When** it reads its configuration
**Then** every environment variable is read in exactly one place, `shell/config.py`, and validated into a frozen settings object
**And** no other module reads `os.environ` directly
**And** startup fails loudly and refuses to serve traffic on a missing or invalid setting

**Given** the deployed application
**When** its running cost is examined at the target volume of 30–200 Reports per month
**Then** every component sits inside a free tier and the running cost is €0/month

### Story 1.2: The purity boundary, enforced by a test rather than by discipline

As Francesco,
I want the separation between pure computation and everything that touches the world to be mechanically enforced,
So that the byte-identical-Payload guarantee cannot be broken silently by a future import.

**Acceptance Criteria:**

**Given** the source tree
**When** it is created
**Then** `core/` exists with `types/`, `errors.py`, `ephemeris/`, `transits/`, `domains/`, `payload/`, `memory/` and `gate/`
**And** `shell/` exists with `config.py`, `ports/`, `adapters/`, `runner/` and `http/`
**And** no module is named `utils`, `helpers` or `common` anywhere in the tree

**Given** `tests/test_import_boundary.py`
**When** it runs in CI
**Then** it fails if any module under `core/` imports anything from `shell/`
**And** it fails if any module under `core/` imports a network, clock, filesystem or environment facility, except the declared ephemeris exception inside `core/ephemeris/`
**And** it runs on every change, not only on demand

**Given** a deliberately introduced import from `core/` to `shell/`
**When** CI runs
**Then** the build fails and names the offending module

### Story 1.3: An ephemeris whose identity is asserted before the application serves anything

As Francesco,
I want the application to refuse to start unless it is using exactly the ephemeris data it was built against,
So that the same code can never produce different numbers on different deployments and put a station on the wrong day.

**Acceptance Criteria:**

**Given** the repository
**When** the ephemeris is vendored
**Then** `data/ephemeris/sepl_18.se1` and `data/ephemeris/semo_18.se1` are committed
**And** their SHA-256 checksums are pinned in the repository, taken from the files actually downloaded

**Given** the application starting up
**When** the shell initializes the ephemeris
**Then** it calls `swe.set_ephe_path()` explicitly against the vendored directory
**And** it verifies each file against its pinned SHA-256

**Given** a missing ephemeris file or a checksum mismatch
**When** the application starts
**Then** it refuses to start and reports which file failed
**And** it never falls back to Moshier — the fallback is not an accepted runtime state under any configuration

**Given** the running application
**When** the ephemeris identity is requested by any component that must record it
**Then** the identity is available as a value that later stories can persist alongside computed output

### Story 1.4: Sign in as the only person who can reach this application

As Francesco,
I want the application to be reachable only by me, with a session that survives a working batch,
So that paying clients' birth data is not exposed and I do not re-authenticate forty times in an afternoon.

**Acceptance Criteria:**

**Given** exactly one configured principal
**When** authentication is set up
**Then** it is a single Argon2 password hash held in an environment variable and a signed session cookie
**And** there is no users table, no account creation, no invitation flow, no password-reset flow and no role distinction

**Given** an unauthenticated request to any application route
**When** it is served
**Then** it returns no application data of any kind, including in error messages and error bodies

**Given** the route table
**When** the authentication test runs
**Then** every route is authenticated by default
**And** the allowlist of unauthenticated routes is declared in exactly one place
**And** the test fails if any route outside that allowlist is reachable anonymously

**Given** a successful sign-in
**When** Francesco works through a batch over several hours
**Then** the session persists across the batch without re-authentication

**Given** any log line the application writes
**When** it is inspected
**Then** it is structured and carries no birth data, no names and no prose — an identifier only

### Story 1.5: One home for every astronomical tuning value

As Francesco,
I want every orb, table and body set to live in one versioned file that is passed explicitly wherever it is needed,
So that two components can never drift apart on what the configuration was, and any stored result can be reproduced.

**Acceptance Criteria:**

**Given** `data/computation.toml`
**When** it is created
**Then** it holds the natal Aspect Orb (default ±7.0°, permitted range ±6.0° to ±8.0°), the transit-to-natal Orb (default ±2.0°, permitted range ±1.5° to ±2.5°), the house system (Placidus), the fast and slow transiting body sets, the traditional and modern Ruler tables for all twelve signs, and the FR-13 harmonic/disharmonic classification table
**And** it carries an integer version and a content hash

**Given** the file
**When** it is loaded
**Then** it produces a frozen `ComputationConfig` value
**And** the config is passed explicitly as an argument into every core function that needs one
**And** no core function reads it ambiently from a module global, the environment or a file at call time

**Given** an orb value outside its permitted range
**When** the configuration is loaded
**Then** loading fails with a typed domain error naming the offending value

**Given** this story
**When** it is complete
**Then** the file holds no logic and drives no computation yet — it exists so that nothing downstream invents a second home for these values

### Story 1.6: A conformance harness that runs before there is anything to conform

As Francesco,
I want the fixture harness to exist and run in CI before the astronomy is written,
So that a Placidus error is found in week two as a fix rather than in week ten as a rewrite of everything layered on top.

**Acceptance Criteria:**

**Given** `tests/conformance/fixtures/`
**When** the harness is built
**Then** a runner walks every fixture in the directory and compares computed output against the transcribed Astro.com values
**And** the fixture format records birth data, the expected planetary positions, house cusps, natal Aspects, and — for month fixtures — the expected Transit Events

**Given** an empty fixture set
**When** CI runs
**Then** the runner executes successfully and reports zero fixtures rather than failing

**Given** a fixture whose expected values do not match computed output
**When** the runner executes
**Then** it fails and names the fixture, the field, the expected value and the computed value

**Given** the harness
**When** any change is made to the repository
**Then** it runs — conformance is not an on-demand check

### Story 1.7: Reference charts chosen to break the computation, not to flatter it

As Francesco,
I want to transcribe reference charts from Astro.com that target the cases most likely to be wrong,
So that conformance means something rather than confirming the easy path.

**Acceptance Criteria:**

**Given** Astro.com's *Natal chart and transits* output
**When** Francesco transcribes reference charts into the fixture set
**Then** at least three charts exist before Epic 2 begins
**And** the full set is chosen adversarially, covering a leap-day birth; births minutes either side of a historical DST switch; a near-midnight birth; a month containing a retrograde station; a month with two Lunations of one kind; and a month with none of one kind

**Given** a transcribed fixture
**When** it is committed
**Then** it records which adversarial case it targets, so a gap in coverage is visible

**Given** this story
**When** it is scheduled
**Then** it is understood to need Francesco rather than a developer, and to sit on the critical path — starting it on day one is deliberate

---

## Epic 2: Enter a Client once and get a natal chart I can verify

Francesco enters the five inputs, the birthplace resolves to coordinates and the offset in force at
the birth instant, and a complete Natal Chart plus the four Domain Profiles are computed and stored
permanently — with a chart wheel he can eyeball against Astro.com, and a delete that removes
everything.

**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-29 · **NFRs:** NFR-1, NFR-2 · **Governed by:** AD-1, AD-2, AD-12, AD-16, AD-18

### Story 2.1: Resolve a birthplace to coordinates and the offset in force at birth

As Francesco,
I want a free-text birthplace resolved to coordinates and to the *historical* UTC offset for that date,
So that a 1975 Italian birth is read as CEST rather than as today's CET, which is the difference between a correct chart and one an hour off.

**Acceptance Criteria:**

**Given** a `Geocoder` port and a Nominatim adapter
**When** a free-text birthplace and a birth date and time are supplied
**Then** resolution returns latitude and longitude to at least four decimal places
**And** it returns the IANA zone and the UTC offset in force at that instant at that location, derived from `timezonefinder` and `zoneinfo`, including historical DST rules
**And** the offset is never the present-day offset for that location

**Given** a birth in Italy on 1975-06-15
**When** the birthplace is resolved
**Then** the applied offset is +02:00 (CEST), not +01:00

**Given** a place name matching more than one location
**When** it is resolved
**Then** the candidate matches are returned for an explicit choice
**And** the system never silently picks one

**Given** a birthplace that has been resolved before
**When** the same place is entered again
**Then** the result is served from the Postgres-backed `PLACE_CACHE` without re-querying the geocoder

**Given** a birthplace that cannot be resolved, or a geocoder that is unreachable
**When** resolution is attempted
**Then** it raises a typed domain error from `core/errors.py` naming which step failed
**And** it never returns `None` to mean failure

**Given** the `PLACE_CACHE` table
**When** it is created
**Then** it is a lookup accelerator only, and is never treated as a source of truth for a Client already persisted

### Story 2.2: Compute a Natal Chart as a pure function

As Francesco,
I want the natal chart computed by a pure function that matches Astro.com,
So that the same birth data always yields the same chart, on every run and every deployment.

**Acceptance Criteria:**

**Given** timezone-aware birth data, resolved coordinates and a `ComputationConfig`
**When** `core/ephemeris/` computes the Natal Chart
**Then** it returns the ascendant and midheaven; sign, degree and natal house for Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune and Pluto; the North and South Lunar Nodes with sign, degree and house; all twelve Placidus house cusps; and all natal Aspects within Orb
**And** Aspects are limited to conjunction, sextile, square, trine and opposition
**And** the natal Aspect Orb is read from the passed `ComputationConfig`, defaulting to ±7.0°

**Given** the computation
**When** it runs
**Then** it consults no system clock, no default timezone, no network and no database
**And** every angle is a `Decimal`, never a binary float
**And** longitudes are normalized to `[0, 360)` and orbs are signed with an explicit applying/separating flag
**And** every instant is timezone-aware UTC

**Given** the natal reference fixtures transcribed in Story 1.7
**When** the conformance runner executes
**Then** computed positions, cusps and natal Aspects match Astro.com for every natal fixture

**Given** the same birth data and configuration
**When** the chart is computed twice, on two machines
**Then** the results are identical

### Story 2.3: Create a Client, or fail visibly

As Francesco,
I want a Client persisted only when all five inputs are present and fully resolved,
So that a half-formed Client can never silently corrupt Amore, Lavoro and Benessere, which are load-bearing on houses.

**Acceptance Criteria:**

**Given** the Client creation form
**When** Francesco enters a Client
**Then** it takes name, birth date, birth time and birthplace, and all four are required
**And** birth time is entered exactly, to the minute

**Given** a Client without a known birth time
**When** creation is attempted
**Then** the Client cannot be created, and no Natal Chart or Report is produced for them
**And** no noon chart, solar-house fallback or house-less path exists anywhere in the codebase to accept them

**Given** the `Client` type
**When** it is defined
**Then** it has no optional birth fields and no partial constructor
**And** birthplace and historical-offset resolution complete before the Client row is written
**And** a resolution failure means no Client row at all

**Given** a birthplace that resolved to several candidates
**When** the form is submitted
**Then** Francesco is shown the candidates and must choose one explicitly before the Client is persisted

**Given** a successfully created Client
**When** the row is written
**Then** it stores its own immutable snapshot of the resolved latitude, longitude and IANA zone
**And** the Natal Chart is computed once and stored with it
**And** both use UUIDv7 primary keys

**Given** two Clients entered with the same name
**When** both are created
**Then** both persist and remain distinct records — names are not required to be unique

**Given** an existing Client
**When** any later request needs their chart
**Then** it is read from storage and never recomputed

### Story 2.4: Resolve the Ruler of every house, traditional and modern

As Francesco,
I want each house cusp's governing planet resolved in both systems,
So that the Domain Profiles can be assembled the way I actually read a chart.

**Acceptance Criteria:**

**Given** a Natal Chart and a `ComputationConfig`
**When** Rulers are resolved
**Then** both the traditional and the modern Ruler are resolved and stored for all twelve cusps
**And** assignment follows the Ruler tables in `data/computation.toml` exactly, with no rulership rule hardcoded in a function

**Given** a cusp falling in Scorpio, Aquarius or Pisces
**When** its Ruler is resolved
**Then** both the modern Ruler and the traditional co-ruler are recorded — Pluto with co-ruler Mars; Uranus with co-ruler Saturn; Neptune with co-ruler Jupiter

**Given** resolution
**When** it runs
**Then** it is a pure function of the Natal Chart and the passed configuration

### Story 2.5: Assemble the four Domain Profiles

As Francesco,
I want the chart regrouped from how an ephemeris emits it into how an astrologer reads it,
So that each life area arrives as one coherent body of natal material rather than as scattered placements.

**Acceptance Criteria:**

**Given** a Natal Chart with Rulers resolved
**When** `core/domains/` assembles the Profiles
**Then** **amore** contains Venus (sign, house, Aspects); Mars (sign, house, Aspects); the 5th house (sign, planets in it, Ruler); the 7th house (sign, planets in it, Ruler); and the Moon (sign, house, Aspects)
**And** **lavoro** contains the 10th, 6th and 2nd houses and the midheaven, each with sign, planets in it, Rulers and principal Aspects
**And** **denaro** contains the 2nd and 8th houses, and Venus, Jupiter and Saturn with their Aspects
**And** **benessere** contains the ascendant, the Ruler of the ascendant, the 6th house, Mars, Saturn and the Moon

**Given** the four Profiles
**When** they are named in code, in the database and in configuration
**Then** they are `amore`, `lavoro`, `denaro` and `benessere` — Italian, lowercase, never translated

**Given** the same Natal Chart
**When** the Profiles are assembled twice
**Then** the results are byte-identical, asserted by test
**And** assembly consulted no clock, network or database

### Story 2.6: See the chart wheel and check it against Astro.com

As Francesco,
I want to look at the computed chart as a wheel,
So that I can eyeball it against what I would have seen on Astro.com before I trust anything built on it.

**Acceptance Criteria:**

**Given** a Client with a stored Natal Chart
**When** Francesco opens the chart wheel
**Then** the wheel shows planetary positions, house cusps and natal Aspects

**Given** the wheel
**When** it is rendered
**Then** it is rendered in `shell/http/`, because it is presentation rather than computation

**Given** any Client-facing artifact
**When** it is produced
**Then** the wheel is never included in a Report or any export — no route reaches it from an exported file

### Story 2.7: Correct birth data, and know what it invalidates

As Francesco,
I want to correct a Client's birth data with the consequences spelled out first,
So that I do not silently invalidate work I have already sent to a client.

**Acceptance Criteria:**

**Given** a Client whose birth data needs correcting
**When** Francesco submits the change
**Then** the system warns, before applying it, that prior Reports were generated against the previous chart
**And** the change is applied only after the warning is acknowledged

**Given** an applied correction
**When** the change completes
**Then** the stored Natal Chart is invalidated and recomputed from the corrected data
**And** the superseded chart is retained and marked as superseded rather than overwritten
**And** anything already generated against the superseded chart remains readable and stays associated with it

**Given** a correction that changes the birthplace
**When** it is applied
**Then** the birthplace is re-resolved and the Client's immutable coordinate and zone snapshot is replaced as part of the same change

**Given** a Client whose birth data has not changed
**When** any operation runs
**Then** no recomputation occurs — the chart is computed exactly once per Client and recomputed only on correction

### Story 2.8: Delete a Client and everything derived from them

As Francesco,
I want to remove a Client outright,
So that an abandoned or mistaken record leaves nothing behind, and so a client's data can be removed when asked.

**Acceptance Criteria:**

**Given** a Client
**When** Francesco requests deletion
**Then** the system asks for confirmation and reports exactly what will be removed before executing

**Given** a confirmed deletion
**When** it executes
**Then** the Client record, the Natal Chart (including any superseded charts) and the Domain Profiles derived from them are removed
**And** deletion is complete rather than a soft flag — no deleted Client data remains readable through the application

**Given** any table created by a later story that references a Client
**When** that story is implemented
**Then** it carries its own acceptance criterion that the new table joins this cascade
**And** the cascade is asserted by a test that fails when a Client-referencing table is added without being covered

**Given** a deletion
**When** it is logged
**Then** the log line carries the Client identifier only, never the name or birth data

---

## Epic 3: Every dated fact for a Client's month, inspectable

Francesco picks a Client and a month and gets every Transit Event located to the exact instant,
assembled into a versioned Report Payload he can read entry by entry. This realizes UJ-3 on its own:
he could write reports by hand from these facts and still have removed almost all the transcription
labor.

**FRs covered:** FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15 · **NFRs:** NFR-1, NFR-2, NFR-4, NFR-9, NFR-10 · **Governed by:** AD-1, AD-2, AD-3, AD-4, AD-5, AD-10, AD-11, AD-12, AD-13, AD-18

### Story 3.1: Find every transit-to-natal Aspect and the exact moment it perfects

As Francesco,
I want every Aspect between a transiting body and a natal point located to the exact instant,
So that I can say "the 19th" instead of "around the 10th" — which four-date sampling could never do.

**Acceptance Criteria:**

**Given** a Client's Natal Chart, a requested month and a `ComputationConfig`
**When** the analyzed month is established
**Then** it is a single half-open UTC interval derived once from the Client's local calendar-month boundaries
**And** every event's membership is decided against that one interval, so an event at 23:30 local on the last day belongs to exactly one month — never to two and never to none

**Given** the scan
**When** it runs over the interval
**Then** it covers Sun, Mercury, Venus and Mars as fast bodies and Jupiter, Saturn, Uranus, Neptune and Pluto as slow bodies, read from the passed configuration
**And** the transiting Moon is excluded from Aspect detection entirely
**And** natal points targeted are the ten planets, the ascendant, the midheaven, and the North and South Lunar Nodes
**And** Aspects are limited to conjunction, sextile, square, trine and opposition

**Given** a detected Aspect
**When** it is recorded
**Then** it carries the transiting body, the natal point, the aspect type, the exact perfection date and UTC time located by bisection, and the in-orb window as entry and exit dates
**And** the transit-to-natal Orb is read from the passed configuration, defaulting to ±2.0°

**Given** an Aspect that is in orb during the month but never reaches perfection within it
**When** the scan completes
**Then** it is recorded and explicitly flagged as never perfecting in the month, rather than dropped

**Given** the transit reference fixtures from Story 1.7
**When** the conformance runner executes
**Then** computed Aspect Perfections match Astro.com for every month fixture

**Given** the same Natal Chart, month and configuration
**When** the scan is run repeatedly
**Then** the set of Aspects is identical every time

### Story 3.2: Date every Station and know what is standing retrograde

As Francesco,
I want each retrograde turn dated exactly and each standing retrograde recorded,
So that *Giorni di attenzione* has real Stations to name and the general energy section knows what is backwards all month.

**Acceptance Criteria:**

**Given** the analyzed month interval and a `ComputationConfig`
**When** retrograde condition is determined
**Then** it is derived from longitudinal velocity — a body is retrograde where dλ/dt < 0

**Given** a body whose longitudinal velocity changes sign within the month
**When** the Station is located
**Then** it records the body, the direction of the turn (retrograde or direct), the exact date and UTC time, and the zodiacal degree

**Given** a body retrograde for the entire month with no Station inside it
**When** the scan completes
**Then** it is recorded as a standing condition with the month's retrograde span, not omitted

**Given** the month fixture that targets a retrograde station
**When** the conformance runner executes
**Then** the computed Station matches Astro.com on body, direction, date, time and degree

### Story 3.3: Detect every crossing of a natal house cusp

As Francesco,
I want each transiting body's entry into a new natal house dated exactly, including the ones it makes backwards,
So that a planet that crosses a cusp three times in a month is described as three events rather than one.

**Acceptance Criteria:**

**Given** the analyzed month interval and a Client's twelve Placidus cusps
**When** the scan runs
**Then** each crossing of a natal cusp by a transiting body is recorded with the body, the house departed, the house entered, and the exact date and UTC time of the crossing

**Given** a body moving retrograde back across a cusp it already crossed
**When** the scan runs
**Then** the crossing is detected and recorded in the same way as a direct one
**And** repeated crossings of the same cusp within one month are each recorded as separate Ingresses

**Given** the month fixtures
**When** the conformance runner executes
**Then** computed Ingresses match Astro.com

### Story 3.4: Locate the month's new and full moons

As Francesco,
I want each Lunation located exactly and placed in the natal house it falls in,
So that the closing advice has the month's lunations to synthesize against the overall picture.

**Acceptance Criteria:**

**Given** the analyzed month interval
**When** Lunations are located
**Then** Δλ = (λ_Moon − λ_Sun) mod 360° is tracked, with a new moon at 0° and a full moon at 180°, located by temporal bisection
**And** each Lunation records its kind, exact date, UTC time, zodiacal degree, and the natal house it falls in

**Given** a month containing no Lunation of a given kind, or two of one kind
**When** the scan completes
**Then** the result is recorded as found and requires no intervention from Francesco — neither case is an error

**Given** the fixtures targeting a month with two Lunations of one kind and a month with none
**When** the conformance runner executes
**Then** computed Lunations match Astro.com in both cases

### Story 3.5: Start a month's computation and watch it finish

As Francesco,
I want a month's work to run as a checkpointed job I can watch,
So that a spin-down, a redeploy or a rate-limit stall costs me the current stage rather than the whole run.

**Acceptance Criteria:**

**Given** a Client and a requested month
**When** Francesco starts a run
**Then** a `ReportRun` row is created and advances forward only through `natal_ready → transits_ready → payload_ready → draft_ready → gate_passed → exported`
**And** each stage persists its output to Postgres before the next begins
**And** the stages beyond those implemented so far are declared but not yet reachable

**Given** a run interrupted partway
**When** it is re-driven
**Then** it resumes at the first incomplete stage and recomputes nothing that already succeeded
**And** every stage function is idempotent on its input

**Given** the process being killed mid-run
**When** the application restarts and the run is re-driven
**Then** the completed stages are read back from Postgres — nothing depended on the container filesystem

**Given** a running job
**When** Francesco watches it
**Then** an HTMX polling view shows the current stage and updates as it advances

**Given** any external call the runner makes
**When** it hits a rate limit or a transient error
**Then** it is absorbed by bounded backoff, and every log line for the run carries its `ReportRun` id

**Given** the `REPORT_RUN` table
**When** it is created
**Then** it joins the FR-29 Client deletion cascade

### Story 3.6: Assemble the Report Payload each Section needs

As Francesco,
I want the natal material and the month's events organized into exactly what each of the eight Sections requires,
So that nothing downstream ever has to go looking for a fact, and nothing can introduce one.

**Acceptance Criteria:**

**Given** a Natal Chart, its Domain Profiles, the month's Transit Events and a `ComputationConfig`
**When** `core/payload/` assembles the Payload
**Then** *Energia generale* receives slow-planet transits to the angular houses (1st, 4th, 7th, 10th) and to the personal planets (Sun, Moon, Mercury, Venus, Mars), plus all active retrogrades
**And** *Amore* receives the amore Profile, transits to the 5th and 7th houses, and transit Aspects to natal Venus and Mars
**And** *Lavoro* receives the lavoro Profile, transits to the midheaven, 10th and 6th houses, and transit Aspects to natal Mercury, Mars and Saturn
**And** *Denaro* receives the denaro Profile, transits to the 2nd and 8th houses, and transit Aspects to natal Jupiter and Saturn
**And** *Benessere* receives the benessere Profile, transits to the ascendant and 6th house, and transit Aspects to natal Mars, Saturn and Moon
**And** *Consiglio finale* receives the natal houses the month's Lunations fall in, against the overall transit picture

**Given** the Section-to-Payload mapping
**When** it is implemented
**Then** it lives in `data/sections.toml` as versioned data loaded by the core
**And** assembly contains no per-Section branch — adding a report format adds a mapping, not a branch

**Given** assembly
**When** it runs
**Then** it is a pure function: no clock, no network, no database, no randomness
**And** identical Natal Chart, month and configuration produce the same Payload every time

### Story 3.7: Project the two day-lists by code, so a day cannot be misfiled

As Francesco,
I want the favorable and difficult days sorted by a table rather than by judgement,
So that the most client-visible error the product could make cannot occur at all.

**Acceptance Criteria:**

**Given** the month's Transit Events and the harmonic/disharmonic table in `data/computation.toml`
**When** the day-lists are projected
**Then** trines and sextiles classify as harmonic, and squares and oppositions as disharmonic
**And** a conjunction by transiting Venus or Jupiter classifies as harmonic
**And** a conjunction by transiting Mars, Saturn or Pluto classifies as disharmonic
**And** a conjunction by any other transiting body classifies as neutral and appears in neither day list

**Given** a Lunation
**When** it is classified
**Then** it is favorable if it forms a trine or sextile to a natal point within Orb, or is conjunct natal Venus or Jupiter
**And** all other Lunations appear in their Section payloads but in neither day list

**Given** *Giorni favorevoli*
**When** it is projected
**Then** it receives the dated harmonic Aspect Perfections and the favorable Lunations

**Given** *Giorni di attenzione*
**When** it is projected
**Then** it receives the dated disharmonic Aspect Perfections and the retrograde Stations

**Given** a neutral event
**When** the day-lists are projected
**Then** it is never silently dropped — it remains available to Sections 1–5 and 8

**Given** the projection
**When** it runs
**Then** it is a pure function applying the configured table, and the dated entries it produces are the only source of dates for Sections 6 and 7

### Story 3.8: Freeze the Payload so any Report can be reproduced years later

As Francesco,
I want each Payload versioned, content-addressed and immutable,
So that a citation means the same entry forever and a stored Payload can be reproduced exactly.

**Acceptance Criteria:**

**Given** an assembled Payload
**When** entry identifiers are created
**Then** each entry's ID is a stable hash of its canonical field tuple
**And** IDs are never sequential, never time-derived and never random
**And** entries are emitted in a total order over those same fields

**Given** a Payload being serialized
**When** it is written
**Then** it is canonical JSON: sorted keys, no insignificant whitespace, `Decimal` serialized as a fixed-precision string
**And** byte-identity for identical inputs is asserted by test across two machines, not assumed

**Given** a stored Payload
**When** it is persisted
**Then** it records its own schema version, the `computation.toml` version and content hash, the `sections.toml` version, and the ephemeris file identity that produced it
**And** it is stored in Postgres, never on the container filesystem

**Given** a Payload whose Report has been generated
**When** any later operation runs
**Then** the Payload is immutable — no path exists to modify it

**Given** a Payload produced under an older schema version
**When** it is read back
**Then** it remains interpretable

**Given** the `REPORT_PAYLOAD` table
**When** it is created
**Then** it joins the FR-29 Client deletion cascade

### Story 3.9: Read the facts behind a month, entry by entry

As Francesco,
I want to open the computed facts for a month and see them per Section,
So that when a client asks "why do you say that?" mid-call I can answer in one sentence.

**Acceptance Criteria:**

**Given** a completed run with a stored Payload
**When** Francesco opens the Payload view
**Then** he can see, for each of the eight Sections, the exact Transit Events and natal placements supplied to it

**Given** an entry in the view
**When** it is displayed
**Then** it shows the transiting body, the natal point, the aspect type, the exact date and time, and the orb

**Given** an instant stored in UTC
**When** it is displayed
**Then** it is converted to the Client's local time using the historical zone resolved at Story 2.1, and the conversion happens only in `shell/http/`

**Given** a Payload from a run completed months earlier
**When** Francesco opens it
**Then** it is fully readable, with no loss of detail

**Given** the view
**When** it is reached
**Then** it is reachable within one interaction from the run it belongs to

---

## Epic 4: Eight Sections of Italian prose in my register, that don't repeat last month

Francesco writes the Style Guide, edits it in the application without a deploy, and generation
produces eight Sections conditioned on it — treating still-active transits as continuing rather than
reintroducing them.

**FRs covered:** FR-16, FR-17, FR-18, FR-19, FR-30 · **NFRs:** NFR-3, NFR-12, NFR-13, NFR-17, NFR-18, NFR-19 · **Governed by:** AD-3, AD-6, AD-9, AD-14, AD-19

### Story 4.1: Write the Style Guide

As Francesco,
I want my own register written down as an artifact,
So that the Generator has something to be conditioned on — because this is the one deliverable no amount of engineering can produce.

**Acceptance Criteria:**

**Given** Francesco's existing hand-written reports as reference
**When** the Style Guide is authored
**Then** it covers register and address to the reader; sentence rhythm and length habits; vocabulary he uses and vocabulary he avoids; how a claim is anchored to its transit and date; and the interpretive territory of each of the eight Sections

**Given** the interpretive territory of each Section
**When** it is written
**Then** it is written from scratch, because the material the PRD cites as its starting point does not exist as cited — `addendum.md` §8 is *Validation approach*, and §4 records which data feeds each Section rather than what each Section is for
**And** the Section on *Benessere* is written to stay clear of anything a reader could take as a medical statement, which is the register against which the GDPR Article 9 determination was made

**Given** the guide
**When** it is delivered
**Then** it is committed as `data/style-guide.seed.md`
**And** it is understood to be writing work rather than engineering, startable on day one, and blocking only this epic

**Given** PRD §12
**When** this story is scheduled
**Then** it is treated as the highest-risk item in the build, because SM-2 rests entirely on how well it is written

### Story 4.2: Edit the Style Guide without a deploy

As Francesco,
I want to revise my Style Guide in the application and keep every prior version,
So that a change in output quality can be traced back to the revision that caused it.

**Acceptance Criteria:**

**Given** the seed file `data/style-guide.seed.md`
**When** the application first runs
**Then** it seeds Style Guide version 1 into the database
**And** thereafter the database is the source of truth — the repository file seeds version 1 only

**Given** the Style Guide editor
**When** Francesco saves a revision
**Then** a new version row is written with an incremented version number
**And** all prior versions are retained and readable
**And** no code change or redeploy is required

**Given** a database with no Style Guide version
**When** generation is attempted
**Then** it refuses to run and says why

### Story 4.3: Derive a ReportTheme from a Payload

As Francesco,
I want what the system remembers about a month computed rather than judged,
So that two runs of the same month never seed different continuity the following month.

**Acceptance Criteria:**

**Given** a stored Report Payload
**When** `derive_theme(payload)` runs in `core/memory/`
**Then** it returns the dominant slow-planet Aspects ordered by tightness, the natal houses the month's Lunations fall in, and the standing retrogrades

**Given** the derivation
**When** it runs
**Then** it is pure and model-free — no Generator call, no I/O, no clock
**And** the same Payload always yields the same Theme

**Given** a derived Theme
**When** it is stored
**Then** it is written to its own table, separate from generation, so a later change to what is remembered does not change the Generator contract
**And** the `REPORT_THEME` table joins the FR-29 Client deletion cascade

### Story 4.4: Compute what has changed since last month

As Francesco,
I want the difference between two months computed as a fact,
So that "nothing significant has changed" is something the system knows rather than something the model decides.

**Acceptance Criteria:**

**Given** two ReportThemes for consecutive months
**When** they are compared
**Then** the comparison yields each theme element as still-active, tightened, resolved or new
**And** the comparison is deterministic — the same pair always produces the same diff

**Given** two consecutive months whose themes differ in no meaningful element
**When** they are compared
**Then** the result states plainly that nothing significant has changed, as a computed value

**Given** a Client's first month
**When** a Theme is derived
**Then** there is no previous Theme, and the comparison is not attempted

### Story 4.5: Generate eight Sections as cited structure

As Francesco,
I want the model to return sentences that each name the facts they rest on,
So that verification is reading a citation rather than guessing what a sentence was based on.

**Acceptance Criteria:**

**Given** the `Generator` port
**When** it is defined
**Then** it accepts exactly `(ReportPayload, StyleGuide, ReportTheme_previous, ReportTheme_current)` and nothing else
**And** its adapter holds no database handle, no filesystem access and no tool definitions
**And** prior Report prose is never sent to the Generator

**Given** a generation request
**When** it is made
**Then** the Style Guide version in force is supplied with every request, and the version used is recorded on the Report
**And** generation cannot proceed without a Style Guide present

**Given** a generation response
**When** it is returned
**Then** each Section is an ordered list of sentences, each carrying the Payload entry IDs it rests on
**And** the eight Sections are present in fixed order: Energia generale del mese, Amore, Lavoro, Denaro, Benessere, Giorni favorevoli, Giorni di attenzione, Consiglio astrologico finale
**And** the output language is Italian, under every configuration

**Given** Sections 6 and 7
**When** the model writes them
**Then** it emits no date token within them — it writes only connective prose around the dated entries projected in Story 3.7

**Given** the generated text
**When** it is inspected
**Then** the register is professional and non-fatalistic, and no sentence predicts a fixed outcome, a medical event, a death or a financial result

**Given** the configured provider
**When** real Client data is first sent
**Then** its data terms have been verified and the check recorded

### Story 4.6: Render cited sentences into prose I could read aloud

As Francesco,
I want the structured response turned into continuous Italian prose,
So that a report works as a script on a call, not just as a document on a page.

**Acceptance Criteria:**

**Given** a generated Section of cited sentences
**When** the shell renders it
**Then** Sections 1–5 and 8 render as continuous prose, never as bullet fragments
**And** Sections 6 and 7 render the code-projected dated entries, and may use list form

**Given** the rendering
**When** it happens
**Then** it happens in the shell, and the citations are retained against the stored draft rather than discarded at render time

**Given** a rendered Report
**When** it is read aloud
**Then** the sentences survive it — this is a review criterion on the Style Guide, checked by ear rather than by test

**Given** a completed draft
**When** the run advances
**Then** the cited draft structure is persisted at the `draft_ready` stage, because the hand sampling behind SM-7 needs it
**And** the draft table records the Style Guide version and the Section-composition version that produced it
**And** the draft table joins the FR-29 Client deletion cascade

### Story 4.7: Write this month as a continuation, not a reprint

As Francesco,
I want a returning client's report to build on what I already told them,
So that Giulia's March reads like the next chapter rather than a reprint of February.

**Acceptance Criteria:**

**Given** a Client with at least one prior month
**When** generation runs
**Then** the previous and current ReportThemes are both supplied to the Generator
**And** a transit covered in the prior month and still active is treated as continuing — what has moved, tightened or resolved — rather than reintroduced from scratch

**Given** a computed diff stating that nothing significant has changed
**When** generation runs
**Then** the Report says so plainly and does not manufacture novelty

**Given** a Client's first Report
**When** generation runs
**Then** it runs with no previous Theme and the text makes no reference to prior months

**Given** continuity
**When** it is supplied
**Then** it travels only as ReportTheme — no prior Report's prose reaches the Generator by any path

### Story 4.8: Absorb a rate limit without my involvement

As Francesco,
I want transient generation failures handled by the system,
So that forty reports in an afternoon do not become forty interruptions.

**Acceptance Criteria:**

**Given** a provider rate limit or a transient error
**When** generation is attempted
**Then** it is retried automatically with bounded backoff sized for the provider's 10 requests-per-minute ceiling
**And** Francesco is not involved

**Given** exactly one configured Generator adapter
**When** any failure occurs
**Then** there is no automatic failover to another provider under any circumstances
**And** changing provider is a deliberate configuration change gated on a recorded data-terms verification

**Given** retries that are exhausted
**When** the run ends
**Then** the Report is marked failed and surfaced to Francesco with the reason
**And** no partial Report exists that could be exported

### Story 4.9: Build against the Generator without spending quota

As Francesco,
I want local development to use recorded responses,
So that building and testing the generation path costs nothing and stays deterministic.

**Acceptance Criteria:**

**Given** the local environment
**When** the application runs under Docker Compose against a local Postgres
**Then** the configured Generator adapter replays recorded responses instead of calling the provider

**Given** the recorded-response adapter
**When** it is used in tests
**Then** the shell is tested at the port boundary with fakes, and the same tests exercise the real port contract

**Given** the two environments
**When** they are configured
**Then** exactly two exist — local and production — with no staging environment

---

## Epic 5: A report I can trust enough to send without reading it

Every Claim is checked against the Report Payload before Francesco sees the Report; failures
regenerate automatically and, when persistent, are shown alongside the Payload entries they
contradict. This is the emotional job-to-be-done: send a report without reading it first, and not
worry about what is in it.

**FRs covered:** FR-20, FR-21, FR-22 · **NFRs:** NFR-3, NFR-4, NFR-11, NFR-14 · **Governed by:** AD-5, AD-6, AD-7, AD-8

### Story 5.1: Define what counts as a Claim, as versioned data

As Francesco,
I want the line between a Claim and an interpretation drawn in one place and versioned,
So that the Gate's strictness cannot drift and make its pass rate meaningless.

**Acceptance Criteria:**

**Given** `core/gate/vocabulary.it.json`
**When** it is created
**Then** it holds the closed Italian astronomical vocabulary: the ten planets, the twelve signs, `casa` with an ordinal, a day-of-month numeral, `retrogrado` and `stazionario`
**And** it carries its own integer version, independent of the Payload and Section-composition versions

**Given** a sentence
**When** it is classified
**Then** it is a Claim if and only if it contains a token from that vocabulary
**And** a sentence containing no such token is interpretation: never a Claim, never failing the Gate, governed by the Style Guide instead

**Given** the vocabulary
**When** it is revised
**Then** the version increments, and every Report records which version classified it

**Given** a sentence that leans on a fact without naming it
**When** the Gate runs
**Then** it is not policed, and this limit is documented rather than papered over — it is not verifiable against a Payload by any mechanism

### Story 5.2: Check every Claim against the Payload

As Francesco,
I want each astronomical sentence verified against the facts that produced it,
So that nothing a client reads under my name was invented by a model.

**Acceptance Criteria:**

**Given** a cited draft and its Payload
**When** `run_gate(draft, payload)` executes in `core/gate/`
**Then** it calls no model and performs no I/O, and is a pure function of its two arguments

**Given** a Claim naming a planet, sign, house, degree, aspect, date or retrograde condition not present in the Payload
**When** the Gate runs
**Then** the Claim fails the check

**Given** a Claim that contradicts the Payload — a wrong date for a named Aspect Perfection, a wrong house for a Lunation, a body described as retrograde that is not
**When** the Gate runs
**Then** the Claim fails the check

**Given** a sentence containing a closed-vocabulary token with an empty citation list
**When** the Gate runs
**Then** it is a violation

**Given** a date token appearing anywhere in Section 6 or Section 7 of the model's own output
**When** the Gate runs
**Then** it is a violation, because those dates are projected by code and the model may not write them

**Given** a deliberately corrupted draft
**When** the Gate runs
**Then** it fails on every injected class: an invented body, a wrong date, a wrong house, and a false retrograde

**Given** the same draft and Payload
**When** the Gate runs twice
**Then** the result is identical

### Story 5.3: Make the Gate the only path to an exportable Report

As Francesco,
I want it to be structurally impossible to reach an export without passing the Gate,
So that the guarantee holds without anyone remembering to check.

**Acceptance Criteria:**

**Given** a run reaching the `draft_ready` stage
**When** it advances
**Then** the Gate runs before the Report is shown to Francesco in any exportable state
**And** the run advances to `gate_passed` only on a passing `GateResult`

**Given** a passing `GateResult`
**When** the run advances
**Then** the `REPORT` row is written — a Report exists only on a Gate pass, never before
**And** it records the Style Guide version, the Payload schema version and the Gate vocabulary version that produced it
**And** the `REPORT` table joins the FR-29 Client deletion cascade

**Given** a Report whose stored `GateResult` is not `passed`
**When** any export is attempted
**Then** it is refused

**Given** the codebase
**When** export functions are counted
**Then** exactly one exists, and it takes a stored Report ID
**And** no function anywhere accepts a draft and produces an exportable artifact
**And** a test asserts this, so a second export path cannot be added quietly

### Story 5.4: Regenerate a failing Report automatically, whole

As Francesco,
I want a failing Report retried without me,
So that the occasional bad generation costs nothing and the Sections never come from different drafts.

**Acceptance Criteria:**

**Given** a Report failing the Gate
**When** regeneration triggers
**Then** it is automatic and bounded by a configured limit
**And** the whole Report is regenerated, never a single failing Section
**And** the regeneration count for the run is incremented

**Given** a regeneration
**When** it runs
**Then** it re-runs from the same stored Payload, so the astronomy cannot change between attempts

**Given** the bound being reached
**When** the last attempt still fails
**Then** the run stops and the Report is surfaced rather than discarded

### Story 5.5: See exactly what failed and what it contradicts

As Francesco,
I want a persistently failing Report shown to me with its failing Claims against the facts,
So that I can tell a Style Guide problem from a Gate problem instead of guessing.

**Acceptance Criteria:**

**Given** a Report that has exhausted its regeneration bound
**When** Francesco opens it
**Then** he sees the Report text, each failing Claim, and the Payload entries each Claim contradicts or is missing from

**Given** such a Report
**When** it is handled
**Then** it is never silently discarded

**Given** such a Report
**When** export is attempted
**Then** it is refused, and the reason is stated

### Story 5.6: Keep the Gate's record so a regression is visible early

As Francesco,
I want every Gate outcome stored and queryable,
So that a rising regeneration rate warns me before a client ever sees the problem.

**Acceptance Criteria:**

**Given** a Report that has been through the Gate
**When** its result is stored
**Then** it records whether it passed, how many regenerations were required, every Claim flagged, and the vocabulary version that classified it
**And** the `GATE_RESULT` table joins the FR-29 Client deletion cascade

**Given** the stored results
**When** they are queried across Reports
**Then** the first-generation pass rate is reportable, which is where SM-5 is answered from
**And** the regeneration count is reportable as its own series, which is what keeps SM-5 honest

**Given** a monthly sample of Reports that passed
**When** Francesco checks them by hand against their stored Payloads
**Then** the stored draft citations and Payload entries are available to make that check possible — this is the only measure of the Gate's false-negative rate

---

## Epic 6: Review, export and history — the forty-reports-in-an-afternoon loop

Francesco reads a Report with its Payload alongside and the Gate result visible, exports to PDF and
Markdown recording send disposition in one interaction, browses Report History, and takes a durable
backup with a staleness warning when he has not.

**FRs covered:** FR-25, FR-26, FR-27 · **NFRs:** NFR-4, NFR-5, NFR-6, NFR-9 · **Governed by:** AD-7, AD-17

### Story 6.1: Read a Report with its facts one click away

As Francesco,
I want the finished Report and the facts behind it on the same screen,
So that skimming a report and defending a sentence are the same interaction.

**Acceptance Criteria:**

**Given** a Report that has passed the Gate
**When** Francesco opens it
**Then** all eight Sections are displayed in their fixed order
**And** the Gate result is visible, including the regeneration count

**Given** the displayed Report
**When** Francesco wants the underlying facts
**Then** the Payload view built in Story 3.9 is reachable within one interaction, without leaving the Report

**Given** a Report generated months earlier
**When** it is opened
**Then** its Payload and Gate result are intact and equally reachable

### Story 6.2: Export a passed Report to PDF and Markdown

As Francesco,
I want a clean file containing only what the client should see,
So that I can send it without checking what leaked into it.

**Acceptance Criteria:**

**Given** a Report whose stored `GateResult` is `passed`
**When** Francesco exports it
**Then** both PDF and Markdown are available

**Given** an exported file
**When** its contents are inspected
**Then** it contains only the eight Sections and the Client's name
**And** it contains no chart wheel, no Payload, no Gate result, no run identifier and no internal metadata

**Given** a Report that has not passed the Gate
**When** export is attempted
**Then** it is refused

**Given** the first export of a Report
**When** it completes
**Then** the run reaches `exported` once
**And** each subsequent export writes an `EXPORT_RECORD` row rather than moving the stage again

### Story 6.3: Record how the report went out, in one interaction

As Francesco,
I want to say whether I sent it as generated or edited it first, in a single click,
So that the measurement survives forty reports in an afternoon instead of being abandoned by report six.

**Acceptance Criteria:**

**Given** an export
**When** it happens
**Then** Francesco records the send disposition — *sent as generated* or *edited before sending* — in exactly one interaction
**And** nothing heavier than a single choice is required

**Given** a completed Report
**When** the export is recorded
**Then** the elapsed time from Client selection to export is recorded with it

**Given** the recorded dispositions and elapsed times
**When** they are queried
**Then** the unedited send rate is reportable (SM-2) and the time per Report is reportable (SM-1)
**And** the `EXPORT_RECORD` table joins the FR-29 Client deletion cascade

### Story 6.4: Browse everything I have produced for a Client

As Francesco,
I want every prior Report for a Client listed in order,
So that I can reopen a month a client is asking about and see exactly what I told them.

**Acceptance Criteria:**

**Given** a Client with prior Reports
**When** Francesco opens their history
**Then** the Reports are listed by Client and month, in order

**Given** a prior Report in the list
**When** Francesco opens it
**Then** it reopens with its Payload and Gate result intact

**Given** a Report generated against a Natal Chart that has since been superseded by a correction
**When** it is opened
**Then** it remains readable and is marked as belonging to the superseded chart

### Story 6.5: Take a backup I actually hold

As Francesco,
I want one action that downloads everything to my own machine,
So that the durability requirement does not rest on a six-hour restore window I cannot extend.

**Acceptance Criteria:**

**Given** an authenticated request to the backup route
**When** it runs
**Then** it produces a complete logical export containing Clients, Natal Charts, Reports, Report Payloads, Gate results, Themes and Corpus entries
**And** the export downloads to Francesco's machine

**Given** the export
**When** it is produced
**Then** it is complete enough that a restore reconstructs the application's state — not a partial dump

**Given** the route
**When** it is reached
**Then** it is authenticated like every other route

### Story 6.6: Be told when my backup is out of date

As Francesco,
I want a visible warning when I have produced work I have not backed up,
So that the gap is something I notice during a batch rather than after a loss.

**Acceptance Criteria:**

**Given** a newest Report that postdates the last recorded export
**When** Francesco uses the application
**Then** a warning is displayed

**Given** a fresh backup
**When** it completes
**Then** the warning clears

**Given** the last-export timestamp
**When** it is stored
**Then** it lives in Postgres, not on the container filesystem

---

## Epic 7: Corpus collection (parallel track — gates nothing in v1)

Francesco adds past reports as text, marks each paired or unpaired, and sees the composition count
that decides whether phase-2 conditioning is viable. Nothing in v1 waits on it.

**FRs covered:** FR-23, FR-24 · **Governed by:** AD-11

### Story 7.1: Add a past report to the Corpus

As Francesco,
I want to paste in a report I wrote by hand, whatever it came from,
So that the material for phase-2 voice conditioning stops being scattered across email and folders.

**Acceptance Criteria:**

**Given** a past report from email, messaging or a file
**When** Francesco adds it
**Then** it is stored as text, regardless of its original source
**And** it is stored in Postgres, never on the container filesystem

**Given** the `CORPUS_ENTRY` table
**When** it is created
**Then** it joins the FR-29 Client deletion cascade for any entry that references a Client

**Given** this epic
**When** it is scheduled
**Then** it can start on day one and blocks nothing else in v1

### Story 7.2: Mark an entry paired or unpaired

As Francesco,
I want each entry marked according to whether I know the chart behind it,
So that the paired subset is identifiable when exemplar selection becomes possible.

**Acceptance Criteria:**

**Given** a Corpus entry
**When** it is recorded
**Then** it is marked either paired — matched to birth data and month — or unpaired, prose only

**Given** a paired entry
**When** a matching Client exists in the application
**Then** the entry links to that Client and that month

**Given** a paired entry whose Client is not in the application
**When** it is recorded
**Then** it is still marked paired, and the link is left unset rather than forcing a Client to be invented

**Given** the identifiable client material these entries contain
**When** any phase-2 use is contemplated
**Then** an anonymization position is required first — recorded here as an open question that gates no v1 story

### Story 7.3: See how much Corpus I actually have

As Francesco,
I want the paired and unpaired counts visible,
So that I can decide whether few-shot conditioning is worth attempting.

**Acceptance Criteria:**

**Given** the Corpus
**When** Francesco opens the composition view
**Then** the total entry count is shown, split into paired and unpaired

**Given** the counts
**When** they are requested
**Then** they are visible at any time, without a batch job or a manual query

---

## Epic 8: Release validation — measure what the PRD assumed

The PRD carries four numbers it never validated and one guarantee it never re-checked. This epic
settles them by measurement before anything reaches a paying client.

**FRs covered:** none directly · **NFRs:** NFR-1, NFR-5, NFR-9, NFR-10, NFR-17 · **Governed by:** AD-2, AD-17

### Story 8.1: Pass conformance across the full adversarial fixture set

As Francesco,
I want every reference chart matching Astro.com before anything ships,
So that the benchmark my professional judgement is calibrated to is actually met.

**Acceptance Criteria:**

**Given** the complete adversarial fixture set from Story 1.7
**When** the conformance runner executes
**Then** computed positions, house cusps, transit-to-natal Aspects, Stations, Ingresses and Lunations match Astro.com for every fixture
**And** the pass rate is 100% — this is a release gate, not a trend

**Given** any fixture that does not match
**When** the runner reports
**Then** release does not proceed

### Story 8.2: Re-verify the generation provider's data terms and record it

As Francesco,
I want the data terms checked against what is published today, not what was published during planning,
So that a paying client's birth data is not used to train a third party's model.

**Acceptance Criteria:**

**Given** the configured Generator provider
**When** release validation runs
**Then** its current published data terms are read and compared against the EEA paid-tier terms the design relies on
**And** the check is recorded with its date and outcome

**Given** terms that have changed materially
**When** the check is made
**Then** release does not proceed until the change is assessed

**Given** hosting and data storage
**When** they are verified
**Then** both are located in the EU/EEA where the chosen free tier offers the choice

### Story 8.3: Measure the latency the PRD only assumed

As Francesco,
I want the real numbers for a report and for a month scan,
So that the budgets in the PRD are facts rather than derivations.

**Acceptance Criteria:**

**Given** real Reports produced end to end
**When** latency is measured
**Then** the p90 from "Client selected" to "Report on screen" — scan, assembly, generation, Gate and any bounded regeneration included — is recorded against the 3-minute budget

**Given** a full-month transit scan for one Client
**When** it is measured
**Then** the elapsed time is recorded against the 10-second bound

**Given** a measurement that exceeds its documented budget
**When** it is recorded
**Then** the documented budget is revised to match reality rather than left standing as an unmet number
**And** PRD Assumptions 3 and 4 are marked resolved with the measured values

**Given** a working session
**When** throughput is exercised
**Then** forty Reports can be produced, reviewed and exported in one sitting

### Story 8.4: Project storage growth against the free-tier ceiling

As Francesco,
I want to know how long permanent Payload retention fits in the database I have,
So that the traceability guarantee does not quietly run out of room.

**Acceptance Criteria:**

**Given** a real Report Payload
**When** its stored size is measured
**Then** the measurement is recorded

**Given** the measured size and the target volume of 100–200 Reports per month
**When** growth is projected
**Then** the projection is compared against Neon's 0.5 GB free-plan ceiling and the date it would be reached is recorded

**Given** a projection reaching half the ceiling
**When** it is recorded
**Then** a storage growth policy is raised as a decision rather than absorbed

### Story 8.5: Restore from a backup, for real

As Francesco,
I want a restore actually performed before release,
So that the durability requirement is demonstrated rather than assumed.

**Acceptance Criteria:**

**Given** a complete logical export from Story 6.5
**When** it is restored into an empty database
**Then** Clients, Natal Charts, Reports, Report Payloads, Gate results, Themes and Corpus entries are all reconstructed

**Given** the restored application
**When** a previously exported Report is opened
**Then** its Payload and Gate result are intact, and its Claims remain traceable

**Given** the rehearsal
**When** it completes
**Then** the procedure is recorded, so it can be followed under pressure rather than reconstructed
