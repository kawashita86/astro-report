---
title: 'Story 7.3 — See how much Corpus I actually have'
type: 'feature'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '17e9bbe1b8bd553f5c0361dd1d317daa8c5717e1'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 7.1 and 7.2 let Francesco add past reports and mark each paired or unpaired, but nothing shows the composition — how many entries exist and how they split. That count (FR-24) decides whether phase-2 voice conditioning is worth planning, and today the only way to get it is a manual SQL query.

**Approach:** Render the composition — total, paired, unpaired — as a summary line at the top of the existing `GET /corpus` page, computed in the route from the entry list that page already loads. A live read: no extra query, no new route, no batch job.

## Boundaries & Constraints

**Always:**
- `corpus_list` (`shell/http/routes/corpus.py`) computes, from the `stored_entries` list it already fetches: `total = len(stored_entries)`, `paired_count = sum(1 for e in stored_entries if e.paired)`, `unpaired_count = total - paired_count`. All three are added to the `corpus_list.html` context.
- An entry is counted by its stored `paired` boolean alone — a paired entry with `client_id` and `month` both `NULL` still counts as paired (Story 7.2: pairing is Francesco's assertion, independent of whether the app holds the Client).
- `corpus_list.html` renders one line near the top of `<main>`, above the `{% if entries %}` block so it shows for an empty corpus too. Exact copy: `Corpus composition: {{ total }} total · {{ paired_count }} paired · {{ unpaired_count }} unpaired`. No pluralisation logic.
- Everything else about `GET /corpus` is unchanged: most-recent-first ordering, per-entry paired/unpaired rendering with Client name and month, empty-state text and `/corpus/new` link, the single `IN` query for linked Clients, authenticated-by-default.
- `tests/test_http_corpus.py`'s `_seed_entry` helper gains keyword-only `paired: bool = False` passed to the `CorpusEntry(...)` constructor; existing call sites keep the default.

**Ask First:**
- A dedicated `GET /corpus/composition` page or a store-layer `corpus_composition(session)` reader — this story deliberately computes inline on the list page.
- Splitting `paired_count` further (linked vs unlinked). The output is three numbers: total / paired / unpaired.

**Never:**
- No new route, template, or adapter function; no `select(func.count())` — the counts are derived in Python from a list the page already holds.
- No change to `list_corpus_entries`, `add_corpus_entry`, the `CorpusEntry` schema, or any migration.
- No `core/` changes; nothing durable on the container filesystem.
- No phase-2 exemplar selection, retrieval, or anonymization machinery.
- No entry content or client identifiers in logs or telemetry.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior |
|----------|--------------|---------------------------|
| Empty corpus | no rows | `GET /corpus` `200`; line reads `0 total · 0 paired · 0 unpaired`; empty-state text and `/corpus/new` link still shown |
| Mixed corpus | 2 paired, 3 unpaired rows | line reads `5 total · 2 paired · 3 unpaired`; all 5 entries still listed most-recent-first |
| All unpaired | 4 unpaired rows | line reads `4 total · 0 paired · 4 unpaired` |
| Paired without a link | 1 paired row, `client_id` and `month` both `NULL` | counted as paired: `1 total · 1 paired · 0 unpaired` |
| Line precedes the list | any populated corpus | the composition line appears before the first entry in the rendered HTML |
| Unauthenticated | request without a valid session | rejected before the handler runs (unchanged): `401`, empty body |

</frozen-after-approval>

## Code Map

- `shell/http/routes/corpus.py:120` -- `corpus_list`: `stored_entries` fetched at line 130; compute the three counts after it and add them to the `TemplateResponse` context at lines 146-148. No other route touched.
- `shell/http/templates/corpus_list.html:11` -- `<main>` opens; `<h1>` + `/corpus/new` link are lines 11-12, `{% if entries %}` starts line 14. Insert the composition `<p>` between line 12 and line 14 so it renders on both branches. Per-entry rendering (lines 19-25) unchanged.
- `shell/adapters/postgres/corpus_entry.py:70` -- `CorpusEntry.paired` (stored boolean); `list_corpus_entries` at line 113. Read-only evidence: the count reads `entry.paired` off rows already loaded there.
- `tests/test_http_corpus.py:69` -- `_seed_entry`: add keyword-only `paired`. Line 167 `test_empty_corpus_shows_empty_state...` is the empty-corpus assertion pattern; line 150 `test_list_renders_entries_most_recent_first` is the multi-row `response.text` pattern. Reuse the `authenticated_client` / `db_session` fixtures.
- `_bmad-output/implementation-artifacts/epic-7-context.md` -- FR-24: "total / paired / unpaired at a glance … a live read, not a generated report".

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/corpus.py` -- in `corpus_list`, after `stored_entries`, compute `total` / `paired_count` / `unpaired_count` and pass them to the template context; note the line in the docstring.
- [x] `shell/http/templates/corpus_list.html` -- add the composition `<p>` between the `/corpus/new` link and the `{% if entries %}` block, exact copy per Boundaries, always rendered.
- [x] `tests/test_http_corpus.py` -- add `paired: bool = False` to `_seed_entry`; add one test per I/O & Edge-Case Matrix row.

**Acceptance Criteria:**
- Given a corpus of N entries of which P are `paired`, when `GET /corpus` is requested, then the body contains `N total · P paired · {N-P} unpaired` and still lists every entry most-recent-first.
- Given the corpus changes between two `GET /corpus` requests, when the second is made, then the line reflects the new state — recomputed per request, not cached.
- Given `uv run pytest -q`, `uv run ruff check .`, and `uv run mypy .`, when run, then all pass with no stale count or shape assertion.

## Design Notes

Counts are derived from `stored_entries` rather than via `select(func.count())` or a new reader because `GET /corpus` already loads every row to render the list — three integers off that list add zero queries and no new module surface. `unpaired_count` is `total - paired_count`, not a second comprehension: the categories are exhaustive and mutually exclusive (`paired` is `NOT NULL`), so subtraction cannot drift from a filtered recount. The line sits outside the `{% if entries %}` split so an empty corpus shows an explicit `0 total · 0 paired · 0 unpaired` rather than the count vanishing.

## Verification

**Commands:**
- `uv run pytest tests/test_http_corpus.py -q` -- expected: all pass, including the new composition rows.
- `uv run pytest -q` -- expected: full suite green.
- `uv run ruff check . && uv run mypy .` -- expected: clean.

## Suggested Review Order

**Composition counts (entry point)**

- The whole feature: three ints derived from the list `GET /corpus` already loads — zero extra queries, no new route.
  [`corpus.py:136`](../../shell/http/routes/corpus.py#L136)
- `unpaired_count` is `total - paired_count`, not a second scan: `paired` is `NOT NULL`, so the two categories cannot drift.
  [`corpus.py:138`](../../shell/http/routes/corpus.py#L138)
- The three counts join the template context beside the existing `entries` value — the only other change to the return.
  [`corpus.py:159`](../../shell/http/routes/corpus.py#L159)
- Docstring records why the counts live in the route, not a `func.count()` reader or a new page.
  [`corpus.py:131`](../../shell/http/routes/corpus.py#L131)

**Template binding**

- One line, placed above the `{% if entries %}` split so an empty corpus still shows an explicit `0 total · 0 paired · 0 unpaired`.
  [`corpus_list.html:13`](../../shell/http/templates/corpus_list.html#L13)

**Tests**

- `_seed_entry` gains a `paired` keyword so composition rows can be seeded; existing call sites unchanged.
  [`test_http_corpus.py:69`](../../tests/test_http_corpus.py#L69)
- Empty corpus: all-zero line and the empty-state text coexist.
  [`test_http_corpus.py:481`](../../tests/test_http_corpus.py#L481)
- Mixed 2 paired / 3 unpaired: the counts, and every entry still listed.
  [`test_http_corpus.py:492`](../../tests/test_http_corpus.py#L492)
- Paired with `client_id`/`month` both `NULL` still counts as paired.
  [`test_http_corpus.py:531`](../../tests/test_http_corpus.py#L531)
- End-to-end: two `POST /corpus` submissions, then the literal line asserted contiguously in the `GET`.
  [`test_http_corpus.py:575`](../../tests/test_http_corpus.py#L575)
