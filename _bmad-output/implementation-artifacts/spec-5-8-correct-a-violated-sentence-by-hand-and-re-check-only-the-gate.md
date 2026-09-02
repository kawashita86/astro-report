---
title: 'Story 5.8 — Correct a violated sentence by hand, and re-check only the Gate'
type: 'feature'
created: '2026-09-02'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'b490161e416adcdfdc99dd473536d6e66823b681'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When the Gate flags one sentence as ungrounded, Francesco's only recovery today is
Rigenera (Story 5.4, full regeneration) or Accetta (Story 5.7, accept the exception). Neither fits
a pure wording problem: Rigenera spends another paid Generator call and puts all eight Sections at
risk of coming from a different draft; Accetta leaves a permanent exception badge on a Report that
could otherwise pass cleanly.

**Approach:** Add a per-violation "Modifica e ricontrolla" action on the existing Gate-failure
panel: an inline `<details>` disclosure (no JS) revealing a textarea prefilled with the flagged
sentence. Submitting it replaces only that one sentence in the latest persisted draft, persists the
result as a new immutable `ReportDraft`, and re-runs the pure `run_gate()` — never a model call —
against the same stored Payload. A genuine pass writes a normal `Report` row; remaining violations
carry forward any Story 5.7 acceptances that are byte-for-byte unchanged by the edit.

## Boundaries & Constraints

**Always:**
- Only the one named sentence changes; every other sentence (including the corrected sentence's
  own citations) carries over unchanged from the draft that failed.
- The recheck calls the exact same pure `core/gate/run.py::run_gate()` Story 5.2/5.4 already use —
  no model call, no new Gate logic.
- This correction never reads or writes `run.regeneration_count` and is never bounded by
  `_MAX_REGENERATIONS` — mirrors Story 5.7's Boundaries for the accept path.
- The new `ReportDraft`/`StoredGateResult` pair is persisted append-only, exactly as an automatic
  regeneration's pair is — never updated, never replacing the prior attempt.
- A Story 5.7 acceptance on a violation that is byte-for-byte identical (kind, section, sentence,
  entry_ids, detail) in the new result carries forward automatically as a new
  `GateViolationReview` row against the new `StoredGateResult` — Francesco is never asked to
  re-accept it.
- If carrying forward acceptances makes every violation on the new failing result accepted, the run
  closes immediately via the same accepted-exceptions `Report` write Story 5.7's route already
  performs — no separate interaction to trigger it.
- `ReportDraft.attempt` numbering must be a source both this route and `_run_draft_ready` agree on
  (a count of existing `ReportDraft` rows for the run), not `run.regeneration_count` — the latter no
  longer uniquely identifies the next attempt once this route can mint a row without incrementing
  it.
- `_current_cycle_gate_failure` must order candidate `StoredGateResult` rows by `created_at`
  descending, not `regeneration_count` descending — two failing rows can now share one
  `regeneration_count`.

**Ask First:** none identified — the approach is fully determined by epics.md's ACs and the
2026-09-02 correct-course amendment.

**Never:**
- No inline JS for the expand/submit interaction — a native `<details>`/`<summary>` disclosure plus
  a plain form submit, mirroring `report_payload.html`'s existing `<details class="payload-section">`
  use.
- Never let `violation_index` resolve against any `StoredGateResult` other than the run's current
  failing one (same guard `accept_gate_violation` already uses).
- Never fabricate a passing Gate result — a genuine pass is only ever `run_gate()` returning
  `passed=True` on the corrected draft.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Correct fixes it | 1 violation, Francesco edits the sentence, resubmits | New `ReportDraft` (`attempt` = prior count) + `StoredGateResult(passed=True)`; `Report` row written normally (no exception flag); run reaches `gate_passed`; redirect to poll page | N/A |
| Correct still fails, nothing carried | 2 violations, none accepted, edit fixes one but not the other | New draft/result persisted; redirect to draft page shows 1 open card (index re-numbered) | N/A |
| Correct still fails, acceptance carries forward | Violation B already accepted (5.7); edit targets violation A only, B unchanged | New result still has B; a new `GateViolationReview` row is written for B against the new result automatically; draft view shows B as a resolved "Accettata" strip | N/A |
| Carry-forward closes the run | Violations A and B both accepted before this edit; edit targets a third, C, which the recheck now fixes | New result has only A/B, both carried forward; every violation now accepted → `Report` written with `accepted_violation_count=2`; run reaches `gate_passed` | N/A |
| Wrong/out-of-range index, or no current failure | Same guard as `accept_gate_violation` | 404 | N/A |
| Concurrent correct + regenerate on the same run | Two requests both compute the same next `attempt` | Loser's `ReportDraft` insert raises `IntegrityError` (unique on `(report_run_id, attempt)`) | Roll back, redirect to draft page with a "try again" flash — never a raw 500 |
| Concurrent closing correct (two near-simultaneous full-carry-forward closes) | Both compute the closing `Report` write | Loser's insert raises `IntegrityError` (`Report.report_run_id` unique) | Roll back, same redirect the winner gets |

</frozen-after-approval>

## Code Map

- `core/types/gate.py:52-71` (`GateViolation`) -- add `sentence_index: int = 0` (defaulted so every
  existing keyword-arg construction in tests stays valid): the within-section tuple position of the
  flagged `Sentence`, needed to locate the exact sentence to replace in the draft when two sentences
  share identical text.
- `core/gate/run.py:394-522` (`_check_claim`, `_check_date_token`, `_category_violation`,
  `run_gate`) -- thread a `sentence_index` parameter through each `GateViolation(...)` construction;
  `run_gate`'s per-section loop switches from `for sentence in sentences` to
  `for sentence_index, sentence in enumerate(sentences)`. Pure, no behavior change to `passed`/
  ordering.
- `shell/adapters/postgres/report_draft.py` (new) -- `next_report_draft_attempt(session, run_id) ->
  int`: `select(func.count()).select_from(ReportDraft).where(report_run_id == run_id)`. Used by both
  `_run_draft_ready` (replacing `attempt=run.regeneration_count`) and the new route below —
  behavior-preserving for the automatic path (count and `regeneration_count` coincide there today)
  and correct once this route can add a row the counter never sees.
- `shell/runner/driver.py:559` (`_run_draft_ready`) -- `attempt=next_report_draft_attempt(session,
  run.id)` instead of `attempt=run.regeneration_count`.
- `shell/adapters/postgres/report_run.py:108-114` (`regeneration_count` comment) -- update: the
  "N+1 total `ReportDraft.attempt` values" invariant no longer holds once a hand-correction can add
  a row without incrementing this counter.
- `shell/http/routes/report_runs.py:135-171` (`_current_cycle_gate_failure`) -- change
  `.order_by(StoredGateResult.regeneration_count.desc())` to
  `.order_by(StoredGateResult.created_at.desc())`; update the docstring's "latest failing row by
  `regeneration_count` descending" line to match. The `_GATE_RESULT_CORRELATION_WINDOW` guard is
  unaffected.
- `shell/http/routes/report_runs.py:431-605` (`accept_gate_violation`) -- extract the shared
  "every violation on `stored_gate_result` now has a review row -> write closing `Report`, advance
  `run.stage`, handle concurrent-closer `IntegrityError`" block (lines ~556-596) into a private
  helper, e.g. `_close_run_via_accepted_violations(session, run, stored_gate_result, violations) ->
  bool`, reused by the new route below.
- `shell/http/routes/report_runs.py` (new, near `accept_gate_violation`) --
  `POST /report-runs/{run_id}/violations/{violation_index}/correct`, `sentence_text: str = Form(...)`:
  same 404 guards as `accept_gate_violation` (current-cycle failure exists, index in range). Reads
  `section`/`sentence_index` off `violations[violation_index]`, the latest `ReportDraft` (via
  `deserialize_generated_draft`, `shell/http/draft_view.py:97`) and `ReportPayload` for `run.id`
  (same reads `accept_gate_violation` already does). Builds the corrected `GeneratedDraft` with
  `dataclasses.replace` on the one section's sentence tuple (new `Sentence(text=sentence_text,
  entry_ids=<unchanged>)` at `sentence_index`; `IndexError` on a stale index -> 404). Persists via
  `store_report_draft(..., attempt=next_report_draft_attempt(...))`, catching `IntegrityError` ->
  rollback + "try again" redirect. Calls `run_gate(corrected_draft, stored_payload.payload,
  request.app.state.gate_vocabulary)` and `store_gate_result(..., regeneration_count=
  run.regeneration_count, ...)`. Reads existing `GateViolationReview` rows for the *old*
  `stored_gate_result.id`, matches each new violation by `(kind, section, sentence, entry_ids,
  detail)`, and calls `store_gate_violation_review(...)` against the new result for each match. On
  `result.passed`: `store_report(...)` (no `accepted_violation_count`/`closing_gate_result_id` —
  genuine pass), clear `failed_at`/`failure_reason`, `run.stage="gate_passed"`, redirect `303` to
  `/report-runs/{run_id}`. Else, try `_close_run_via_accepted_violations(...)`; if it closed,
  same redirect; if not, redirect `303` to `/report-runs/{run_id}/draft`.
- `shell/http/routes/report_runs.py:738-747` (`view_report_draft`'s violations context) -- unaffected
  in shape (still built from the current-cycle result, now correctly the newest by `created_at`).
- `shell/http/templates/report_draft.html:20-34` (open violation card) -- add, after the existing
  Accetta form, a `<details><summary>Modifica e ricontrolla</summary>` containing a
  `<form method="post" action=".../correct">` with a `<textarea name="sentence_text">{{ v.sentence
  }}</textarea>` and a submit button "Ricontrolla" (`</details>`'s native toggle serves as
  "Annulla" — no separate control, no JS).
- `shell/http/templates/report_draft.html:12-18` (resolved-strip loop) -- a strip whose review row
  came from this route's genuine pass is never rendered here (a genuine pass produces a normal
  `Report`, no `run.failed_at`, so `view_report_draft`'s `{% if violations %}` branch never
  renders); no template change needed for a "Corretta" tag on this page. Carried-forward accepted
  violations still render exactly like any Accettata strip (existing `status-badge--warning`).
- `tests/test_gate_run.py` -- extend: `sentence_index` is correct per-section (0-based, resets each
  section), unaffected by unrelated categories on the same sentence producing multiple violations.
- `tests/test_report_draft_store.py` -- new: `next_report_draft_attempt()` returns `0` for a run
  with no drafts, `N` after `N` stored, unaffected by which code path wrote them.
- `tests/test_http_report_runs.py` -- extend: correct-route happy path (genuine pass), still-fails
  case, carry-forward-of-existing-acceptance case, carry-forward-closes-the-run case, stale/
  out-of-range index 404, concurrent-mint `IntegrityError` handling.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/gate.py` -- add `GateViolation.sentence_index` (defaulted).
- [x] `core/gate/run.py` -- thread `sentence_index` through every `GateViolation` construction.
- [x] `shell/adapters/postgres/report_draft.py` -- `next_report_draft_attempt()`.
- [x] `shell/runner/driver.py` -- `_run_draft_ready` uses `next_report_draft_attempt()`.
- [x] `shell/adapters/postgres/report_run.py` -- update the stale `regeneration_count` comment.
- [x] `shell/http/routes/report_runs.py` -- `_current_cycle_gate_failure` orders by `created_at`;
  extract `_close_run_via_accepted_violations`; add the `.../correct` route.
- [x] `shell/http/templates/report_draft.html` -- `<details>` Modifica e ricontrolla form.
- [x] Tests listed in Code Map.

**Acceptance Criteria:**
- Given a violation card naming one sentence, when Francesco edits it and resubmits, then only that
  sentence changes — every other sentence and that sentence's own citations carry over unchanged.
- Given the resubmit, when it runs, then the Groundedness Gate runs again — pure, no model call —
  against the same stored Payload, and a new immutable `ReportDraft`/`StoredGateResult` pair is
  persisted without touching or being bounded by `regeneration_count`.
- Given the recheck comes back with zero violations, when evaluated, then a `Report` row is written
  exactly as a normal Gate pass would be — no accepted-exception flag.
- Given the recheck still finds violations some of which were already accepted and are
  byte-for-byte unchanged, when evaluated, then those acceptances carry forward automatically.
- Given violations remain after carrying acceptances forward, when the draft view re-renders, then
  it shows exactly the remaining, unresolved cards, each still offering Accetta and Modifica e
  ricontrolla.

## Spec Change Log

## Design Notes

Why `sentence_index` defaults to `0` rather than being required: `StoredGateResult.violations` rows
written before this change have no such key in their stored JSON. A default keeps every existing
`GateViolation(...)` test construction and every historical stored row valid without a migration or
a backfill — only violations from a `run_gate()` call made after this ships carry a meaningful
index, which is exactly the only case this story's hand-correction route ever reads one from (a
*current* failing result, always freshly produced).

Why acceptance carry-forward matches by content, not by list position: the edited sentence's own
violation can disappear from the list (fixed) or shift position if it sorted before another
violation in the same section, so the violation at a given `violation_index` after the recheck is
not reliably "the same one" that was at that index before it. Matching on
`(kind, section, sentence, entry_ids, detail)` is exactly "byte-for-byte unchanged" as the AC states
it, and mirrors why `violation_index` alone was judged sufficient as a *key* for one stored result in
Story 5.8's Design Notes -- it is not stable *across* two different results.

## Verification

**Commands:**
- `uv run pytest tests/test_gate_run.py tests/test_report_draft_store.py tests/test_http_report_runs.py tests/test_gate_result_store.py -q` -- expected: all pass.
- `uv run alembic upgrade head` -- expected: no-op, this story adds no migration.
- `uv run ruff check .` -- expected: no new violations.

**Manual checks:**
- Trigger a Gate failure locally (`Environment.LOCAL`, `RecordedResponseGenerator`), open "Modifica
  e ricontrolla" on one card, edit the sentence to remove the offending token, submit, confirm the
  panel either clears (genuine pass) or shows the remaining cards with any previously-accepted one
  still marked Accettata.

## Suggested Review Order

**Entry point: the hand-correct-and-recheck route**

- Full flow: 404 guards, blank-text rejection, sentence replacement, persist, recheck, carry-forward, outcome branching.
  [`report_runs.py:690`](../../shell/http/routes/report_runs.py#L690)

**Sentence identification: `GateViolation.sentence_index`**

- New field, defaulted so no existing construction or stored row breaks.
  [`gate.py:81`](../../core/types/gate.py#L81)

- `run_gate()`'s per-section loop now enumerates so every violation carries its own within-section position.
  [`run.py:514`](../../core/gate/run.py#L514)

- A `None` (key missing entirely, a pre-story stored row) 404s rather than silently guessing index `0`.
  [`report_runs.py:816`](../../shell/http/routes/report_runs.py#L816)

- An unresolvable `section` also 404s instead of an unguarded `AttributeError`.
  [`report_runs.py:839`](../../shell/http/routes/report_runs.py#L839)

**Attempt renumbering: the flagged risk this story had to resolve first**

- `next_report_draft_attempt()`: a count of existing rows, not `run.regeneration_count` — the one source both minting paths can agree on.
  [`report_draft.py:131`](../../shell/adapters/postgres/report_draft.py#L131)

- `_run_draft_ready` switches to the shared counter; the automatic path is behavior-preserving.
  [`driver.py:567`](../../shell/runner/driver.py#L567)

- Why the old `regeneration_count`-based tagging breaks once this route can mint an extra row.
  [`report_run.py:113`](../../shell/adapters/postgres/report_run.py#L113)

**Ordering fix: two failing results can now share one `regeneration_count`**

- `_current_cycle_gate_failure` orders by `created_at` descending instead.
  [`report_runs.py:181`](../../shell/http/routes/report_runs.py#L181)

- Same invariant note added where `StoredGateResult` itself is defined.
  [`gate_result.py:57`](../../shell/adapters/postgres/gate_result.py#L57)

**Acceptance carry-forward and the shared closing helper**

- `Counter`-based content matching, consumed one-for-one — a plain `set` would double-accept an unreviewed duplicate-content violation.
  [`report_runs.py:903`](../../shell/http/routes/report_runs.py#L903)

- The correction is committed before any closing attempt, so a concurrent-closer rollback can never discard it.
  [`report_runs.py:941`](../../shell/http/routes/report_runs.py#L941)

- Shared close-on-full-acceptance helper (extracted from Story 5.7's accept route), now re-checking it still targets the true current result before writing.
  [`report_runs.py:448`](../../shell/http/routes/report_runs.py#L448)

- The re-check itself: never close against a result a concurrent correction has already superseded.
  [`report_runs.py:514`](../../shell/http/routes/report_runs.py#L514)

- `accept_gate_violation` now delegates its own closing write to the same shared helper.
  [`report_runs.py:566`](../../shell/http/routes/report_runs.py#L566)

**UI**

- No-JS `<details>` disclosure with the prefilled textarea, mirroring `report_payload.html`'s existing pattern.
  [`report_draft.html:32`](../../shell/http/templates/report_draft.html#L32)

**Tests**

- The race regressions: concurrent-closer durability and the accept-vs-correct staleness race.
  [`test_http_report_runs.py:2532`](../../tests/test_http_report_runs.py#L2532)
  [`test_http_report_runs.py:2916`](../../tests/test_http_report_runs.py#L2916)

- `sentence_index` correctness: zero-based, resets per section, shared across a sentence's own multiple violations.
  [`test_gate_run.py:821`](../../tests/test_gate_run.py#L821)

- `next_report_draft_attempt()`'s own coverage.
  [`test_report_draft_store.py:276`](../../tests/test_report_draft_store.py#L276)
