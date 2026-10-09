# Computation Tables — astro-report

The astronomical tuning values every computation reads. **This file is the record of what those values are; where a source document restates one, this file wins.** They live at runtime in a single versioned `ComputationConfig`, passed explicitly into every core function and recorded with its version and content hash on every Report Payload — so any stored Payload can be reproduced exactly, and changing a value is a data edit and a version bump rather than a code change.

Companion of `SPEC.md`. Governs CAP-3, CAP-6, CAP-7, CAP-9, CAP-10, CAP-11, CAP-12, CAP-13, CAP-32–CAP-35.

## House system

Placidus, for all twelve cusps. No alternative house system is offered or configurable.

## Aspects

The five major aspects only. No minor aspects are computed, stored, or available to any Section.

| Aspect | Angle |
|---|---|
| Conjunction | 0° |
| Sextile | 60° |
| Square | 90° |
| Trine | 120° |
| Opposition | 180° |

## Orbs

Natal and transit-to-natal Aspects use different, independently tunable Orbs. The transit Orb is deliberately the tighter of the two.

| Orb | Default | Tunable range |
|---|---|---|
| Natal Aspect | ±7.0° | ±6.0° to ±8.0° |
| Transit-to-natal Aspect | ±2.0° | ±1.5° to ±2.5° |
| Synastry inter-aspect (chart data API only) | ±7.0° | ±6.0° to ±8.0° |

The transit Orb is tunable so the value can be calibrated against real Reports without a code change.

Composite and solar-return aspects (RS chart and RS-to-natal) use the natal Orb. *(Added 2026-10-09, correct-course.)*

## Bodies

| Set | Members |
|---|---|
| Natal chart points | Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto; ascendant; midheaven; North and South Lunar Nodes |
| Transiting — fast | Sun, Mercury, Venus, Mars |
| Transiting — slow | Jupiter, Saturn, Uranus, Neptune, Pluto |
| Natal points targeted by transit Aspects | The ten planets, the ascendant, the midheaven, and the Lunar Nodes |

**The transiting Moon is excluded from Aspect detection.** It aspects every natal point within each month and would swamp the day lists. It enters a Report only through Lunations.

The Lunar Nodes are part of the Natal Chart and are computed for chart completeness; no Section requires them.

## House Rulers

Resolved in both systems for every cusp. Identical except where marked.

| Sign | Traditional | Modern |
|---|---|---|
| Aries | Mars | Mars |
| Taurus | Venus | Venus |
| Gemini | Mercury | Mercury |
| Cancer | Moon | Moon |
| Leo | Sun | Sun |
| Virgo | Mercury | Mercury |
| Libra | Venus | Venus |
| Scorpio | Mars | **Pluto** (co-ruler Mars) |
| Sagittarius | Jupiter | Jupiter |
| Capricorn | Saturn | Saturn |
| Aquarius | Saturn | **Uranus** (co-ruler Saturn) |
| Pisces | Jupiter | **Neptune** (co-ruler Jupiter) |

Where the two systems differ — Scorpio, Aquarius, Pisces — both the modern Ruler and the traditional co-ruler are recorded.

## Harmonic / disharmonic classification

The rule that sorts Transit Events into the two dated day-lists, *Giorni favorevoli* (Section 6) and *Giorni di attenzione* (Section 7). It is table-driven because Payload assembly is pure derivation and the sort cannot rest on judgement.

| Aspect type | Classification |
|---|---|
| Trine, sextile | Harmonic |
| Square, opposition | Disharmonic |
| Conjunction, transiting Venus or Jupiter | Harmonic |
| Conjunction, transiting Mars, Saturn or Pluto | Disharmonic |
| Conjunction, any other transiting body | Neutral — appears in neither day list |

- A **tense Mars or Saturn passage** is a transiting Mars or Saturn forming a conjunction, square or opposition to any natal point. It is disharmonic by the table above; the term is defined only because Francesco's source specification uses it.
- A **favorable Lunation** is a Lunation forming a trine or sextile to a natal point within Orb, or conjunct natal Venus or Jupiter. All other Lunations appear in their Section payloads but in neither day list.
- Retrograde **Stations** enter the *Giorni di attenzione* list.
- Neutral events are never silently dropped. They remain available to Sections 1–5 and 8.

> **Confirmed by Francesco, 2026-08-14** — including the treatment of conjunctions, which assigns by transiting body rather than by the natal point being contacted. This table is domain fact, not inference. It stays data rather than code regardless: it is read by more than one unit, its version and hash are recorded on every Report Payload, and a future revision must remain an edit and a version bump rather than a rewrite.

## Event detection definitions

| Event | Definition |
|---|---|
| **Aspect Perfection** | The instant a transit-to-natal Aspect reaches Orb = 0. Located by bisection over the analyzed interval. Aspects in orb during the month but never perfecting within it are recorded and flagged as such. |
| **Retrograde condition** | A body is retrograde where its longitudinal velocity dλ/dt < 0. |
| **Station** | The instant the sign of dλ/dt inverts — the body turns retrograde or direct. Recorded with body, direction of turn, exact instant and zodiacal degree. A body retrograde for the whole month with no Station inside it is recorded as a standing condition with its span. |
| **Ingress** | A transiting body's ecliptic longitude crossing a natal Placidus cusp. Recorded with body, house departed, house entered and exact instant. Crossings caused by retrograde motion are detected identically, including repeated crossings of the same cusp within one month. |
| **Lunation** | Δλ = (λ_Moon − λ_Sun) mod 360°. New moon at Δλ = 0°, full moon at Δλ = 180°, located by temporal bisection. Recorded with kind, exact instant, zodiacal degree and the natal house it falls in. |

## Month boundaries and time

Every instant is computed and stored in UTC. The analyzed month is **one half-open UTC interval**, derived once from the Client's local calendar-month boundaries using the historical zone resolved for that Client. Every Transit Event's membership is decided against that single interval, so an event at 23:30 local on the last day belongs to exactly one Report — never to two and never to none. Conversion back to local time happens only for display.

## Angles and precision

Degrees are carried as decimals, never binary floats, in every stored or compared value. Longitudes are normalized to `[0, 360)`. Orbs are signed and carry an explicit applying/separating flag.

## Ephemeris identity

The ephemeris data files are vendored and pinned by SHA-256, verified at startup, with the process refusing to start on a missing file or a checksum mismatch. The Moshier fallback is never an accepted runtime state. Every Report Payload records the ephemeris file identity that produced it, alongside the ComputationConfig version and hash.

## Synastry and composite (chart data API only)

- **Inter-aspects:** every pair (A point, B point) over the ten planets, both Lunar Nodes, ascendant and midheaven; the five major aspects; the synastry Orb. No applying/separating flag (two static charts).
- **Overlays:** each person's ten planets and nodes placed in the other person's Placidus houses.
- **Composite (midpoint method):** each planet, node, ascendant and midheaven is the midpoint of the two positions on the shorter arc. For an exact opposition (arc = 180°, which has no shorter arc) the midpoint is A's longitude + 90°, normalized. Composite aspects use the natal Orb, with no applying flag.
- **Composite houses:** `[composite] houses` in the ComputationConfig — `midpoint_cusps` (each cusp the shorter-arc midpoint of the two cusps) or `derived_from_mc` (Placidus cusps from the composite MC at the arithmetic mean of the two birth latitudes). Set by the Astro.com composite fixture; changing it is a data edit and a version bump.

## Solar return (chart data API only)

- **Return instant:** the UTC instant when the transiting Sun's tropical longitude equals the natal Sun's, searched from local 00:00 two days before the birthday in the requested year (28 February for a 29 February birthday in a non-leap year), so the nearest return is found.
- **Chart:** a full Placidus chart for that instant at the stated location (the birthplace by default), with RS aspects within the natal Orb.
- **Comparison:** the natal house of the RS ascendant; the natal house of each RS planet and node; RS-to-natal aspects within the natal Orb.
- **Requires a known birth time.** A ±0.5° error in the natal Sun moves the instant by up to ±12 h, which invalidates the RS angles and cusps.

## Unknown birth time (`time_known: false`, chart data API only)

- The chart is computed for 12:00 local civil time on the birth date at the birthplace.
- **Omitted:** ascendant, midheaven, cusps, house rulers, every `house` field, ingresses and lunation houses.
- **Ranged:** every body carries its longitude at local 00:00 and at 24:00 of the birth date as `range`; `sign_uncertain` is true when the two fall in different signs. The Moon (about 13° per day) always carries its range.
- **Excluded from every aspect list** (natal, transit targets, synastry, composite): the angles, and every aspect involving the natal Moon, whose uncertainty (±6.5°) exceeds the transit Orb and rivals the natal Orb.
- **Synastry:** a time-unknown subject contributes no angles and no Moon aspects; overlays *into* that subject's houses are omitted. If either subject's time is unknown, the composite angles, houses and planet houses are null, and composite Moon aspects are excluded.

## API transit windows

The window is local dates `[start_date, end_date)` in the subject's zone, converted once to one half-open UTC interval, and at most 13 calendar months long. Bodies, Orbs and the transiting-Moon exclusion are exactly those of the monthly scan. **Boundary rule:** an aspect already in orb when the window opens is reported with `orb_entry_at` equal to the window's UTC start; one still in orb when it closes has `orb_exit_at` null; a standing retrograde is clamped the same way. Nothing in orb inside the window is dropped.
