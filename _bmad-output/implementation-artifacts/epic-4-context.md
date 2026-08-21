# Epic 4 Context: Eight Sections of Italian prose in my register, that don't repeat last month

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Francesco writes the Style Guide describing his own register, edits it in the application without a
deploy, and generation produces the eight Report Sections in Italian, conditioned on that guide —
treating still-active transits as continuing rather than reintroducing them, and stating plainly when
nothing significant has changed. The Generator computes nothing: it receives a Report Payload, the
Style Guide, and two purely-derived summaries of prior and current months (`ReportTheme`), and returns
cited sentences rather than free prose. This is the highest-risk epic in the whole build — one
deliverable (the Style Guide) is writing work no engineering can substitute for, and the product's
output quality rests on it.

## Stories

- Story 4.1: Write the Style Guide
- Story 4.2: Edit the Style Guide without a deploy
- Story 4.3: Derive a ReportTheme from a Payload
- Story 4.4: Compute what has changed since last month
- Story 4.5: Generate eight Sections as cited structure
- Story 4.6: Render cited sentences into prose I could read aloud
- Story 4.7: Write this month as a continuation, not a reprint
- Story 4.8: Absorb a rate limit without my involvement
- Story 4.9: Build against the Generator without spending quota

## Requirements & Constraints

- Exactly eight Sections, fixed order, Italian only: Energia generale del mese, Amore, Lavoro, Denaro,
  Benessere, Giorni favorevoli, Giorni di attenzione, Consiglio astrologico finale. Sections 1–5 and 8
  are continuous prose, never bullet fragments; Sections 6–7 may use list form but the model must never
  emit a date token there — dates are code-projected upstream (Epic 3).
- Register: professional, warm, non-fatalistic, addressing the reader as an adult; no sentence predicts
  a fixed outcome, medical event, death or financial result. Prose must be **speakable** (survives being
  read aloud on a call, no thread-losing nested clauses) and **specific** (claims name the transit and
  the date, not vague seasonal language — generic horoscope prose that would apply to anyone is the
  named anti-pattern).
- The Style Guide is authored by Francesco alone — a first-class v1 deliverable, not a config step. It
  must cover register/address, sentence rhythm and length, vocabulary used/avoided, how a claim is
  anchored to its transit and date, and each Section's interpretive territory. Generation refuses to run
  without a Style Guide version present, and says why.
- **Benessere is the one Section where interpretive richness and product safety pull against each
  other.** Its territory (vitality, stress, biorhythms) sits closest to a medical statement anywhere in
  the product; Francesco's GDPR Article 9 determination for it was made against a register that stays
  clear of health-assessment language, and drifting from that register would put the determination back
  in question. The Style Guide is what has to hold this line.
- Returning-Client generation treats a transit still active from a prior month as continuing (moved,
  tightened, resolved), never reintroduced fresh; where nothing significant changed, the Report says so
  plainly rather than manufacturing novelty (claim-level determinism forbids inventing change). A
  Client's first Report has no history and no reference to prior months.
- Before real Client data is first sent to the configured provider, its data terms must be verified and
  the check recorded — the zero-cost guarantee is jurisdiction-contingent (EEA paid-tier data terms
  applied to free tiers), and this is what makes it safe.
- Rate-limit/transient generation failures retry automatically and invisibly to Francesco, bounded,
  sized to the provider's 10 requests/minute ceiling. Exhausted retries mark the Report failed with a
  surfaced reason; never a partial, exportable Report. No automatic failover to another provider ever —
  changing provider is a separately gated, deliberate configuration change with its own data-terms
  verification.
- Local development runs generation against recorded responses, not the live provider, so building and
  testing this epic costs no quota and stays deterministic; the same tests exercise the real port
  contract at the port boundary.
- Exactly two environments exist — local and production — no staging.

## Technical Decisions

- **Generator port is fixed and exclusive**: `(ReportPayload, StyleGuide, ReportTheme_previous,
  ReportTheme_current)`, nothing else. The adapter holds no DB handle, filesystem access or tool
  definitions. Prior Report prose is never sent to it — continuity travels only as `ReportTheme`.
- **The Generator returns cited structure, not prose**: each Section is an ordered list of sentences,
  each carrying the Payload entry IDs it rests on (a closed-vocabulary sentence with none is a Gate
  violation, enforced in Epic 5). Rendering into continuous prose is the shell's job; citations are kept
  against the stored draft, not discarded at render time.
- **`ReportTheme` must be built before generation**, since it's a Generator port argument — building it
  after would force a breaking port change. `derive_theme(payload, config) -> ReportTheme` lives in
  `core/memory/`, pure and model-free, yielding dominant slow-planet Aspects by tightness, the natal
  houses of the month's Lunations, and standing retrogrades. `config` is read only for
  `config.bodies.slow` — the single source of truth for the slow/fast split, so `core/memory/` never
  carries a second, drifting hardcoded body list. Comparing two ReportThemes (still-active / tightened /
  resolved / new) is what makes "nothing significant changed" computed rather than judged. Stored in its
  own table, separate from generation, joining the Client-deletion cascade.
- **Exactly one Generator adapter** (Google Gemini `gemini-2.5-flash`, free tier, EEA data terms), no
  runtime failover ever. Rate limits/transient failures are absorbed by bounded backoff sized to the
  10 RPM ceiling plus run checkpointing (a `ReportRun` advances forward only through persisted stages;
  re-driving a run resumes at the first incomplete stage).
- **The Style Guide is versioned data in the database**, not a repo file: versioned rows, edited in the
  UI, every prior version retained. `data/style-guide.seed.md` seeds version 1 only; the database is
  the source of truth thereafter. Every Report records the Style Guide version that produced it.
- The draft table (persisted at the `draft_ready` run stage) records the Style Guide version and the
  Section-composition version that produced it, and joins the Client-deletion cascade.
- Domain vocabulary is fixed and untranslated (`Generator`, `StyleGuide`, `ReportTheme`, `Section`,
  `Claim`, …) — a synonym anywhere is a defect. The four domain names (`amore`, `lavoro`, `denaro`,
  `benessere`) stay lowercase Italian everywhere in code, database and configuration.
- Core stays pure: no I/O, no clock, no network, no randomness in `core/memory/`. Only `shell/` reaches
  the Generator, the database or the clock; `core/` cannot import `shell/`.

## UX & Interaction Patterns

- A Style Guide editor over versioned rows, with prior versions retained and readable, reachable
  without a deploy or code change.

## Cross-Story Dependencies

- Story 4.1 (Style Guide) blocks Story 4.5 (Generation) and nothing else in this epic — it can and
  should start on day one, independent of everything else here.
- Story 4.3 (`derive_theme`) must land before Story 4.5, because `ReportTheme` is a Generator port
  argument (AD-3) — building generation first would force a breaking port change later.
- Story 4.4 (theme-diffing) depends on Story 4.3 producing two comparable ReportThemes.
- Story 4.7 (continuation, not reprint) depends on Stories 4.4 and 4.5/4.6 together — it's the
  behavioral outcome of feeding both ReportThemes and the computed diff into generation.
- Story 4.6 (prose rendering) depends on Story 4.5's cited-structure output.
- Stories 4.8 (backoff) and 4.9 (recorded-response adapter) both extend the Generator adapter built in
  Story 4.5.
- Upstream: this epic consumes the Report Payload from Epic 3 (payload assembly) as the sole source of
  fact for both `ReportTheme` derivation and generation itself.
- Downstream: Epic 5 (Groundedness Gate) consumes the cited draft structure this epic produces
  (Story 4.6) and is the only path from a draft to an exportable Report.
</content>
