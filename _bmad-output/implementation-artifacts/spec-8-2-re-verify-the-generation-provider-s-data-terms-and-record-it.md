---
title: 'Story 8.2 — Re-verify the generation provider''s data terms and record it'
type: 'chore'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
baseline_commit: '4b217213ffd6327a9206e40978818b6228a556be'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The zero-cost design (AD-9, PRD §6.2, NFR-17) rests on Google applying its paid-tier
data terms — no training on submitted content, no human review of submitted content — to the Gemini
free tier for the EEA. That was read once at planning time (`GEMINI_DATA_TERMS_VERIFIED_AT=2026-01-15`
is the only trace) and never re-checked against what is published now. Epic 8 is the release gate and
requires this verified against today's terms, recorded with a date and outcome, with hosting and
storage confirmed to sit in the EU/EEA.

**Approach:** Add a durable, machine-checkable record at `docs/release-validation/gemini-data-terms.md`
holding the dated check: the guarantees the design depends on, the currently published terms quoted
with their source and effective date, a clause-by-clause comparison, any change since the planning
reading with its assessment, the hosting/storage location check, and a `pass`/`blocked` outcome that
Francesco ratifies. Bind it with guard tests: the record parses and permits release, the render
region is an EU region matching `render.yaml`, and the `GEMINI_DATA_TERMS_VERIFIED_AT` example values
equal the record's `checked` date. Bump those example dates to the check date. No runtime behaviour
changes.

## Boundaries & Constraints

**Always:**
- The record's machine-readable block is a fenced ` ```toml ` block parsed by `tomllib` (stdlib) — no
  YAML library exists in this repo (`test_compose_local_generator.py` / `render.yaml` tests all do
  line parsing). Keys: `provider`, `model`, `tier`, `checked` (bare ISO date → `datetime.date`),
  `ratified_by`, `terms_source`, `terms_effective`, `hosting_region`, `storage_region`, `outcome`.
- `outcome` is exactly `"pass"` (release may proceed) or `"blocked"` (release must not proceed). The
  guard test asserts `== "pass"`, so a recorded material change keeps the suite red until reassessed.
- `hosting_region` and `storage_region` in the record must match `render.yaml`'s `region:` value and
  the Neon project region documented in `README.md` / `render.yaml` (`frankfurt` / `Europe/Frankfurt`).
- The comparison covers the two guarantees §6.2 names: (a) no training on submitted content, (b) no
  human review of submitted content — plus the EEA/Switzerland/UK carve-out that extends the paid
  terms to free quota. Quote the published wording verbatim; cite the source URL and the terms'
  effective date.
- Bump `GEMINI_DATA_TERMS_VERIFIED_AT` to the record's `checked` date in `.env.example` and
  `compose.yaml`, and update the literal in `tests/test_compose_local_generator.py` to match.
- New tests mirror the existing read-the-file style (`REPO_ROOT` from `Path(__file__)`, no network,
  no Docker).

**Ask First:**
- If today's published terms show a real change to guarantee (a) or (b) for the EEA free tier — record
  `outcome = "blocked"`, stop, and surface it. Do not write `"pass"` over a genuine regression.
- Changing the Generator provider or model, or touching `shell/adapters/gemini/generator.py` /
  `shell/config.py` logic — out of scope; this story records and guards, it does not re-architect.

**Never:**
- No runtime behaviour change: no new staleness banner, no startup check, no UI surface. `outcome`
  enforcement lives in the test suite, not the running app.
- Do not rewrite the ~20 unit-test fakes that hardcode `gemini_data_terms_verified_at="2026-01-15"` —
  those are fixtures, not records of fact; only the two example configs and their one assertion move.
- No new dependency (no `pyyaml`); `tomllib` only.
- Do not add `docs/` content beyond this one record file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Record present, terms unchanged | `docs/release-validation/gemini-data-terms.md` with valid toml block, `outcome = "pass"` | All guard tests pass | N/A |
| Record missing | file absent | `test_record_exists` fails naming the path | Loud failure |
| Toml block malformed / absent | no ` ```toml ` fence, or unparseable | extraction/`tomllib` raises → test fails | Loud failure |
| `checked` not an ISO date | `checked = "soon"` (string) | `test_checked_is_a_date` fails (`tomllib` yields non-`date`) | Assertion |
| Material change recorded | `outcome = "blocked"` | `test_outcome_permits_release` fails: "release blocked until data-terms change reassessed" | Assertion |
| Non-EU render region | record `hosting_region = "oregon"` or `render.yaml` drifts off `frankfurt` | `test_hosting_region_is_eu` / `test_region_matches_render_yaml` fails | Assertion |
| Example date drift | `.env.example` or `compose.yaml` `GEMINI_DATA_TERMS_VERIFIED_AT` ≠ record `checked` | `test_env_example_dates_match_record` fails naming the file | Assertion |

</frozen-after-approval>

## Code Map

- `docs/release-validation/gemini-data-terms.md` — **new.** The record. Fenced ` ```toml ` metadata
  block (keys per Boundaries) followed by prose sections: *What the design relies on* · *Published
  terms as read on {checked}* (verbatim quotes) · *Comparison* (table) · *Changes since the 2026-01-15
  planning reading* (with assessment) · *Hosting and storage location* · *Outcome* · *Next
  re-verification trigger*. Draft content is in Design Notes below — implementation transcribes it;
  Francesco ratifies the quotes and the outcome before merge.
- `tests/test_data_terms_record.py` — **new.** `REPO_ROOT = Path(__file__).resolve().parent.parent`.
  Helper extracts the ` ```toml `…` ``` ` block from the record and `tomllib.loads()` it (module-scope
  fixture). Tests: `test_record_exists`, `test_toml_block_parses`, `test_checked_is_a_date`
  (`isinstance(meta["checked"], datetime.date)`), `test_outcome_permits_release`
  (`meta["outcome"] == "pass"`), `test_hosting_region_is_eu` (`in _EU_RENDER_REGIONS = {"frankfurt"}`),
  `test_region_matches_render_yaml` (regex `^\s*region:\s*(\S+)` out of `render.yaml`, `== meta["hosting_region"]`),
  `test_env_example_dates_match_record` (pull `GEMINI_DATA_TERMS_VERIFIED_AT` value from `.env.example`
  and `compose.yaml`, each `== meta["checked"].isoformat()`).
- `.env.example:42` — `GEMINI_DATA_TERMS_VERIFIED_AT=2026-01-15` → `=2026-08-27`. Comment on L38–41
  already explains NFR-17; add "see `docs/release-validation/gemini-data-terms.md`".
- `compose.yaml:46` — `GEMINI_DATA_TERMS_VERIFIED_AT: "2026-01-15"` → `"2026-08-27"`.
- `tests/test_compose_local_generator.py:52` — assertion literal `"2026-01-15"` → `"2026-08-27"`.
- `render.yaml:18` — `region: frankfurt`. Read-only; the source of truth the record and test bind to.
- `README.md` — Deploy section (~L99–120, "region **Frankfurt**"). Add one line pointing operators to
  the record file and stating `GEMINI_DATA_TERMS_VERIFIED_AT` must be set to its `checked` date.
- `shell/config.py:280` `_read_gemini_data_terms_verified_at` — read-only context: validates the var
  is a non-blank ISO date, nothing more. `shell/adapters/gemini/generator.py:35` — the `_MODEL =
  "gemini-2.5-flash"` / "Free tier, EEA data terms" comment this record backs. Neither changes.
- Governing refs: PRD §6.2 (`prd.md:738–748`), NFR-17 (`epics.md:143`), AD-9 (`ARCHITECTURE-SPINE.md:175`).

## Tasks & Acceptance

**Execution:**
- [x] `docs/release-validation/gemini-data-terms.md` — create the record from the Design Notes draft:
      toml block with `checked = 2026-08-27`, `outcome = "pass"`, `hosting_region = "frankfurt"`,
      `storage_region = "Europe/Frankfurt"`, `terms_source`, `terms_effective = 2026-03-23`,
      `ratified_by = "Francesco"`; prose sections with verbatim quotes and the comparison table.
- [x] `tests/test_data_terms_record.py` — new guard suite covering every I/O & Edge-Case Matrix row
      (toml-block extraction helper + the seven tests named in the Code Map).
- [x] `.env.example` / `compose.yaml` — bump `GEMINI_DATA_TERMS_VERIFIED_AT` to `2026-08-27`; add the
      record-file pointer to the `.env.example` comment.
- [x] `tests/test_compose_local_generator.py` — update the asserted literal to `"2026-08-27"`.
- [x] `README.md` — one line under Deploy linking the record and the `GEMINI_DATA_TERMS_VERIFIED_AT`
      requirement.

**Acceptance Criteria:**
- Given the configured Generator provider, when release validation runs, then
  `docs/release-validation/gemini-data-terms.md` holds the current published data terms quoted with
  their source URL and effective date, compared clause-by-clause against the no-training /
  no-human-review guarantees the design relies on, with the check's date and `pass`/`blocked` outcome.
- Given terms that changed materially against guarantee (a) or (b), when the check is made, then the
  record carries `outcome = "blocked"` and `test_outcome_permits_release` fails — the suite does not
  go green, so release does not proceed until reassessed.
- Given hosting and storage, when verified, then the record's `hosting_region` / `storage_region` are
  EU (`frankfurt` / `Europe/Frankfurt`) and a test binds `hosting_region` to `render.yaml`'s `region:`.
- Given the recorded `checked` date, when the suite runs, then `.env.example` and `compose.yaml` both
  carry `GEMINI_DATA_TERMS_VERIFIED_AT=2026-08-27` and `test_env_example_dates_match_record` passes.
- Given the full suite, when `uv run pytest -q` and `uv run ruff check .` run, then both are clean.

## Design Notes

**Why a test that asserts `outcome == "pass"`.** The AC says a material change means "release does not
proceed until assessed". Nothing in the running app gates a release here, but the CI suite does:
recording `outcome = "blocked"` keeps `uv run pytest` red, which is the release gate for this repo
(story 1.2's "enforced by a test rather than by discipline"). After reassessment the value moves to
`pass` (change was benign) or the release is genuinely stopped.

**Why `tomllib` and a fenced block.** No YAML parser is a dependency; `tomllib` is stdlib on 3.13 and
a bare `checked = 2026-08-27` parses straight to `datetime.date`, so "is it a real date" needs no
extra validation.

**Drafted record content — verified against `https://ai.google.dev/gemini-api/terms` on 2026-08-27,
effective 2026-03-23 (Francesco to ratify the quotes and the outcome before merge):**

- *Design relies on* — EEA free-tier Gemini use is governed by Google's **Paid Services** data terms:
  no use of prompts/responses to train or improve Google products, and no human review of submitted
  content.
- *Published terms, quoted:*
  - Paid Services: "Google doesn't use your prompts (including associated system instructions, cached
    content, and files such as images, videos, or documents) or responses to improve our products."
  - Paid Services logging: "Google logs prompts and responses for a limited period of time, solely for
    detecting and preventing violations of the Prohibited Use Policy to maintain the safety and
    security of the Services."
  - Human review appears only under **Unpaid Services**: "human reviewers may read, annotate, and
    process your API input and output" — with no equivalent clause under Paid Services.
  - EEA carve-out: "If you're in the European Economic Area, Switzerland, or the United Kingdom, the
    terms under 'How Google uses Your Data' in 'Paid Services' apply to all Services, including Google
    AI Studio and unpaid quota in the Gemini API, even though they are offered free of charge."
- *Comparison:* (a) no training — **holds** (Paid Services wording, extended to free quota for the
  EEA). (b) no human review — **holds**: the human-review clause is Unpaid-Services-only and the EEA
  carve-out replaces Unpaid with Paid terms for all services.
- *Changes since the 2026-01-15 planning reading:* terms now stamped "Effective March 23, 2026"; a
  Paid-Services safety-logging clause (Prohibited-Use-Policy abuse detection, limited retention) is
  now explicit. **Assessed:** neither touches §6.2's question (training + human review); abuse-
  detection logging with limited retention is not model training and not human annotation. → not
  material; `outcome = "pass"`.
- *Hosting and storage:* Render web service `region: frankfurt` (`render.yaml:18`); Neon Postgres
  project `Europe/Frankfurt` (`README.md`, `render.yaml` header). Both EU/EEA. ✅
- *Next re-verification trigger:* any change of Generator provider or model (AD-9), or any change to
  the quoted clauses; re-run this check and update `checked` + the example dates.

## Verification

**Commands:**
- `uv run pytest tests/test_data_terms_record.py tests/test_compose_local_generator.py -q` — expected: all pass.
- `uv run pytest -q` — expected: full suite green.
- `uv run ruff check .` — expected: clean.

**Manual checks:**
- Francesco: open `https://ai.google.dev/gemini-api/terms`, confirm the three quoted clauses and the
  EEA carve-out read as transcribed and the effective date is current, then confirm `outcome = "pass"`
  in the record (or set `outcome = "blocked"` and re-open the story if a clause has regressed). The
  record's `ratified_by` / `ratified_on` assert ratification happened — correct them if it did not.

## Suggested Review Order

**The recorded check (the deliverable)**

- Entry point: the machine-readable block — 12 keys, each guarded by a test; `outcome = "pass"` is
  the release gate.
  [`gemini-data-terms.md:10`](../../docs/release-validation/gemini-data-terms.md#L10)

- The clause-by-clause verdict: both §6.2 guarantees still hold via the EEA Paid-Services carve-out.
  [`gemini-data-terms.md:68`](../../docs/release-validation/gemini-data-terms.md#L68)

- What changed since the 2026-01-15 reading (new effective date, safety-logging clause) and why it is
  not material.
  [`gemini-data-terms.md:97`](../../docs/release-validation/gemini-data-terms.md#L97)

- The canonical re-verification procedure — the complete list of places `GEMINI_DATA_TERMS_VERIFIED_AT`
  must be updated.
  [`gemini-data-terms.md:106`](../../docs/release-validation/gemini-data-terms.md#L106)

**The guard suite (enforcement)**

- The gate: a recorded material change sets `outcome = "blocked"`, which keeps this red and stops the
  release.
  [`test_data_terms_record.py:157`](../../tests/test_data_terms_record.py#L157)

- Binds the record's `model` to the configured Generator's `_MODEL`, so an AD-9 provider/model change
  can't slip past.
  [`test_data_terms_record.py:140`](../../tests/test_data_terms_record.py#L140)

- `checked` sanity: not in the future (epic-4 retro item 25), not before `terms_effective`.
  [`test_data_terms_record.py:107`](../../tests/test_data_terms_record.py#L107)

- Storage region bound to `Europe/Frankfurt` and to README's Deployment section — PRD §6.2's
  storage-in-EEA requirement.
  [`test_data_terms_record.py:171`](../../tests/test_data_terms_record.py#L171)

- Hosting region bound to `render.yaml`'s single `region:` line.
  [`test_data_terms_record.py:182`](../../tests/test_data_terms_record.py#L182)

- The env-file bind: `.env.example` and `compose.yaml` dates must equal the record's `checked`.
  [`test_data_terms_record.py:194`](../../tests/test_data_terms_record.py#L194)

**Config & docs alignment (peripheral)**

- Compose test now asserts key + ISO-date shape, not a hardcoded literal — removes a third hand-edit
  point.
  [`test_compose_local_generator.py:54`](../../tests/test_compose_local_generator.py#L54)

- `GEMINI_DATA_TERMS_VERIFIED_AT` bumped to the check date.
  [`.env.example:45`](../../.env.example#L45)
  [`compose.yaml:46`](../../compose.yaml#L46)

- README reduced to a pointer at the record; the record owns the procedure.
  [`README.md:104`](../../README.md#L104)
