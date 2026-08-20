---
title: 'Story 4.1 — Write the Style Guide'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 0
baseline_commit: '6497366a3d3dfb41e0072a6f913aee7e979d7d90'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Generation (Story 4.5) cannot condition on a register that does not exist yet, and no amount of engineering can substitute for it — it must be authored. Nothing at `data/style-guide.seed.md` exists.

**Approach:** Author `data/style-guide.seed.md` as continuous Markdown instruction-prose covering register/address, sentence rhythm and length, vocabulary used/avoided, claim-anchoring method, and the interpretive territory of all eight Sections — drawn from `addendum.md` §8 (the PRD's own stated starting material, correcting `epics.md`'s stale "does not exist as cited" claim) plus structural patterns (not vocabulary) drawn from Francesco's own social-channel horoscope writing in `text_sample/`.

## Boundaries & Constraints

**Always:**
- Covers exactly: register and address to the reader; sentence rhythm and length habits; vocabulary used and vocabulary avoided; how a claim is anchored to its transit and date; and the interpretive territory of each of the eight Sections in fixed order (Energia generale del mese, Amore, Lavoro, Denaro, Benessere, Giorni favorevoli, Giorni di attenzione, Consiglio astrologico finale).
- Register per PRD §7: warm, addresses the reader as an adult; non-fatalistic (no fixed outcome, medical event, death, or financial result); speakable (no thread-losing nested clauses); specific (claims name the transit and the date, never vague seasonal language).
- Explicitly instructs against PRD §7's anti-references — generic horoscope prose applicable to anyone, mystical register, ominous/deterministic framing, fluent-but-hollow AI tone, vagueness — citing `text_sample/`'s own vocabulary and engagement-bait conventions as the concrete anti-pattern, while retaining their placement→life-area-consequence structural shape as legitimate raw material.
- Benessere guidance stays clear of anything a reader could take as a medical statement (vitality, stress, biorhythm, energy language only — never diagnosis, prognosis, or treatment), consistent with the PRD §6.2 GDPR Article 9 determination.
- Sections 6–7 guidance covers day-list caption tone only — never instructs emitting a date token in prose; dates are code-projected upstream (Epic 3).
- Per-Section interpretive territory is adapted from `addendum.md` §8's table and semantic-intent notes, reframed in instruction voice — not invented, not pasted verbatim as prose.
- Delivered as one Markdown file at `data/style-guide.seed.md`, human-readable, no TOML or code.

**Ask First:** None anticipated — every constraint above is already confirmed in the PRD/addendum.

**Never:**
- No StyleGuide database table, loader, versioning, or editor UI — Story 4.2.
- No Generator/adapter code, no `ReportTheme` code — Stories 4.5/4.3.
- No vocabulary, tone, or second-person social-CTA conventions ("segui", "interagisci", "mi raccomando") carried from `text_sample/` into the guide's prescribed register.
- No interpretive-territory claim beyond `addendum.md` §8 and the epic context — nothing invented.

</frozen-after-approval>

## Code Map

**Read-only references:**
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/addendum.md:147-186` (§8) — per-Section interpretive territory table, semantic intent behind each house/planet placement, and the Benessere caution; this is the guide's primary content source.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:501-513` (FR-30) — the guide's minimum required content, and explicit confirmation that §8 is the starting material (not written from scratch, contra `epics.md`'s stale claim).
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:784-799` (§7 Aesthetic and Tone) — register, speakable/specific tests, and the anti-references list.
- `_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md:719-763` (§6.1–6.2) — non-fatalistic guardrail and the Benessere GDPR determination the register must not undermine.
- `text_sample/oroscopo_mese_segni.txt`, `text_sample/SnapInsta*.txt` — Francesco's own social-channel horoscope writing. Source for structural shape only (opening → per-domain paragraphs → closing advice; naming a placement then its life-area consequence). Their vocabulary, CTAs, and vague-affirmation phrasing are the anti-pattern §7 warns against, confirmed by Francesco this session.
- `data/computation.toml:1-11`, `data/sections.toml:1-11` — sibling `data/` file header-comment convention (purpose, story reference, hand-bumped `version`) to mirror in the new file's own header.

**To create:**
- `data/style-guide.seed.md` — the Style Guide, version 1.

## Tasks & Acceptance

**Execution:**
- [x] `data/style-guide.seed.md` -- author the guide per Boundaries & Constraints, with a short header naming its purpose/story and a `version: 1` marker Story 4.2's seeding logic can read -- AC1-AC6
- [x] `data/style-guide.seed.md` -- apply 5 patch-level fixes from review: replace §3's near-verbatim
  example with an invented illustrative sentence; correct the Purpose section's description of the
  Generator's input from "a summary of prior months" to the two `ReportTheme` snapshots per
  `epic-4-context.md`; add an explicit tu/Lei rule to §1; add a date-format rule to §4; add a PRD §6.2
  citation to §5's Benessere GDPR determination -- AC1, AC2, AC5

**Acceptance Criteria:**
- Given the guide, when read, then it covers register/address, sentence rhythm and length, vocabulary used and avoided, claim-anchoring method, and the interpretive territory of all eight Sections in fixed order.
- Given the per-Section territory content, when compared to `addendum.md` §8, then it is recognizably derived from that table and its semantic-intent notes.
- Given the Benessere Section's guidance, when read, then it contains no diagnosis, prognosis, or treatment framing.
- Given Sections 6 and 7's guidance, when read, then it never instructs emitting a date token in prose.
- Given `text_sample/`'s vocabulary and CTA conventions, when compared to the guide's prescribed register, then they are absent and named as anti-references to avoid.
- Given the file, when committed, then it lives at `data/style-guide.seed.md` and carries a `version: 1` marker.

## Spec Change Log

- **Language of the instruction prose.** The spec is silent on whether the guide's own directive
  prose should be written in Italian or English; only the Report output language is fixed (FR-16).
  Chosen: English instruction voice, matching every other planning artifact this spec cites
  (`prd.md`, `addendum.md`, `epic-4-context.md`), with the eight Section names kept in Italian as
  fixed domain vocabulary and all illustrative sentences given in Italian and clearly marked as
  examples. Rationale: the guide's job is to instruct a Generator/editor, not to perform Francesco's
  register itself — writing the directives in his actual Italian voice would risk an AI-authored
  imitation of that register, which is exactly what Boundaries forbids carrying over from
  `text_sample/`. Francesco can revise this choice via the Story 4.2 editor once it exists.

## Design Notes

The guide is written in *instruction voice* — directives a Generator prompt (or a future human editor) follows — not as a sample Report itself. Illustrative sentences are fine but must read as clearly-marked examples, never as templates to fill in verbatim (the Generator must produce its own sentences from the Payload, not paraphrase a stored one).

## Verification

**Manual checks (performed):**
- Read the file against each Acceptance Criterion above: covers register/address (§1), sentence
  rhythm/length (§2), vocabulary used/avoided (§3), claim anchoring (§4), and all eight Sections in
  fixed order (§5) -- AC1. Per-Section territory in §5 traces line-for-line to `addendum.md` §8's
  table and semantic-intent notes, nothing added -- AC2. Benessere's guidance (§5.5) contains no
  diagnosis/prognosis/treatment language, only vitality/energy/rhythm vocabulary, with an explicit
  "never" list -- AC3. Sections 6-7 (§5.6-5.7) instruct captions only and explicitly forbid writing
  or paraphrasing a date in prose -- AC4. `text_sample/`'s CTA and fate-as-agent vocabulary is
  quoted verbatim in §3 and named as anti-pattern, absent from the prescribed register elsewhere in
  the file -- AC5.
- `file data/style-guide.seed.md` -- confirmed UTF-8 text.
- Header follows the sibling `data/` files' convention (purpose, story reference, hand-bumped
  version) adapted to Markdown: a blockquote note plus a plain `version: 1` line in place of TOML's
  `#`-comment block and `version = 1` field -- AC6.
- Verified none of `text_sample/`'s CTA/vocabulary phrases ("mi raccomando", "interagisci",
  "seguimi") appear anywhere outside their quoted, labeled anti-pattern citation in §3.

**Re-verification after review fixes (2026-08-20):** Review found 5 patch-level findings; all 5
were fixed directly in `data/style-guide.seed.md` and the manual checks above were re-run against
the updated file.

- **§3 example no longer lifted from source.** Re-read §3's illustrative sentence against
  `text_sample/oroscopo_mese_segni.txt`: the guide now reads *"Il 22 marzo Venere entra in Toro e
  rende più stabile il modo in cui gestisci le tue finanze quotidiane"* — invented, not the
  file's "Il 9 agosto Mercurio entra in Leone..." opening that repeats near-verbatim across many
  sign-entries in that file. `grep -n "Venere\|Toro\|22 marzo\|finanze quotidiane\|rende più
  stabile"` against `text_sample/*.txt` confirms no overlapping planet/sign pairing, date, or
  phrasing with the source file (the file pairs Venere with Bilancia and Urano with Toro, never
  Venere with Toro, and never in this phrasing) -- re-confirms AC1 and AC5, and the frozen spec's
  boundary against carrying `text_sample/` vocabulary into the guide's prescribed register.
- **Purpose section now matches the frozen Generator port.** Re-read against
  `epic-4-context.md`'s Technical Decisions: the Purpose section no longer says "a summary of
  prior months" and instead names the two `ReportTheme` snapshots (dominant slow-planet Aspects by
  tightness, natal houses of the month's Lunations, standing retrogrades) as what actually carries
  continuity, with prior Report prose explicitly excluded -- re-confirms AC1's coverage of "how to
  read this guide" against the epic context's own wording.
- **§1 now states the tu/Lei rule explicitly.** Re-read §1: it now states in its own sentence that
  address is always informal "tu," never formal "Lei" -- re-confirms AC1's "register and address to
  the reader" coverage, which previously depended only on the example's implicit "tu"/"ti aiuta."
- **§4 now states a date-format rule.** Re-read §4: it now specifies day-number-plus-lower-case-
  month-name as the written form for Sections 1-5 and 8 ("il 19 agosto"), and explicitly rules out
  numeral-only dates, weekdays, and spelled-out ordinals, cross-referencing Sections 6-7's no-date-
  in-prose rule -- re-confirms AC1's claim-anchoring coverage and AC4 (Sections 6-7 still never
  instruct emitting a date token in prose; the new §4 text explicitly says Sections 6-7 never write
  a date at all).
- **§5 Benessere determination now cites its source.** Re-read §5: the GDPR Article 9 sentence now
  reads "(PRD §6.2 — the Benessere Section does not produce GDPR Article 9 special category data)",
  matching the citation style already used elsewhere in the file (e.g. "Story 4.1, FR-30", "Epic 3",
  "the PRD addendum's own table") and matching PRD §6.2's own "Resolved 2026-08-14" wording at
  `prd.md:757` -- re-confirms AC3 (no diagnosis/prognosis/treatment language was touched by this
  fix) and strengthens AC2's traceability to source material.
- Re-read the full updated file end to end against every Acceptance Criterion: AC1-AC6 all still
  hold; no fix introduced diagnosis/prognosis/treatment language, a date token in a Sections 6-7
  caption, or `text_sample/` vocabulary outside its quoted anti-pattern citation.
- `file data/style-guide.seed.md` -- re-confirmed UTF-8 text after edits.

## Suggested Review Order

**Purpose and scope**

- Start here: what this document is, who reads it, and the corrected Generator input (two `ReportTheme` snapshots, never prior prose).
  [`style-guide.seed.md:13`](../../data/style-guide.seed.md#L13)

**Register and address**

- The tu/Lei rule added in review — governs every verb conjugation in the Report.
  [`style-guide.seed.md:36`](../../data/style-guide.seed.md#L36)

**Vocabulary and the text_sample anti-pattern**

- The most consequential design call: Francesco's own social-channel writing named explicitly as what to avoid, not what to imitate.
  [`style-guide.seed.md:86`](../../data/style-guide.seed.md#L86)

- The illustrative example, replaced in review after the original was found lifted from `text_sample/`.
  [`style-guide.seed.md:105`](../../data/style-guide.seed.md#L105)

**Claim-anchoring and date format**

- Core mechanism: how a sentence earns the right to make a claim.
  [`style-guide.seed.md:113`](../../data/style-guide.seed.md#L113)

- Date-format rule added in review, plus the Sections 6–7 no-date-in-prose exception.
  [`style-guide.seed.md:122`](../../data/style-guide.seed.md#L122)

**Per-Section interpretive territory**

- Where richness and safety pull against each other hardest — the Benessere hard line, now cited to PRD §6.2.
  [`style-guide.seed.md:174`](../../data/style-guide.seed.md#L174)

- The remaining seven Sections, each traced to `addendum.md` §8.
  [`style-guide.seed.md:143`](../../data/style-guide.seed.md#L143)
