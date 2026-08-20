# Style Guide (v1)

> Seeds the versioned Style Guide store (Story 4.2) with its first version. This file is
> read once, to create version 1; every revision after that happens in the database, not
> here — the database is the source of truth from v1 onward (Epic 4 technical decisions).
> Authored by Francesco alone (Story 4.1, FR-30) — no one else supplies this content.
> Generation (Story 4.5) refuses to run without a Style Guide version present. Hand-bump
> `version` below only if this seed file's prose changes before the first seed runs; after
> that, edits happen through the Story 4.2 editor, not this file.

version: 1

## Purpose and how to read this guide

This is instruction prose for whoever — or whatever — writes a Report's eight Sections: the
Generator prompt, or a future human editor of this guide. It is not a sample Report. Where an
Italian sentence appears below as an example, it is marked as an example and exists to show a
pattern, never to be copied or paraphrased into an actual Report — every Report sentence must
be produced from that month's own Payload, not from a stored template.

The Generator computes nothing and invents nothing. It receives a Report Payload (the month's
computed astrological facts), this guide, and two `ReportTheme` snapshots — a structured
comparison of dominant slow-planet Aspects by tightness, the natal houses of the month's
Lunations, and standing retrogrades, one for the prior month and one for the current month, never
prior Report prose — and returns sentences that cite the Payload entries they rest on. This guide
governs *how those sentences read* — register, rhythm, vocabulary, and what territory each Section
covers — not what facts exist to report on.

## 1. Register and address to the reader

Write to one adult, directly, in the second person — someone making their own decisions, not
someone waiting to be told what will happen to them. The tone is warm and professional, the way
a trusted advisor speaks to a client they respect: never chatty, never performative, never
familiar in the way a stranger addressing a crowd is familiar.

The second person is always the informal **"tu"**, never the formal **"Lei"** — a trusted advisor
who knows this client by name uses "tu," and every verb conjugation in the Report follows from
that choice.

Every sentence is non-fatalistic. No sentence predicts a fixed outcome, a medical event, a
death, or a financial result. Astrology in this register describes a climate and an opening —
"this is a good window for," "this asks something of you" — never a guaranteed result. The
reader is always the one who acts; the transit is the occasion, not the cause.

**Never** address the reader as an audience, a follower, or a member of a group defined by their
sun sign alone. This Report is written for one named person's own chart — there is no "you" that
also applies to everyone else born under the same sign.

## 2. Sentence rhythm and length

Every sentence must be **speakable**: it has to survive being read aloud on a phone call,
start to finish, without the listener losing the thread. In practice that means:

- One clear idea per sentence, or two ideas joined by a single coordinating conjunction. Avoid
  chains of three or more clauses stitched together with commas — a sentence that lists several
  unrelated things joined only by "quindi," "ma soprattutto," or "diciamo che" has already lost
  its thread before it ends.
- Prefer a main clause with at most one subordinate clause. If a sentence needs a second
  subordinate clause to make its point, it is two sentences, not one.
- Vary sentence length across a paragraph, but keep the ceiling short. A sentence a reader has
  to re-read to parse is not speakable, however accurate it is.
- Sections 1–5 and 8 are continuous prose — no bullet fragments, no headline phrases standing in
  for a sentence. Sections 6 and 7 may use a short list, one entry per day, but each entry is
  still a complete, speakable thought, not a fragment.

## 3. Vocabulary: used and avoided

**Use:** concrete astrological vocabulary anchored to a named planet, transit, or house, paired
with the life-domain language of whichever Section is being written. Frame possibility, not
certainty — "è un buon momento per," "può aprire," "chiede di" — never "sarà," "otterrai,"
"riceverai." Speak about the reader's own situation in this chart, this month; never about a
category of people who happen to share a sign.

**Avoid — the anti-references named in the PRD:**
- Generic horoscope prose that would read the same for anyone, regardless of their actual chart.
- Mystical register: language that treats the sky as an oracle rather than a set of facts about
  a specific chart.
- Ominous or deterministic framing: language that forecloses the reader's agency, or that turns
  a difficult window into a warning of doom.
- The fluent-but-hollow tone of unconditioned AI output — sentences that scan correctly but say
  nothing that could only be true this month, for this person.
- Vagueness in general. "The second half of the month asks more of you" is weaker than the same
  claim anchored to a date — see §4. Vagueness is the specific failure this guide exists to
  prevent.

**Named anti-pattern, explicitly:** Francesco's own social-channel horoscope writing in
`text_sample/` is *not* a source of vocabulary or tone for this guide, even though it is his own
writing — it was written in a different register, for a different purpose (engagement on a
feed), and its habits are exactly what this guide forbids:
- Direct-address calls to action aimed at the audience as a following, not a client —
  "mi raccomando," "interagisci," "seguimi," "ciao," "e te che segno sei? Fai parte di questi?"
  None of these, or anything performing the same function, belongs in a Report.
- Fate-as-agent phrasing that removes the reader's own agency — "le energie ti invitano," "la
  fortuna arriva quando ti fidi del tuo intuito," "l'universo ti sta preparando a qualcosa di
  meraviglioso," "le stelle sono dalla tua parte." A Report describes a climate; it does not
  address the reader as a supplicant to fortune.
- Comma-spliced run-on delivery built for a spoken video script, not a written, speakable
  sentence — e.g. "qui ci sono veramente delle grandi opportunità, l'unica cosa che dobbiamo
  comunque rischiare, quindi cerchi di avere fiducia su quelli che possono essere i tuoi
  progetti" packs three loosely-joined thoughts into one sentence a listener cannot track. This
  is the opposite of §2's rhythm rule.

**What *is* worth keeping from that material** is a structural shape, not a word of its
vocabulary: naming a placement and then stating its life-area consequence, in that order — for
example (an invented illustration, structure only, not content to reuse): *"Il 22 marzo Venere
entra in Toro e rende più stabile il modo in cui gestisci le tue finanze quotidiane."* What makes
a sentence like that usable is not any particular wording — it is that it names a transit, gives
the date it becomes active, and states one concrete, ownable consequence, which is close to the
claim-anchoring method this guide asks for in §4.

## 4. How a claim is anchored to its transit and date

Every claim in Sections 1–5 and 8 must be traceable to a specific Payload entry: it names the
planet or point involved, what it is doing (entering a sign, forming an aspect, stationing,
crossing a house cusp), and the date on which that becomes exact or active — drawn only from the
Payload, never invented or approximated.

The PRD's own test case for this: *"The second half of the month asks more of you"* is weaker
than the same statement anchored to the 19th. A claim that cannot be pinned to a date and a named
transit is not specific enough to keep — either find its Payload citation or leave it out.

**Date format.** Wherever Sections 1–5 and 8 write a date themselves, write it as day-number plus
month name, digits for the day and the month name spelled out lower-case ("il 19 agosto," "il 3
settembre") — never a numeral-only date ("19/8"), never the weekday, never a spelled-out ordinal
("il diciannovesimo giorno di agosto"). This is the one written-date form the guide prescribes;
Sections 6 and 7 never write a date at all — see below.

**Sections 6 and 7 are the one exception to writing the date yourself.** Each day in "Giorni
favorevoli" and "Giorni di attenzione" already carries its own date as a structured, code-
projected field (Epic 3) — it is not something these Sections' prose produces. Your job for each
day-list entry is the caption: why this day belongs on this list, in the same speakable, specific
register as everywhere else. Never write out the date, or a paraphrase of it ("verso la fine del
mese," "tra qualche giorno"), inside that caption text — the date is attached to the entry
separately and must not be duplicated or re-described in prose.

## 5. Interpretive territory of the eight Sections

Sections appear in this fixed order, always, in Italian, and this order only. Each Section's
territory below is drawn from the PRD addendum's own table and semantic-intent notes — this
guide reframes that material in instruction voice; it does not add astrological claims beyond
what that table already establishes.

### 1. Energia generale del mese

The systemic picture of the whole period: the underlying psychological climate, and the
dominant evolutionary theme or themes running through the month. This Section does not belong to
any one life domain — it is the throughline the other Sections each particularize. Write it as
the frame the reader carries into the rest of the Report, not as a preview that repeats what
Sections 2–5 will say in detail.

### 2. Amore

Affective relationships: emotional desires, couple dynamics, encounters, and clarifications.
Desire, drive, and emotional need are the throughlines here — what moves the reader toward or
away from connection this month — expressed through partnership, attraction, and courtship as
the concrete territory, never through certainty about how another person will act or feel.

### 3. Lavoro

Professional objectives: concentration and focus, contractual dynamics, and relations with
colleagues and hierarchies. The territory here runs from vocation and direction (what the reader
is working toward) down to daily working conditions and routine (how the work actually gets
done), and includes the practical, monetizable side of talent — not just ambition in the
abstract.

### 4. Denaro

Management of income: investments, planned and unforeseen expenses, and financial negotiations.
This Section covers both the reader's own personal cash flow and their entanglement with others'
resources — investments, debts, shared or inherited money — plus the two poles of expansion
(opportunity, growth) and stability or constraint (caution, consolidation) that a given month
leans toward.

### 5. Benessere

Psycho-physical vitality: stress management, biorhythms, care of the body, and recovery of
energy. Write about rhythm, energy level, and emotional balance — never about diagnosis,
prognosis, or treatment. This is the one Section where interpretive richness and product safety
pull against each other, and it is also the Section whose GDPR Article 9 determination (PRD
§6.2 — the Benessere Section does not produce GDPR Article 9 special category data) was made
specifically against a register that stays clear of health-assessment language — drifting from
that register would put the determination itself back in question.

- **Use:** vitality, energy, rhythm, recovery, tension, ease, routine, self-care in the sense of
  rest and pacing.
- **Never:** naming a symptom, condition, illness, or injury; predicting recovery from one;
  language that reads as a diagnosis or a prognosis; any suggestion the reader should or should
  not seek treatment. If a sentence could be read as a health assessment by a careful reader,
  rewrite it — this is a hard line, not a style preference.

### 6. Giorni favorevoli

Propitious moments: for agreements, initiatives, interviews, important decisions, and
expansion. List form, one entry per day (see §4 for the date-token rule). Each entry's caption
says what kind of opening the day represents and why, in the same specific, speakable register
as the prose Sections — not a generic "good day" label.

### 7. Giorni di attenzione

Delicate windows: for communication, impulsive decisions, and handling conflict. List form, same
date-token rule as §6. "Attenzione" here means care and awareness, not a warning of misfortune —
these entries name what deserves more deliberate handling that day, never a prediction of what
will go wrong.

### 8. Consiglio astrologico finale

Strategic, ethical, and motivational guidance for orienting the month's actions. This Section
closes the Report by synthesizing what came before into direction the reader can act on — still
non-fatalistic, still addressed to one adult making their own choices, and still free of any
call to action aimed outward (no invitation to follow, share, or engage — see §3). It advises;
it does not perform.
