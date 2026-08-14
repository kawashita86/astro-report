# Sections and Domain Profiles — astro-report

The per-Section catalog: what the eight Sections are, what computed material each receives, and what each one is *about*. **This file is the record of the Section contract; where a source document restates it, this file wins.**

Two distinct things live here and must not be conflated. **What a Section receives** is a testable mapping — configuration, loaded as data, never a branch in assembly code. **What a Section is about** is generation guidance, not a testable requirement; it is the most concrete raw material available for writing the Style Guide, on which output quality depends entirely.

Companion of `SPEC.md`. Governs CAP-7, CAP-13, CAP-15, CAP-16.

## The four Domain Profiles

Assembled from the Natal Chart by pure derivation — no judgement, no model involvement. Names stay Italian and lowercase in code, database and configuration.

| Domain | Contents |
|---|---|
| `amore` | Venus (sign, house, Aspects); Mars (sign, house, Aspects); 5th house (sign, planets in it, Ruler); 7th house (sign, planets in it, Ruler); Moon (sign, house, Aspects) |
| `lavoro` | 10th, 6th and 2nd houses and the midheaven — each with sign, planets in it, Rulers, and principal Aspects |
| `denaro` | 2nd and 8th houses; Venus, Jupiter, Saturn and their Aspects |
| `benessere` | Ascendant; Ruler of the ascendant; 6th house; Mars; Saturn; Moon |

The same Natal Chart always yields byte-identical Profiles.

## The eight Sections

Fixed order. A Report has exactly these eight, always in this sequence.

| # | Section | Payload material it receives |
|---|---|---|
| 1 | **Energia generale del mese** | Slow-planet transits to the angular houses (1st, 4th, 7th, 10th) and to the personal planets (Sun, Moon, Mercury, Venus, Mars); all active retrogrades |
| 2 | **Amore** | The `amore` Domain Profile; transits to the 5th and 7th houses; transit Aspects to natal Venus and Mars |
| 3 | **Lavoro** | The `lavoro` Domain Profile; transits to the midheaven, 10th and 6th houses; transit Aspects to natal Mercury, Mars and Saturn |
| 4 | **Denaro** | The `denaro` Domain Profile; transits to the 2nd and 8th houses; transit Aspects to natal Jupiter and Saturn |
| 5 | **Benessere** | The `benessere` Domain Profile; transits to the ascendant and 6th house; transit Aspects to natal Mars, Saturn and Moon |
| 6 | **Giorni favorevoli** | Dated harmonic Aspect Perfections and favorable Lunations, classified by the table in `computation-tables.md` |
| 7 | **Giorni di attenzione** | Dated disharmonic Aspect Perfections and retrograde Stations, classified by the same table |
| 8 | **Consiglio astrologico finale** | The natal houses the month's Lunations fall in, set against the overall transit picture |

Neutral events — those the classification table places in neither day list — are never dropped. They remain available to Sections 1–5 and 8.

## Form

- Sections 1–5 and 8 are **continuous prose**, never bullet fragments. The Report is sometimes read aloud on a call, in which case it is a script rather than a document, and fragments do not survive that use.
- Sections 6 and 7 present dated days and may use list form. *(Inferred from the speakability constraint and the dated nature of those two Sections; not specified by Francesco.)*
- The dated entries of Sections 6 and 7 are **projected from the Payload by code**, not written by the Generator. The Generator supplies only the connective prose around them and emits no date token inside those two Sections.

## Interpretive territory

What each Section is *about* — needed so the Generator writes about a placement rather than merely naming it. This is Style Guide material, not a testable requirement.

| Section | Interpretive territory |
|---|---|
| 1. Energia generale del mese | Systemic picture of the period; the underlying psychological climate; the dominant evolutionary themes |
| 2. Amore | Affective relationships; emotional desires; couple dynamics; encounters and clarifications |
| 3. Lavoro | Professional objectives; concentration and focus; contractual dynamics; relations with colleagues and hierarchies |
| 4. Denaro | Management of income; investments; planned and unforeseen expenses; financial negotiations |
| 5. Benessere | Psycho-physical vitality; stress management; biorhythms; care of the body; recovery of energy |
| 6. Giorni favorevoli | Propitious moments — for agreements, initiatives, interviews, important decisions, expansion |
| 7. Giorni di attenzione | Delicate windows — for communication, impulsive decisions, handling conflict |
| 8. Consiglio astrologico finale | Strategic, ethical and motivational guidance for orienting the month's actions |

## Semantic intent behind each placement

Why a given house or planet belongs to a given Domain Profile.

- **`lavoro`** — the midheaven and 10th house carry vocation; the 6th carries professional routine and daily working conditions; the 2nd carries monetization and practical talent.
- **`denaro`** — the 2nd house is personal cash flow; the 8th is investments, debts, inheritance and other people's resources; Jupiter is expansion; Saturn is stability and constraint.
- **`benessere`** — the ascendant is constitution and vitality; the 6th house is somatization and day-to-day health management; Mars is energy level; Saturn is stress and structure; the Moon is emotional balance.
- **`amore`** — Venus, Mars and the Moon carry desire, drive and emotional need respectively; the 5th house is attraction and courtship, the 7th is partnership and commitment.

## Caution for the Style Guide author

The *Benessere* territory as written — somatization, health management, biorhythms — is the material Reports are forbidden from turning into predictions of medical events. Francesco has determined (2026-08-14) that the Section does not produce GDPR Article 9 special category data; the register requirement is unaffected and stands on product-safety grounds alone. Whatever register the Style Guide sets for this Section must stay well clear of anything a reader could take as a medical statement. This is the one Section where interpretive richness and product safety pull against each other.
