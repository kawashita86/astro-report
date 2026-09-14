# Sprint Change Proposal — 2026-09-14

**Trigger:** Feature request from Francesco (not a story defect) — add a `.env`-configured dual mode
for report generation: keep today's poll-driven behavior as one mode, add a mode where generation
continues in the background after the browser tab is closed, with the frontend stage-track view
unchanged. A related, independent request (JS poll-retry backoff too slow) was scoped out of this
proposal — see Implementation Handoff.

**Mode:** Incremental (all four edit proposals reviewed and approved individually with Francesco)

---

## Section 1: Issue Summary

Report generation today (`spec-3-10`, in review) is deliberately poll-driven under **AD-20**
(`ARCHITECTURE-SPINE.md:319`): a single `advance()` function performs at most one stage transition
per call, invoked only from the run's poll handler. AD-20's own rule text forbids any thread, async
task, queue consumer or scheduled job from calling it, and states explicitly that introducing one
"is a spine amendment."

Francesco wants a second mode, selected by a single `.env` setting for the whole deployment (not
per-run): generation keeps advancing even if he closes the tab, while the existing stage-track UI
(Story 9.5) still shows live progress exactly as today, so he can watch it and still resolve Gate
violations.

This is not a defect — no incident, no error. It is a deliberate request to relax a rule that was
written on purpose, so it is routed as a correct-course change to the architecture spine rather than
a plain feature story.

**Discovery context:** raised directly by Francesco outside any in-flight story, during Epic 9
(UI restyle, currently `in-progress`).

## Section 2: Impact Analysis

**Epic Impact**

- **Epic 3** ("Every dated fact for a Client's month, inspectable," owns `shell/runner/`) gains one
  new backlog story: `3-11-run-in-background-when-the-tab-closes`. No epic added, removed, or
  redefined.
- **Epic 9** (UI restyle, in-progress) is unaffected in scope — the stage-track view it restyled
  must render identically in both modes, which is a constraint on Epic 3's story, not new UI work
  for Epic 9.
- **Epic 5** (Gate) and **Epic 6** (export/history) consume `ReportRun.stage` only and are
  unaffected — both modes still drive the same stage machine.
- No epic resequencing needed; Epic 9 can finish independently of the new Epic 3 story.

**Story Impact**

- New: `3-11-run-in-background-when-the-tab-closes` (backlog). Full acceptance criteria to be
  produced by `bmad-spec` before `bmad-build` implements it.
- No existing story is invalidated. `spec-3-10`'s `advance()` contract is extended, not replaced —
  `poll` mode is byte-for-byte what Story 3.10 already implemented (currently `in review`).

**Artifact Conflicts**

- **Architecture** (`ARCHITECTURE-SPINE.md`) — AD-20 amended (see Section 4, Edit 1). The
  "Deferred" section's worker-process/queue-broker note is explicitly *not* triggered by this
  change and stays as-is.
- **PRD** (`prd.md`) — Throughput & Latency NFR gets a one-sentence addition (Section 4, Edit 3).
  No MVP or FR conflict.
- **UX** (`EXPERIENCE.md`) — addendum confirming the stage-track view is mode-agnostic
  (Section 4, Edit 4).
- **Configuration convention** (`ARCHITECTURE-SPINE.md`'s Consistency Conventions table) — already
  requires all env vars go through `shell/config.py`; `REPORT_RUN_MODE` follows this unchanged, no
  edit needed there.
- **AGENTS.md** — not edited directly by this proposal (it's a generated/managed file); flagged as
  a follow-up action for `bmad-project-context` to pick up the new env var and the Render-plan
  prerequisite on its next refresh.

**Technical Impact**

- New in-process scheduler task (started at app startup, stopped at shutdown) calling the existing
  `advance()` on a tick, for every `ReportRun` with `failed_at IS NULL` and `stage != 'gate_passed'`,
  when `REPORT_RUN_MODE=background`.
- Poll handler (`GET /report-runs/{run_id}`) becomes conditionally read-only: in `background` mode
  it renders `run` without calling `advance()`; in `poll` mode it is unchanged.
- **Operational prerequisite:** `background` mode requires a Render plan with no idle spin-down
  (Francesco has already purchased this). On a spin-down plan, `background` mode would silently
  stop advancing runs while the tab is closed — a deployment-configuration risk documented in the
  amendment and in `AGENTS.md`, not enforced in code.
- **Accepted risk:** a dyno restart or redeploy loses only the scheduler's in-memory timer, never
  persisted stage data (AD-10 checkpoints are unaffected). No boot-time reconciliation pass is
  required — Francesco has explicitly accepted resuming on the next poll or next scheduler tick
  after restart as sufficient.
- No schema change. No new deployable, no queue, no broker.

## Section 3: Recommended Approach

**Selected: Option 1 — Direct Adjustment**, via a narrow AD-20 carve-out (config-gated in-process
scheduler), not a full architectural rollback or a PRD/MVP review.

**Mechanism decision — in-process background task vs. a separate worker service:** evaluated with
Francesco; in-process wins given he has already provisioned a Render plan without idle spin-down.

- A separate worker service's main advantage (surviving a *web* dyno restart independently) buys
  nothing here, since restart-loss is explicitly accepted and the project's policy is single-service,
  auto-deploy-on-push (`AGENTS.md`) — there's no independent deploy cadence for a worker to exploit.
- A separate worker doubles infrastructure cost (a second paid Render service) and reintroduces the
  exact "worker process and queue broker" the architecture's Deferred section reserves for a scale
  change that hasn't happened (the 100–200-reports/month ceiling is unchanged).
- The in-process approach keeps the amendment to "one process, one new scheduler loop," preserves
  every one of AD-20's original guarantees (AD-10 stage semantics, the advisory lock, idempotent
  `advance()`) for the default `poll` mode, and costs nothing beyond what Francesco already pays for.

**Effort:** Low–Medium (one new scheduler module, one config flag, one conditional branch in the
poll handler; no schema/migration work).
**Risk:** Low. The only real risk (spin-down plan silently breaking `background` mode) is a
deployment-configuration concern, explicitly documented rather than coded around.
**Timeline impact:** None on Epic 9; additive to Epic 3's backlog.

## Section 4: Detailed Change Proposals

**Edit 1 — Architecture (`ARCHITECTURE-SPINE.md`), append after AD-20's rule, line 342:**

> **(Amended 2026-09-14, correct-course):** A single `.env`-configured `REPORT_RUN_MODE` setting
> (`poll` | `background`, read once in `shell/config.py` into `Settings`, default `poll`) selects
> between two ways forward progress happens for the whole deployment — never per-run. In `poll`
> mode, AD-20's rule above holds verbatim: only the poll handler calls `advance()`; forward progress
> is bounded by operator polling. In `background` mode, a single in-process scheduler task — started
> once at application startup, stopped at shutdown, still just calling the same one-stage-per-call
> `advance()` under the same advisory lock — periodically advances every `ReportRun` with
> `failed_at IS NULL` and `stage != 'gate_passed'`; AD-10's stage machine, `advance()`'s idempotence,
> and the advisory lock are unchanged. The poll handler still renders the stage-track view at the
> same cadence in this mode, but becomes read-only: it renders `run` without calling `advance()`, so
> the operator sees identical live progress whether or not they keep polling. `background` mode
> requires a Render plan with no idle spin-down — on a plan that sleeps the dyno, `background` mode
> silently stops advancing while the tab is closed, defeating its purpose; this is a documented
> deployment prerequisite (`AGENTS.md`), not something the app enforces. A dyno restart or redeploy
> loses only the scheduler's timer, never persisted stage data; resuming is left to the next poll or
> the next post-restart scheduler tick — no boot-time reconciliation pass, by Francesco's explicit
> acceptance of that gap. This amendment introduces no queue, no broker, no second deployable — the
> Deferred section's "worker process and queue broker" stays out of scope, reserved for if the
> 200-reports-per-month ceiling moves.

**Edit 2 — Sprint Tracking (`sprint-status.yaml`), new entry under `epic-3`:**

```
3-11-run-in-background-when-the-tab-closes: backlog
```

Story scope note (for the spec this feeds):
> Add `REPORT_RUN_MODE` (`poll`/`background`) to `Settings`. In `background` mode, an in-process
> scheduler advances every incomplete `ReportRun` on a fixed tick without waiting for a poll; the
> poll handler renders state read-only instead of calling `advance()`. In `poll` mode, behavior is
> unchanged from Story 3.10. Governed by AD-20 (amended).

**Edit 3 — PRD (`prd.md`), Throughput & Latency NFR, append one sentence:**

> *When `REPORT_RUN_MODE=background` (AD-20, amended), a Report may also continue advancing while
> Francesco is not actively watching it — the 3-minute p90 and the forty-per-session ceiling are
> unchanged; only the requirement to keep the tab open while it runs is relaxed.*

**Edit 4 — UX (`EXPERIENCE.md`, ux-astro-report-2026-08-28), addendum:**

> **Addendum (2026-09-14, correct-course):** The stage-track view (Story 9.5) is identical in both
> `REPORT_RUN_MODE` values — same nodes, same captions, same poll cadence, same Gate-failure
> recovery affordances. In `background` mode the poll no longer *drives* the run forward, only reads
> and renders it; an operator who never reopens the tab still finds the run at (or past)
> `gate_passed` when they return, exactly as if they had kept polling.

## Section 5: Implementation Handoff

**Scope classification: Moderate** — a spine amendment plus one new backlog story, but no PRD/MVP
rework, no epic restructuring, and all four artifact edits are already fully drafted above (no
further strategic replanning needed).

**Routing:**

1. **Apply Edits 1–4 directly** to `ARCHITECTURE-SPINE.md`, `sprint-status.yaml`, `prd.md`,
   `EXPERIENCE.md` — mechanical, can be done by the Developer agent or Francesco directly.
2. **`bmad-spec`** — produce the full spec contract for
   `3-11-run-in-background-when-the-tab-closes` (I/O matrix, code map, tasks & acceptance,
   verification commands), consuming this proposal and the amended AD-20 as its architecture
   grounding.
3. **`bmad-build`** — implement against that spec.
4. **Follow-up (not blocking):** next `bmad-project-context` refresh should add `REPORT_RUN_MODE`
   and the no-spin-down Render plan prerequisite to `AGENTS.md`.

**Independent action item (not part of this proposal — no architecture conflict, Minor scope):**
reduce the poll-failure backoff in `shell/http/static/shell.js:529-530`
(`POLL_BACKOFF_MS_FIRST` / `POLL_BACKOFF_MS_SUBSEQUENT`, currently 5000/15000) to at most 1–2
seconds. Route straight to `bmad-build` as a standalone change request; does not need this proposal
or an AD-20 reference.
**Update (2026-09-14):** done — `POLL_BACKOFF_MS_FIRST`/`POLL_BACKOFF_MS_SUBSEQUENT` are now
1000/2000. See `_bmad-output/implementation-artifacts/spec-reduce-poll-retry-backoff-to-1-2s.md`.

**Success criteria:** `REPORT_RUN_MODE=poll` reproduces Story 3.10's behavior exactly (regression
tests must still pass unchanged); `REPORT_RUN_MODE=background` advances a run to `gate_passed` (or a
terminal failure) with the browser tab closed the entire time, and the stage-track view, when
reopened, renders identically to how it would have rendered under continuous polling.
