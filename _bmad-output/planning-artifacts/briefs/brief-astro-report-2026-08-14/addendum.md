---
title: "Addendum: astro-report"
status: draft
created: 2026-08-14
updated: 2026-08-14
---

# Addendum — astro-report

Depth that earned its place but does not belong in a two-page brief. Everything here is intended
for the PRD, the architecture, or the implementation that follows. Sourced from
`product_research.md` (Francesco's own technical feasibility study, in Italian) and from the
coaching session of 2026-08-14.

---

## 1. Report specification, as Francesco wrote it

The original request, verbatim in structure. This is the contract the product must satisfy.

**Client inputs:** name, date of birth, time of birth, place of birth, month to analyze.

**Natal chart (extracted once per client):** ascendant and midheaven; planets by sign, degree and
house; the twelve house cusps; principal natal aspects.

**Domain groupings:**

| Domain | Required elements |
|---|---|
| Love | Venus (sign, house, aspects); Mars (sign, house, aspects); 5th house (sign, planets, ruler); 7th house (sign, planets, ruler); Moon (sign, house, aspects) |
| Work | 10th, 6th and 2nd houses and the midheaven — sign, planets, rulers, principal aspects |
| Money | 2nd and 8th houses; Venus, Jupiter, Saturn and their aspects |
| Wellbeing | Ascendant, ruler of the ascendant, 6th house, Mars, Saturn, Moon |

**Monthly transits — the manual procedure being replaced:** open *Natal chart and transits* on
Astro.com; analyze the requested month on days 1, 10, 20 and the last day; annotate fast planets
(Sun, Mercury, Venus, Mars), slow planets (Jupiter, Saturn, Uranus, Neptune, Pluto), retrogrades,
house ingresses, aspects to natal planets, new and full moons.

**Report structure — eight sections, in order:** general energy of the month; love; work; money;
wellbeing; favorable days; days to watch; closing astrological advice.

> Note for the PRD: the four-date sampling (1, 10, 20, last) is a transcription of Francesco's
> existing hand process, adopted because it is what he does — not because it is optimal. A
> continuous or event-driven scan would be strictly more accurate and should be evaluated. The
> four dates are a floor, not a ceiling.

## 2. Technology assessment

Comparison of the candidate computation approaches, from `product_research.md` §1.

| Option | Type | License | Notes |
|---|---|---|---|
| **Kerykeion + pyswisseph** | Python library over Swiss Ephemeris | AGPL-3.0 / LGPL | Selected. Local computation, no external calls, full control of orbs and rulers. |
| FreeAstroAPI | Hosted REST API | Freemium, 80 req/day | Rejected — third-party dependency; advanced transit endpoints behind paid tiers; limited orb control. |
| Astrologer-API (g-battaglia) | FastAPI wrapper over Kerykeion | AGPL-3.0 | Useful reference implementation; the underlying library is the actual choice. |
| Zodiac-Engine (gsinghjay) | FastAPI + HTMX monolith | Open source | Architectural reference for wiring Kerykeion to a frontend and to an LLM. Natal-focused; transits need extending. |
| chart2txt (simpolism) | TypeScript pattern detection | MIT | Reference for expressing chart geometry as relational entities (stelliums, grand trines, dispositor chains). Does not compute ephemerides. |

**Proposed stack:** Python 3.11+, FastAPI, Kerykeion v5 over pyswisseph. Geocoding via `geopy`
against Nominatim with a local SQLite cache. Historical timezone and DST resolution via
`timezonefinder` plus `zoneinfo`. Generation via Google Gemini Flash, with Groq (Llama 3.3 70B)
or a local Ollama model as fallbacks. Frontend either Jinja2 + HTMX + Tailwind/DaisyUI in-process,
or a decoupled SPA. Deployment on Render.com or Hugging Face Spaces, containerized.

## 3. Domain rules

**House rulers, traditional and modern.** Identical for both systems except where noted.

| Sign | Traditional | Modern |
|---|---|---|
| Aries | Mars | Mars |
| Taurus | Venus | Venus |
| Gemini | Mercury | Mercury |
| Cancer | Moon | Moon |
| Leo | Sun | Sun |
| Virgo | Mercury | Mercury |
| Libra | Venus | Venus |
| Scorpio | Mars | **Pluto**, co-ruler Mars |
| Sagittarius | Jupiter | Jupiter |
| Capricorn | Saturn | Saturn |
| Aquarius | Saturn | **Uranus**, co-ruler Saturn |
| Pisces | Jupiter | **Neptune**, co-ruler Jupiter |

**Orbs.** Natal aspects ±6.0° to ±8.0°. Transit-to-natal aspects use a tighter ±1.5° to ±2.5°.
Major aspects only: conjunction 0°, sextile 60°, square 90°, trine 120°, opposition 180°.

**Houses.** Placidus.

**Retrograde detection.** From longitudinal velocity dλ/dt supplied by Swiss Ephemeris; a body is
retrograde where dλ/dt < 0. Stations are the moments the sign of the velocity inverts, and should
be recorded as dated events.

**House ingresses.** For each interval between sample points, test whether a transiting planet's
ecliptic longitude crosses a natal Placidus cusp.

**Lunations.** Track Δλ = (λ_Moon − λ_Sun) mod 360°. New moon at Δλ = 0°, full moon at Δλ = 180°,
located by temporal bisection over the month. For each, record exact date, UTC time, zodiacal
degree, and the natal house it falls in.

## 4. Data sourcing per report section

What the generation layer receives for each of the eight sections.

| Section | Data supplied |
|---|---|
| 1. General energy | Slow-planet transits to angular houses and personal planets; active retrogrades |
| 2. Love | Natal Venus, Mars, Moon condition; transits to 5th and 7th houses; transit aspects to radix Venus/Mars |
| 3. Work | Natal MC, 6th and 10th houses and their rulers; transits to MC/10th/6th; aspects to radix Mercury, Mars, Saturn |
| 4. Money | Natal 2nd and 8th houses and rulers; transits to 2nd/8th; transit aspects to natal Jupiter and Saturn |
| 5. Wellbeing | Ascendant and its ruler, 6th house; transits to ascendant and 6th; transit aspects to Mars, Saturn, Moon |
| 6. Favorable days | Dated list of exact harmonic aspects (trines, sextiles, favorable conjunctions) between transits and natal points; favorable lunations |
| 7. Days to watch | Dated list of exact disharmonic aspects (squares, oppositions, tense Mars/Saturn passages); retrograde stations |
| 8. Closing advice | Synthesis of the natal house touched by the month's lunations against the overall planetary picture |

## 5. Generation constraints

- The model receives a structured payload and nothing else. It must not compute, infer, or
  supply any astronomical fact not present in that payload.
- Output language is Italian. Non-negotiable.
- Register is professional and non-fatalistic. Claims cite the transit dates and positions
  involved.
- Prose must be **speakable** — Francesco sometimes reads reports aloud to clients. Avoid
  bullet-fragment style in the narrative sections.
- Every sentence must be defensible live: if a client asks "why do you say that?", the underlying
  computed fact must be retrievable.

## 6. Voice conditioning — open technical question

Francesco holds hundreds of hand-written reports and wants them used so the output reads as his
rather than as generic AI prose. This is the product's central differentiator and its least
specified area.

**Known as of 2026-08-14:**

- **Corpus condition — scattered but recoverable.** The reports exist across email, messaging and
  assorted folders. Collecting and normalizing them is a real task and a prerequisite for the
  voice work. Treat it as a work item in the plan, not as an available input.
- **Pairing — partial.** Recurring clients have records that allow a report to be matched back to
  the birth data and month that produced it. One-off reports are prose only. A paired subset
  therefore exists.

**Still unresolved:**

- **Usable corpus size.** Unknown until collection is done. This determines what the voice work
  can realistically promise, and it should be measured early — a count of paired and unpaired
  reports is the first useful output of the collection task.
- **Method.** Few-shot exemplar selection versus fine-tuning versus a distilled style guide
  extracted from the corpus. Few-shot is cheapest to try, works within the free tier, and can use
  the paired subset directly — likely the right first attempt. Fine-tuning is stronger but adds
  cost and provider lock-in.
- **Exemplar retrieval.** With a paired subset available, exemplars could be selected by
  similarity to the current chart and transit picture rather than at random. Worth evaluating;
  it is the difference between imitating tone and imitating reasoning.
- **Client confidentiality.** Past reports contain identifiable client material. Any use as
  conditioning data needs a position on anonymization.

## 7. Cost and hosting

At Francesco's real volume — 30–50 reports per month now, 100–200 at target — every component sits
inside a free tier:

| Component | Cost at 30–200 reports/month |
|---|---|
| Backend hosting (Render free tier / Hugging Face Spaces) | €0 |
| Astronomical computation (local Swiss Ephemeris) | €0 |
| Geocoding and timezone (Nominatim + local cache, timezonefinder) | €0 |
| Text generation (Gemini Flash free tier: 1,500 req/day) | €0 |
| **Total** | **€0 / month** |

> The 1,000 / 10,000 / 50,000 request tiers modelled in `product_research.md` §6 were cut from the
> brief. The real ceiling is 200 reports per month. Retained here only as evidence that cost is
> not a constraint on any plausible growth path.

**Jurisdiction dependency — must be preserved through implementation.** Google's free Gemini and
AI Studio tiers normally permit submitted content to be used to improve Google's products, with
human review possible. For the EEA, Switzerland and the UK, Google applies the paid-tier data
terms to all services including free tiers. Francesco operates from Italy, so the free tier is
acceptable for paying clients' data. **This guarantee is contingent on jurisdiction and on
Google's terms remaining as they are.** It breaks if the service is operated from outside the EEA,
if the provider changes terms, or if generation moves to a fallback provider (Groq) without the
equivalent check. Re-verify before launch and record the check.

## 8. Validation approach

Conformance testing against Astro.com's *Natal chart and transits* output for a set of reference
charts: planetary positions, house cusps, transit events, retrograde stations, ingresses and
lunations. This is Francesco's own benchmark and the one his professional judgement is calibrated
to. No report reaches a client before it passes.

## 9. Development sequence

From `product_research.md` §5, retained as a starting proposal for the PRD.

1. **Environment and natal core** — Python 3.11, Poetry or uv, geocoding with SQLite cache,
   Kerykeion `AstrologicalSubject`, natal planets, Placidus cusps, natal aspects with configurable
   orbs.
2. **Transit and lunation engine** — monthly sampling, retrograde and station detection, house
   ingresses, lunation location by bisection.
3. **Domain rules and generation** — ruler resolution per cusp, clustering into the four domains,
   async client to the generation provider with Pydantic response validation and rate-limit retry.
4. **Interface and output** — data entry form, internal chart wheel, position and cusp tables, the
   eight sections, PDF and Markdown export.
5. **Validation and release** — conformance against Astro.com, containerisation, deployment.

> Two additions this sequence does not cover, both surfaced during the coaching session and both
> load-bearing for the product: **voice conditioning from the corpus** (§6 above), and
> **month-over-month memory** so a recurring client's report does not repeat its predecessor.
> Neither is optional; both need placing in the sequence.
