# Gemini data-terms re-verification (Story 8.2)

The zero-cost design (AD-9, PRD §6.2, NFR-17) depends on Google applying its
**Paid Services** data terms — no training on submitted content, no human review
of submitted content — to the Gemini API **free tier** for the EEA. This file is
the durable, dated record of that check. The machine-readable block below is
parsed by `tests/test_data_terms_record.py`; the guard suite stays red while
`outcome` is anything other than `"pass"`.

The ratified outcome is indexed as **RGD-1** in
[`docs/decisions/README.md`](../decisions/README.md).

```toml
provider = "Google"
model = "gemini-2.5-flash"
tier = "free"
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
terms_source = "https://ai.google.dev/gemini-api/terms"
terms_effective = 2026-03-23
terms_snapshot = "https://web.archive.org/web/20260820061356/https://ai.google.dev/gemini-api/terms"
hosting_region = "frankfurt"
storage_region = "Europe/Frankfurt"
outcome = "pass"
```

## What the design relies on

EEA free-tier use of the Gemini API is governed by Google's **Paid Services**
data terms, by way of a jurisdictional carve-out:

- **(a) No training on submitted content** — Google does not use prompts,
  associated system instructions, cached content, uploaded files, or responses to
  train or improve Google products.
- **(b) No human review of submitted content** — no human reviewer reads,
  annotates, or otherwise processes API input or output.
- **EEA / Switzerland / UK carve-out** — the "How Google uses Your Data" terms
  from the *Paid Services* section apply to **all** Services, including Google AI
  Studio and the unpaid quota of the Gemini API, even though they are free of
  charge.

If any of these stops holding, the release is blocked until reassessed
(`outcome = "blocked"`).

## Published terms as read on 2026-08-27

Source: <https://ai.google.dev/gemini-api/terms> — stamped "Effective March 23,
2026". The verbatim quotes below are the durable snapshot of record: this file
does not depend on the live page staying unchanged, and a re-verification
compares the then-current page against these quotes. A Wayback Machine capture
of the source page is pinned as `terms_snapshot` in the block above
(`web.archive.org` capture dated 2026-08-20, the nearest available; a fresh
save could not be triggered from the verification environment). Verbatim
quotes:

- **Paid Services, training** — "Google doesn't use your prompts (including
  associated system instructions, cached content, and files such as images,
  videos, or documents) or responses to improve our products."
- **Paid Services, logging** — "Google logs prompts and responses for a limited
  period of time, solely for detecting and preventing violations of the
  Prohibited Use Policy to maintain the safety and security of the Services."
- **Unpaid Services, human review** — "human reviewers may read, annotate, and
  process your API input and output". No equivalent clause exists under Paid
  Services.
- **EEA / Switzerland / UK carve-out** — "If you're in the European Economic
  Area, Switzerland, or the United Kingdom, the terms under 'How Google uses Your
  Data' in 'Paid Services' apply to all Services, including Google AI Studio and
  unpaid quota in the Gemini API, even though they are offered free of charge."

## Comparison

| Guarantee the design relies on | Published clause | Verdict |
|---|---|---|
| (a) No training on submitted content | Paid Services: "Google doesn't use your prompts … or responses to improve our products." — extended to the unpaid Gemini API quota for the EEA/CH/UK by the carve-out. | **Holds** |
| (b) No human review of submitted content | The human-review clause ("human reviewers may read, annotate, and process your API input and output") is **Unpaid-Services-only**. The EEA/CH/UK carve-out replaces the Unpaid terms with the Paid terms for all Services, and Paid Services carries no human-review clause. | **Holds** |
| EEA/CH/UK carve-out extends the paid terms to the free quota | "… the terms under 'How Google uses Your Data' in 'Paid Services' apply to all Services … including … unpaid quota in the Gemini API, even though they are offered free of charge." | **Holds** |

## Changes since the 2026-01-15 planning reading

- The terms are now stamped **"Effective March 23, 2026"**; the planning reading
  (`GEMINI_DATA_TERMS_VERIFIED_AT=2026-01-15`) predates this revision.
- A **Paid-Services safety-logging clause** is now explicit: prompts and
  responses are logged for a limited period **solely** for detecting and
  preventing Prohibited Use Policy violations.

**Assessment:** neither change touches PRD §6.2's two questions. Limited-retention
abuse-detection logging is not model training and not human annotation — it does
not weaken guarantee (a) or (b). **Not material → `outcome = "pass"`.**

## Hosting and storage location

- **Hosting** — Render web service, `region:` key set to `frankfurt` in
  `render.yaml`. EU.
- **Storage** — Neon Postgres project in `Europe/Frankfurt` (`README.md`
  Deployment section; `render.yaml` header comment). EU.

Both the compute and the durable data sit in the EU/EEA. Confirmed.

## Outcome

**`pass`** — the currently published terms preserve both guarantees the
zero-cost design depends on, and hosting and storage are in the EU/EEA. Release
may proceed.

Ratified by Francesco on 2026-08-27 (`ratified_on`), confirming the quoted
clauses and the `pass` outcome against a live reading of the terms.

## Next re-verification trigger

Re-run this check whenever any of these happens:

- the Generator provider, model, or tier changes (AD-9);
- any of the quoted clauses, or the EEA/CH/UK carve-out, changes wording or is
  removed;
- the `terms_effective` date on <https://ai.google.dev/gemini-api/terms>
  advances.

When re-verifying, update the `checked` date (and `ratified_on`, `terms_source`,
`terms_effective`, `terms_snapshot`, `outcome` as needed) in the block above,
then set `GEMINI_DATA_TERMS_VERIFIED_AT` to the new `checked` date in **every**
place it is configured — this is the complete list:

- `.env.example` (local, non-Docker path);
- `compose.yaml`, the `app` service (local Docker path);
- the value set manually on the Render service dashboard for the production
  deployment (`render.yaml` declares the key `GEMINI_DATA_TERMS_VERIFIED_AT`
  with `sync: false`, so it is entered by hand, not from the repo).

The guard suite in `tests/test_data_terms_record.py` binds `.env.example` and
`compose.yaml` to this record's `checked` date, so a missed edit there fails
the build; the Render dashboard value is operator-owned and is not checkable
from the repo.

If a re-check finds guarantee (a) or (b) materially weakened for the EEA free
tier, set `outcome = "blocked"` and re-open the story — do not write `"pass"`
over a regression.

## Governing references

- **PRD §6.2 — Privacy and Data Protection**
  (`_bmad-output/planning-artifacts/prds/prd-astro-report-2026-08-14/prd.md`):
  the generation provider's data terms are verified before real Client data is
  sent, and again if generation falls back to another provider; hosting and
  storage sit in the EU/EEA where the free tier offers the choice.
- **NFR-17 — Provider data terms verified**
  (`_bmad-output/planning-artifacts/epics.md`): the recorded-verification
  requirement; the zero-cost guarantee is jurisdiction-contingent.
- **AD-9** (`_bmad-output/planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md`):
  a single configured Generator — Gemini `gemini-2.5-flash`, free tier, EEA data
  terms — with no runtime failover. Mirrored in
  `shell/adapters/gemini/generator.py` (`_MODEL`).
