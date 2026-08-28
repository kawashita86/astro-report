# Epic 3 Context: Every dated fact for a Client's month, inspectable

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Francesco picks a Client and a month and gets every transit event of that month located to the exact
instant, then assembled into a versioned, immutable Report Payload he can read entry by entry. This
epic builds the monthly transit engine (aspect perfections, retrograde stations, house-cusp
crossings, lunations), the checkpointed run machinery that drives a month's computation to
completion, the per-Section Payload assembly that is the sole fact channel for everything
downstream, and the operator view that exposes those facts behind a Report. It delivers standalone
value — with these dated facts Francesco could write reports by hand and still have removed almost
all the transcription labor — and it supplies the astronomical ground truth that generation (Epic 4)
and the Groundedness Gate (Epic 5) depend on.

## Stories

- Story 3.1: Find every transit-to-natal Aspect and the exact moment it perfects
- Story 3.2: Date every Station and know what is standing retrograde
- Story 3.3: Detect every crossing of a natal house cusp
- Story 3.4: Locate the month's new and full moons
- Story 3.5: Start a month's computation and watch it finish
- Story 3.6: Assemble the Report Payload each Section needs
- Story 3.7: Project the two day-lists by code, so a day cannot be misfiled
- Story 3.8: Freeze the Payload so any Report can be reproduced years later
- Story 3.9: Read the facts behind a month, entry by entry
- Story 3.10: Advance a report run without blocking the request

## Requirements & Constraints

- The month is scanned continuously and every event located to an exact date and UTC time by
  bisection — never a sample-date approximation. The event set for a given natal chart, month and
  config is identical on every run and deployment.
- Aspect detection: fast bodies (Sun, Mercury, Venus, Mars) and slow bodies (Jupiter, Saturn,
  Uranus, Neptune, Pluto) against the ten natal planets, the ascendant, the midheaven and both
  Lunar Nodes; five major aspects only. The transiting Moon is excluded from aspect detection and
  enters only via lunations. Each aspect records transiting body, natal point, aspect type, exact
  perfection instant, and the in-orb window (entry/exit dates). Aspects in orb but never perfecting
  in the month are kept and flagged, not dropped.
- Retrograde condition from longitudinal velocity (dλ/dt < 0). Each station records body, direction
  of turn, exact instant, zodiacal degree. A body retrograde all month with no station is recorded
  as a standing condition with the month's retrograde span.
- Every house-cusp crossing recorded with body, house departed, house entered, exact instant —
  including retrograde re-crossings, each repeated crossing of the same cusp counted separately.
- New and full moons located by bisection on Sun–Moon elongation; record kind, exact instant,
  zodiacal degree, and the natal house they fall in. Zero or two lunations of one kind is normal,
  never an error.
- The Payload organizes the natal chart, the four Domain Profiles and the month's events into
  exactly the material each of the eight Sections needs (Energia generale, Amore, Lavoro, Denaro,
  Benessere, Giorni favorevoli, Giorni di attenzione, Consiglio finale). Assembly is a pure
  function — identical inputs yield a byte-identical Payload.
- Each Payload carries a schema version, is stored permanently in Postgres with its Report (exactly
  one Payload per Report), and is immutable once its Report is generated. Older-schema Payloads stay
  interpretable.
- Francesco can open the computed facts for any month — including runs from months earlier — and
  see, per Section, the exact events and natal placements supplied to it (body, natal point, aspect
  type, exact date/time, orb). Reachable within one interaction from the run.
- Success criteria: output matches Astro.com for every conformance fixture (natal + month); the
  full-month scan for one Client completes well within budget (target under 10s); every delivered
  Claim stays traceable to a stored Payload entry; loss of a Payload is unacceptable.

## Technical Decisions

- **Purity boundary.** Scanning, classification and Payload assembly live in `core/transits/` and
  `core/payload/` as pure functions — no clock, network, DB, randomness, env reads, or import from
  `shell/`. The ephemeris read in `core/ephemeris/` is the only sanctioned I/O. The shell loads
  inputs, calls core, persists results.
- **UTC in core; local time only at the edges.** Every computed/stored instant is timezone-aware
  UTC, ISO-8601 with explicit `Z`. The analyzed month is one half-open UTC interval derived once
  from the Client's local calendar-month boundaries, so an event at 23:30 local on the last day
  belongs to exactly one Report. Conversion to local time happens only in `shell/http/`, using the
  historical zone snapshot stored on the Client.
- **ComputationConfig passed explicitly.** Orbs (natal ±7.0°, tunable 6.0–8.0; transit-to-natal
  ±2.0°, tunable 1.5–2.5), house system, fast/slow body sets, Ruler tables and the
  harmonic/disharmonic table come from one versioned data file, loaded into a frozen value and
  passed as an argument to every core function that needs it — never read ambiently. Its version
  and content hash are recorded on every Payload.
- **Payload is the only fact channel.** Nothing downstream may introduce an astronomical fact;
  everything a Section needs enters through the Payload.
- **Content-derived entry IDs.** Each entry's ID is a stable hash of its canonical field tuple —
  never sequential, time-derived or random. Entries emitted in a total order over those fields.
  Serialization is canonical JSON (sorted keys, no insignificant whitespace, `Decimal` as
  fixed-precision string); byte-identity asserted by test across two machines.
- **Day-lists rendered by code, not the model.** Sections 6 and 7 dated entries are projected from
  the Payload by a pure function applying the configured table: trine/sextile harmonic;
  square/opposition disharmonic; conjunction by transiting Venus/Jupiter harmonic; by
  Mars/Saturn/Pluto disharmonic; otherwise neutral (in neither list). A favorable lunation forms a
  trine/sextile to a natal point within orb, or is conjunct natal Venus or Jupiter. Neutral events
  are never dropped — they stay available to Sections 1–5 and 8. This projection is the only source
  of dates for Sections 6 and 7.
- **Section composition is data.** The Section-to-selector mapping lives in a versioned data file
  loaded by core; adding a format adds a mapping, not a branch — no per-Section conditional in
  assembly. The Payload schema, the section-composition file and the Gate vocabulary each carry an
  independent integer version, all recorded on every Report.
- **Checkpointed report run.** A `ReportRun` row advances forward-only through
  `natal_ready → transits_ready → payload_ready → draft_ready → gate_passed → exported`. Each stage
  persists its output to Postgres before the next begins; re-driving resumes at the first incomplete
  stage; every stage function is idempotent. Stages past this epic's scope are declared but
  unreachable. All durable state is in Postgres — nothing written to the container filesystem at
  runtime is read back.
- **Non-blocking advance (AD-20, Story 3.10).** The runner exposes a single `advance` function that
  performs at most one stage transition and returns, invoked only from the poll handler
  `GET /report-runs/{run_id}` — never from a thread, task, queue or scheduled job. `POST
  /clients/{client_id}/report-runs` creates the row and returns immediately without advancing; the
  first stage runs on the first poll. Concurrent polls are single-flighted by a Postgres
  transaction-scoped advisory lock on the run id (released on commit/rollback/dropped connection). A
  poll may take as long as its one stage (including one external call and bounded backoff) but
  never chains into a second. Story 3.10 also fixes the now-stale `shell/runner/driver.py` and
  `shell/http/routes/report_runs.py` docstrings.
- **Conventions.** UUIDv7 primary keys (Payload entry hashes are not DB identities). Angles are
  `Decimal`, never binary float; longitudes normalized to `[0, 360)`; orbs signed with an
  applying/separating flag. Core raises typed errors from `core/errors.py`, never returns `None` for
  failure, never imports an HTTP status code. `snake_case` modules named for their stage — no
  `utils`/`helpers`/`common`. Structured logging carrying an identifier only — never birth data,
  names or prose — with the `ReportRun` id on every run log line. Alembic migrations forward-only,
  one per change. Every new Client-referencing table joins the FR-29 delete cascade (`REPORT_RUN`
  and `REPORT_PAYLOAD` here). Core is covered by example tests and Astro.com conformance fixtures
  that run on every change.

## UX & Interaction Patterns

- Story 3.5 ships an HTMX polling view over run status showing the current stage and updating as it
  advances; Epic 9 later re-flows it into a six-node stage-track component, so keep the endpoint
  poll-friendly.
- The Payload-behind-the-Report view (Story 3.9) must be reachable within one interaction from the
  run, group facts by the eight Sections, and show instants in the Client's local time (converted
  only in the shell). Epic 9 later replaces its markup with a typed per-Section disclosure and
  click-to-copy entry-ID chips — keep the data contract stable.

## Cross-Story Dependencies

- Depends on Epic 2: the stored Natal Chart, the four Domain Profiles, and the per-Client immutable
  zone snapshot (used for the UTC month interval and local-time display).
- Within the epic: Stories 3.1–3.4 (the detectors) feed Story 3.6 (assembly), which feeds Story 3.7
  (day-list projection). Story 3.5 introduces the run frame all stages slot into; Story 3.8 freezes
  and versions the assembled Payload; Story 3.9 reads back a frozen Payload; Story 3.10 refactors
  the Story 3.5 runner to the non-blocking one-stage-per-poll model (AD-20) and adds the
  advisory-lock single-flight test.
- Downstream: Epic 4 (generation) and Epic 5 (Gate) consume the Payload as their only fact source;
  ReportTheme derivation (Epic 4) is a pure function of the Payload. Story 3.10 is a prerequisite
  for Epic 9 and realizes CAP-30 ("watch a report run progress") together with Epic 9 Story 9.5.
