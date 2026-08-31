# Sprint Change Proposal — 2026-08-31 (Epic 9 gap closure + new UX scope)

**Workflow:** Correct Course
**Trigger:** Francesco's post-Epic-9 walkthrough surfaced seven UI/UX complaints, the sharpest
being: *"generating a report for a client should be the main feature, but when I access a
client and the report tab I don't have a way to generate a report — where is it?"*
**Mode:** Batch (chosen for this run; no back-and-forth per item — see Change log).
**Owner:** Francesco.
**Change scope classification:** **Minor-to-Moderate.** Four of the seven items are defects
against artifacts Epic 9 itself was governed by (`EXPERIENCE.md`, and Epic 9's own written
acceptance criteria) — not new requirements. Two are genuine new scope, folded into the same
in-progress stories as light amendments. One is unverified. No PRD change, no architecture
change, no `core/` change, no new epic.

---

## Section 1 — Issue Summary

`sprint-status.yaml` had `epic-9: in-progress` with all nine stories at `review` — every
screen rendered, nothing formally marked `done`. Francesco's first real read of the rebuilt UI
found four of those "reviewed" stories don't actually meet the acceptance criteria already
written for them, plus two reasonable asks the AC never covered.

**Evidence, defect items (verified in code, not assumed):**

1. **No way to start a report run.** `EXPERIENCE.md`'s own route map says
   `/clients/{id}/reports — month history + "Nuovo report"`, and its Month Selection section
   says starting a run is a `YYYY-MM` field "on the **Report** tab (matches the current
   `POST /clients/{id}/report-runs`)". `shell/http/templates/client_reports.html` renders only
   the history list — `grep` across every template for the start-run route returns zero
   matches. The backend (`report_runs.py::start_report_run`) is fully built and unused from
   the UI. This is the literal answer to Francesco's question: **there is currently no page
   that does this.**
2. **Unauthenticated navigation doesn't redirect to sign-in.** Story 9.2's own AC says *"an
   unauthenticated request to `/` … is redirected to sign-in like every other guarded route."*
   `shell/http/auth.py::AuthMiddleware` returns a bare empty-body `401` for every unauthenticated
   request, confirmed by `tests/test_http_home.py::test_anonymous_get_slash_is_empty_body_401_…`.
   Francesco lands on a blank page unless he already knows to type `/login`.
3. **Report-run screens carry no breadcrumb.** `EXPERIENCE.md`'s route map states
   `/report-runs/{run_id} — breadcrumb: Clienti / {nome} / {mese}`. `report.html` (and
   `report_draft.html`/`report_payload.html`) receive no `client` in their route context and
   render no breadcrumb — opening a report gives no visible link back to whose it is. This is
   most of what reads as "too plain and can get confusing."

**New-scope items (not previously specified anywhere):**

4. **Login page has no vertical centring and no mark.** `.auth-view` (tokens.css) centres the
   column horizontally with top padding only; `login.html` has no logo element. `DESIGN.md`
   never specified a wordmark — this is a genuinely new ask.
5. **Home dashboard's recent-runs rows aren't links.** `home.html`'s `dash-run` rows are plain
   `<span>`s. Neither `EXPERIENCE.md` nor the AC required them clickable; Francesco wants to
   open a report straight from Home.

**Unverified:**

6. **"New/edit client forms look bad, buttons unstyled."** Reading `client_new.html` /
   `client_edit.html` and `tokens.css` `.field`/`.btn` rules directly, the DESIGN.md input spec
   (label-above, 24px rhythm, 560px measure, four button variants with focus/disabled states)
   appears fully implemented. No concrete gap found by static inspection, and this session did
   not stand up the Postgres-backed dev server to screenshot it live. **Flagged, not actioned
   — see Section 3.**

**Duplicate of item 1:** "I'd like to start report creation directly from the client UI" and
"is it not possible?" — same gap, same fix.

---

## Section 2 — Impact Analysis

### Epic impact

| Epic | Impact |
|---|---|
| Epic 9 (operator UI rebuild) | Stories **9.1, 9.2, 9.3, 9.6** amended in place — new/clarified AC closing items 1–5 above. Stories 9.4, 9.5, 9.7, 9.8, 9.9 unaffected. No new story, no new epic. |
| All other epics | None — every change is presentation-layer inside `shell/http/`, matching Epic 9's own boundary (no `core/`, no FR, no data model). |

### Artifact conflicts

- **`epics.md`** — amended directly (this run): Story 9.1 gained a sign-in-branding AC; Story
  9.2 gained a dashboard-row-link AC and its existing unauthenticated-redirect AC was made
  specific (302 + `next`, scoped to browser navigations); Story 9.3 gained the Report-tab
  "Nuovo report" AC; Story 9.6 gained the report-run breadcrumb AC. Each amendment is inline-
  dated and marked either "defect, not new scope" or "new scope" so the distinction isn't lost.
- **`sprint-status.yaml`** — `9-1`, `9-2`, `9-3`, `9-6` moved from `review` back to
  `in-progress` (they don't meet their own written AC yet); `9-4`, `9-5`, `9-7` left at
  `review` — no evidence they're deficient. `epic-9` stays `in-progress`. `last_updated`
  already `2026-08-31`.
- **`EXPERIENCE.md` / `DESIGN.md`** — no change needed for items 1–3 (already specify the
  correct behavior; the code just didn't build it). Item 4 (login mark) and item 5 (dashboard
  row links) are small enough to implement directly against the existing token system without
  a formal spec amendment — `DESIGN.md`'s "no gradients, one brand hue" rule bounds the mark's
  design.
- **PRD / Architecture** — no change. Item 2 (auth redirect) does not touch `AD-15`: the
  allowlist, its test, and the opaque-401 behavior for non-navigational requests (HTMX polls,
  anything JSON-shaped) are explicitly preserved in the amended AC.

### Technical impact

- `shell/http/templates/client_reports.html` — add a `Nuovo report` form (month field, submit
  to `POST /clients/{id}/report-runs`), gated on the Client having a stored chart.
- `shell/http/auth.py::AuthMiddleware` — for unauthenticated requests that look like a browser
  navigation (`Accept: text/html`, no `HX-Request` header), return a 302 to `/login?next=<path>`
  instead of the bare 401; `shell/http/app.py`'s `/login` GET/POST handlers read/honor `next`.
  Every other caller shape keeps the current 401.
- `shell/http/routes/report_runs.py` — pass `client` into the `report.html` / `report_draft.html`
  / `report_payload.html` context; those templates render a breadcrumb via (or matching)
  `_client_tabs.html`'s pattern.
- `shell/http/templates/login.html` + `tokens.css` `.auth-view` — flex, vertically centred
  column; a small inline SVG mark using existing tokens.
- `shell/http/templates/home.html` — wrap each `.dash-run` row in an `<a>` to the report or the
  stage view, keyed on the run's terminal status.
- No migration, no new dependency, no `core/` touch.

---

## Section 3 — Recommended Approach

**Direct Adjustment** — amend the four in-progress Epic 9 stories in place (done this run);
route to the dev loop to close them out; leave item 6 for Francesco to confirm live before it
becomes a story.

| Option | Verdict |
|---|---|
| 1. Direct adjustment (amend 9.1/9.2/9.3/9.6, no new epic) | **Selected.** Effort Low–Medium (four of five fixes are template/route wiring against a spec that already exists), risk Low (no `core/`, no architecture change, `AD-15` explicitly preserved). |
| 2. Rollback | Not viable — nothing to revert; Epic 9's foundation (shell, tokens, forms) is sound, only specific screens are incomplete against their own spec. |
| 3. PRD MVP review | Not needed — no scope reduction implied; these are completions, not new requirements at the MVP level. |

**Rationale:** three of five confirmed items are the *dev loop marking a story `review` before
its own acceptance criteria were actually met* — the fix is to finish the story, not replan.
The two genuinely new items (login mark, dashboard links) are small enough to fold into the
same stories rather than open a tenth Epic-9 story or an Epic 10.

**Timeline impact:** small — reopens four stories already `in-progress`/`review`, no new
story count, no dependency change.

---

## Section 4 — Detailed Change Proposals

Applied directly to `epics.md` (this run) — see the four inline, dated amendments under
Stories 9.1, 9.2, 9.3, and 9.6 (each marked "Added" or "Amended," 2026-08-31, correct-course,
with its rationale). Full before/after is in the file's git diff; summarized in Section 1/2
above rather than reproduced twice here.

`sprint-status.yaml`:

```
OLD  9-1-the-application-shell: review
     9-2-a-home-dashboard-instead-of-a-404: review
     9-3-the-clienti-list-and-the-client-scoped-tabs: review
     9-6-the-report-reading-sheet-and-the-payload-view-made-readable: review

NEW  9-1-the-application-shell: in-progress
     9-2-a-home-dashboard-instead-of-a-404: in-progress
     9-3-the-clienti-list-and-the-client-scoped-tabs: in-progress
     9-6-the-report-reading-sheet-and-the-payload-view-made-readable: in-progress
```

(`9-4`, `9-5`, `9-7`, `9-8`, `9-9` unchanged at their current status.)

---

## Section 5 — Implementation Handoff

**Scope classification: Minor-to-Moderate** — closing acceptance criteria on stories already
in flight, plus two small in-scope additions. No replan, no architecture change, no PRD change.

| Recipient | Responsibility |
|---|---|
| **Correct-course (this run)** | Amended `epics.md` (Stories 9.1, 9.2, 9.3, 9.6) and `sprint-status.yaml`; wrote this proposal. Not committed — left for Francesco to review alongside the rest of this session's findings before it lands on `main` (this repo deploys every commit to `main`, docs included). |
| **Dev loop (`bmad-build`, per story)** | Close out 9.1 (login centring + mark), 9.2 (auth redirect + dashboard row links), 9.3 (Nuovo report on the Report tab), 9.6 (report-run breadcrumb) against the amended AC. Suggested order: 9.3 first (highest-value, most confusing gap), then 9.2's redirect, then 9.6's breadcrumb, then 9.1's login styling — independent of each other, any order is safe. |
| **Francesco** | Confirm item 6 (client-form styling) live — open `/clients/new` and `/clients/{id}/edit` in a browser. If a concrete defect is visible, it becomes a fifth amendment to Story 9.4 (currently `review`, left untouched by this proposal); if the forms read fine, no action needed. |

**Success criteria:**

- Opening a Client's Report tab shows a working "Nuovo report" control that starts a run.
- Visiting any protected URL while signed out lands on a styled `/login`, not a blank page.
- Every report-run screen shows which Client and month it belongs to.
- The login screen is centred with a small mark; dashboard rows open their report/run.
- `uv run pytest` green before any push (per `AGENTS.md`).

---

## Change log

- 2026-08-31 — proposal created and applied (Correct Course, Batch mode, background session).
  `epics.md`: amended Stories 9.1, 9.2, 9.3, 9.6 with dated, rationale-tagged AC additions.
  `sprint-status.yaml`: `9-1`, `9-2`, `9-3`, `9-6` moved `review` → `in-progress`. Not yet
  committed — awaiting Francesco's review.
