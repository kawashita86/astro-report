---
title: 'Story 5.7 — Accept a Gate violation after review, so a Report can complete despite it'
type: 'feature'
created: '2026-09-02'
status: 'done'
review_loop_iteration: 0
baseline_commit: '9573a9bcff11d6d14d3dfe9978a794183fe18223'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When the Groundedness Gate rejects a draft and regeneration is exhausted
(`run.failed_at` set), Francesco's only recovery is Rigenera — full regeneration, another paid
Generator call. He has no way to say "I've read this violation, it's fine" and let the Report
complete, so a Report he judges correct can be stuck forever behind a check he disagrees with.

**Approach:** Add a per-violation "Accetta" action on the existing Gate-failure panel
(`report_draft.html`). Accepting one violation records an append-only, immutable review row
against the specific `StoredGateResult` + violation. Once every violation in the current failing
result is accepted, a `Report` row is written immediately (no new Gate check), the run advances to
`gate_passed`, and every surface that names the Report shows a permanent "Superato con N
eccezioni" badge alongside its normal status — never rendered as a clean pass.

## Boundaries & Constraints

**Always:**
- An accept decision is append-only: one `gate_violation_review` row per (gate_result, violation
  index), never updated or deleted except via the existing FR-29 Client-deletion cascade.
- A `Report` row is written only when every violation in the *current* failing `StoredGateResult`
  (`_current_cycle_gate_failure`, already in `report_runs.py`) has been accepted — never partially.
- The closing `Report` row records `accepted_violation_count` and `closing_gate_result_id`; a
  clean-pass `Report` row (existing path, `driver.py::_run_gate_passed`) leaves both at their
  defaults (`0` / `None`) — unchanged behavior.
- `run.stage` becomes `gate_passed` and `run.failed_at`/`failure_reason` are cleared only on that
  same closing write — mirrors `regenerate_report_run`'s existing state transition, not a new
  pattern.
- The existing Rigenera flow, `GateResult`/`StoredGateResult` invariants, and `run_gate()` are
  untouched — this is an additive shell-only review layer, never a fabricated Gate re-check.
- Accepting an already-accepted violation index is a no-op (idempotent double-submit), not an
  error and not a second row.

**Ask First:** none identified — the approach is fully determined by epics.md's ACs and the
2026-09-02 correct-course amendment.

**Never:**
- No inline JS (spinner, expand-in-place, auto-collapsing cards) — cards render server-side as
  open or resolved on each page load/redirect. That interaction polish, and Story 5.8's
  hand-correct-and-recheck action, are explicitly out of scope for this story.
- Never let `violation_index` resolve against any `StoredGateResult` other than the run's current
  failing one (no accepting a stale/superseded violation from an earlier, since-regenerated cycle).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Accept one of several | Run has a current Gate failure with 3 violations, none accepted | One review row persisted; run stays `failed_at` set; redirect to draft page shows 1 resolved strip + 2 open cards | N/A |
| Accept the last one | 2 of 3 violations already accepted, Francesco accepts the 3rd | `Report` row written (`accepted_violation_count=3`), `run.stage="gate_passed"`, `failed_at`/`failure_reason` cleared | N/A |
| Double-submit same violation | Violation index already has a review row | No new row written; same redirect as a fresh accept | N/A |
| Wrong/out-of-range index | `violation_index` not in the current failing result's violations, or run has no current Gate failure | 404 | N/A |
| Already closed | `run.failed_at is None` (already passed, via any path) | 404 | N/A |
| `view_report` on an accept-closed Report | `Report.accepted_violation_count > 0`, no passing `StoredGateResult` exists | Renders via `closing_gate_result_id`, not the `passed=True` lookup | N/A |

</frozen-after-approval>

## Code Map

- `migrations/versions/0023_gate_violation_review.py` (new) -- `gate_violation_review` table
  (mirrors `0013_gate_result.py`'s shape) + two nullable `report` columns
  (`accepted_violation_count int not null default 0`, `closing_gate_result_id uuid null`),
  revises `0022_birthplace_name`.
- `shell/adapters/postgres/gate_violation_review.py` (new) -- `GateViolationReview` model +
  `store_gate_violation_review()`, mirrors `gate_result.py`'s shape/immutability guard exactly.
  Columns: `id`, `client_id`, `report_run_id`, `gate_result_id` (FK `gate_result.id`),
  `violation_index`, `kind`, `section`, `sentence`, `entry_ids` (JSON), `detail`, `created_at`.
- `shell/adapters/postgres/report.py:30-65` (`Report`) -- add `accepted_violation_count: int = 0`
  and `closing_gate_result_id: UUID | None = None`. `store_report()` (`:81-110`) gains the same two
  optional kwargs (defaults `0`/`None`); `driver.py`'s existing call site (`:622-629`) stays
  unchanged, relying on the defaults.
- `shell/adapters/postgres/client.py:51-63` (`_CLIENT_CASCADE_TABLES`), `:353-473`
  (`delete_client_and_derived`) -- add `"gate_violation_review"`; delete those rows *before* the
  existing `gate_results` deletion block (`gate_violation_review.gate_result_id` FKs to
  `gate_result.id`).
- `shell/http/routes/report_runs.py:130-166` (`_current_cycle_gate_failure`) -- reused unchanged as
  the guard for the new route.
- `shell/http/routes/report_runs.py:374-423` (`regenerate_report_run`) -- pattern to mirror for the
  new route's shape (404s, redirect-with-flash).
- `shell/http/routes/report_runs.py` (new, near `regenerate_report_run`) --
  `POST /report-runs/{run_id}/violations/{violation_index}/accept`: 404 unless
  `_current_cycle_gate_failure(session, run)` is not `None` and `violation_index` is in range of
  its `violations`; no-op if already accepted; else `store_gate_violation_review(...)`. If accepted
  count now equals `len(violations)`: read the latest `ReportDraft`/`ReportPayload` for
  `style_guide_version`/`payload_schema_version` (same reads `_run_gate_passed` already does),
  call `store_report(..., accepted_violation_count=len(violations),
  closing_gate_result_id=stored_gate_result.id)`, clear `run.failed_at`/`failure_reason`, set
  `run.stage="gate_passed"`, commit, redirect `303` to `/report-runs/{run_id}`. Else commit, redirect
  `303` to `/report-runs/{run_id}/draft`.
- `shell/http/routes/report_runs.py:539-546` (`view_report_draft`'s `if run.failed_at is not None`
  branch) -- also query accepted `violation_index` values for `stored_gate_result.id` and add
  `"index": i, "accepted": i in accepted_indices` to each violation dict.
- `shell/http/routes/report_runs.py:585-601` (`view_report`) -- the `stored_gate_result` lookup
  needs a second branch: when `bundle.report.accepted_violation_count > 0`, read
  `session.get(StoredGateResult, bundle.report.closing_gate_result_id)` instead of the
  `passed.is_(True)` query; pass `accepted_violation_count` to the template. Existing clean-pass
  branch unchanged.
- `shell/http/templates/report_draft.html:12-23` (violation card loop) -- open cards (`not
  v.accepted`) get a form `POST /report-runs/{{ run.id }}/violations/{{ v.index }}/accept` with an
  "Accetta" button; accepted violations render a one-line resolved strip instead (kind + Sezione +
  `status-badge--warning` "Accettata" tag).
- `shell/http/templates/report.html:8` -- add `{% if report.accepted_violation_count %}` a second
  `status-badge status-badge--warning` reading "Superato con N eccezioni", stacked after the
  existing success badge. `view_report` passes `report=bundle.report` (not currently in context —
  add it).
- `shell/http/routes/home.py:101-149` (`home_dashboard`) -- change the `reported_run_ids` set query
  to `select(Report.report_run_id, Report.accepted_violation_count)`, build a dict instead, and add
  `"accepted_violation_count"` to each run's context dict.
- `shell/http/templates/home.html:34-38` -- stack the warning badge next to the existing
  `status-badge` when `run.accepted_violation_count`.
- `shell/http/routes/clients.py:862-883` (`list_client_reports`) -- `_stored_report` is already
  selected; add `"accepted_violation_count": _stored_report.accepted_violation_count` to each entry.
- `shell/http/templates/client_reports.html:36-44` -- render the same warning badge per entry when
  `entry.accepted_violation_count`.
- `shell/http/static/tokens.css:750-754` (after `.status-badge--danger`) -- add
  `.status-badge--warning` using `--warning`/`--warning-surface`, mirroring `.row-badge` (`:906-914`).
- `core/types/gate.py`, `core/gate/run.py`, `core/errors.py::GateFailedError` -- read-only, unchanged.
- `tests/test_gate_violation_review.py` (new) -- row shape, immutability, cascade join, the I/O
  matrix.
- `tests/test_http_report_runs.py` -- extend: accept route happy path, last-violation closes the
  run, double-submit idempotency, wrong-index/no-failure 404s, `view_report`/`view_report_draft`/
  home/client-reports badge rendering.
- `tests/test_gate_result_store.py` or a new assertion near it -- a Report closed via accepted
  violations is excluded from the existing first-generation pass-rate query (SM-5) and eligible for
  the SM-7 hand-sample query (both already demonstrated by Story 5.6's queries, this just adds a
  covering row).
- `tests/test_client_store.py:282-309` -- add `"gate_violation_review"` to the cascade-constant
  regression test.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0023_gate_violation_review.py` -- create table + `report` columns.
- [x] `shell/adapters/postgres/gate_violation_review.py` -- model + store function.
- [x] `shell/adapters/postgres/report.py` -- new columns + `store_report()` kwargs.
- [x] `shell/adapters/postgres/client.py` -- cascade join.
- [x] `shell/http/routes/report_runs.py` -- accept route, `view_report_draft`/`view_report` changes.
- [x] `shell/http/templates/report_draft.html` -- Accetta button + resolved strips.
- [x] `shell/http/templates/report.html`, `home.py`/`home.html`, `clients.py`/`client_reports.html`
  -- warning badge everywhere a closed-with-exceptions Report is named.
- [x] `shell/http/static/tokens.css` -- `.status-badge--warning`.
- [x] Tests listed in Code Map -- cover the I/O matrix, cascade, and metric-exclusion queries.

**Acceptance Criteria:**
- Given a run whose current Gate failure is showing its violation cards, when Francesco accepts
  one, then that decision is recorded append-only against the specific `StoredGateResult` and
  violation index.
- Given every violation in the current failing `GateResult` has been accepted, when the last one is
  accepted, then a `Report` row is written immediately recording the accepted count and closing
  result, and the run advances to `gate_passed` — no new Gate check is run.
- Given a Report closed this way, when shown on the reading sheet, Home, or Report History, then it
  carries a permanent "Superato con N eccezioni" badge, never identical to a clean pass.
- Given SM-5's first-generation pass rate and SM-7's hand-sample query, when computed over a Report
  closed this way, then it is excluded from the former and eligible for the latter (test-confirmed).

## Spec Change Log

## Design Notes

Why `violation_index` is a plain list position, not a new `GateViolation` field: `GateResult.violations`
is documented as a fixed, deterministic order for a given `(draft, payload, vocabulary)` triple
(`core/types/gate.py`), and `StoredGateResult.violations` is the immutable JSON snapshot of exactly
that tuple — so the position within the stored list is already a stable, sufficient key for one
persisted result. This sidesteps the "add a within-section sentence index to `GateViolation`" change
the epic context flags — that's needed for Story 5.8's hand-correction (to locate a sentence inside
the *draft*), not for identifying an entry in an already-stored violation list here.

Why the "still open" redirect goes back to `/report-runs/{run_id}/draft` rather than the poll page
(unlike `regenerate_report_run`, which always redirects to `/report-runs/{run_id}`): regenerate
clears `failed_at` and kicks off real work, so the poll page's stage track is the right destination.
Accepting one of several violations changes nothing about `failed_at`/`stage` — redirecting to the
poll page would just show the still-failed state and force an extra click back to the panel to
accept the next one. Only the *closing* accept (which does clear `failed_at`/advance `stage`)
redirects to the poll page, mirroring regenerate exactly.

## Verification

**Commands:**
- `uv run pytest tests/test_gate_violation_review.py tests/test_http_report_runs.py tests/test_gate_result_store.py tests/test_client_store.py -q` -- expected: all pass.
- `uv run alembic upgrade head` -- expected: `0023_gate_violation_review` applies cleanly.
- `uv run ruff check .` -- expected: no new violations.

**Manual checks:**
- Trigger a Gate failure locally (`Environment.LOCAL` uses `RecordedResponseGenerator`), accept each
  violation one at a time, confirm the panel updates and the run reaches `gate_passed` with the
  warning badge visible on the reading sheet, Home, and Report History.

## Suggested Review Order

**Accept-and-close route (the core mechanism)**

- Entry point: guards (current-cycle failure, index range), idempotent accept, closing write, and the redirect split between "still open" vs "just closed".
  [`report_runs.py:434`](../../shell/http/routes/report_runs.py#L434)

- Race-condition handling: concurrent double-submit and concurrent closing-accept both degrade to a graceful redirect instead of a raw 500.
  [`report_runs.py:533`](../../shell/http/routes/report_runs.py#L533)
  [`report_runs.py:584`](../../shell/http/routes/report_runs.py#L584)

**Data model & migration**

- New append-only audit table, immutable, DB-level unique on `(gate_result_id, violation_index)` for idempotency.
  [`gate_violation_review.py:42`](../../shell/adapters/postgres/gate_violation_review.py#L42)
  [`gate_violation_review.py:57`](../../shell/adapters/postgres/gate_violation_review.py#L57)

- `Report` gains `accepted_violation_count`/`closing_gate_result_id`, both defaulted so the existing clean-pass call site is untouched.
  [`report.py:84`](../../shell/adapters/postgres/report.py#L84)
  [`report.py:105`](../../shell/adapters/postgres/report.py#L105)

- Schema for both, plus the new FK-consistency index on `report.closing_gate_result_id`.
  [`0023_gate_violation_review.py:51`](../../migrations/versions/0023_gate_violation_review.py#L51)

- Client-deletion cascade extended, ordered before `gate_result` deletion (FK direction).
  [`client.py:454`](../../shell/adapters/postgres/client.py#L454)

**Reading a closed-with-exceptions Report**

- `view_report_draft` tags each violation with its stable list-position `index` and whether it's already reviewed.
  [`report_runs.py:738`](../../shell/http/routes/report_runs.py#L738)

- `view_report` resolves the Gate result via `closing_gate_result_id` instead of the `passed=True` lookup when the Report was closed this way.
  [`report_runs.py:800`](../../shell/http/routes/report_runs.py#L800)

**UI**

- Per-violation Accetta form on open cards; accepted violations collapse to a resolved strip.
  [`report_draft.html:16`](../../shell/http/templates/report_draft.html#L16)
  [`report_draft.html:30`](../../shell/http/templates/report_draft.html#L30)

- New warning badge variant, and its three display sites (reading sheet, Home, Report History).
  [`tokens.css:758`](../../shell/http/static/tokens.css#L758)
  [`home.py:123`](../../shell/http/routes/home.py#L123)

**Incidental cross-cutting fix**

- `Report`'s new FK to `gate_result` broke the backup model's FK-safe ordering; reordered and documented.
  [`backup.py:82`](../../shell/http/routes/backup.py#L82)

**Tests**

- Core behavior: partial accept leaves the run open; the closing accept advances it to `gate_passed`.
  [`test_http_report_runs.py:1735`](../../tests/test_http_report_runs.py#L1735)
  [`test_http_report_runs.py:1779`](../../tests/test_http_report_runs.py#L1779)

- SM-5/SM-7 metric-exclusion proof for a Report closed via accepted violations.
  [`test_gate_result_store.py:542`](../../tests/test_gate_result_store.py#L542)
