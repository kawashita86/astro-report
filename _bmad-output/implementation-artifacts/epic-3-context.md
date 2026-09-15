# Epic 3 Context: Every dated fact for a Client's month, inspectable

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

For a given Client and month, locate every astronomical fact — transit-to-natal Aspects and their
exact perfection moments, retrograde Stations, house Ingresses, and Lunations — to the exact UTC
instant, then assemble those facts into a single versioned, immutable Report Payload organized by
what each of the eight report Sections needs. The Payload is the sole channel through which any
astronomical fact can ever reach a generated Report (AD-3): nothing downstream may introduce a fact
that isn't in it. This epic also owns the report-run lifecycle — a checkpointed, resumable job the
operator can start, watch and (as of the pending Story 3.11) let finish unattended — and a read view
so any Payload, including one behind a months-old Report, can be inspected entry by entry. Together
this realizes UJ-3: a client can be told "why" a Report says what it says, in one sentence, at any
time later.

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
- Story 3.11: Run in background when the tab closes (backlog; full spec at
  `_bmad-output/specs/spec-3-11-run-in-background-when-the-tab-closes/SPEC.md`)

## Requirements & Constraints

- Every located event (Aspect perfection, Station, Ingress, Lunation) must carry an exact date and
  UTC time, never a sampled approximation, and the set of events for a given Natal Chart + month
  must be identical on every run (computational determinism).
- Fast transiting bodies (Sun, Mercury, Venus, Mars) and slow ones (Jupiter, Saturn, Uranus, Neptune,
  Pluto) are scanned for Aspects; the transiting Moon is excluded from Aspect detection and enters
  only through Lunations. Natal targets: the ten planets, ascendant, midheaven, and both Lunar Nodes.
  Only the five major aspect types apply.
- The harmonic/disharmonic/neutral classification for the two day-list Sections is a fixed,
  table-driven rule (trine/sextile → harmonic; square/opposition → disharmonic; conjunction by
  Venus/Jupiter → harmonic; conjunction by Mars/Saturn/Pluto → disharmonic; conjunction by any other
  body → neutral, dropped from both day lists but retained for other Sections). This is confirmed
  domain fact, not an inferred convention, and must never become a judgement call in code.
- Computed output must match the Astro.com reference fixtures for every conformance case before a
  Report can reach a client.
- Full-month scan for one Client must complete in under 10 seconds; the full run (scan through Gate)
  targets under 3 minutes at the 90th percentile, sustaining forty Reports in a session.
- All durable state (ReportRun, Report Payload) lives in Postgres, never the container filesystem,
  and joins the Client deletion cascade.
- Payload assembly and the day-list projection are pure functions: no clock, no network, no database,
  no randomness — identical inputs always produce a byte-identical Payload.

## Technical Decisions

- **Purity boundary (AD-1):** `core/` (including all of this epic's detection and assembly logic)
  is pure — no I/O, clock, network or env reads. The one declared exception is the ephemeris read
  inside `core/ephemeris/`.
- **Payload as sole channel (AD-3):** the Generator receives only `(ReportPayload, StyleGuide,
  ReportTheme_previous, ReportTheme_current)`. Any fact a Section needs must be added at Payload
  assembly, never supplied another way.
- **Content-derived entry IDs (AD-4):** each Payload entry's ID is a stable hash of its canonical
  field tuple — never sequential, time-derived or random — so a citation means the same entry across
  regenerations.
- **Day-lists are code, not model output (AD-5):** Sections 6/7 dates come only from the pure
  projection function; the Generator emits no date token in those Sections.
- **Checkpointed run (AD-10):** `ReportRun` advances forward-only through `natal_ready →
  transits_ready → payload_ready → draft_ready → gate_passed → exported`, each stage persisting
  before the next begins; every stage function is idempotent; re-driving resumes at the first
  incomplete stage.
- **No filesystem durability (AD-11):** all state goes to Postgres; nothing written at runtime is
  read back after a restart.
- **UTC in the core (AD-12):** every computed/stored instant is UTC; conversion to Client local time
  happens only in `shell/http/`. The analyzed month is a single half-open UTC interval derived once
  from local calendar-month boundaries, so a boundary event belongs to exactly one month.
- **Section composition is data (AD-13):** the Section-to-Payload mapping lives in `data/sections.toml`,
  versioned; assembly contains no per-Section branch.
- **One ComputationConfig (AD-18):** Orb values, house system, body sets, Ruler tables and the
  harmonic/disharmonic table all live in one versioned, frozen `ComputationConfig` passed explicitly
  into every core function; its version and content hash are recorded on every Payload.
- **AD-20, amended 2026-09-14 (governs Story 3.11):** a single deployment-wide `REPORT_RUN_MODE`
  setting (`poll` | `background`, read once into `shell/config.py` `Settings`, default `poll`)
  selects how forward progress happens — never configurable per run.
  - `poll` mode is AD-20's original rule verbatim: `advance()` performs at most one stage transition
    and is invoked only from `GET /report-runs/{run_id}`, under a Postgres advisory lock on the run
    id; Story 3.10's behavior and regression tests must remain byte-for-byte unchanged.
  - `background` mode adds one in-process scheduler task (started at app startup, stopped at
    shutdown) that ticks the same `advance()`, under the same advisory lock, for every `ReportRun`
    with `failed_at IS NULL` and `stage != 'gate_passed'`. The poll handler becomes read-only in this
    mode — it renders state without calling `advance()`, so a run is never advanced twice for the
    same transition.
  - No queue, broker or second deployable in either mode; the architecture's Deferred worker/queue
    option stays reserved for a scale change that hasn't happened.
  - `background` mode requires a Render plan with no idle spin-down — a documented deployment
    prerequisite, not something the app enforces or detects.
  - No boot-time reconciliation pass after a restart/redeploy: only the scheduler's in-memory timer
    is lost, never persisted stage data; resuming is left to the next poll or next scheduler tick.
  - A run rewound to `payload_ready` for human Gate review (Stories 5.7/5.8) is ticked by the
    scheduler like any other incomplete run — no special-case pause; AD-10's existing
    `stage_failure_count` / max bound still terminally fails it.

## UX & Interaction Patterns

- The stage track (Story 9.5) is the loading pattern for a running report — never a generic spinner.
  It shows nodes for each stage and, while active, polls at a fixed 2s cadence, pausing when the tab
  is hidden and stopping on any terminal stage.
- **Vedi Payload** is available as soon as `payload_ready` (and later stages) is reached, giving the
  Payload-inspection view (Story 3.9 / FR-15) reachable within one interaction from the run.
- The Payload view shows, per Section, the exact Transit Events and natal placements supplied to it;
  each entry shows transiting body, natal point, aspect type, exact date/time (converted to Client
  local time only at this display layer) and orb.
- **Addendum (2026-09-14) for Story 3.11:** the stage-track view must render identically regardless
  of `REPORT_RUN_MODE` — same nodes, captions, poll cadence and Gate-failure recovery affordances.
  In `background` mode the poll only reads and renders; an operator who never reopens the tab still
  finds the run at (or past) `gate_passed` on return, exactly as if they had kept polling throughout.

## Cross-Story Dependencies

- Stories 3.1–3.4 (Aspects, Stations, Ingresses, Lunations) feed directly into Story 3.6's Payload
  assembly and Story 3.7's day-list projection; 3.6/3.7 cannot be implemented meaningfully without
  detection output shaped per their acceptance criteria.
- Story 3.8 (freezing/versioning the Payload) depends on 3.6's assembled structure existing.
- Story 3.9 (Payload inspection view) depends on 3.8's persisted, versioned Payload.
- Story 3.5 (checkpointed run) and Story 3.10 (non-blocking poll-driven advance) together define the
  `ReportRun` lifecycle that Story 3.11 extends — 3.11 must not alter AD-10 stage semantics,
  `advance()`'s idempotence, or the advisory lock, and `poll` mode must remain exactly what 3.10
  shipped.
- Story 3.11 is a constraint on, but not new scope for, Epic 9's stage-track view: the view must be
  mode-agnostic. Epic 5 (Gate) and Epic 6 (export/history) consume only `ReportRun.stage` and are
  unaffected by which mode produced it.
