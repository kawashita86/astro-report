---
title: "Product Brief: astro-report"
status: draft
created: 2026-08-14
updated: 2026-08-14
---

# Product Brief: astro-report

## Executive Summary

astro-report is a private production tool for a working astrologer. It turns five facts — a
client's name, birth date, birth time, birthplace, and the month to read — into a finished,
client-ready report in Italian, without its operator ever opening Astro.com again.

Today that report is made by hand. Francesco loads a client's chart on Astro.com, opens *Natal
chart and transits*, samples the month on four dates, and writes down by hand what he finds:
fast planets, slow planets, retrogrades, house ingresses, aspects to natal points, new and full
moons. Then he interprets all of it into eight sections of finished Italian prose. **One report
takes between one and three hours.** He produces thirty to fifty of them a month.

The arithmetic is the product. At thirty to fifty reports a month, the manual process consumes
between 30 and 150 hours — call it eighty. At the volume Francesco actually wants to reach, one
to two hundred reports a month, it would consume between 100 and 600 hours. A full-time month
holds about 160 hours. **His own hands are the ceiling on his business, and he has nearly
reached it.** astro-report is not a convenience. It is the only route to the volume he is
aiming at.

## The Problem

The work being replaced is not interpretation. It is **transcription**.

Every month, for every client, the same sequence: open the chart, read the wheel, sample four
dates, annotate six categories of event, cross-reference each transit against the natal
positions, group the findings into love, work, money and wellbeing, then write. The
interpretation is the part Francesco is paid for and the part he is good at. The two or three
hours are mostly spent on everything else — the clerical labor of getting exact astronomical
facts out of a website and onto a page in an order he can write from.

Beyond the hours it costs, that labor carries a second risk. Hand-annotating retrogrades, house
ingresses and aspect orbs across four sample dates, fifty times a month, is exactly the kind of
repetitive precision work where a mistake stays invisible until a client acts on it.

And it is not the work. Nobody pays an astrologer to read coordinates off a screen.

## Who This Serves

**Francesco — the operator.** A professional astrologer with paying clients, a mix of recurring
subscribers and one-off commissions. He is the only person who will ever open the application.
Success for him is measured in hours returned and in reports he can send without reading them
first. He does not need to be taught astrology by the tool; he needs it to stop making him do
data entry.

**The client — the reader.** Never touches the application, and may not know it exists. They
receive a finished report in Italian: eight sections covering the month's general energy, love,
work, money, wellbeing, favorable days, days to watch, and a closing piece of advice.
Sometimes Francesco reads it to them aloud, in which case the report is not a document but a
script — and any sentence in it may be questioned live, and must be answerable.

Two implications follow, and neither appears in the original technical research. **The report
ships unedited** — there is no review step to catch a bad sentence, so what the system generates
is what a paying client reads. And **recurring clients accumulate history**: March's report for a
returning client must not restate February's, so the system needs memory of what it has already
said to whom.

## The Solution

Francesco enters five things — name, date of birth, time of birth, place of birth, and the month
to analyze. He gets back a finished report in Italian, in his own voice, ready to send.

Between those two moments the system does the work he currently does by hand, in three stages:

**It computes, exactly.** Swiss Ephemeris, running locally, produces the natal chart once per
client and keeps it. For the requested month it samples the transits, tracks retrogrades and
their stations, detects ingresses into the natal houses, measures every transit-to-natal aspect
against a tight orb, and locates the new and full moons to the minute. This is the two-to-three
hours of annotation, done in seconds and without transcription error.

**It organizes, by domain.** The computed facts are grouped the way an astrologer reads them,
not the way an ephemeris emits them — into love, work, money and wellbeing, with the traditional
and modern rulers resolved for each cusp. The specific placements each domain draws on are
listed in the addendum.

**It writes, in Francesco's voice.** The language model receives only the computed facts — it is
never asked to calculate anything — and renders them into the eight sections of the finished
report, in Italian, conditioned on Francesco's existing body of written work so the prose reads
as his. Output goes to PDF or Markdown.

The chart wheel is drawn, but for Francesco alone: a visual check that the computation matches
what he would have seen on Astro.com. The client receives prose.

## What Makes This Different

**The voice is the moat, and it is not a technical one.** Francesco has written hundreds of
these reports by hand. That corpus is proprietary, unrepeatable, and the reason no commercial
product can serve this need — an off-the-shelf report generator can be accurate, but it cannot
sound like him, and his clients are paying for him. Every other advantage listed here could be
rebuilt by a competent developer in a month. This one could not be rebuilt at all. That
advantage is not yet in hand: the reports exist but are scattered across email, messaging and
folders, and collecting them is real work that has to happen before it becomes available.

**The model narrates; it never calculates.** Generic AI writes fluent astrological prose over
invented astronomy. Here the language model is handed exact geometry and forbidden from
producing any claim not present in it. This is what makes an unedited report safe to send under
a professional's name, and what lets Francesco defend any sentence when a client questions it
mid-consultation.

**It is built for the person producing the report, not the person reading it.** This is the gap
every existing tool falls into. The consumer astrology category — Co-Star, CHANI, My Zodiac AI,
Astrolink — sells interpretation directly to end users and produces nothing a working astrologer
can deliver under his own name. Astro.com and Astro-Seek compute exactly but stop at the data,
which is precisely where the three hours begin. Generic AI chat writes fluent Italian prose over
invented astronomy, which is worse than useless when a paying client acts on it. Between tools
that compute but do not write, and tools that write but do not compute, every hour of the manual
process is spent standing in the gap.

One honest caveat: running at zero cost is a constraint the design satisfies, not an advantage.
The accuracy benchmark this system chases is already free, and cost was never what made the work
hard.

## Success Criteria

**Time per report falls from 1–3 hours to under 15 minutes** of Francesco's involvement — entering
client data, a final look, sending. This is the primary measure; everything else supports it.

**Capacity reaches 100–200 reports per month** without a corresponding increase in hours. The
target volume is currently unreachable by hand; the tool succeeds if it becomes reachable.

**Astronomical output matches Astro.com** for the same chart and month — positions, cusps,
retrogrades, ingresses, aspects and lunations — verified against a set of reference charts before
any report goes to a client, and no claim in a delivered report goes beyond what that data
supports.

**Reports are sent unedited.** The honest measure of whether the voice conditioning works is how
often Francesco changes a word before sending. If he is routinely rewriting, the system has moved
the work rather than removed it.

**Running cost stays at zero** at 30–200 reports per month.

## Scope

**In, for the first version**

- Single operator. Francesco is the only user of the application.
- Client records: birth data entered once, natal chart computed once and stored, reusable every
  month thereafter.
- Monthly transit analysis: fast and slow planets, retrogrades and stations, ingresses into natal
  houses, aspects to natal points, new and full moons.
- Domain grouping into love, work, money and wellbeing, with traditional and modern house rulers.
- The eight-section report, generated in Italian, in Francesco's voice.
- Export to PDF and Markdown.
- Chart wheel rendering — internal, for verification only.
- Memory across months for recurring clients, so a report does not repeat what its predecessor
  already said.
- Recovery of the historical report corpus — collecting the existing reports into one usable
  place. A prerequisite for the voice work, and a real task in its own right.

**Explicitly out**

- Client-facing accounts, logins, or any interface the client touches.
- Multi-astrologer or multi-tenant operation. Not deferred — this tool serves one person,
  permanently.
- Mobile application.
- Synastry, compatibility, solar returns, progressions, or any technique outside natal chart and
  monthly transits.
- Billing, payments, scheduling, or CRM beyond the client record needed to produce a report.
- Output in any language other than Italian.
- Any capacity planning beyond 200 reports per month.

## Key Risks

**The corpus may not survive contact with reality.** The voice conditioning is the product's
central claim and rests on material that is currently scattered across email, messaging and
folders. Recurring clients have records that could pair a report with the chart and month behind
it; one-off reports are prose only. Paired examples teach the model Francesco's reasoning;
unpaired prose teaches only his tone. Until the collection is done, the size and quality of the
usable corpus are unknown, and so is how close the output can get to his voice.

**Ship-ready quality is an unproven bar.** No report currently reaches a client unedited. That
the system can clear that bar consistently, fifty times a month, is an assumption — not a
demonstrated result. The honest test is Francesco sending one without changing a word.

**The zero-cost guarantee is jurisdiction-contingent.** Free AI tiers generally reserve the right
to use submitted content; Francesco is protected only because he operates from the EEA. That
protection is a condition to re-check before launch, not a property to assume. Detail in the
addendum.

## Vision

The ambition is unglamorous and worth stating plainly: remove the ceiling. If the tool works,
Francesco's practice is limited by how many clients he can find and serve well, rather than by
how many hours he can spend transcribing coordinates — and the hours it returns go back into the
interpretive work he is actually paid for.

From there it deepens rather than widens. More techniques as he wants them, richer memory of each
client's history, reports that read as an ongoing conversation across years rather than a
monthly artifact. This is a tool for one astrologer, built around one astrologer's voice, and it
stays that way by choice.
