---
title: 'Story 4.7 — Write this month as a continuation, not a reprint'
type: 'feature'
created: '2026-08-21'
status: 'done'
review_loop_iteration: 1
baseline_commit: '9335d9e891f13e9b98eb91afebb447797d01e7e9'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `_run_draft_ready` (Story 4.6) calls the Generator with `theme_previous=None` unconditionally — even a returning Client's Report is generated as if it were their first, so nothing prevents the model from reintroducing an already-covered transit or manufacturing "what's new" when nothing significant changed. `core/memory/diff.py::diff_themes()` (Story 4.4) already computes exactly that classification but is called from nowhere.

**Approach:** Fetch a Client's most recent prior month's `ReportTheme` (if any) and thread it into `_run_draft_ready` as `theme_previous`; have the Gemini adapter call `diff_themes(theme_previous, theme_current)` itself and embed the computed classification in the prompt — a computed continuity fact the model is told, never one it has to infer from two raw Theme dumps.

## Boundaries & Constraints

**Always:**
- A new `shell/adapters/postgres/report_theme.py` query returns the most recent `StoredReportTheme` for a Client whose `ReportRun.month` is strictly less than the current run's month (string comparison on `"YYYY-MM"`, correct because the format is always zero-padded) — "most recent", not "the immediately preceding calendar month": a skipped month must not reset a genuinely still-active slow transit back to "first Report" behavior. `None` when no such row exists (the Client's first Report, or no prior run ever reached `payload_ready`).
- `_run_draft_ready` reads this back and deserializes it via the existing `_deserialize_theme`, then passes it as `theme_previous` — never recomputed, mirroring every other stage's "read back" pattern.
- `GeminiGenerator.generate()` calls `diff_themes(theme_previous, theme_current)` itself and embeds the resulting `ThemeDiff` (or, when `theme_previous is None`, an explicit "first Report" statement) in the prompt. The existing raw `theme_previous`/`theme_current` JSON dump is removed — `ThemeDiff` carries no citation ids (`ReportTheme` never did either) and the diff *is* the continuity signal; keeping both would just be redundant prompt tokens.
- The Generator port's four-argument signature (`payload, style_guide, theme_previous, theme_current`) does not change — `diff_themes` is called inside the adapter, not added as a fifth port argument.
- When `nothing_significant_changed` is `True`, the prompt explicitly instructs the model to say so plainly rather than manufacture novelty.

**Ask First:** none identified — the "most recent prior month, not necessarily calendar-adjacent" reading is the only one a genuinely still-active slow transit's continuity can rest on without falsely resetting after a skipped month; documented, not gated.

**Never:** No change to citation or date-token validation. No new Generator port argument. No calendar-adjacency requirement on `theme_previous` (a skipped month does not force `None`). Prior Report *prose* is still never an input, by any path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Returning Client, immediately-preceding month exists | `ReportRun` for month M-1 reached `payload_ready` | Its `ReportTheme` is fetched as `theme_previous` | N/A |
| Returning Client, a month was skipped | Most recent prior run is M-2, not M-1 | M-2's `ReportTheme` is still fetched as `theme_previous` (not `None`) | N/A |
| Client's first Report | No prior `ReportRun` for this Client reached `payload_ready` | `theme_previous=None`; prompt states this is the first Report, no prior-month reference | N/A |
| Nothing significant changed | `diff_themes(...).nothing_significant_changed is True` | Prompt explicitly instructs stating this plainly | N/A |
| A transit still active from last month | Matched `AspectChange` with `status="still_active"`/`"tightened"`/`"resolved"` | Prompt states it as continuing (moved/tightened/resolved), never reintroduced fresh | N/A |
| Multiple prior `ReportRun`s exist, out of creation order | Runs for months "2026-01" and "2026-03" both persisted before "2026-02" is requested | The query orders by `ReportRun.month`, not by row-creation order, so "2026-01" is correctly chosen as prior to "2026-02" | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/report_theme.py` -- `StoredReportTheme`, `store_report_theme()`: add `most_recent_prior_report_theme(session, client_id, *, before_month) -> StoredReportTheme | None`, joining `ReportRun` to filter/order by `.month`.
- `shell/runner/driver.py:357-411` -- `_deserialize_theme`, `_run_draft_ready` (the `None` currently hardcoded at the `generator.generate(...)` call is what this story replaces): fetch the prior row, deserialize it, pass it through.
- `core/memory/diff.py:122` -- `diff_themes(previous, current) -> ThemeDiff | None` (Story 4.4) -- called from the adapter for the first time.
- `core/types/memory.py:88-135` -- `AspectChange`/`RetrogradeChange`/`ThemeDiff` field shapes to render into the prompt.
- `shell/adapters/gemini/generator.py:208-238` -- `_build_prompt` (the raw `theme_previous`/`theme_current` JSON embed this story replaces with a rendered `ThemeDiff` summary); `_json_safe` in the same file becomes unused once the raw Theme dump is removed and should be deleted, not left dead.
- `core/memory/derive.py:70-77` -- `derive_theme()`'s own docstring: "No top-N truncation: every deduplicated slow Aspect... is kept, in full." This is why a `dominant_aspects` element entirely absent from `theme_current` (a `diff_themes()`-unmatched "resolved" `AspectChange`) is *not* merely filtered out of a larger list -- it genuinely does not appear anywhere in this month's Payload either, since `ReportTheme` is a complete, untruncated reduction of it (review loop 1 finding).
- `tests/test_runner_driver.py:657` -- the existing "calls Generator with `theme_previous=None` unconditionally" test (Story 4.6) -- update to reflect conditional fetching.
- `tests/test_gemini_generator.py` -- `test_first_report_omits_prior_month_material_and_still_returns_a_draft` (asserts on the raw JSON dump this story removes) -- update to assert against the new rendering instead.
- `tests/test_diff_themes.py` -- fixture conventions for constructing `ReportTheme`/`AspectChange`/`RetrogradeChange` test data to mirror.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/report_theme.py` -- add `most_recent_prior_report_theme()`.
- [x] `shell/runner/driver.py` -- `_run_draft_ready`: call the new query with `run.client_id`/`before_month=run.month`, deserialize via `_deserialize_theme` if found, pass as `theme_previous` instead of the hardcoded `None`.
- [x] `shell/adapters/gemini/generator.py` -- `generate()`/`_build_prompt`: call `diff_themes(theme_previous, theme_current)`; add a rendering function turning the `ThemeDiff` (or `None`) into the prompt's continuity section, replacing the raw JSON theme dump; remove the now-unused `_json_safe`.
- [x] `tests/test_report_theme_store.py` -- new: `most_recent_prior_report_theme()` covering the I/O & Edge-Case Matrix's month-ordering rows (immediately-preceding, skipped-month, first-Report, out-of-order creation), plus a year-boundary case (e.g. `before_month="2026-01"` against a prior run at `"2025-12"`) proving the zero-padded string comparison holds across a year rollover.
- [x] `tests/test_runner_driver.py` -- update `_run_draft_ready`'s test(s) for conditional `theme_previous` (both the found-row and no-prior-row cases).
- [x] `tests/test_gemini_generator.py` -- update/extend for the new prompt rendering: still-active/tightened/resolved(-still-present-in-current)/new phrasing, the resolved-and-entirely-absent-from-current case (Boundaries), a case combining more than one simultaneous continuity signal in one call (e.g. a tightened Aspect and a resolved-but-still-present Retrograde together), the `nothing_significant_changed` instruction (present and absent, including the all-`"new"` case below), and the first-Report case.

**Acceptance Criteria:**
- Given a Client with at least one prior month, when generation runs, then both ReportThemes are supplied to the Generator and a transit still active from the prior month is treated as continuing, never reintroduced fresh.
- Given a computed diff stating nothing significant has changed, when generation runs, then the prompt instructs the model to say so plainly rather than manufacture novelty.
- Given a Client's first Report, when generation runs, then it runs with `theme_previous=None` and the prompt makes no reference to prior months.
- Given continuity, when it is supplied, then it travels only as `ReportTheme`/`ThemeDiff` — no prior Report's prose reaches the Generator by any path.

## Spec Change Log

- **Finding (review loop 1, bad_spec):** a `"resolved"` `AspectChange`/`RetrogradeChange` whose identity is entirely absent from `theme_current` (`diff_themes`'s unmatched-in-`previous`-only branch) carries an Aspect/Retrograde that — per `derive_theme()`'s own "no top-N truncation" contract — genuinely does not appear anywhere in this month's Payload either. The original Design Notes/Tasks said to render every `"resolved"` element with the same phrasing regardless, which would instruct the model to describe a closed-vocabulary fact it cannot cite: either the model fabricates an `entry_id` (caught only at `_validate_citations`, an avoidable generation failure) or writes it uncited, which is a Groundedness Gate violation later (AD-6: "a sentence containing a closed-vocabulary token with an empty citation list is a Gate violation") — the exact class of ungrounded-fact failure this whole epic exists to prevent, just deferred to Epic 5 instead of caught here.
  **Amended:** added a Boundaries-adjacent Code Map note tying this to `derive_theme()`'s contract, and a Design Note (below) requiring the resolved-and-absent-from-current case to explicitly instruct the model to mention it, if at all, without citing an `entry_id` — never inviting a citation the Payload cannot support. Folded in the reviewer's other cheap, clearly-valid coverage gaps (a combined-signals test, a year-boundary test) into Tasks at the same time, since re-derivation touches these test files regardless.
  **Known-bad state avoided:** a continuity instruction that reads as fully safe (mirroring the "still-active"/"tightened" cases, which are always grounded) but silently sets up either a wasted generation retry or a downstream Gate failure for a case this story's own Boundaries already claimed to handle ("a transit... treated as continuing... resolved").
  **KEEP:** the query design (`most_recent_prior_report_theme`, ordered by `ReportRun.month` not creation order, "most recent" not "calendar-adjacent"), calling `diff_themes` inside the adapter rather than the driver, removing the raw JSON Theme dump, the `"new"`-gets-no-continuity-phrasing rule, and the `nothing_significant_changed` instruction all held up under review and must survive re-derivation unchanged.

- **Finding (review loop 1, bad_spec):** when every `AspectChange`/`RetrogradeChange` this month has status `"new"`, the continuity header ("Continuità rispetto al mese precedente...") was specified with no fallback for zero rendered lines beneath it — `"new"` entries are deliberately never mentioned (Design Notes), and `nothing_significant_changed` is `False` whenever any `"new"` entry exists, so the model would receive a dangling header instructing nothing.
  **Amended:** added a Design Note (below) requiring the header to be omitted entirely (not replaced with a "nothing changed" line, which would be false) when there is nothing to render beneath it and `nothing_significant_changed` is `False`.
  **Known-bad state avoided:** a prompt fragment that announces "here's what changed" and then says nothing, which is confusing filler rather than the "computed fact, stated plainly" this epic's prompts otherwise strive for.
  **KEEP:** everything else about `_render_continuity`'s shape (per-status phrasing tables, one line per changed element, the explicit `nothing_significant_changed` instruction) is unchanged and confirmed working.

## Design Notes

- **Why "most recent prior month" rather than "the immediately preceding calendar month":** `diff_themes`'s own classification (`still_active`/`tightened`/`resolved`) is driven purely by each `ThemeAspect`'s `orb_entry_at`/`orb_exit_at`/`never_perfected` — astronomical continuity, not calendar adjacency. A slow transit genuinely can still be active two months later; resetting to "first Report" behavior just because Francesco skipped a month would misreport it as brand new, which is exactly the "computed fact, not a guess" premise (AD-14) this epic exists to protect. Documented as a Design Note rather than gated at Ask First because no other reading survives that reasoning.
- **Why `diff_themes` is called inside the adapter, not the driver:** the diff is *how this one adapter chooses to prompt the model* — a different future Generator adapter might render continuity differently, or not need a diff at all. The port's four-argument signature stays exactly `(payload, style_guide, theme_previous, theme_current)`; nothing about the diff crosses the port boundary itself.
- **Why the raw `theme_previous`/`theme_current` JSON dump is removed, not kept alongside the diff:** `ReportTheme` (and by extension `ThemeDiff`) never carried a Payload entry id — it was never a citation source, only a continuity summary. Once the diff itself is embedded, the raw dump is pure duplication of the same underlying facts (which also already exist, with entry ids, in `payload` itself) — removing it directly serves this story's own I/O Matrix and keeps the prompt from growing for no reason.
- **Resolved-and-entirely-absent-from-current (review loop 1):** when a `"resolved"` `AspectChange`/`RetrogradeChange`'s element is not present in `theme_current` at all (as opposed to present with `orb_exit_at` newly set — that case *is* grounded, since the element is still in this month's Payload), its rendered line must explicitly instruct the model to mention it, if relevant, without citing an `entry_id` for that specific claim — e.g. append "(non presente nel Payload di questo mese: se lo menzioni, non citare un id per questa affermazione)" to that line only. This keeps the epic's continuity requirement intact for this case while never inviting a citation the Payload cannot support.
- **Dangling header (review loop 1):** `_render_continuity` must omit the "Continuità rispetto al mese precedente" header entirely when there are zero rendered Aspect/Retrograde lines *and* `nothing_significant_changed` is `False` (every element this month is `"new"`) — nothing follows the header in that case, and there is nothing true to say instead (unlike the `nothing_significant_changed=True` case, which does have something true to say). The function's three possible outputs are: the first-Report statement, the header plus at least one line, or an empty/absent continuity section.

## Verification

**Commands:**
- `uv run pytest tests/test_report_theme_store.py tests/test_runner_driver.py tests/test_gemini_generator.py -q` -- expected: all pass.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**The query: fetching the prior month's continuity input**

- Entry point: "most recent", not "calendar-adjacent" -- ordered by `ReportRun.month`, never row-creation order.
  [`report_theme.py:102`](../../shell/adapters/postgres/report_theme.py#L102)

- `_run_draft_ready` threading the query's result into the Generator call, replacing the old hardcoded `None`.
  [`driver.py:403`](../../shell/runner/driver.py#L403)

**Computing continuity: `diff_themes` called inside the adapter (AD-3 stays intact)**

- `generate()` computes the diff itself -- the port's four-argument signature never grows a fifth.
  [`generator.py:146`](../../shell/adapters/gemini/generator.py#L146)

- `_render_continuity` -- the three-shape contract: first-Report statement, header+lines, or nothing.
  [`generator.py:263`](../../shell/adapters/gemini/generator.py#L263)

**Review loop 1's fix: never invite an uncitable claim**

- `_render_aspect_change` -- the caveat only appends when the element is entirely absent from `theme_current`.
  [`generator.py:235`](../../shell/adapters/gemini/generator.py#L235)

- `_render_retrograde_change` -- same check; a resolved Retrograde is *always* absent from current by construction.
  [`generator.py:251`](../../shell/adapters/gemini/generator.py#L251)

- The caveat text itself, and why `derive_theme()`'s "no top-N truncation" contract makes it necessary.
  [`generator.py:213`](../../shell/adapters/gemini/generator.py#L213)

**Tests: the two review-loop findings, by name**

- The resolved-and-absent case actually gets the no-citation instruction.
  [`test_gemini_generator.py:325`](../../tests/test_gemini_generator.py#L325)

- All-`"new"` elements omit the header entirely, rather than leaving it dangling.
  [`test_gemini_generator.py:396`](../../tests/test_gemini_generator.py#L396)

- More than one continuity signal in a single call renders correctly together.
  [`test_gemini_generator.py:343`](../../tests/test_gemini_generator.py#L343)

- Cross-Client isolation: another Client's prior theme is never returned.
  [`test_report_theme_store.py:313`](../../tests/test_report_theme_store.py#L313)
