# Reconciliation — `product_research.md` against PRD draft

Input: `product_research.md` (Italian, ~2,900 words, Francesco's own technical feasibility study).
Reconciled against `prd.md` and `addendum.md` on 2026-08-14, before polish.

## Verdict

The research is substantially represented. Its architecture and cost sections were already distilled
into the brief addendum and correctly stay out of the PRD as implementation. **Five gaps found: two
material, one qualitative and load-bearing, two minor.**

---

## GAP 1 — Lunar Nodes are missing from the Natal Chart *(material)*

`product_research.md` §3, Tema Natale row: *"Ascendente (ASC), Medio Cielo (MC), 12 cuspidi Placidus,
posizioni di 10 pianeti **e Nodi Lunari**."*

PRD FR-3 enumerates the ten planets, the angles and the cusps — but not the lunar nodes. Nothing else
in the PRD mentions them. This is a silent drop of a natal point the research explicitly listed.

**Disposition:** add the North and South Node to FR-3. Note that Francesco's own eight-part
specification does not name them either, so their inclusion is about chart completeness, not about a
Section that demands them.

## GAP 2 — Natal orb value is never stated in the PRD *(material)*

`product_research.md` §3: natal aspects use *"orbi natali (±6.0° a ±8.0°)"*.

The PRD Glossary states that natal and transit-to-natal Orbs use different values and points to §4.3 —
but §4.3 specifies only the transit-to-natal Orb (±2.0°, confirmed). The natal Orb is referenced
throughout (FR-3, FR-7) and defined nowhere. A build reading only the PRD would have to guess.

**Disposition:** state the natal Orb in FR-3 with the same default-plus-range treatment the transit Orb
received.

## GAP 3 — Per-Section interpretive focus was dropped *(qualitative, load-bearing)*

`product_research.md` §4 carries a *"Focus Interpretativo"* column, and §3 a *"Regole di Associazione e
Dominio"* column. Together they describe **what each Section and each placement is actually about** —
not which data feeds it, but what it means:

| Section | Interpretive focus as written |
|---|---|
| Energia generale | Systemic picture of the period, underlying psychological climate, dominant evolutionary themes |
| Amore | Affective relationships, emotional desires, couple dynamics, encounters and clarifications |
| Lavoro | Professional objectives, focus, contractual dynamics, relations with colleagues and hierarchies |
| Denaro | Management of income, investments, planned or unforeseen expenses, financial negotiations |
| Benessere | Psycho-physical vitality, stress management, biorhythms, care of the body, recovery of energy |
| Giorni favorevoli | Propitious moments for agreements, initiatives, interviews, important decisions, expansion |
| Giorni di attenzione | Delicate windows for communication, impulsive decisions, handling conflict |
| Consiglio finale | Strategic, ethical and motivational guidance for orienting the month's actions |

And per placement: vocation (MC/10th), professional routine (6th), monetization and practical talents
(2nd); personal cash flow (2nd), investments, debts, inheritance and third-party resources (8th),
expansion (Jupiter), stability (Saturn); constitution and vitality (ASC), somatization and daily health
management (6th), energy levels (Mars), stress and structure (Saturn), emotional balance (Moon).

The PRD's FR structure captured *which data* each Section receives (FR-13) and dropped *what the
Section is for*. This is exactly the qualitative material an FR list loses. It is also directly useful:
it is raw material for the Style Guide, which is the single artifact v1 generation quality depends on.

**Disposition:** preserved in `addendum.md` §8 and referenced from PRD §4.5. Not promoted into the PRD
body — it is generation guidance, not a testable requirement.

## GAP 4 — Chart pattern detection was considered and is absent *(minor)*

`product_research.md` §1 cites `chart2txt` for detecting relational configurations — stelliums, grand
trines, dispositor chains — and argues that feeding the model pre-aggregated relational entities
reduces hallucination.

The PRD has no such requirement. Francesco's eight-part specification does not ask for it, so this is
not an omission from the contract — but it was a live idea in the research and vanished without a
decision being recorded.

**Disposition:** recorded as an explicit non-goal for v1 with the rationale, rather than left silent.
Naturally re-enters via the §10 Extension Model seam 1 (additive Payload versioning) if wanted.

## GAP 5 — Transit Aspects to ASC and MC not explicit *(minor)*

`product_research.md` §3 point 5: transit aspects are computed against *"punti natali (ASC, MC, pianeti
radix)"*.

PRD FR-9 says "a Natal Chart point", and the Glossary defines Natal Chart as including ascendant and
midheaven — so it is covered by construction. But given that the angles are the most build-skippable
natal points, making them explicit costs one clause.

**Disposition:** name ASC and MC explicitly in FR-9.

---

## Correctly excluded — no action

- **Cost scaling to 1,000 / 10,000 / 50,000 requests per month** (§6). The PRD caps at 200/month and
  says so. The brief addendum already recorded this cut.
- **Full technology stack** — FastAPI, Kerykeion v5, pyswisseph, geopy/Nominatim, timezonefinder,
  Gemini Flash, Groq/Ollama fallbacks, Jinja2/HTMX or React, Render/Hugging Face, Docker (§2, §5).
  Implementation, belongs to architecture. Already in the brief addendum.
- **Four-date sampling at 12:00 UTC** (§3, §5 Fase 2). Deliberately superseded by the continuous scan;
  rationale recorded in `addendum.md` §2.
- **Five-phase roadmap** (§5). Adapted into PRD §14 with the two additions the brief addendum flagged
  as missing (voice conditioning, month-over-month memory).
- **Pydantic response validation, rate-limit retry** (§5 Fase 3). Retry is FR-19; schema validation is
  implementation.

## Capacity note — no gap, worth recording

The research budgets one generation call per Report against Gemini's free tier (1,500/day). The PRD
adds a second model call per Report for Claim extraction in the Groundedness Gate (`addendum.md` §4),
plus bounded regenerations (FR-21). At 200 Reports/month this is roughly 3–4× the research's assumed
call volume and still two orders of magnitude inside the free tier. The zero-cost constraint (§6.3)
holds.

---

## Second input — `brief.md` + brief `addendum.md`

Reconciled in full; **no gaps**. Every in-scope item, exclusion, success criterion and risk from the
brief appears in the PRD: scope items in §9.1, the exclusion list in §8, all five success criteria in
§11 (SM-1 through SM-6), and all three brief risks in §12. The brief addendum's ruler table, orb ranges,
retrograde/ingress/lunation methods and jurisdiction analysis are referenced rather than duplicated, as
PRD §0 declares.
