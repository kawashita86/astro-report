# Epic 3 Context: Every dated fact for a Client's month, inspectable

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Francesco picks a Client and a month and gets every Transit Event — Aspect Perfections, Stations,
Ingresses, Lunations — located to the exact instant and assembled into a versioned, immutable Report
Payload he can read entry by entry. This replaces his manual four-date sampling, which can only say
"around the 10th" and cannot drive the dated day lists Sections 6 and 7 need. The epic has standalone
value: with these facts alone he could write reports by hand and still cut nearly all the transcription
labor. It also builds the correctness spine everything downstream depends on — no fact may enter a
Report except through this Payload.

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

## Requirements & Constraints

- The analyzed month is one half-open UTC interval derived from the Client's local calendar-month
  boundaries, so every event belongs to exactly one month. Events are recorded in UTC, shown in local
  time. Full scan completes in under 10 seconds (unvalidated budget).
- Transit-to-natal Aspects: fast bodies (Sun, Mercury, Venus, Mars) and slow bodies (Jupiter, Saturn,
  Uranus, Neptune, Pluto) against the ten natal planets, ascendant, midheaven, both Lunar Nodes; five
  major aspects only. The transiting Moon is excluded from Aspect detection (it would swamp the day
  lists) and enters only through Lunations. Transit-to-natal Orb defaults ±2.0°, tunable ±1.5°–±2.5°.
  An Aspect in orb but never perfecting in the month is recorded and flagged, not dropped.
- Retrograde condition: dλ/dt < 0. A body retrograde all month with no Station is recorded as a
  standing condition. Ingresses (cusp crossings) are recorded identically for direct and retrograde
  motion, including repeated crossings of the same cusp. Lunations are located by bisection on
  Δλ = (λ_Moon − λ_Sun) mod 360° (new at 0°, full at 180°); zero or two of one kind in a month is
  normal, not an error.
- Payload assembly (FR-13) is a pure function of Natal Chart + Domain Profiles + Transit Events +
  config, byte-identical for identical inputs. Each of the eight Sections receives a fixed slice: the
  four Domain-Profile sections get their Profile plus transits/Aspects to their governing houses and
  planets (Amore→Venus/Mars/5th/7th; Lavoro→Mercury/Mars/Saturn/MC/10th/6th; Denaro→Jupiter/Saturn/
  2nd/8th; Benessere→Mars/Saturn/Moon/ASC/6th); Energia generale gets slow-planet transits to angular
  houses (1/4/7/10) and personal planets plus all active retrogrades; Consiglio finale gets the natal
  houses the month's Lunations fall in.
- Sections 6/7 day lists are table-driven, never judgement: trine/sextile → harmonic; square/opposition
  → disharmonic; conjunction by transiting Venus/Jupiter → harmonic; by Mars/Saturn/Pluto →
  disharmonic; by any other body → neutral (appears in neither list, but never dropped from Sections
  1–5/8). A favorable Lunation trines/sextiles a natal point in orb, or conjuncts natal Venus/Jupiter.
- Every stored Report has exactly one immutable Payload once generated; older schema versions stay
  interpretable. Francesco can view, for any Report (even months old), the exact entries — body, natal
  point, aspect type, date/time, orb — behind each Section, one interaction away from the Report.
- Conformance: computed Aspects, Stations, Ingresses and Lunations must match Astro.com on every
  transcribed month fixture (Epic 1); identical inputs must yield an identical event set and
  byte-identical Payload on every run and machine.

## Technical Decisions

- **Purity (AD-1/AD-11):** scanning and assembly live in `core/` — no I/O, clock, network, randomness;
  only exception is the ephemeris reader. All Payload/run state lives in Postgres, nothing durable on
  the host filesystem.
- **AD-2:** every Payload records the pinned ephemeris file identity that produced it.
- **AD-3:** this Payload is the *only* channel through which the Generator (Epic 4) will ever see
  facts.
- **AD-4:** Payload entry IDs are stable hashes of each entry's canonical field tuple — never
  sequential/time/random — emitted in a total order over those fields.
- **AD-5:** Sections 6/7 day-list entries are projected from the Payload by pure code applying the
  harmonic/disharmonic table; no date token in those Sections is ever written by a model later.
- **AD-10:** a `ReportRun` row advances forward-only through persisted stages
  (`natal_ready → transits_ready → payload_ready → …`), each stage persisting before the next begins,
  each stage function idempotent, resuming at the first incomplete stage after interruption. Bounded
  backoff absorbs rate limits/transient errors; every log line carries the `ReportRun` id. An HTMX view
  polls run status.
- **AD-12:** every instant computed/stored is UTC; local-time conversion happens only in `shell/http/`.
- **AD-13:** the Section-to-Payload mapping lives in `data/sections.toml`, versioned data loaded by the
  core — assembly has no per-Section branch.
- **AD-18:** the transit-to-natal Orb, fast/slow body sets and harmonic/disharmonic table live in the
  single versioned `data/computation.toml` → frozen `ComputationConfig`, passed explicitly, never read
  ambiently. Its version/hash, the Payload's own schema version, and the `sections.toml` version are
  all recorded on every Payload.
- Payload serialization is canonical JSON (sorted keys, no insignificant whitespace, `Decimal` as
  fixed-precision string); byte-identity is asserted by test across machines.
- `REPORT_RUN` and `REPORT_PAYLOAD` must each join the FR-29 Client-deletion cascade when created.

## UX & Interaction Patterns

- HTMX polling view shows a running `ReportRun`'s current stage, updating live; this epic implements
  stages through Payload assembly, later stages declared but not yet reachable.
- Payload-behind-the-Report view (FR-15): per-Section entries (body, natal point, aspect type,
  date/time, orb), reachable in one interaction from the run/Report, fully readable months later.

## Cross-Story Dependencies

- Story 3.6 consumes the events from 3.1–3.4 plus Epic 2's Domain Profiles.
- Story 3.5 (checkpointed runner) is the execution frame the other stage functions plug into.
- Story 3.7 (day-lists) depends on 3.6's assembled, classified events; Story 3.8 (freeze/version)
  applies to the Payload only once 3.7's classification is part of it; Story 3.9 (read view) depends on
  a completed run with a frozen Payload (3.8) and reuses Epic 2's Client local-time resolution.
- This epic's Payload is Epic 4's Generator's sole input (AD-3); Epic 4's `ReportTheme` is derived
  purely from it. Epic 5's Gate checks every Claim against these Payload entries; Epic 6's review view
  builds on Story 3.9.
