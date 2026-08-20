---
title: 'Read the facts behind a month, entry by entry'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
baseline_commit: '5749a9e30b2b41d42b4e4dc0eead0613e5d63fce'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A frozen `ReportPayload` (Story 3.8) is stored but nowhere readable -- Francesco cannot
answer "why do you say that?" mid-call, and PRD FR-15 is entirely unimplemented.

**Approach:** New `GET /report-runs/{run_id}/payload` route reads the stored `ReportPayload` row,
converts every UTC instant in it to the Client's local time (`client.iana_zone`), and renders it
generically -- one block per `sections.*` key and `day_lists.*` key, one entry per stored event/profile
dict -- with no per-event-kind branching. Linked from `report_run_poll.html` once `run.stage ==
"payload_ready"`.

## Boundaries & Constraints

**Always:**
- New `shell/http/payload_view.py::localize_payload(payload: dict[str, Any], *, iana_zone: str) ->
  dict[str, Any]` (resolves `ZoneInfo(iana_zone)` -- lives in `shell/http/` per AD-12/this story's AC).
  Deep-walks every dict/list; any `str` parseable via `datetime.fromisoformat()` becomes
  `value.astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")`. Every stored instant is ISO 8601 tz-aware
  (freeze.py's `_json_safe`), so no key-name special-casing is needed; ids/hashes/enum strings fail
  `fromisoformat()` and pass through unchanged.
- New route `GET /report-runs/{run_id}/payload` in `shell/http/routes/report_runs.py`. 404 if `run_id`
  doesn't resolve, or no `ReportPayload` row exists for it (`select(...).where(report_run_id == run_id)`).
  Otherwise loads the owning `Client`, calls `localize_payload(stored.payload, iana_zone=client.iana_zone)`,
  renders `report_payload.html`.
- New `shell/http/templates/report_payload.html`: iterate `payload.sections.items()` (`profile` as a
  nested key/value block when not `None`; the five event-tuple fields each as a list of key/value
  blocks, `id` omitted) then `payload.day_lists.items()` the same way -- eight blocks, no per-kind
  branch. Plain semantic HTML, mirroring `client_edit.html` (no CSS framework).
- `report_run_poll.html`: when `run.stage == "payload_ready"`, add `<a href="/report-runs/{{
  run.id }}/payload">View Payload</a>` inside `#run-status` (survives the HTMX `outerHTML` swap).

**Ask First:** None identified.

**Never:**
- No change to `core/` or to `freeze_payload()`'s stored shape -- read-only against `ReportPayload.payload`.
- No hand-listed per-kind field mapping -- generic key/value rendering covers every kind, mirroring
  AD-13's no-per-Section-branch philosophy.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Aspect never perfected | `perfected_at: null`, window fields set | No perfection time shown; window still localized | N/A |
| Aspect still open at month end | `orb_exit_at: null` | No exit time shown | N/A |
| No `ReportPayload` for `run_id` | Run hasn't reached `payload_ready` | 404 | Raised, not swallowed |
| Unknown `run_id` | No matching `ReportRun` | 404 | Raised, not swallowed |
| Non-datetime string field | e.g. `id` (sha256), `aspect` ("trine") | Passes through unchanged | N/A |
| Payload from a run months ago | Any stored `ReportPayload` row | Renders identically to a fresh one | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/report_payload.py` -- `ReportPayload:28` (`payload`/`report_run_id`/
  `client_id` columns) -- the row this route queries.
- `core/payload/freeze.py` -- `freeze_payload:148`, `_json_safe:58` -- stored shape:
  `{"sections": {name: {"profile":..., "aspects":[...], ...}}, "day_lists": {...}}`.
- `shell/http/routes/report_runs.py` -- `poll_report_run:100` (404 pattern to mirror), `_templates:40`,
  `router:37`.
- `shell/http/templates/report_run_poll.html` -- `#run-status:15` div -- add the link inside it.
- `shell/adapters/postgres/client.py` -- `Client.iana_zone:66`.
- `tests/test_http_report_runs.py` -- app/fixture wiring (`LOCAL:45`) to mirror.
- `tests/test_report_payload_store.py` -- how a `ReportPayload` row is built in tests, to reuse.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/payload_view.py` -- new `localize_payload()` per Boundaries.
- [x] `shell/http/routes/report_runs.py` -- new `GET /report-runs/{run_id}/payload` route.
- [x] `shell/http/templates/report_payload.html` -- new generic render template.
- [x] `shell/http/templates/report_run_poll.html` -- add the payload link when `stage == "payload_ready"`.
- [x] `tests/test_payload_view.py` -- one test per I/O & Edge-Case Matrix row, covering `localize_payload`.
- [x] `tests/test_http_report_runs.py` -- extend with the new route's 404s and happy path.

**Acceptance Criteria:**
- Given a completed run with a stored `ReportPayload`, when Francesco opens `/report-runs/{run_id}/payload`,
  then he sees all eight groupings (six `sections` keys plus `giorni_favorevoli`/`giorni_di_attenzione`).
- Given `report_run_poll.html` once `run.stage == "payload_ready"`, when it renders, then a link to the
  payload view is present and reachable in one click.
- Given any stored UTC instant, when the view renders it, then it is shown in `client.iana_zone` local
  time, and no other module performs this conversion.

## Design Notes

**Why "orb" means the in-orb window, not a numeric degree.** `TransitAspectEvent` has no numeric orb
field -- PRD line 347 describes what's recorded as "the in-orb window (entry and exit dates)"; FR-15's
"and orb" is shorthand for that window. `orb_entry_at`/`orb_exit_at` already satisfy it.

## Verification

**Commands:**
- `uv run pytest tests/test_payload_view.py tests/test_http_report_runs.py -q` -- expected: all pass.
- `uv run ruff check shell/http/payload_view.py shell/http/routes/report_runs.py` -- expected: no findings.

## Suggested Review Order

**UTC-to-local conversion (AD-12)**

- Entry point: deep-walks the whole stored dict, converting any ISO-parseable, tz-aware string -- the one and only place a Payload instant leaves UTC.
  [`payload_view.py:19`](../../shell/http/payload_view.py#L19)

- Naive (tzinfo-less) parseable strings pass through unchanged rather than being silently misconverted via the server's own local time -- a review-driven hardening.
  [`payload_view.py:44`](../../shell/http/payload_view.py#L44)

- Public entry: resolves the zone once, then hands the whole dict to the recursive walk.
  [`payload_view.py:50`](../../shell/http/payload_view.py#L50)

**Route (404 collapsing, read-only)**

- One query covers both "unknown run" and "run not yet `payload_ready`" -- no separate `ReportRun` lookup needed first.
  [`report_runs.py:120`](../../shell/http/routes/report_runs.py#L120)

- The query itself: `report_run_id` is the only join key, `.first()` returning `None` is the single 404 trigger.
  [`report_runs.py:132`](../../shell/http/routes/report_runs.py#L132)

**Generic rendering (no per-kind branch, AD-13-style)**

- Recursive macro: any dict becomes a `<dl>`, any list a `<ul>`, everything else inline -- one code path for all five event kinds and every Domain Profile shape.
  [`report_payload.html:13`](../../shell/http/templates/report_payload.html#L13)

- Iterates the six `sections` keys generically -- no `{% if section_name == ... %}` anywhere.
  [`report_payload.html:33`](../../shell/http/templates/report_payload.html#L33)

- Empty-grouping guard: a field with no entries renders no heading, so a typical sparse month doesn't drown in empty categories.
  [`report_payload.html:43`](../../shell/http/templates/report_payload.html#L43)

- Same emptiness guard applied to the two day-lists.
  [`report_payload.html:55`](../../shell/http/templates/report_payload.html#L55)

**Reachability (one interaction from the run)**

- The payload link appears only once the run has actually reached `payload_ready`, matching the AC.
  [`report_run_poll.html:22`](../../shell/http/templates/report_run_poll.html#L22)

**Tests**

- `localize_payload`'s five I/O-matrix-driven cases plus the naive-string regression case.
  [`test_payload_view.py:16`](../../tests/test_payload_view.py#L16)

- The naive-datetime defensive fix's own regression test.
  [`test_payload_view.py:124`](../../tests/test_payload_view.py#L124)

- Fixture producing a real frozen Payload via `freeze_payload()` -- one populated field per grouping, everything else empty, to exercise both the happy path and the empty-grouping guard from one build.
  [`test_http_report_runs.py:170`](../../tests/test_http_report_runs.py#L170)

- Both 404 matrix rows -- unknown run and un-payload-ready run.
  [`test_http_report_runs.py:370`](../../tests/test_http_report_runs.py#L370)

- Happy path: all eight groupings present, one instant correctly localized to `America/Chicago`, event `id` omitted.
  [`test_http_report_runs.py:394`](../../tests/test_http_report_runs.py#L394)

- Proves the review-driven empty-grouping guard actually hides headings, not just that populated ones show.
  [`test_http_report_runs.py:427`](../../tests/test_http_report_runs.py#L427)

- The poll-view link's presence/absence at the `payload_ready` boundary.
  [`test_http_report_runs.py:456`](../../tests/test_http_report_runs.py#L456)
