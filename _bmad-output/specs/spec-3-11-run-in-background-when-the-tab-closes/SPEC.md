---
id: SPEC-3-11-run-in-background-when-the-tab-closes
companions:
  - '../../planning-artifacts/architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md'
sources:
  - '../../planning-artifacts/sprint-change-proposal-2026-09-14.md'
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Run in background when the tab closes

## Why

Report generation (Story 3.10, AD-20) is deliberately poll-driven: forward progress happens only inside the run's poll request, so closing the browser tab pauses a run at its last checkpoint until the operator reopens it and polls again. Francesco asked — as a deliberate feature request, not a defect fix — to stop being tied to keeping the tab open while a report runs, without changing how the stage-track view looks or behaves. This is a mandate met by a correct-course amendment to AD-20 (`ARCHITECTURE-SPINE.md`, amended 2026-09-14): a single deployment-wide `.env` setting chooses between today's poll-bound progress and a new mode where progress continues unattended.

## Capabilities

- **CAP-1**
  - **intent:** An operator can select, for the whole deployment (never per-run), whether report runs advance by poll only or by an in-process background scheduler, via a `REPORT_RUN_MODE` setting (`poll` | `background`, default `poll`).
  - **success:** `REPORT_RUN_MODE=poll` reproduces Story 3.10's behavior byte-for-byte, with its regression tests passing unchanged.

- **CAP-2**
  - **intent:** In `background` mode, a run keeps advancing toward completion even while no one is watching or polling it — an in-process scheduler task, running for the app's lifetime, periodically drives forward every `ReportRun` that isn't finished or failed.
  - **success:** With `REPORT_RUN_MODE=background`, a run reaches `gate_passed` (or a terminal failure) with the browser tab closed the entire time.

- **CAP-3**
  - **intent:** In `background` mode, reopening the tab and polling shows the run's true current state without the poll itself advancing it, so the scheduler is the only thing moving the run forward.
  - **success:** In `background` mode, the stage-track view, when reopened, renders identically to how it would have rendered under continuous polling — no run is ever advanced twice for the same transition.

## Constraints

- The background scheduler must drive runs through the same `advance()` (one stage per call) under the same Postgres advisory lock that poll mode uses — no second advance path, and no change to AD-10 stage semantics, `advance()`'s idempotence, or the `stage_failure_count`/`regeneration_count` bookkeeping.
- `REPORT_RUN_MODE` defaults to `poll`; poll-mode behavior and its regression tests must remain unchanged.
- No queue, broker, or second deployable — `background` mode stays single-process, single-service, matching the Render plan already provisioned; the architecture's Deferred worker/queue-broker option stays reserved for a scale change that hasn't happened.
- `background` mode requires a Render plan with no idle spin-down. This is a documented deployment prerequisite (a follow-up `AGENTS.md` entry), not something the app enforces or detects in code — on a spin-down plan, `background` mode would silently stop advancing runs while the tab is closed.
- A run rewound to `payload_ready` pending human Gate review (Stories 5.7/5.8) is ticked by the scheduler like any other incomplete run — no special-case pause; it is still terminally failed by AD-10's existing `stage_failure_count` / `_MAX_STAGE_FAILURES` bound.
- No boot-time reconciliation pass after a dyno restart or redeploy: only the scheduler's in-memory timer is lost, never persisted stage data; resuming is left to the next poll or the next post-restart scheduler tick. This gap is explicitly accepted, not an open question.

## Non-goals

- A separate worker process, queue, or broker.
- A boot-time reconciliation pass after a restart or redeploy.
- App-level enforcement or detection of the Render no-spin-down prerequisite.
- Changing the JS poll-retry backoff (`shell/http/static/shell.js` `POLL_BACKOFF_MS_*`) — an independent, already-shipped change tracked separately (`spec-reduce-poll-retry-backoff-to-1-2s.md`), out of scope here.
- Any schema or migration change — `ReportRun` is untouched.

## Success signal

`REPORT_RUN_MODE=poll` reproduces Story 3.10's behavior exactly, unchanged regression tests green. With `REPORT_RUN_MODE=background`, a report run advances to `gate_passed` (or a terminal failure) with the browser tab closed the entire time, and the stage-track view (Story 9.5), when the operator reopens it, renders exactly as it would have under continuous polling.
