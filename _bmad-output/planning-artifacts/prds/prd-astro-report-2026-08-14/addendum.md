---
title: "PRD Addendum: astro-report"
status: final
created: 2026-08-14
updated: 2026-08-14
---

# PRD Addendum — astro-report

Depth from the PRD session of 2026-08-14 that belongs downstream (architecture, solution design) or
that records why a road was not taken. The **brief addendum**
(`_bmad-output/planning-artifacts/briefs/brief-astro-report-2026-08-14/addendum.md`) remains the
reference for the verbatim source specification, the technology assessment, the ruler tables, orb
values, cost model and jurisdiction analysis. This document does not repeat it.

**If you are here to write the Style Guide (PRD FR-30), go straight to §8** — it is the most directly
usable section in this file. Sections 1–7 record why the PRD decided what it decided.

---

## 1. Determinism — options considered

Francesco opened the session with non-deterministic report output as his primary worry. Decomposing it
produced four distinct layers, which do not all want the same answer:

| Layer | Question | Disposition |
|---|---|---|
| Computation | Same birth data + month → identical astronomy? | Free from Swiss Ephemeris. Not a design problem. |
| Payload | Same facts → identical structured payload? | Design requirement. Pure functions, no model involvement. FR-7, FR-13. |
| Wording | Same payload → byte-identical prose? | **Rejected as a goal.** See below. |
| Claims | May two runs disagree on a fact? | **Selected as the bar.** FR-20 – FR-22. |

**Options presented and their disposition:**

- **Claim-level determinism — SELECTED.** Wording may vary; astronomical Claims may not vary, exceed
  the Payload, or contradict each other. Enforced by the Groundedness Gate. Chosen because it is
  testable, enforceable, and compatible with month-over-month variation.
- **Claim-level plus stable wording — rejected.** Would add temperature-0 generation, a pinned model
  version and output caching. Rejected because it works against FR-18: a recurring client receiving
  visibly reprinted prose is a more likely and more damaging failure than varied phrasing.
- **Fully byte-identical output — rejected.** Maximum auditability, but directly incompatible with
  month-over-month non-repetition, which would then require a separate mechanism to reintroduce the
  variation that caching removed. Complexity for a property the operator does not actually need;
  traceability (FR-15) delivers the auditability that motivated it.

**Consequence for architecture.** Auditability is carried by the persisted Report Payload, not by
reproducible generation. The Payload is the immutable artifact; the prose is a rendering of it.

## 2. Transit sampling — why the hand process was superseded

Francesco's original specification samples the month on days 1, 10, 20 and the last day, transcribed
from how he works on Astro.com. The brief addendum already flagged this as "a floor, not a ceiling."

It was superseded outright rather than kept, for a reason internal to the specification itself:
**Sections 6 and 7 — *Giorni favorevoli* and *Giorni di attenzione* — are day lists.** Four sample
points cannot produce them. They can locate an aspect as in-orb on the 10th and out by the 20th; they
cannot say it perfects on the 19th. The four-date method is a constraint of doing the work by hand, and
the constraint does not survive automation.

A third option — continuous engine plus a 1/10/20/last snapshot view for eyeballing against Astro.com —
was offered and not taken. The chart wheel (FR-5) and the Payload view (FR-15) cover the verification
habit, and conformance testing (SM-3) covers it systematically.

## 3. Deployment — local versus hosted

**Recommended:** local web application on Francesco's own machine. Client personal data never leaves
it; no processor relationship; no residency question; simplest possible data-protection position; zero
cost by construction.

**Chosen by Francesco:** hosted web application, for reachability from anywhere including a phone.

**Accepted, with consequences made explicit and written into the PRD §6.2:**

- Francesco becomes a data controller with a processor relationship to manage, rather than a person
  with a private file on a private machine.
- EU/EEA hosting and storage becomes a hard requirement, not a preference.
- A data processing agreement with the host is required before real client data is entered.
- A deletion path per client becomes a requirement rather than a filesystem operation.
- The generation provider's EEA paid-tier-terms carve-out was already load-bearing for the zero-cost
  constraint; hosting adds a second processor whose terms need the same check.

None of this is prohibitive. It is paperwork that the local option would not have required, and it
should be sequenced before real client data is entered rather than after.

## 4. Groundedness Gate — mechanism notes for architecture

Not specified in the PRD because it is implementation, but load-bearing enough to record:

- The Gate is a **post-generation verification pass**, not a prompt instruction. Instructing the model
  not to fabricate is necessary and insufficient; the check must be independent of the thing it checks.
- Candidate mechanism: extract Claims from generated Italian text (named bodies, signs, houses,
  degrees, dates, aspect types, retrograde assertions), then match each against the Report Payload.
  Extraction is the hard part and is itself a language task — implying a second model call with a
  narrow, structured, verifiable output rather than a regex pass.
- The extractor and the Generator should not share a prompt or a context. A shared context invites the
  extractor to inherit the Generator's fabrications.
- Open Question 1 in the PRD — the boundary between an unverifiable Claim and legitimate interpretation
  — is the single decision that determines whether this mechanism is useful or merely noisy. It should
  be settled empirically against real generated Reports, not decided in advance.
- False negatives (Claims the Gate misses) are the dangerous class, since Reports ship unedited. False
  positives merely cost a regeneration. Tune accordingly.

## 5. Month-over-month memory — mechanism options

PRD Open Question 2, expanded. Three candidate mechanisms for supplying FR-18:

1. **Generator summarizes the prior Report** at generation time. Cheapest. Non-deterministic, and
   compounds: each month's summary is a summary of a summary.
2. **Extract themes from the prior Report Payload.** Deterministic, since the Payload is immutable and
   structured. Captures which transits were covered but not how they were framed in prose.
3. **Write a theme record at generation time** and store it with the Report. Most deterministic and
   most work; the record is produced once, from both the Payload and the prose, and read thereafter.

Option 3 is the most consistent with the product's determinism posture and is the recommended default
for architecture to evaluate. Option 1 should be avoided: it introduces exactly the compounding drift
the rest of the design works to eliminate.

## 6. Voice conditioning — phasing rationale

Three options were offered. **Phase 2, with v1 shipping on a hand-written Style Guide, was selected.**

- **Blocking v1 on the Corpus — rejected.** The corpus is scattered across email, messaging and
  folders, and its size is unknown. Blocking the entire product on a task of unmeasured size is a
  larger risk than shipping with weaker voice conditioning and improving it.
- **Style guide only, dropping the Corpus — rejected.** The brief identifies the Corpus as the
  product's only advantage that a competent developer could not rebuild in a month. Dropping it
  discards the moat to save effort.

The phasing places FR-24 (Corpus composition count) as the gate on phase 2 planning: the count of
paired versus unpaired entries determines whether few-shot exemplar conditioning is viable at all, and
whether similarity-based retrieval (phase 3) has enough paired material to work with.

## 7. Extension model — what was not prioritized

Francesco selected **richer multi-year client memory** and **longer or alternative report formats** as
the directions to leave open. He did **not** select:

- **Additional astrological techniques** (solar returns, progressions, synastry). Consistent with the
  brief's explicit exclusion. The PRD moves these from "deferred" to "non-goal."
- **Client delivery and follow-up** (sending reports, tracking what went to whom). Delivery stays
  manual; the product produces a file.

This tightened §10 of the PRD considerably. The seams are designed for the two selected directions —
the memory store being independent of the Generator, and Section composition being configuration rather
than code — rather than for a general-purpose plugin surface no one asked for.

## 8. Interpretive territory of each Section

Recovered from `product_research.md` §4 (*Focus Interpretativo*) and §3 (*Regole di Associazione e
Dominio*) during finalization reconciliation. PRD FR-13 specifies **which data** each Section receives;
this specifies **what the Section is about**. The distinction matters because the second is not a
testable requirement — it is generation guidance, and it is the most concrete raw material available
for writing the Style Guide, which v1 output quality depends on entirely (PRD FR-30).

| Section | Interpretive territory |
|---|---|
| 1. Energia generale del mese | Systemic picture of the period; the underlying psychological climate; the dominant evolutionary themes. |
| 2. Amore | Affective relationships; emotional desires; couple dynamics; encounters and clarifications. |
| 3. Lavoro | Professional objectives; concentration and focus; contractual dynamics; relations with colleagues and hierarchies. |
| 4. Denaro | Management of income; investments; planned and unforeseen expenses; financial negotiations. |
| 5. Benessere | Psycho-physical vitality; stress management; biorhythms; care of the body; recovery of energy. |
| 6. Giorni favorevoli | Propitious moments — for agreements, initiatives, interviews, important decisions, expansion. |
| 7. Giorni di attenzione | Delicate windows — for communication, impulsive decisions, handling conflict. |
| 8. Consiglio astrologico finale | Strategic, ethical and motivational guidance for orienting the month's actions. |

**Semantic intent behind each placement.** Why a given house or planet belongs to a given Domain
Profile — needed so the Generator writes *about* the placement rather than merely naming it.

- **Lavoro** — the midheaven and 10th house carry vocation; the 6th carries professional routine and
  daily working conditions; the 2nd carries monetization and practical talent.
- **Denaro** — the 2nd house is personal cash flow; the 8th is investments, debts, inheritance and
  other people's resources; Jupiter is expansion; Saturn is stability and constraint.
- **Benessere** — the ascendant is constitution and vitality; the 6th house is somatization and
  day-to-day health management; Mars is energy level; Saturn is stress and structure; the Moon is
  emotional balance.
- **Amore** — Venus, Mars and the Moon carry desire, drive and emotional need respectively; the 5th
  house is attraction and courtship, the 7th is partnership and commitment.

**Caution for the Style Guide author.** The *Benessere* territory as written — somatization, health
management, biorhythms — is the material closest to a medical statement anywhere in the product.
Francesco determined on 2026-08-14 that the Section does not produce GDPR Article 9 special category
data (PRD §6.2). That settles the data-protection question and changes nothing here: whatever register
the Style Guide sets for this Section must stay well clear of anything a reader could take as a medical
statement, because PRD §6.1 forbids predicting medical events — and because the Article 9 determination
was made against this register and assumes it holds. This is the one Section where interpretive richness
and product safety pull against each other.
