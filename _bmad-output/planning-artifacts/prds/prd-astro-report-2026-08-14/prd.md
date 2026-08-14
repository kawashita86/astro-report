---
title: astro-report
status: final
created: 2026-08-14
updated: 2026-08-14
---

# PRD: astro-report

## 0. Document Purpose

This PRD is the build contract for astro-report: a single-operator production tool that turns five
client facts into a finished, client-ready monthly astrological report in Italian. It is written for
the downstream architecture, UX and story workflows, and for Francesco as the sole operator and
decision-maker.

It builds on two existing artifacts and does not duplicate them: the **product brief**
(`_bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/brief.md`) for positioning and
market rationale, and its **addendum** (same folder) for the verbatim source specification, the
technology assessment, the ruler tables, orb values and the jurisdiction analysis. Where this PRD
states a rule that the addendum details, the addendum is the reference. Technical *how* — libraries,
stack, deployment mechanics — stays in the addendum and belongs to the architecture phase, not here.

Structure: vocabulary is fixed in §3 Glossary and used verbatim everywhere. Features are grouped in
§4 with functional requirements nested and numbered globally (FR-1…FR-N) so they survive
reorganization. FR numbers are **append-only and never reused** — a requirement added later keeps the
next free number rather than being inserted in sequence, so a feature may legitimately contain
non-consecutive FR numbers. Inferences are tagged inline as `[ASSUMPTION]` and indexed in §15.

---

## 1. Vision

A working astrologer spends one to three hours producing a single monthly report, and almost none of
that time is spent on astrology. It goes to transcription: loading a chart on Astro.com, sampling the
month by hand, annotating retrogrades and ingresses and aspect orbs across four dates, then
cross-referencing all of it against the natal positions before a single sentence gets written. At
thirty to fifty reports a month that is roughly eighty hours of clerical labor. At the volume the
practice is aiming for — one to two hundred a month — it exceeds what a full-time month contains.

astro-report removes that labor entirely. Five inputs go in: name, birth date, birth time, birthplace,
and the month to read. A finished report comes out: eight sections of Italian prose covering the
month's general energy, love, work, money, wellbeing, favorable days, days to watch, and a closing
piece of advice — in Francesco's own register, ready to send without editing.

The thing that makes this safe to send is a hard separation. **The system computes; the language model
narrates.** Every astronomical fact in a delivered report is calculated locally by Swiss Ephemeris and
handed to the model as a fixed payload. The model is forbidden from producing any claim that is not in
that payload, and generated output is checked against it before anyone sees it. Generic AI writes
fluent astrological prose over invented astronomy — which is worse than useless the moment a paying
client acts on it. Here, every sentence traces back to a computed fact, which is what lets Francesco
defend any line of a report when a client questions it mid-consultation.

---

## 2. Target User

### 2.1 Jobs To Be Done

- **Functional** — Get exact astronomical facts for a client's month without opening Astro.com or
  transcribing anything by hand.
- **Functional** — Produce eight sections of finished Italian prose that read as my own writing, not
  as generated text.
- **Functional** — Reuse a client's natal chart every month instead of re-deriving it.
- **Emotional** — Send a report without reading it first, and not worry about what is in it.
- **Social** — Answer "why do you say that?" live, mid-consultation, with the actual transit and date
  behind the sentence.
- **Contextual** — Work through thirty to fifty clients a month now, and one to two hundred later,
  without the hours scaling with them.

### 2.2 Non-Users (v1)

- **Clients.** They receive a report. They never see, log into, or know about the application.
- **Other astrologers.** Not deferred — this tool serves one operator, permanently. Multi-tenancy is
  not a roadmap item.
- **Anyone learning astrology.** The tool assumes professional competence and explains nothing.

### 2.3 Key User Journeys

Downscaled shape: this is single-operator tooling, so journeys are short. They exist because the
*client* is a real second stakeholder who never touches the product, and two of the three journeys
turn on what happens after the report leaves.

- **UJ-1. Francesco produces a month's reports in an afternoon.**
  It is the 28th and next month's reports are due. He opens astro-report in the browser, already
  signed in. His client list is there from last month. He selects a recurring client, confirms the
  month, and starts generation; the natal chart is already computed and stored, so only the transits
  and the prose are new. Within a couple of minutes he has an eight-section Italian report on screen
  alongside the computed facts that produced it. He skims, exports to PDF, moves to the next client.
  **Climax:** the report is finished and he did not open Astro.com once. **Resolution:** forty reports
  done in an afternoon instead of a month of evenings.

- **UJ-2. A returning client's March report does not repeat February's.**
  Giulia has been a subscriber for eight months. Francesco generates her March report. The system
  knows what it already told her — February leaned heavily on a Saturn transit to her 10th house that
  is still in orb — and writes March as a continuation rather than a restatement: what has moved,
  what has resolved, what is newly exact. **Climax:** Giulia reads a report that sounds like the next
  chapter, not a reprint. **Edge case:** if nothing astrologically significant has changed since the
  prior month, the system says so plainly rather than inventing novelty.

- **UJ-3. A client questions a sentence while Francesco reads it aloud.**
  Francesco is on a call, reading Marco's report aloud. Marco stops him: "why do you say the second
  half of the month is harder?" Francesco opens the report's underlying facts and sees the exact
  entry — transiting Mars square natal Saturn, perfecting on the 19th, within a 2° orb. He answers in
  one sentence. **Climax:** the claim holds up under live scrutiny. **Resolution:** the client's trust
  in the reading increases rather than erodes.

---

## 3. Glossary

Downstream workflows must use these terms exactly. Introducing a synonym anywhere is a discipline
violation.

- **Client** — A person Francesco produces reports for. Holds a name, birth date, birth time,
  birthplace, and a resolved geographic coordinate and historical timezone. One Client has exactly one
  Natal Chart and zero-to-many Reports.
- **Natal Chart** — The computed birth chart for a Client: ascendant, midheaven, each planet's sign,
  degree and house, the Lunar Nodes, the twelve Placidus house cusps, and the principal natal Aspects.
  Computed once per Client and stored permanently; never recomputed unless birth data is corrected.
- **Lunar Nodes** — The North and South Nodes of the Moon, recorded with sign, degree and house. Part
  of the Natal Chart; not required by any Section, but computed for chart completeness.
- **Aspect** — An angular relationship between two chart points, limited to the five major aspects:
  conjunction (0°), sextile (60°), square (90°), trine (120°), opposition (180°). Qualified as *natal*
  (between two Natal Chart points) or *transit-to-natal* (between a transiting body and a Natal Chart
  point).
- **Orb** — The permitted angular deviation from an exact Aspect. Natal Aspects and transit-to-natal
  Aspects use different Orb values — see FR-3 and FR-9 respectively.
- **Transit Event** — A single dated astronomical occurrence within the analyzed month, with an exact
  date and UTC time. One of four kinds: an **Aspect Perfection**, a **Station**, an **Ingress**, or a
  **Lunation**.
- **Aspect Perfection** — The moment a transit-to-natal Aspect becomes exact (Orb = 0).
- **Station** — The moment a transiting body's longitudinal velocity changes sign; the body turns
  retrograde or direct.
- **Ingress** — The moment a transiting body crosses a Natal Chart house cusp, entering a new natal
  house.
- **Lunation** — A new moon (Sun–Moon elongation 0°) or full moon (180°), recorded with exact date,
  UTC time, zodiacal degree, and the natal house it falls in.
- **Ruler** — The planet governing a sign, and by extension the planet governing a house whose cusp
  falls in that sign. Resolved in both **traditional** and **modern** systems.
- **Domain Profile** — The natal material for one life area, assembled from the Natal Chart per fixed
  rules. Exactly four exist: **Amore** (love), **Lavoro** (work), **Denaro** (money), **Benessere**
  (wellbeing).
- **Report Payload** — The complete, versioned, structured set of computed facts handed to the
  Generator for one Report. The sole source of astronomical truth available to the Generator. Stored
  permanently alongside the Report it produced.
- **Generator** — The language model that renders a Report Payload into Italian prose. It narrates; it
  never calculates.
- **Report** — The finished Italian document for one Client and one month: eight Sections in fixed
  order.
- **Section** — One of the eight ordered parts of a Report: *Energia generale del mese*, *Amore*,
  *Lavoro*, *Denaro*, *Benessere*, *Giorni favorevoli*, *Giorni di attenzione*, *Consiglio astrologico
  finale*.
- **Claim** — A statement of astronomical fact within generated Report text (a position, a date, an
  Aspect, a retrograde condition). Every Claim must be traceable to an entry in the Report Payload.
- **Groundedness Gate** — The automated check that every Claim in a generated Report is supported by
  the Report Payload, before the Report is shown to Francesco.
- **Style Guide** — The hand-written description of Francesco's register, tone and sentence habits used
  to condition the Generator in v1. Authored by Francesco (FR-30); a v1 deliverable in its own right.
- **Send disposition** — Francesco's record, made at export, of whether a Report was sent as generated
  or edited before sending. The measurement source for SM-2.
- **Corpus** — The collected body of Francesco's existing hand-written reports. **Paired** where a
  report can be matched to the birth data and month that produced it; **unpaired** where only prose
  survives.
- **Report History** — The stored sequence of prior Reports for a Client, used to prevent a Report from
  restating its predecessors.

---

## 4. Features

### 4.1 Client Record and Natal Chart

**Description:** Francesco enters a Client once. The system resolves the birthplace to coordinates and
to the timezone in force *at the moment of birth* — historical, not current, which is the difference
between a correct chart and a chart that is an hour off — then computes the Natal Chart and stores it
permanently. Every subsequent month reuses it. Realizes UJ-1.

Correcting birth data is possible and invalidates the stored Natal Chart, forcing recomputation.
Because prior Reports were produced against the old chart, the system warns before allowing it.

**Functional Requirements:**

#### FR-1: Create a Client

Francesco can create a Client from five inputs: name, birth date, birth time, birthplace, and (per
report) the month to analyze.

**Consequences (testable):**
- All five inputs are required; a Client cannot be persisted with any missing.
- **Birth time is mandatory and exact, to the minute.** A Client without a known birth time cannot be
  created, and no Natal Chart or Report is produced for them. There is no degraded path: the system
  does not substitute a noon chart, solar houses, or a house-less reading. Houses, ascendant and
  midheaven are load-bearing for three of the four Domain Profiles, so an approximated birth time would
  silently corrupt Amore, Lavoro and Benessere rather than fail visibly.
- Birthplace is entered as free text and resolved (FR-2) before the Client is persisted.
- Names are not required to be unique. Two Clients may share a name and remain distinct records.

#### FR-2: Resolve birthplace to coordinates and historical timezone

The system resolves a free-text birthplace to latitude, longitude, and the UTC offset in force at the
Client's birth date and time, including historical DST rules.

**Consequences (testable):**
- Resolution returns latitude and longitude to at least four decimal places.
- The UTC offset applied is the one in force at the birth instant at that location, not the present-day
  offset. A birth in Italy on 1975-06-15 resolves to CEST (+02:00), not CET.
- Ambiguous place names present Francesco with the candidate matches and require an explicit choice;
  the system never silently picks one.
- A resolved birthplace is cached, so repeat entries of the same place do not re-query the geocoder.
- If resolution fails, the Client is not persisted and Francesco is told which step failed.

#### FR-3: Compute and store the Natal Chart

On Client creation the system computes the Natal Chart and stores it.

**Consequences (testable):**
- The stored chart contains: ascendant and midheaven; for each of Sun, Moon, Mercury, Venus, Mars,
  Jupiter, Saturn, Uranus, Neptune and Pluto — sign, degree and natal house; the North and South Lunar
  Nodes with sign, degree and house; all twelve Placidus house cusps; and all natal Aspects within Orb.
- Houses use the Placidus system.
- Natal Aspect Orb: **default ±7.0°**, configurable within ±6.0° to ±8.0°. Distinct from and wider than
  the transit-to-natal Orb (FR-9).
- The Natal Chart is computed exactly once per Client and read from storage thereafter.
- Recomputation occurs only when birth data is corrected (FR-4).

#### FR-4: Correct birth data

Francesco can correct a Client's birth data, which invalidates and recomputes the Natal Chart.

**Consequences (testable):**
- The system warns that prior Reports were generated against the previous chart before applying the
  change.
- Prior Reports and their Report Payloads are retained unchanged and remain marked as belonging to the
  superseded chart.

#### FR-5: Render the chart wheel for verification

The system renders a chart wheel for a Client's Natal Chart, for Francesco's verification only.

**Consequences (testable):**
- The wheel shows planetary positions, house cusps and natal Aspects.
- The wheel is never included in a Report or any Client-facing export.

#### FR-28: Restrict access to the application

The application is reachable only by Francesco. *(Appended during finalization — see §0 on FR
numbering.)*

**Consequences (testable):**
- No Client data, Report, Report Payload or chart wheel is reachable without authenticating.
- Unauthenticated requests to any route return no Client data of any kind, including in error messages.
- A session persists across a working batch so Francesco does not re-authenticate per Report (UJ-1
  assumes he is already signed in).
- There is exactly one account. Account creation, invitations, password reset flows for other people,
  and role distinctions are all out of scope (§8).

#### FR-29: Delete a Client and their Reports

Francesco can delete a Client outright.

**Consequences (testable):**
- Deleting a Client removes the Client record, the Natal Chart, every Report, every Report Payload and
  every Corpus pairing that referenced them.
- Deletion is confirmed before it executes and reports what will be removed.
- Deletion is complete rather than a soft flag: no deleted Client data remains readable through the
  application.

**Notes:** `[NOTE FOR PM]` The wheel (FR-5) exists so Francesco can eyeball the computation against what
he would have seen on Astro.com. Its value is highest during conformance validation (§14 step 8, SM-3)
and may decline afterward.

---

### 4.2 Domain Profiles

**Description:** The Natal Chart is regrouped from the way an ephemeris emits it into the way an
astrologer reads it: four Domain Profiles, each assembled by a fixed rule from the addendum's
specification. This is pure derivation — no judgement, no model involvement — which is what makes it
reproducible.

**Functional Requirements:**

#### FR-6: Resolve house Rulers

For each house cusp, the system resolves the governing planet in both traditional and modern systems.

**Consequences (testable):**
- Both traditional and modern Rulers are resolved and stored for all twelve cusps.
- Where the two systems differ — Scorpio, Aquarius, Pisces — both the modern Ruler and the traditional
  co-ruler are recorded.
- Ruler assignment follows the table in the brief addendum §3 exactly.

#### FR-7: Assemble the four Domain Profiles

The system assembles Amore, Lavoro, Denaro and Benessere from the Natal Chart.

**Consequences (testable):**
- **Amore** contains: Venus (sign, house, Aspects); Mars (sign, house, Aspects); 5th house (sign,
  planets in it, Ruler); 7th house (sign, planets in it, Ruler); Moon (sign, house, Aspects).
- **Lavoro** contains: 10th, 6th and 2nd houses and the midheaven — each with sign, planets in it,
  Rulers, and principal Aspects.
- **Denaro** contains: 2nd and 8th houses; Venus, Jupiter, Saturn and their Aspects.
- **Benessere** contains: ascendant, Ruler of the ascendant, 6th house, Mars, Saturn, Moon.
- Assembly is a pure function of the Natal Chart: the same Natal Chart always yields byte-identical
  Domain Profiles.

---

### 4.3 Monthly Transit Engine

**Description:** For a requested month, the system finds every Transit Event and dates it exactly. This
supersedes Francesco's hand method of sampling days 1, 10, 20 and the last of the month — that sampling
was a transcription of what is possible by hand, not of what is correct, and it cannot produce the
dated day lists that Sections 6 and 7 of a Report require. A four-date sample can say "around the
10th"; the product must say "the 19th".

Realizes UJ-1, UJ-3.

**Functional Requirements:**

#### FR-8: Scan the month continuously

The system scans the requested month at a resolution fine enough to locate every Transit Event to the
exact date and UTC time.

**Consequences (testable):**
- Every Transit Event carries an exact date and UTC time, not a sample-date approximation.
- Scanning covers the full calendar month in the Client's local timezone, with events recorded in UTC
  and presented in local time.
- The set of Transit Events for a given Natal Chart and month is identical on every run.

#### FR-9: Detect transit-to-natal Aspects and their perfection dates

The system detects every Aspect between a transiting body and a Natal Chart point during the month, and
locates the exact moment of perfection.

**Consequences (testable):**
- Transiting bodies covered: **fast** — Sun, Mercury, Venus, Mars; **slow** — Jupiter, Saturn, Uranus,
  Neptune, Pluto. The transiting Moon is deliberately excluded: it aspects every natal point within
  each month and would swamp the day lists. It enters the Report only through Lunations (FR-12).
- Natal points targeted: the ten planets, **the ascendant and the midheaven**, and the Lunar Nodes.
- Aspects limited to the five major aspects.
- Transit-to-natal Orb is tighter than natal Orb: **default ±2.0°**, configurable within ±1.5° to
  ±2.5° so the value can be tuned against real Reports without a code change.
- Each detected Aspect records the transiting body, the natal point, the aspect type, the exact
  perfection date and UTC time, and the in-orb window (entry and exit dates).
- Aspects that are in orb during the month but never perfect within it are recorded and flagged as
  such.

#### FR-10: Detect retrogrades and Stations

The system identifies which bodies are retrograde during the month and dates every Station.

**Consequences (testable):**
- Retrograde condition is determined from longitudinal velocity: a body is retrograde where dλ/dt < 0.
- Each Station records the body, the direction of the turn (retrograde or direct), the exact date and
  UTC time, and the zodiacal degree.
- Bodies retrograde for the entire month with no Station inside it are recorded as a standing condition
  with the month's retrograde span.

#### FR-11: Detect Ingresses into natal houses

The system detects each crossing of a natal house cusp by a transiting body.

**Consequences (testable):**
- Each Ingress records the body, the house departed, the house entered, and the exact date and UTC time
  of the cusp crossing.
- Cusp crossings caused by retrograde motion are detected and recorded in the same way as direct ones,
  including repeated crossings of the same cusp within one month.

#### FR-12: Locate Lunations

The system locates the new and full moons falling within the month.

**Consequences (testable):**
- Each Lunation records its kind (new or full), exact date, UTC time, zodiacal degree, and the natal
  house it falls in.
- A month containing no Lunation of a given kind, or two of one kind, requires no intervention from
  Francesco.

**Feature-specific NFRs:**
- The full month scan for one Client completes in under 10 seconds. `[ASSUMPTION: bounds set by the
  target of forty-plus reports in an afternoon; not measured.]`

---

### 4.4 Report Payload Assembly

**Description:** This is the spine of the product's correctness guarantee. Everything the Generator
will ever know about a Client's month is assembled here, into one versioned structure, by pure
derivation. Nothing downstream of this point may introduce an astronomical fact. If a fact is not in
the Report Payload, it may not appear in the Report.

The Payload is stored permanently alongside the Report it produced — which is what makes UJ-3 possible
months after the fact.

**Functional Requirements:**

#### FR-13: Assemble the Report Payload per Section

The system assembles a Report Payload organizing the Natal Chart, Domain Profiles and Transit Events
into the material each of the eight Sections requires.

**Consequences (testable):**
- **Energia generale** receives: slow-planet transits to the angular houses (1st, 4th, 7th, 10th) and
  to the personal planets (Sun, Moon, Mercury, Venus, Mars); all active retrogrades.
- **Amore** receives: the Amore Domain Profile; transits to the 5th and 7th houses; transit Aspects to
  natal Venus and Mars.
- **Lavoro** receives: the Lavoro Domain Profile; transits to the midheaven, 10th and 6th houses;
  transit Aspects to natal Mercury, Mars and Saturn.
- **Denaro** receives: the Denaro Domain Profile; transits to the 2nd and 8th houses; transit Aspects
  to natal Jupiter and Saturn.
- **Benessere** receives: the Benessere Domain Profile; transits to the ascendant and 6th house;
  transit Aspects to natal Mars, Saturn and Moon.
- **Giorni favorevoli** receives: dated harmonic Aspect Perfections and favorable Lunations, classified
  by the fixed rule below.
- **Giorni di attenzione** receives: dated disharmonic Aspect Perfections and retrograde Stations,
  classified by the fixed rule below.
- **Consiglio finale** receives: the natal houses the month's Lunations fall in, against the overall
  transit picture.
- Assembly is a pure function: identical Natal Chart, month and configuration always produce a
  byte-identical Report Payload.

**Harmonic / disharmonic classification rule.** Sections 6 and 7 sort Transit Events into two day
lists. Because §4.4 asserts that Payload assembly is pure derivation, the sort cannot rest on
judgement — it is table-driven:

| Aspect type | Classification |
|---|---|
| Trine, sextile | Harmonic |
| Square, opposition | Disharmonic |
| Conjunction, transiting Venus or Jupiter | Harmonic |
| Conjunction, transiting Mars, Saturn or Pluto | Disharmonic |
| Conjunction, any other transiting body | Neutral — appears in neither day list |

- A **tense Mars or Saturn passage** is a transiting Mars or Saturn forming a conjunction, square or
  opposition to any natal point. It is disharmonic by the table above; the term is defined here only
  because Francesco's source specification uses it.
- A **favorable Lunation** is a Lunation forming a trine or sextile to a natal point within Orb, or
  conjunct natal Venus or Jupiter. All other Lunations appear in their Section payloads but in neither
  day list.
- Neutral events are never silently dropped: they remain available to Sections 1–5 and 8.

**Confirmed by Francesco on 2026-08-14**, including the treatment of conjunctions, where the rule
assigns by transiting body rather than by the natal point being contacted. This is his professional
judgement on his own method, so the table above is domain fact rather than inferred convention. It
stays configuration rather than code — a future revision is a data edit and a version bump, never a
code change.

#### FR-14: Version and persist the Report Payload

Each Report Payload carries a schema version and is stored permanently with its Report.

**Consequences (testable):**
- Every stored Report has exactly one stored Report Payload.
- The Payload schema version is recorded, so Payloads produced under older rules remain interpretable.
- A stored Payload is immutable once its Report is generated.

#### FR-15: Expose the Payload behind the Report

Francesco can view the Report Payload entries underlying any Report, including Reports generated months
earlier. Realizes UJ-3.

**Consequences (testable):**
- For any Section, Francesco can see the exact Transit Events and natal placements supplied to it.
- Each entry displays body, natal point, aspect type, exact date and time, and orb.
- The view is reachable within one interaction from a displayed Report.

---

### 4.5 Italian Report Generation

**Description:** The Generator receives a Report Payload, the Style Guide, and the relevant Report
History, and writes eight Sections of Italian prose. It is given no tools, no computation ability, and
no astronomical knowledge it is expected to apply — only facts and instructions about how to say them.

The prose must be **speakable**: Francesco sometimes reads reports aloud, in which case the Report is a
script rather than a document. Bullet fragments do not survive that use.

Realizes UJ-1, UJ-2.

**Functional Requirements:**

#### FR-16: Generate the eight Sections in Italian

The system generates a Report of exactly eight Sections in the fixed order.

**Consequences (testable):**
- Section order is always: Energia generale del mese, Amore, Lavoro, Denaro, Benessere, Giorni
  favorevoli, Giorni di attenzione, Consiglio astrologico finale.
- Output language is Italian. No other language is produced under any configuration.
- Narrative Sections (1–5, 8) are continuous prose, not bullet fragments.
- Sections 6 and 7 present dated days and may use list form. `[ASSUMPTION: inferred from the
  speakability constraint and the dated nature of those two Sections; Francesco did not specify.]`
- Register is professional and non-fatalistic; the Report never predicts fixed outcomes.
- Each Section addresses its own interpretive territory. What each Section is *for* — as distinct from
  which data feeds it — is recorded in `addendum.md` §8 and is primary source material for the Style
  Guide.

#### FR-30: Author and maintain the Style Guide

The Style Guide exists as a written artifact before v1 generation is usable, and Francesco can revise
it without a code change. *(Number appended during finalization — see §0 on FR numbering.)*

**Consequences (testable):**
- The Style Guide is authored by Francesco — it describes his register, and no one else can supply it.
  Producing the first version is a v1 deliverable, not a configuration step (§14 step 4).
- It covers at minimum: register and address to the reader; sentence rhythm and length habits;
  vocabulary he uses and vocabulary he avoids; how a claim is anchored to its transit and date; and
  the interpretive territory of each Section (`addendum.md` §8 is the starting material).
- It is stored as editable text and versioned, so a change in output quality can be traced to a change
  in the guide.

#### FR-17: Condition generation on the Style Guide

Generation is conditioned on the Style Guide (FR-30) so output reads in Francesco's register.

**Consequences (testable):**
- The Style Guide is supplied to every generation request.
- Generation cannot proceed without a Style Guide present.
- Revising the Style Guide changes subsequent generation without a code change.

#### FR-18: Avoid restating prior Reports

For a Client with Report History, generation accounts for what prior Reports already said. Realizes
UJ-2.

**Consequences (testable):**
- The Generator receives a summary of the preceding Report's principal themes.
- Where a transit was covered in a prior Report and is still active, the Report treats it as continuing
  — what has moved, tightened or resolved — rather than reintroducing it.
- Where nothing significant has changed since the prior month, the Report states that plainly. It does
  not manufacture novelty. This is a direct consequence of claim-level determinism (§4.6): inventing
  change to seem fresh would fabricate Claims.
- A Client's first Report is generated with no history and no reference to prior months.

**Dependency:** `[NOTE FOR PM]` The first consequence above rests on a mechanism that has no
requirement — nothing in this PRD produces the theme summary the Generator receives. Open Question 2
holds that decision, and FR-18 is not buildable until it resolves.

#### FR-19: Retry on generation failure

Transient generation failures are retried without Francesco's involvement.

**Consequences (testable):**
- Provider rate limits and transient errors trigger bounded automatic retry.
- After exhausting retries the Report is marked failed and surfaced to Francesco with the reason.
- A failed generation never produces a partial Report that could be exported.

**Notes:** `[NOTE FOR PM]` Voice conditioning in v1 rests entirely on the hand-written Style Guide.
Corpus-based few-shot conditioning is phase 2 (§4.7, §9). The brief is explicit that the Corpus is the
product's only durable moat, so this is a real deferral, not a cut. **FR-30 is the highest-risk
requirement in this PRD**: it is the one v1 deliverable that no amount of engineering can produce, and
SM-2 rests entirely on how well it is written.

---

### 4.6 Groundedness Gate

**Description:** This feature exists because of the product's defining risk: a Report ships unedited to
a paying client under Francesco's professional name. There is no human review step to catch a
fabricated transit, so the check is automated and runs before Francesco ever sees the text.

The bar is **claim-level determinism**, chosen deliberately over byte-identical output. Wording may
vary between runs — it must, or recurring clients would receive prose that visibly repeats itself.
What may never vary is the astronomy: no Claim may exceed the Report Payload, and two generations from
the same Payload may never contradict each other on a fact.

Realizes UJ-3.

**Functional Requirements:**

#### FR-20: Validate every Claim against the Report Payload

Before a generated Report is shown to Francesco, the system checks each Claim in it against the Report
Payload.

**Consequences (testable):**
- A Claim naming a planet, sign, house, degree, aspect, date or retrograde condition not present in the
  Report Payload fails the check.
- A Claim contradicting the Report Payload — wrong date for a named Aspect Perfection, wrong house for
  a Lunation, a body described as retrograde that is not — fails the check.
- A Report containing at least one failing Claim does not reach the Report review screen in an
  exportable state.
- Interpretive statements that assert no astronomical fact are not treated as Claims and do not fail
  the check.

#### FR-21: Regenerate or surface on gate failure

A Report failing the Groundedness Gate is regenerated a bounded number of times; persistent failure is
surfaced.

**Consequences (testable):**
- Regeneration is automatic and bounded.
- On persistent failure Francesco is shown the Report, the failing Claims, and the Payload entries they
  contradict — never a silent discard.
- A Report that has not passed the Gate cannot be exported.

#### FR-22: Retain the Gate result

The Gate outcome for each Report is stored with the Report.

**Consequences (testable):**
- Each Report records whether it passed, how many regenerations were required, and any Claims flagged.
- Regeneration counts are reportable across Reports, so a rising rate is visible before it becomes a
  quality problem.

**Feature-specific NFRs:**
- The Gate is the last step before Francesco sees a Report. No path exists from Generator to export
  that bypasses it.

---

### 4.7 Corpus Collection

**Description:** Francesco holds hundreds of hand-written reports scattered across email, messaging and
folders. They are the raw material for phase-2 voice conditioning, and their volume and quality are
currently unknown. Collection is real work with an unknown size, so v1 treats it as a tracked activity
that produces a *measurement* — not as an available input.

**Functional Requirements:**

#### FR-23: Ingest and normalize past reports

Francesco can add past reports to the Corpus.

**Consequences (testable):**
- A past report can be added as text regardless of its original source.
- Each Corpus entry records whether it is paired (matched to birth data and month) or unpaired (prose
  only).
- Paired entries link to a Client and a month where one exists.

#### FR-24: Report Corpus composition

The system reports how many Corpus entries exist, split paired and unpaired.

**Consequences (testable):**
- Counts of paired and unpaired entries are visible at any time.
- This count is the decision input for whether phase-2 few-shot conditioning is viable (§9).

**Notes:** `[NOTE FOR PM]` Past reports contain identifiable client material. A position on
anonymization is required before any Corpus content is used as conditioning data — see §12 and Open
Question 3.

---

### 4.8 Review, Export and Report History

**Description:** Francesco's remaining involvement, and the fifteen minutes the product budgets him.
He sees the Report next to the facts that produced it, exports it, and moves on. Realizes UJ-1, UJ-3.

**Functional Requirements:**

#### FR-25: Review a generated Report

Francesco can read a generated Report with its underlying Report Payload accessible alongside.

**Consequences (testable):**
- All eight Sections are displayed in order.
- The Payload view (FR-15) is reachable from the Report without leaving it.
- The Gate result (FR-22) is visible.

#### FR-26: Export to PDF and Markdown

Francesco can export a Report that has passed the Groundedness Gate.

**Consequences (testable):**
- Both PDF and Markdown export are available.
- Exports contain only the eight Sections and the Client's name — no chart wheel, no Payload, no
  internal metadata.
- A Report that has not passed the Gate cannot be exported (FR-21).
- At export Francesco records the Report's **send disposition** in one interaction: *sent as generated*
  or *edited before sending*. This is the measurement source for SM-2 and is deliberately a single
  choice — anything heavier will not survive forty Reports in an afternoon.
- The system records the elapsed time from Client selection to export for each Report. This is the
  measurement source for SM-1.

#### FR-27: Browse Report History

Francesco can see all Reports previously generated for a Client, in order.

**Consequences (testable):**
- Reports are listed by Client and month.
- Any prior Report can be reopened with its Payload and Gate result intact.
- Report History is what FR-18 draws on.

---

## 5. Cross-Cutting NFRs

- **Astronomical conformance.** Computed output — planetary positions, house cusps, transit-to-natal
  Aspects, Stations, Ingresses and Lunations — matches Astro.com's *Natal chart and transits* for a
  defined set of reference charts. This is Francesco's own benchmark and the one his professional
  judgement is calibrated to. No Report reaches a Client before conformance passes.
- **Computational determinism.** Identical Client birth data, month and configuration produce identical
  Transit Events and a byte-identical Report Payload, on every run and every deployment.
- **Claim-level determinism.** Report prose may vary between generations. Claims may not. See §4.6.
- **Traceability.** Every Claim in every delivered Report remains traceable to a stored Report Payload
  entry for as long as the Report is retained.
- **Throughput and latency.** One Report goes from "Client selected" to "Report on screen" — transit
  scan, Payload assembly, generation, Groundedness Gate and any bounded regeneration included — in
  **under 3 minutes at the 90th percentile**. The system sustains forty Reports in a single working
  session and 100–200 per month. `[ASSUMPTION: the 3-minute budget is derived from UJ-1's "within a
  couple of minutes" and from SM-1's 15-minute total; it has not been validated against real generation
  latency and may need loosening once the Gate's regeneration rate is known.]`
- **Time budget.** End-to-end Francesco involvement per Report — entering or selecting a Client,
  generating, reviewing, exporting — stays under 15 minutes.
- **Cost.** Running cost stays at zero at 30–200 Reports per month.
- **Availability.** Best-effort. This is a single-operator tool used in batches; an hour of downtime is
  an inconvenience, not an incident. No SLA. `[ASSUMPTION: inferred from the batch working pattern in
  UJ-1; not stated by Francesco.]`
- **Data durability.** Client records, Natal Charts, Reports and Report Payloads survive host restarts
  and redeploys. Loss of a Natal Chart is recoverable by recomputation; loss of a Report Payload
  permanently breaks the traceability guarantee for that Report and is not acceptable.

---

## 6. Constraints and Guardrails

### 6.1 Safety

- The Generator computes nothing. It receives a Report Payload and produces prose. It has no tools, no
  calculation ability, and no authority to supply an astronomical fact.
- Reports are non-fatalistic. No Report predicts a fixed outcome, a medical event, a death, or a
  financial result.
- Reports ship unedited. Every guardrail must therefore hold without a human catching the failure.

### 6.2 Privacy and Data Protection

Francesco chose a hosted deployment over a local one, and has decided that v1 operates without formal
data-protection management on the grounds that use is private. That decision is recorded and accepted.
The requirements below are the subset that costs nothing to honor and would be needed operationally
regardless.

**Required in v1:**

- The application is access-controlled. Francesco is the only person who can reach Client data.
- Hosting and data storage are located in the EU/EEA where the chosen free tier offers the choice.
- A Client and all their Reports can be deleted outright. This is an operational capability, not a
  compliance artifact — it is also how a corrected or abandoned Client record gets cleaned up.
- **The generation provider's data terms are verified once before real Client data is sent, and again
  if generation ever falls back to another provider.** This is not paperwork: the question is whether a
  paying client's birth data and personal reading are used to train a third party's model. Google
  applies paid-tier data terms — no training on submitted content, no human review — to free tiers for
  the EEA, Switzerland and the UK, which is what lets the zero-cost constraint (§6.3) and this
  requirement coexist. The guarantee is contingent on jurisdiction and on Google's terms remaining as
  they are.

**Consciously deferred — accepted risk, not resolved:**

- A data processing agreement with the hosting provider.
- A written retention policy and records of processing.

**Resolved 2026-08-14:**

- **The Benessere Section does not produce GDPR Article 9 special category data.** Francesco's
  determination as controller, made against the Section's interpretive territory as specified: it
  draws on the 6th house, Mars, Saturn and the Moon to speak about vitality, stress and rhythm, not to
  record or infer health data about an identified living person. The lawful basis and safeguards are
  unchanged.
- **This settles the data-protection question only.** The register requirement is untouched — §6.1
  still forbids predicting a medical event, and the Style Guide must keep the Section clear of anything
  a reader could take as a medical statement (addendum §8). The determination was made against that
  register and holds while it holds: prose that drifted into health assessment would put the question
  back on the table.

`[NOTE FOR PM]` The deferral rests on the tool being private. It does not rest on the *data* being
private: the data subjects are paying clients rather than Francesco himself, so controller obligations
attach regardless of how few people use the application. **Revisit trigger** — before onboarding anyone
who is not Francesco, if a client asks what happens to their data, if the hosting or generation
provider changes terms, or before volume grows materially past the current practice.

### 6.3 Cost

- Zero running cost at 30–200 Reports per month is a constraint the design must satisfy.
- It is not a competitive advantage. The accuracy benchmark this product chases — Astro.com — is
  already free, and cost was never what made the work hard.
- Any design that requires paid infrastructure at target volume fails this constraint and must be
  raised rather than absorbed.

---

## 7. Aesthetic and Tone

This section governs product-generated Italian prose, which *is* the deliverable.

- **Voice reference:** Francesco's own hand-written reports. In v1 this is mediated by the Style Guide;
  in phase 2, by the Corpus directly.
- **Register:** warm, and addressing the reader as an adult making their own decisions. FR-16 carries
  the testable half of this (professional, non-fatalistic, continuous prose); what is here is the part
  that can only be judged by ear.
- **Speakable.** Sentences must survive being read aloud on a call — no nested clauses that lose their
  thread, no construction that only works on a page.
- **Specific.** Claims name the transit and the date. "The second half of the month asks more of you"
  is weaker than the same statement anchored to the 19th.
- **Anti-references:** generic horoscope prose that would apply to anyone; mystical register; ominous
  or deterministic framing; the fluent-but-hollow tone of unconditioned AI output. Vagueness is the
  specific failure mode to guard against — see the counter-metric SM-C1.

---

## 8. Non-Goals (Explicit)

- **No client-facing surface.** No accounts, no logins, no portal, no interface any Client touches.
- **No multi-astrologer or multi-tenant operation.** Not deferred — permanently out. The product serves
  one operator.
- **No mobile application.** The hosted web app is reachable from a phone browser; a native app is not
  built.
- **No astrological techniques beyond natal chart and monthly transits.** Synastry, compatibility,
  solar returns and progressions are out. Francesco explicitly did not prioritize them for the
  extension model.
- **No billing, payments, scheduling or CRM.** The Client record exists to produce Reports, nothing
  more.
- **No output language other than Italian.**
- **No support for Clients with an unknown birth time.** Rectification, noon charts, solar houses and
  house-less readings are all out. Exact birth time is an entry requirement (FR-1), and a Client who
  cannot supply one is not served by this product.
- **No capacity planning beyond 200 Reports per month.**
- **No delivery mechanics.** The product produces a file. Sending it to the Client stays manual and out
  of scope. `[ASSUMPTION: inferred — Francesco did not select client delivery as an extension
  direction.]`
- **No chart pattern detection.** Stelliums, grand trines, dispositor chains and similar relational
  configurations were considered during research and are out for v1. No Section requires them, and each
  one added is a new class of Claim the Groundedness Gate must learn to verify. They re-enter cleanly
  through the §10 seam if wanted later.
- **The system does not teach astrology.** It assumes a professional operator and explains nothing
  about its own reasoning beyond exposing the facts.

---

## 9. MVP Scope

### 9.1 In Scope

- Single operator, access-controlled hosted web application.
- Client records with birth data, geocoding and historical timezone resolution.
- Natal Chart computed once per Client and stored.
- The four Domain Profiles with traditional and modern Rulers.
- Continuous monthly transit scan producing exactly dated Aspect Perfections, Stations, Ingresses and
  Lunations.
- Versioned, persisted Report Payload.
- **The Style Guide itself**, authored by Francesco — a v1 deliverable, not a configuration step.
- Eight-Section Italian Report generation conditioned on the Style Guide.
- Single-account access control; outright deletion of a Client and everything derived from them.
- Month-over-month memory preventing restatement for recurring Clients.
- The Groundedness Gate, with bounded regeneration and stored results.
- Report review with Payload traceability; PDF and Markdown export; Report History.
- Chart wheel rendering, internal only.
- Corpus collection and composition measurement.
- Conformance validation against Astro.com reference charts.

### 9.2 Out of Scope for MVP

- **Corpus-based voice conditioning** — few-shot exemplar selection or fine-tuning. Deferred to phase 2
  because the usable Corpus size is unknown and blocking v1 on a task of unmeasured size is the larger
  risk. `[NOTE FOR PM] This is emotionally and strategically load-bearing: the brief names the Corpus as
  the product's only advantage that a competent developer could not rebuild in a month. Revisit as soon
  as FR-24 produces a count.`
- **Similarity-based exemplar retrieval** — selecting Corpus exemplars by resemblance to the current
  chart. Phase 3; the difference between imitating tone and imitating reasoning.
- **Multi-year narrative memory** — Reports that reference themes across years. Extension direction
  Francesco named; see §10.
- **Alternative report formats** — quarterly, annual, per-domain deep dives. Extension direction
  Francesco named; see §10.
- **A four-date snapshot view** matching the old hand process. Considered and dropped: the continuous
  scan supersedes it and the chart wheel already serves the verification habit. `[ASSUMPTION: that the
  wheel adequately replaces the snapshot as Francesco's verification habit — he chose the continuous
  scan without requesting the snapshot view, but did not confirm the substitution.]`
- **Anonymization tooling for the Corpus.** Required before phase 2, not before v1.

---

## 10. Extension Model

Francesco asked explicitly for room to iterate without losing the main goal. That requires naming what
is fixed and what is free to move.

**Fixed — the core the product exists to serve.** These do not change as features are added:

- The five Client inputs.
- The Natal Chart computed once per Client.
- The four Domain Profiles and their compositions.
- The eight Sections, in order.
- Italian output.
- The computation/narration separation, and the Groundedness Gate that enforces it.

**The seams — where extension is designed to happen:**

1. **Report Payload is versioned and additive.** New computed material is added under a new schema
   version. Old Payloads stay interpretable, so historical traceability never breaks.
2. **Section composition is data, not code.** Which Payload material feeds which Section is
   configuration. New Report formats reuse the entire computation layer and change only this mapping —
   this is the seam that makes quarterly and annual formats cheap.
3. **The memory store is separate from generation.** What the system remembers about a Client is its
   own concern, independent of how a Report is written. Extending from one-month lookback to multi-year
   thematic memory changes the store, not the Generator contract.
4. **The transit engine is independent of report shape.** It produces dated Transit Events for a date
   range. A different range or a different consumer requires no change to it.

**The rule.** An extension that would require weakening the Groundedness Gate, adding a Section, or
letting the Generator compute is not an extension — it is a change to the product, and belongs in a
revision of this PRD rather than in a ticket.

---

## 11. Success Metrics

**Primary**

- **SM-1: Time per Report.** Francesco's involvement per Report, measured end to end, falls from 1–3
  hours to **under 15 minutes**. *Measured from* the Client-selection-to-export elapsed time recorded at
  FR-26. Validates FR-1, FR-8, FR-16, FR-25, FR-26. This is the primary measure; everything else
  supports it.
- **SM-2: Unedited send rate.** The share of Reports Francesco sends without changing a word. Target:
  the majority, and rising. *Measured from* the send disposition recorded at FR-26. Validates FR-17,
  FR-18, FR-20, FR-30. If he is routinely rewriting, the product has moved the work rather than removed
  it.
- **SM-3: Astronomical conformance.** Computed output matches Astro.com for every reference chart in
  the validation set, across positions, cusps, Aspects, Stations, Ingresses and Lunations. Target:
  100%, as a release gate rather than a trend. Validates FR-3, FR-9, FR-10, FR-11, FR-12.

**Secondary**

- **SM-4: Sustained capacity.** Reports produced per month without a corresponding rise in hours.
  Target: 100–200. Validates FR-8, FR-27.
- **SM-5: Groundedness Gate pass rate.** Share of Reports passing on first generation. A falling rate
  is an early warning about the Generator or the Style Guide before it becomes a client-visible
  problem. Validates FR-20, FR-21, FR-22.
- **SM-6: Running cost.** Stays at €0/month at 30–200 Reports. Validates the §6.3 constraint.
- **SM-7: Gate leakage.** Of a periodic sample of Reports that **passed** the Groundedness Gate, the
  share containing a Claim the Gate should have caught. Target: zero, checked by hand against the
  stored Report Payload on a small sample each month. Validates FR-20. This is the only measure of the
  Gate's *false-negative* rate, which §12 names as the failure that actually reaches a paying Client —
  SM-5 measures pass rate and is blind to it.

**Counter-metrics (do not optimize)**

- **SM-C1: Claim density.** Astronomical Claims per Report, and the share of Sections anchored to a
  specific date. Counterbalances **SM-2**. The unedited send rate can be trivially gamed by generating
  vague horoscope prose that is never wrong because it never says anything — and Francesco would have
  no reason to edit it. If SM-2 rises while claim density falls, the product is failing while its
  headline metric improves.
- **SM-C2: Regeneration count.** Counterbalances **SM-5**. A Gate pass rate driven up by loosening what
  counts as a Claim is a regression disguised as an improvement. Pass rate is only meaningful with the
  Gate's strictness held constant.
- **SM-C3: Report length.** Counterbalances **SM-1**. Time per Report can be cut by producing less.
  Reports should not shrink as throughput rises.

---

## 12. Key Risks

Each risk names where it is handled rather than re-arguing it.

- **Ship-ready quality is an unproven bar.** No Report currently reaches a Client unedited. That the
  system clears that bar consistently, fifty times a month, is an assumption — not a demonstrated
  result. The honest test is Francesco sending one without changing a word. *Measured by SM-2; nothing
  in the design de-risks it, which is why it leads this list.*
- **The Groundedness Gate can leak, and no one would know.** Its false-negative rate is unknown until
  it runs against real Reports, and a missed Claim reaches a paying Client unedited. *SM-7 samples for
  it by hand — a check, not a guarantee. Open Question 1 must settle before the Gate's strictness can
  be calibrated at all.*
- **The Corpus may not survive contact with reality.** Its size and quality are unknown until
  collection is done, and with them how close the output can get to Francesco's voice. *Mitigated for
  v1 by shipping on the Style Guide (FR-30) rather than blocking; measured by FR-24.*
- **Voice rests on one unwritten document.** FR-30 is the only v1 deliverable that engineering cannot
  produce, and SM-2 depends on how well it is written. *No mitigation exists other than writing it
  well and revising against real output.*
- **The zero-cost guarantee is jurisdiction-contingent.** It holds because Francesco operates from the
  EEA. *Conditions and the re-verification requirement are in §6.2.*
- **Data-protection exposure is accepted rather than managed.** Identifiable birth data for paying
  clients sits on a third-party host without a processing agreement. *Decision, residual scope and
  revisit triggers are in §6.2.*

---

## 13. Open Questions

1. **What does the Groundedness Gate do about interpretive statements that lean on a fact without
   naming it?** "The month asks patience of you" following a Saturn passage asserts no verifiable
   Claim but depends on one. Where the boundary sits between an unverifiable Claim and legitimate
   interpretation determines whether the Gate is useful or merely noisy.
2. **How is the preceding Report's content summarized for FR-18?** By the Generator itself, by
   extraction from the prior Report Payload, or by a stored theme record written at generation time.
   The last is the most deterministic and the most work.
3. **What is the anonymization position for Corpus content?** Past reports contain identifiable client
   material. Required before phase-2 conditioning, not before v1 — but the answer shapes how the Corpus
   is collected now.

*Closed during finalization:* the transit Orb default (±2.0°, FR-9); mandatory exact birth time (FR-1,
§8); formal data-protection management (deferred by decision, §6.2); and *who writes the Style Guide*
— now answered by FR-30, which makes it Francesco's own v1 deliverable rather than an open question.

*Closed after finalization, 2026-08-14:* **Open Question 4 — the harmonic/disharmonic classification
rule (§4.4, FR-13)** — confirmed correct by Francesco, including its treatment of conjunctions. The
number is retired rather than reused. Resolved in the same pass, though it lived in §6.2 rather than
here: the **Benessere** Article 9 position, determined not to produce special category data.

---

## 14. Development Sequence

A starting proposal, adapted from the addendum §9 with the two additions it flagged as missing.

0. **Access and data lifecycle** — single-account authentication and Client deletion. First, because
   everything after it stores identifiable Client data. (FR-28, FR-29)
1. **Natal core** — geocoding with historical timezone resolution and cache; Natal Chart computation;
   Placidus cusps; natal Aspects. (FR-1 – FR-4)
2. **Transit engine** — continuous scan, Aspect Perfections, Stations, Ingresses, Lunations. (FR-8 –
   FR-12)
3. **Domain rules and Payload** — Ruler resolution, Domain Profiles, versioned Report Payload
   assembly. (FR-6, FR-7, FR-13, FR-14)
4. **Generation and the Gate** — Style Guide authored, eight-Section generation conditioned on it,
   Groundedness Gate, bounded regeneration. (FR-16, FR-17, FR-19 – FR-22, FR-30). The Style Guide is
   written work, not engineering, and can start at step 1 — it blocks this step and nothing else.
5. **Memory** — Report History and month-over-month non-repetition. (FR-18, FR-27)
6. **Interface and output** — data entry, chart wheel, Report review with Payload traceability, PDF and
   Markdown export. (FR-5, FR-15, FR-25, FR-26)
7. **Corpus collection** — runs in parallel from step 1; produces the count that gates phase 2. (FR-23,
   FR-24)
8. **Validation and release** — Astro.com conformance across the reference set, data-protection
   verification per §6.2, deployment.

---

## 15. Assumptions Index

Every `[ASSUMPTION]` in this document, surfaced for confirmation. Ordered by what it costs to be wrong.
Resolved entries stay at their original number rather than being removed, so downstream references to
them by number remain resolvable.

1. ~~**§4.4 / FR-13 — the harmonic/disharmonic classification rule.**~~ **RESOLVED 2026-08-14** —
   confirmed correct by Francesco, including the treatment of conjunctions by transiting body. The
   classification is his own method rather than inferred convention. Retained at this number because
   the architecture (AD-5) and the build order (E6) both cite "PRD Assumption 1".
2. **§4.5 / FR-16** — Sections 6 and 7 may use list form while Sections 1–5 and 8 must be continuous
   prose. Inferred from the speakability constraint and the dated nature of those two Sections.
3. **§5 — the 3-minute per-Report latency budget.** Derived from UJ-1 and SM-1, not validated against
   real generation latency; may need loosening once the Gate's regeneration rate is known.
4. **§4.3** — Full-month transit scan completes in under 10 seconds. Bound inferred from the
   forty-reports-in-an-afternoon target; not measured or stated.
5. **§9.2** — The chart wheel adequately replaces the four-date snapshot as Francesco's verification
   habit. He chose the continuous scan without requesting the snapshot view, but did not confirm the
   substitution.
6. **§5** — Availability is best-effort with no SLA. Inferred from the batch working pattern in UJ-1;
   not stated by Francesco.
7. **§8** — Report delivery to Clients stays manual. Inferred: Francesco did not select client delivery
   as an extension direction.
