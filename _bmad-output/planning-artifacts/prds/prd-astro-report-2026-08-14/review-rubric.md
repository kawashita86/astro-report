# PRD Quality Review — astro-report

Rubric walk against `assets/prd-validation-checklist.md`, run at finalization on 2026-08-14, after
input reconciliation and before polish.

> **Resolution status.** Every finding below was applied to `prd.md` in the same session. Three FRs
> were added (FR-28 access control, FR-29 Client deletion, FR-30 Style Guide authoring), the
> harmonic/disharmonic classification rule was specified in FR-13, SM-7 was added for Gate leakage,
> SM-1 and SM-2 were given measurement sources in FR-26, the three broken cross-references were fixed,
> the throughput NFR was given a bound, and the three one-way Assumptions Index entries were tagged
> inline. The one finding left unactioned is the §2.2 filler entry, judged harmless. This file is
> retained as the point-in-time review record; the PRD has moved past it.

## Overall verdict

This PRD has a genuine thesis — compute exactly, narrate never — and it holds that thesis consistently
from the Vision through the Groundedness Gate to the counter-metrics. Trade-offs are stated as
decisions with what was given up, and the counter-metric set is unusually honest for a solo-tool PRD.
**What is at risk is the gap between what the PRD promises and what it specifies:** three of its
load-bearing mechanisms — the Style Guide, access control, and the harmonic/disharmonic classification
that Sections 6 and 7 depend on — are named repeatedly but have no requirement behind them. Two of the
three primary success metrics have no measurement mechanism anywhere in the document.

---

## Decision-readiness — **strong**

Every significant fork in this product was decided, and each decision names its cost. The determinism
fork (§4.6) states plainly that byte-identical output was rejected and why. The four-date sampling
supersession (§4.3) argues from the specification rather than from preference. The hosting decision and
the data-protection deferral (§6.2) are both recorded as the operator's calls with the residual risk
left visible in §12 rather than smoothed away. The §6.2 `[NOTE FOR PM]` explicitly refuses to accept
the user's own rationale at face value — it distinguishes the tool being private from the data being
private — which is the opposite of a PRD dodging pushback.

Open Questions are genuinely open: none has its answer in the next sentence, and the "Closed during
finalization" tail makes the resolution history legible.

### Findings
- **low** Non-Users includes filler (§2.2) — "Anyone learning astrology" does not drive a single
  decision downstream, unlike the other two entries. *Fix:* drop or leave; harmless.

## Substance over theater — **strong**

No persona theater: JTBD plus three UJs, each of which drives requirements (UJ-3 alone justifies FR-15,
FR-14 and the entire traceability NFR). No innovation theater — the differentiation claim is confined
to the Vision and is falsifiable. NFRs mostly carry product-specific thresholds rather than adjectives.

### Findings
- **medium** Throughput NFR is an adjective, not a bound (§5) — "supports producing forty Reports in a
  single working session **without Francesco waiting on it**" has no number. UJ-1 says "within a couple
  of minutes" but no NFR states a per-Report end-to-end budget, and generation plus Gate plus bounded
  regeneration could plausibly exceed that. This is the one NFR that reads as furniture. *Fix:* state a
  per-Report wall-clock budget covering scan → generation → Gate → display.

## Strategic coherence — **strong**

The thesis is stated in the Vision, enforced by an entire feature (§4.6), protected by an invented
section (§10 Extension Model), and defended by the counter-metrics. Feature ordering in §14 follows the
thesis — the computation spine is built before anything that consumes it, and the Gate arrives with
generation rather than after it.

The counter-metric set is the strongest part of this PRD. SM-C1 in particular identifies that the
headline metric (unedited send rate) is gameable by blandness — a failure mode that would otherwise
have looked like success on every dashboard.

### Findings
- **high** Two of three primary metrics have no measurement mechanism (§11) — **SM-2** (unedited send
  rate) requires knowing whether Francesco changed a word before sending, but export produces a file
  and all editing happens outside the system. **SM-1** (time per Report) has the same problem. No FR
  captures either. As specified, the PRD's second-most-important metric cannot be computed. *Fix:*
  either add a lightweight FR (mark a Report as "sent as generated" / "sent edited" at export time,
  timestamp the Client-selected → exported span) or state explicitly that these are estimated by hand
  rather than instrumented. Both are acceptable; silence is not.

## Done-ness clarity — **adequate**

Most FRs carry genuinely testable consequences, and several are exemplary — FR-2's "a birth in Italy on
1975-06-15 resolves to CEST (+02:00), not CET" is a test case, not a requirement. FR-9 through FR-12
give an engineer everything needed. But three load-bearing mechanisms have no requirement at all, and
one has an undefined classification rule at exactly the point the architecture depends on being
mechanical.

### Findings
- **high** The Style Guide has no FR that creates it (§4.5, FR-17) — FR-17 requires generation to be
  conditioned on the Style Guide and specifies that it is "a stored, editable artifact," but nothing in
  the PRD says who authors it, what it must contain, or that it must exist before v1 generation is
  usable. Meanwhile §9.1 lists "generation conditioned on the Style Guide" as in-scope, SM-2 rests on
  it, §7 defers to it, and Open Question 4 admits it does not exist. **v1 output quality depends
  entirely on an artifact with no requirement behind it.** *Fix:* add an FR covering the Style Guide's
  authoring, minimum content and its status as a v1 deliverable — or move it into §14 as an explicit
  work item with an owner.
- **high** Access control has no FR (§6.2, §9.1) — both sections state the application is
  access-controlled and UJ-1 says Francesco is "already signed in," but no FR defines authentication.
  For a hosted application holding identifiable birth data for paying clients, this is the single
  requirement most likely to be skipped precisely because everyone assumed it was written down. *Fix:*
  add an FR under §4.1 or a new feature.
- **high** "Favorable" and "tense" are undefined judgements inside a layer specified as pure
  derivation (FR-13) — Sections 6 and 7 receive "favorable Lunations," "favorable conjunctions" and
  "tense Mars and Saturn passages." Trine/sextile versus square/opposition is conventional and
  mechanical, but *favorable conjunction* and *tense passage* require a rule the PRD never states. FR-13
  simultaneously asserts that "assembly is a pure function" producing byte-identical output. Either the
  classification rule is specified, or the purity claim is false at the exact boundary the whole
  determinism argument rests on. *Fix:* specify the classification rule — by aspect type, by planet
  pair, or by an explicit table — in FR-13 or the addendum.
- **medium** The Gate's false-negative rate is named as the dangerous failure and never measured
  (§12, SM-5) — §12 states that missed Claims are the risk that reaches a paying Client, and
  `addendum.md` §4 repeats it. SM-5 measures only *pass rate*, which says nothing about Claims the Gate
  failed to catch. Nothing in the PRD would ever tell Francesco the Gate is leaking. *Fix:* add a
  periodic manual spot-check of passed Reports against their Payloads as an SM or a §14 release step.
- **medium** FR-18 depends on a mechanism that has no FR — "The Generator receives a summary of the
  preceding Report's principal themes" is stated as a testable consequence, but nothing produces that
  summary. Open Question 2 acknowledges the mechanism is undecided; the gap is that FR-18 reads as
  buildable while its input has no owner. *Fix:* note the dependency inline in FR-18, or add the
  summary-production FR once OQ-2 resolves.
- **medium** Client deletion is required in §6.2 with no FR (§4.x) — "A Client and all their Reports
  can be deleted outright" appears as a constraint. Constraints are not requirements; nothing in §4
  builds it. *Fix:* add to §4.1.
- **low** "Angular houses" and "personal planets" (FR-13) are domain nouns used once and absent from
  the Glossary. *Fix:* add both, or replace with enumerated houses/planets.
- **low** The transiting Moon is excluded from FR-9 without comment — "fast" covers Sun, Mercury, Venus,
  Mars. This correctly matches Francesco's source specification and the Moon still appears via
  Lunations, but a reader will wonder whether it was an oversight. *Fix:* one clause noting the
  exclusion is deliberate.

## Scope honesty — **strong**

§8 is doing real work: eleven entries, several with the reasoning attached, and the "not deferred —
permanently out" phrasing on multi-tenancy prevents exactly the drift it is there to prevent. §9.2
marks the Corpus deferral as emotionally load-bearing rather than burying it. §10's closing rule
converts scope discipline into an enforceable test.

Open-items density is appropriate for the stakes: four Open Questions, five assumptions, four
`[NOTE FOR PM]` callouts, on a PRD that is explicitly a green light to build a solo tool.

### Findings
- **medium** Three of five Assumptions Index entries have no inline `[ASSUMPTION]` tag (§15) — the
  entries for §4.5/FR-16 (list form in Sections 6–7), §9.2 (chart wheel replaces the snapshot view) and
  §8 (manual delivery) are indexed but never tagged at their location. The roundtrip is one-way, so a
  reader of §9.2 has no signal that the statement is inferred. *Fix:* add the inline tags.

## Downstream usability — **adequate**

The Glossary is thorough and used with discipline — Client, Natal Chart, Report Payload, Claim, Section
and Domain Profile appear identically throughout, including inside FR consequences. FR IDs are
contiguous 1–27 with no gaps or duplicates. UJ-1 through UJ-3 all have named protagonists (Francesco,
Giulia, Marco) carrying context inline. Sections survive extraction; §4.4 and §4.6 in particular read
correctly pulled out alone.

Three cross-references do not resolve, which matters more than usual for a chain-top PRD feeding
architecture and story creation.

### Findings
- **medium** Broken cross-reference in §0 — "indexed in §16." The Assumptions Index is **§15**. There is
  no §16.
- **medium** Broken cross-reference in FR-18 — "a direct consequence of claim-level determinism (§8)."
  §8 is Non-Goals. Claim-level determinism is defined in **§4.6** and restated in **§5**.
- **medium** Broken cross-reference in FR-5 Notes — "Its value is highest during validation (§4.8)."
  §4.8 is Review, Export and Report History. Validation is **§14 step 8** and **SM-3**.
- **low** SM coverage is uneven — FR-2, FR-4, FR-5, FR-6, FR-7, FR-14, FR-19, FR-21, FR-23 and FR-24
  are validated by no SM. Acceptable for a solo tool; noted only because FR-14 (Payload persistence)
  underpins the traceability NFR and FR-24 gates phase 2.

## Shape fit — **strong**

Correctly shaped as a capability spec for a single-operator internal tool that happens to have a second,
non-touching stakeholder. The UJ section justifies its own existence in its opening line rather than
including journeys because the template has them, and three lean UJs is the right density — full
heavy-shape UJs here would have been over-formalization.

Two adapt-in choices earn their place: **§7 Aesthetic and Tone** is not optional for a product whose
deliverable *is* generated prose, and **§10 Extension Model** was invented rather than pulled from the
menu, in direct response to a stated user need. §6 correctly scales down to the three clusters that
apply.

### Findings
None.

---

## Mechanical notes

- **Glossary drift:** none found. Terms are used consistently in case and number, including inside FR
  consequence bullets. Two undefined domain nouns noted above.
- **ID continuity:** FR-1 – FR-27 contiguous, unique. UJ-1 – UJ-3 contiguous. SM-1 – SM-6 plus SM-C1 –
  SM-C3 contiguous. No duplicates.
- **Cross-references:** three broken, listed above. All other §-references and FR-references resolve.
- **Assumptions Index roundtrip:** five index entries, two with inline tags. Three one-way, listed
  above.
- **UJ protagonists:** all three named, all carry persona context inline. No floating UJs.
- **Required sections:** all Essential Spine sections present. Adapt-in clusters appropriate to stakes.
