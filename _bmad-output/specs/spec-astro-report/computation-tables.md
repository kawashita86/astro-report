# Computation Tables — astro-report

The astronomical tuning values every computation reads. **This file is the record of what those values are; where a source document restates one, this file wins.** They live at runtime in a single versioned `ComputationConfig`, passed explicitly into every core function and recorded with its version and content hash on every Report Payload — so any stored Payload can be reproduced exactly, and changing a value is a data edit and a version bump rather than a code change.

Companion of `SPEC.md`. Governs CAP-3, CAP-6, CAP-7, CAP-9, CAP-10, CAP-11, CAP-12, CAP-13.

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

The transit Orb is tunable so the value can be calibrated against real Reports without a code change.

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
