---
title: '10.6 Watch the Sections being written'
type: 'feature'
created: '2026-10-01'
status: 'done'
baseline_commit: '8ed80398ea5ac675ba1043957b24954adaa51bb8'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-10-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** While the driver writes Sections (Story 10.4/10.5), the run view shows only a stage track and a spinner, so Francesco waits for the whole draft before reading anything.

**Approach:** While the Bozza node is active (`run.stage == "payload_ready"` — the UX's "drafting"; the epic's "`draft_ready`" names the same phase), the run view adds EXPERIENCE.md's *Drafting view*: a rail of eight Sections with per-Section state and a sheet of each written Section's prose. The 2 s poll swaps only changed rail rows and Sections out-of-band. Read-only: the poll never advances anything (AD-20).

## Boundaries & Constraints

**Always:** Section state is derived purely (new `shell/http/section_rail.py`, using `core/draft_state.py`) from the latest attempt's `report_draft_section` rows (attempt = `next_report_draft_attempt`) plus an explicit `now`; a missing row reads as `pending`. States: `complete` → *Scritta*; `failed` → *Non riuscita*; `pending` with a live lease or `attempts > 0` → *In scrittura*; other `pending` in an attempt after the first draft → *Da rifare*; otherwise *In attesa*; unleased Consiglio finale with Sections 1–7 not all complete → *In attesa delle altre Sezioni*. Sheet prose reuses `draft_view.py`'s rendering (one Section at a time); unwritten Sections show `.skeleton`. One polite live region (`role="status"`) on the rail summary, updated via `hx-swap-oob="innerHTML"` so the node persists: *"N di 8 Sezioni scritte"*. Italian copy, `tokens.css` tokens, rail collapses to the summary line below `md`. The stage track, caption and spinner stay as in 9.5.

**Ask First:** Any change to `advance()`, the driver, or Section-row semantics.

**Never:** Write from a handler; add JS timers (reuse the existing `every 2s` trigger and shell.js's hidden-tab/backoff gating); show Section text from rows that are not `complete`; touch the Gate, export gate or Payload view.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full page, drafting | GET, stage `payload_ready` | Stage track + rail + sheet; poller swaps nothing itself (`hx-swap="none"`) | N/A |
| One complete, rest leased | row 2 complete, others leased | Rail: 2 *Scritta*, others *In scrittura*; poll includes Section 2's text, no other text | N/A |
| Poll with `seen` | HTMX GET, `seen=1:pending,2:pending…` | OOB fragments for only rows/Sections whose state differs, plus summary | N/A |
| Nothing changed | `seen` matches | Summary and track only; no rail row or Section | N/A |
| Consiglio waiting | Sections 1–7 not all complete | Row 8 *In attesa delle altre Sezioni*, never claimable-looking | N/A |
| Regeneration | Attempt 2, Sections 3, 8 reset, rest carried | 1–2, 4–7 *Scritta* with text; 3, 8 *Da rifare* → *In scrittura* when leased | N/A |
| Section exhausted | Row `failed`, run failed | Row *Non riuscita*; failure caption as today | N/A |
| Leaving drafting | Poll after stage ≠ `payload_ready` or failed | Full `#run-status` with `HX-Retarget`/`HX-Reswap: outerHTML` | N/A |
| Not drafting | Stage ≠ `payload_ready` | Existing 9.5 view, no rail | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/report_runs.py:524` -- `poll_report_run`: add rail/sheet context, OOB-vs-full branch, retarget headers; read-only.
- `shell/http/section_rail.py` -- new pure view-model: `build_rail(rows, *, prior_draft_exists, now)`, state labels, `rail_summary`, changed-vs-`seen` diff, `parse_seen`.
- `shell/http/draft_view.py` -- add `render_section(name, sentences, payload, *, iana_zone)` over existing `_render_prose`/`_render_list`.
- `shell/http/templates/report_run_poll.html` -- drafting block; new `_section_rail.html` / `_section_sheet.html` partials and an OOB fragment template.
- `shell/http/static/shell.js` -- `htmx:configRequest` adds `seen` from `[data-section-ordinal][data-section-state]`; no timer.
- `shell/http/static/tokens.css` -- rail/sheet styles (skeleton exists at `.skeleton`).
- `core/draft_state.py`, `shell/adapters/postgres/report_draft_section.py` -- read-only reference (`is_lease_live`, `section_rows`).
- Tests: new `tests/test_section_rail.py`; `tests/test_http_report_runs.py` (existing spinner/`hx-trigger` tests at ~1355–1440 must keep passing).

## Tasks & Acceptance

**Execution:**
- [ ] `shell/http/section_rail.py` -- pure state/summary/diff functions -- testable without DB or clock
- [ ] `shell/http/draft_view.py` -- `render_section` -- single-Section sheet rendering
- [ ] `shell/http/routes/report_runs.py` + templates -- drafting view, OOB poll, retarget on exit
- [ ] `shell/http/static/shell.js`, `tokens.css` -- `seen` param; rail/sheet/md-collapse styles
- [ ] tests -- one per matrix row (HTTP: complete row's text present while others read *In scrittura*; single live region; Italian copy); negative guard that the poll never writes

**Acceptance Criteria:**
- Given a run drafting with one complete Section and others leased, when the poll is read, then it contains that Section's text and the others read *In scrittura*.
- Given the draft finishes or fails, when the next poll lands, then the view falls back to the 9.5 stage track and stops polling when terminal.
- Given `uv run pytest` and `uv run ruff check . && uv run ruff format --check .`, then all pass.

## Design Notes

OOB over per-row polling: the poller is `#run-status` with `hx-swap="none"`; the response is only `hx-swap-oob` fragments (`id="rail-row-3"`, `id="sheet-section-3"`, summary `innerHTML`). The client reports what it shows via `seen`; the server stays stateless. Exiting drafting returns the full fragment retargeted at `#run-status`, since the poller element itself must lose its attributes.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean

**Manual checks (if no CLI):**
- Run the app against the recorded generator; confirm Sections appear one by one and the summary announces progress.

## Suggested Review Order

**State and the poll contract (entry point)**

- Pure rule: each Section's state, summary line, and the `seen` diff.
  [`section_rail.py:99`](../../shell/http/section_rail.py#L99)

- Read-only poll: full view, OOB fragments, or retargeted full swap.
  [`report_runs.py:576`](../../shell/http/routes/report_runs.py#L576)

- Text only from `complete` rows, rendered one Section at a time.
  [`report_runs.py:546`](../../shell/http/routes/report_runs.py#L546)
  [`draft_view.py:223`](../../shell/http/draft_view.py#L223)

**Client and markup**

- Browser reports what it shows; no new timer.
  [`shell.js:583`](../../shell/http/static/shell.js#L583)

- Poller goes `hx-swap="none"` while drafting; OOB fragments do the work.
  [`report_run_poll.html:13`](../../shell/http/templates/report_run_poll.html#L13)
  [`report_run_poll_oob.html`](../../shell/http/templates/report_run_poll_oob.html)

- Rail/sheet styles; rail collapses below 900px.
  [`tokens.css:1924`](../../shell/http/static/tokens.css#L1924)

**Tests**

- Pure states and diff; HTTP rows in the 10.6 block.
  [`test_section_rail.py`](../../tests/test_section_rail.py)
  [`test_http_report_runs.py`](../../tests/test_http_report_runs.py)
