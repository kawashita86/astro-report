---
title: 'Story 9.5 — A stage track I can watch, and a Gate failure I can read'
type: 'feature'
created: '2026-08-30'
status: 'done'
review_loop_iteration: 1
baseline_commit: '381485d3aacbe1158539f60207e18d717404630c'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/EXPERIENCE.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/ux-designs/ux-astro-report-2026-08-28/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The run stage view (`report_run_poll.html`) is an unstyled
`<p>Stage: draft_ready</p>` that polls forever even after a terminal stage,
leaks the raw English stage token, and — on a Gate failure — shows a bare
`<ul>` of `violation.kind` strings on the draft page with no way to act on it.
Francesco cannot tell at a glance whether to wait, leave, or regenerate, and a
regeneration-bound-exhausted run has no operator-facing recovery path at all
(regeneration is automatic-only inside `shell/runner/driver.py`, bounded at 3).

**Approach:** Render the `ReportRun` lifecycle as the DESIGN.md six-node stage
track (tema natale · transiti · Payload · bozza · verifica di fondatezza ·
esportazione), each node pending / active / done / failed with an Italian
progress-tense caption, polling at a fixed 2s cadence that pauses while the tab
is hidden and stops on any terminal stage. Re-flow the Gate-failure surface on
`/draft` into a `danger` panel — one card per violation (Italian kind label, the
Sezione, the sentence as a blockquote, the detail, cited entry IDs as mono chips
or *nessuna*), each linking to its Sezione anchor in the draft below — with a
**Rigenera** primary action backed by one new shell-only route
`POST /report-runs/{run_id}/regenerate` that rewinds a Gate-failed run to
`payload_ready` so the next poll re-runs draft + Gate for one more attempt. A
non-Gate terminal failure instead shows the failed node in `danger` and names
the stage and reason — no Rigenera. Presentation, one recovery route, and CSS
only: no `core/` change, no data-model change, no change to `advance()` or any
other route contract.

## Boundaries & Constraints

**Always:**
- **Read-only against the stage machine.** `advance()`, `_STAGE_SEQUENCE`, the
  stage functions, `ReportRun`'s columns, and every existing `/report-runs/*`
  route contract (status codes, redirects, HTMX fragment vs full-page split,
  persisted data) are unchanged. The stage view derives node state purely from
  the persisted `run.stage` (nullable) + `run.failed_at`.
- **The one new route is shell-only and additive.**
  `POST /report-runs/{run_id}/regenerate`: authenticated by default (not in
  `shell.http.auth.ALLOWLIST`, which stays exactly `{"/healthz", "/login"}`);
  on a Gate-failed run it sets `run.failed_at = None`, `run.failure_reason =
  None`, `run.stage = "payload_ready"`, `run.updated_at = now`, commits, and
  `303`-redirects to `/report-runs/{run_id}`. It does **not** touch
  `run.regeneration_count` (the driver's existing `except GateFailedError` path
  increments it on the next failing Gate check) and never calls `advance()`
  itself — the next poll drives the re-run.
- **Progressive enhancement holds.** The stage track renders and shows the true
  current stage with JS disabled (no live updates, but never a broken state).
  Rigenera is a full-page `<form method="post">` + redirect; JS only upgrades it
  to a focus-trapped confirm modal. Vedi Payload / Vedi bozza are plain links.
- Every visible string is Italian per EXPERIENCE.md. Stage captions are the
  verbatim progress-tense phrases from EXPERIENCE.md "Voice and Tone → Stage
  labels": `Calcolo del tema natale`, `Ricerca dei transiti`, `Assemblaggio del
  Payload`, `Generazione della bozza`, `Verifica di fondatezza`, `Pronto per
  l'esportazione`; terminal `Esportato` / `Verifica non superata`. Node labels:
  `Tema natale`, `Transiti`, `Payload`, `Bozza`, `Verifica di fondatezza`,
  `Esportazione`. The Gate-failure panel heading is exactly `Verifica di
  fondatezza non superata`. Violation `kind` renders as an Italian label
  (`empty_citation` → `Citazione vuota`, `invented_fact` → `Fatto inventato`,
  `contradicted_fact` → `Fatto contraddetto`, `date_token_in_day_list` → `Data
  in un elenco di giorni`); an unknown kind falls back to the raw token.
- **A11y floor (WCAG 2.1 AA).** One `h1` per screen kept; the stage caption sits
  in a `role="status"` `aria-live="polite"` region; the poll-error banner is
  `role="alert"`. The active-dot pulse, and any sheen/transition added here, are
  suppressed under `prefers-reduced-motion`. Stage-dot and focus-ring colours
  hold ≥ 3:1 non-text contrast in both themes; caption/body text ≥ 4.5:1.
  Interactive targets ≥ 24×24px.
- All touched templates keep `{% extends %}` (`report_run_poll.html` keeps its
  `_bare.html`-when-`hx-request` / `base.html`-otherwise split;
  `report_draft.html` keeps `base.html`). No page ships a second `<html>`.
- Polling stops (no `hx-trigger` in the swapped fragment) when
  `run.failed_at` is set **or** `run.stage in ("gate_passed", "exported")`.

**Ask First:**
- Any need to change `advance()`, `_MAX_REGENERATIONS`, a `ReportRun` column, or
  a `core/` type to make Rigenera work. The spec's design gives one more real
  attempt per click without any of these — if that proves false during
  execution, HALT.
- Restyling the eight-Section reading body of `report_draft.html` /
  `report_payload.html` — that is Story 9.6. This story touches
  `report_draft.html` only for the Gate-failure / non-Gate-failure panel and
  for adding `id="sezione-{name}"` anchors to the existing section loop.

**Never:**
- No background worker, thread, queue, or cron; no second stage driven per poll;
  no `advance()` call from the regenerate route.
- No server-side enforcement gating Rigenera beyond the wrong-state 404 — no
  new auth, no typed-name gate (it is a recovery action, not a destroy).
- No custom date/time widget; no new brand colour; no shadow for structure
  (elevation only for the confirm modal).
- No change to `report.html`, `report_export.html`, the Markdown export, the
  disposition flow, or Epic 6/7 behaviour.
- Do not recompute the Gate in the view — violations are read from the persisted
  `StoredGateResult` exactly as `view_report_draft` already does.
- The Gate-failure discriminator must be scoped to the run's **current**
  failure, not to "a failing `StoredGateResult` has ever existed for this
  `run_id`." A run that failed the Gate once, was rewound by Rigenera, and
  then later fails again **for an unrelated reason in the same or a later
  cycle** (no new Gate check ran) must be treated as a non-Gate failure —
  `run.failure_reason` shown, no stale violation cards, no `Rigenera`. An
  existence-only check across the run's whole history is explicitly
  insufficient (revealed by review-loop 1 of this spec); do not reintroduce
  it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Run just started | `run.stage is None`, `failed_at is None` | Poll fragment: node 0 (`Tema natale`) active, nodes 1-5 pending, caption `Calcolo del tema natale`, `hx-trigger` present | N/A |
| Mid-run | `run.stage == "transits_ready"` | Nodes 0-1 done, node 2 (`Payload`) active, caption `Assemblaggio del Payload`, `hx-trigger` present | N/A |
| Payload ready | `run.stage == "payload_ready"` | Nodes 0-2 done, node 3 active, caption `Generazione della bozza`; a `Vedi Payload` link to `/payload` | N/A |
| Gate running | `run.stage == "draft_ready"`, `failed_at is None` | Nodes 0-3 done, node 4 (`Verifica di fondatezza`) active, caption `Verifica di fondatezza`; `Vedi Payload` link | N/A |
| Gate passed | `run.stage == "gate_passed"` | Nodes 0-4 done, node 5 active, caption `Pronto per l'esportazione`; `Vedi report` link; **no** `hx-trigger` | N/A |
| Exported | `run.stage == "exported"` | All six nodes done, caption `Esportato`; `Vedi report` link; no `hx-trigger` | N/A |
| Tab hidden | any running state | `htmx:beforeRequest` on `#run-status` is prevented while `document.hidden`; timer keeps ticking, no request fires; resumes on visibility | N/A |
| Poll network error | `htmx:responseError` / `htmx:sendError` from `#run-status` | Inline `role="alert"` `.banner--danger` ("Connessione persa — nuovo tentativo…") revealed inside the region; hidden again on the next 2xx | Banner only; polling continues at 2s (5s/15s backoff + `Riprova` deferred to Story 9.8) |
| Closed-tab resume | reopen a run at `payload_ready` | Full page via `base.html`: true stage rendered, polling resumes, next poll advances one stage — no "lost work" copy | N/A |
| Gate failure (bound exhausted) | `run.failed_at` set, `run.stage == "draft_ready"`, a failing `StoredGateResult` exists | `/draft`: `danger` panel headed `Verifica di fondatezza non superata`, `run.failure_reason`, one `.violation-card` per violation (Italian kind, `SECTION_TITLES[section]`, sentence in `<blockquote>`, detail, entry-id `.badge-mono` chips or `nessuna`), each card an anchor to `#sezione-{section}`; primary `Rigenera` form, secondary `Vedi Payload`. Stage view: node 4 failed, caption `Verifica non superata`, no `hx-trigger` | N/A |
| Non-Gate terminal failure | `run.failed_at` set, no failing `StoredGateResult` (e.g. `run.stage == "natal_ready"`) | Stage view: the first-incomplete node shown failed, caption `Verifica non superata` replaced by the reason; `run.failure_reason` shown, **no** Rigenera. `/draft` for a generic failure with a stored draft: `.panel--danger` naming the stage + reason, **no** Rigenera form | `/draft` still `404`s when no `ReportDraft` row exists (unchanged) |
| Non-Gate failure after an earlier, since-superseded Gate failure | Run failed the Gate once (a failing `StoredGateResult` row exists), was rewound via `Rigenera`, then **this** cycle's terminal failure is *not* a new `GateFailedError` (e.g. `_MAX_STAGE_FAILURES` exhausted on `draft_ready`/`gate_passed` for an unrelated error, or any earlier stage fails on a later cycle) | Treated identically to "Non-Gate terminal failure" above: `run.failure_reason` shown, **no** Rigenera, **no** stale violation cards from the earlier cycle — even though a failing `StoredGateResult` row exists somewhere in the run's history | N/A |
| Regenerate a Gate-failed run | `POST /report-runs/{id}/regenerate`, run is Gate-failed | `303` → `/report-runs/{id}`; afterward `failed_at is None`, `failure_reason is None`, `stage == "payload_ready"`, `regeneration_count` unchanged; the next poll runs `draft_ready` | N/A |
| Regenerate wrong state | `POST …/regenerate` on a run with `failed_at is None`, or a non-Gate failure, or unknown id | `404` (mirrors the module's "wrong state / no such run" convention) | `404` |
| Regenerate anonymous | no session | `401` before the handler (AuthMiddleware) | `401` |

</frozen-after-approval>

## Code Map

- `shell/http/stage_view.py` — **new** pure view-model module, mirroring
  `shell/http/draft_view.py` / `shell/http/payload_view.py` (no I/O, no DB).
  - `STAGE_NODES: tuple[tuple[str, str], ...]` — the six `(stage_key, italian_label)`
    pairs, `stage_key` from `shell/runner/driver.py::_STAGE_SEQUENCE`
    (`natal_ready` … `exported`). Bound to `_STAGE_SEQUENCE` by a test so a
    seventh stage cannot ship without a label.
  - `_STAGE_CAPTIONS: dict[str, str]` — progress-tense Italian per stage_key
    (the phrase for the stage that is *active* when `run.stage` names its
    predecessor), plus terminal `exported` → `Esportato`.
  - `build_stage_track(stage: str | None, *, failed: bool, gate_failed: bool) ->
    list[dict]` — one dict per node: `{"key", "label", "state"}` where `state ∈
    {"pending","active","done","failed"}`. `done_index = -1` if `stage is None`
    else `_STAGE_SEQUENCE.index(stage)`. Node `i`: `i <= done_index` → `done`;
    `failed and i == done_index + 1` → `failed`; `i == done_index + 1` → `active`;
    else `pending`. (`gate_passed` ⇒ `done_index == 4`, node 5 active;
    `exported` ⇒ all done.)
  - `stage_caption(stage, *, failed, gate_failed, failure_reason) -> str` —
    `Verifica non superata` when `gate_failed`; `failure_reason` when `failed`
    and not `gate_failed`; the active node's `_STAGE_CAPTIONS` phrase otherwise;
    `Esportato` at `exported`.
  - `VIOLATION_KIND_LABELS: dict[str, str]` — the four Italian kind labels;
    `violation_kind_label(kind)` returns the label or the raw `kind`.
- `shell/http/routes/report_runs.py` — presentation-context only, plus one new route.
  - **new** `_current_cycle_gate_failure(session, run) -> StoredGateResult | None`
    (replaces `_has_failing_gate_result`) — the latest `StoredGateResult` for
    `run.id` with `passed.is_(False)`, ordered `regeneration_count.desc()`
    (same query `view_report_draft` already runs), returned **only** when
    `run.failed_at is not None` and
    `run.failed_at - result.created_at <= _GATE_RESULT_CORRELATION_WINDOW`
    (module constant, `timedelta(seconds=2)`) — else `None`. A real Gate
    check and the `failed_at` it produces are written in the same
    `advance()` call (sub-second gap); a stale row from an earlier,
    Rigenera-superseded cycle is separated from any later `failed_at` by well
    over that window — `/regenerate`'s `303` redirects straight to
    `/report-runs/{id}` (`poll_report_run`), so the first `advance()` for the
    rewound run fires immediately, on that redirect's own page load, not on
    some later timed poll; the real margin instead comes from
    `_MAX_STAGE_FAILURES` (`shell/runner/driver.py`, 5), which requires 5
    *consecutive* stage-failure exhaustions across separate, ~2s-apart polls
    before a fresh non-Gate terminal failure can occur — several poll
    intervals, not one. Review-loop 1's finding was that an existence-only
    check (no window) keeps matching that stale row forever; review-loop 2
    corrected this bullet's own "next poll" timing claim. One indexed,
    read-only query, run only on a failed run — no new `ReportRun` column
    (Ask First honored).
  - `poll_report_run` (l.263) — after `_advance_run(...)`, compute
    `gate_failed = _current_cycle_gate_failure(session, run) is not None`.
    Pass
    `stage_track=build_stage_track(run.stage, failed=run.failed_at is not None,
    gate_failed=gate_failed)`, `stage_caption=stage_caption(...)`,
    `gate_failed=gate_failed`, `poll_active = run.failed_at is None and
    run.stage not in ("gate_passed", "exported")` into the template context
    alongside the existing `run`. No status-code / redirect / advance change.
  - `view_report_draft` (l.309) — when `run.failed_at is not None`, replace
    its existing unconditional
    `select(StoredGateResult).where(passed.is_(False)).order_by(regeneration_count.desc())`
    fetch with `stored_gate_result = _current_cycle_gate_failure(session, run)`
    (review-loop 1: the old unconditional version is the same stale-history
    bug — it surfaces the old cycle's `violations` whenever a non-Gate
    failure follows a Rigenera rewind, impossible before this story added
    `/regenerate`). `context["violations"]` stays `stored_gate_result.violations
    if stored_gate_result is not None else []`; put `gate_failed =
    stored_gate_result is not None` and `section_titles` (already present)
    into context; `section_order` is already there. Still read-only against
    `StoredGateResult` — a query-scoping change, not a Gate recomputation.
  - **new** `@router.post("/report-runs/{run_id}/regenerate", include_in_schema=False)`
    `regenerate_report_run(run_id, session)` — `session.get(ReportRun, run_id)`,
    `404` if `None`; `404` unless `run.failed_at is not None` **and**
    `_current_cycle_gate_failure(session, run) is not None` (not the old
    any-history-ever existence check — otherwise a non-Gate-failed run with
    an older resolved Gate failure could still be regenerated by direct POST
    even though the UI hides the button); then set
    `failed_at=None`,
    `failure_reason=None`, `stage="payload_ready"`, `updated_at=datetime.now(UTC)`,
    `session.add(run)`, `session.commit()`, `RedirectResponse(f"/report-runs/{run_id}",
    status_code=303)`. Docstring: shell-only recovery, driver still owns the
    count increment, no `advance()` call here (mirrors `start_report_run`'s
    "returns immediately, first stage runs on the first poll").
- `shell/http/templates/report_run_poll.html` — replace the `<p>Stage: …</p>` /
  `<p>Failed: …</p>` bodies inside `#run-status` with: a `<ol class="stage-track">`
  of `{% for node in stage_track %}<li class="stage-track__node stage-track__node--{{ node.state }}">`
  (dot `<span class="stage-track__dot">` + `<span class="stage-track__label">{{ node.label }}</span>`,
  connector between nodes); a `<p class="stage-caption" role="status" aria-live="polite">{{ stage_caption }}</p>`;
  a hidden `<p class="banner banner--danger" role="alert" data-poll-error hidden>Connessione persa — nuovo tentativo…</p>`.
  Gate the `hx-get`/`hx-trigger`/`hx-swap` attrs on `{% if poll_active %}`
  (replaces the current `{% if not run.failed_at %}`). Keep the existing
  `Vedi Payload` / `Vedi Draft` (→ `Vedi bozza`) / `Vedi report` conditional
  links; on `run.failed_at` with `gate_failed`, show `Vedi bozza`; relabel to
  Italian. `id="run-status"` unchanged.
- `shell/http/templates/report_draft.html` — replace the
  `{% if run %}<section id="gate-failures">` block with two mutually-exclusive
  panels:
  - `{% if violations %}` → `<section class="panel panel--danger" aria-labelledby="gate-fail-h">`
    `<h2 id="gate-fail-h">Verifica di fondatezza non superata</h2>`,
    `<p class="panel__body">{{ run.failure_reason }}</p>`, then
    `{% for v in violations %}<article class="violation-card">` with
    `<p class="violation-card__kind">{{ violation_kind_label(v.kind) }}</p>`
    (expose the helper as a Jinja global or pass a pre-mapped list — see Design
    Notes), `<p>{{ section_titles[v.section] }}</p>`,
    `<blockquote>{{ v.sentence }}</blockquote>`, `<p class="violation-card__detail">{{ v.detail }}</p>`,
    `<p class="violation-card__chips">{% for eid in v.entry_ids %}<span class="badge-mono">{{ eid }}</span>{% else %}nessuna{% endfor %}</p>`,
    `<a href="#sezione-{{ v.section }}">Vai alla sezione</a>`. Then
    `<div class="panel__actions">`: a full-page `<form method="post" action="/report-runs/{{ run.id }}/regenerate">`
    `<button class="btn btn--primary" data-regen-trigger>Rigenera</button></form>`
    and `<a class="btn btn--secondary" href="/report-runs/{{ run.id }}/payload">Vedi Payload</a>`.
    Inline `<div class="modal-scrim" data-regen-modal hidden>` → `<div class="modal" role="dialog"
    aria-modal="true" aria-labelledby="regen-h">` with `<h2 id="regen-h" class="modal__title">Rigenerare il report?</h2>`,
    `<p class="modal__body">La rigenerazione sostituisce l'intero report e incrementa il contatore di rigenerazioni.</p>`,
    `<div class="modal__actions">` a `data-regen-cancel` `.btn--secondary` `Annulla`
    and a `<form method="post" action="/report-runs/{{ run.id }}/regenerate"><button class="btn btn--primary">Rigenera</button></form>`.
  - `{% elif run %}` → `<section class="panel panel--danger"><h2>Generazione non riuscita</h2><p class="panel__body">{{ run.failure_reason }}</p><a class="btn btn--secondary" href="/report-runs/{{ run.id }}/payload">Vedi Payload</a></section>`.
  - In the existing `{% for section_name in section_order %}` loop, add
    `id="sezione-{{ section_name }}"` to the `<section>`. Leave its reading body
    otherwise as-is (Story 9.6).
- `shell/http/static/shell.js` — add **section 6. Report-run stage view**:
  on `document.body` `htmx:beforeRequest`, `evt.preventDefault()` when
  `document.hidden` and `evt.detail.elt` is (or is inside) `#run-status`;
  on `htmx:responseError` / `htmx:sendError` for `#run-status`, un-`hidden` the
  `[data-poll-error]` node; on `htmx:afterOnLoad` with a 2xx, re-`hidden` it.
  Add **section 7. Regenerate-confirm modal**: guarded on
  `[data-regen-modal]`; open on `[data-regen-trigger]` click
  (`preventDefault`), focus-trap cancel-first, `Esc` / scrim / `[data-regen-cancel]`
  close, restore focus to trigger — no typed-name gate. **Refactor:** extract the
  drawer's + Story 9.4 delete-modal's shared focus-trap into one
  `trapFocus(container, { onEscape, initialFocus })` helper and route all three
  (drawer, delete modal, regen modal) through it — the Story 9.4 Design Notes
  called for this once a third consumer appeared. Update the file docstring
  ("Seven jobs …").
- `shell/http/static/tokens.css` — append a `PROVISIONAL — Story 9.5` block
  after the Story 9.4 block (ends l.1160): `.stage-track` (flex row, `wrap`,
  `--space-md` gap, `list-style:none`, `padding:0`), `.stage-track__node`
  (flex column, centre, `--space-xs` gap), `.stage-track__dot`
  (`12px` square, `--radius-full`, `background` per state:
  `--border-strong` pending / `--primary-700` active / `--success` done /
  `--danger` failed — via `.stage-track__node--{state} .stage-track__dot`),
  `.stage-track__node--active .stage-track__dot` a gentle `@keyframes`
  pulse, `.stage-track__label` (`--font-small`, `--ink-secondary`;
  `--ink-primary` when `--active`; `--danger` when `--failed`),
  `.stage-track__connector` (1px `--border-hairline`, flex filler),
  `.stage-caption` (`--font-body`, `--ink-secondary`, `--space-md` top margin),
  `.violation-card` (`1px --border-hairline`, `--radius-md`, `--space-base`
  padding, `--space-md` stack gap), `.violation-card__kind` (`--font-label`
  weight, `--ink-primary`), `.violation-card blockquote`
  (`margin:0`, `border-left:3px solid --border-strong`, `padding-left:--space-md`,
  `--ink-primary`), `.violation-card__detail` (`--ink-secondary`),
  `.violation-card__chips` (flex `wrap`, `--space-xs` gap; bare text `nessuna`
  reads as `--ink-secondary`). Extend the existing
  `@media (prefers-reduced-motion: reduce)` block with
  `.stage-track__node--active .stage-track__dot { animation: none; }`.
  Reuse `.panel`, `.panel--danger`, `.panel__body`, `.panel__actions`, `.btn*`,
  `.banner`, `.banner--danger`, `.badge-mono`, `.modal-scrim`, `.modal`,
  `.modal__title/__body/__actions` verbatim from Stories 9.2-9.4. Semantic
  tokens only; comment as Story 9.8 consolidation fodder.
- `tests/test_stage_view.py` — **new**. Unit-test `build_stage_track` /
  `stage_caption` / `violation_kind_label` across the I/O Matrix stage states;
  assert `len(STAGE_NODES) == len(_STAGE_SEQUENCE)` and keys match in order.
- `tests/test_http_report_runs.py` — amend + add:
  - Update the Story 5.5 assertions that check `"empty_citation" in
    response.text` (l.879+, l.944+) and the section-name check to the Italian
    labels (`Citazione vuota`, `SECTION_TITLES` heading) and add: `.panel--danger`,
    heading `Verifica di fondatezza non superata`, one `.violation-card` per
    violation, `<blockquote>` with the sentence, `.badge-mono` per entry id (or
    `nessuna`), `href="#sezione-energia_generale"` + a matching
    `id="sezione-energia_generale"`, and a `<form … action="…/regenerate">`.
  - Update `test_getting_the_draft_for_a_generic_failure_with_a_grounded_draft…`
    (l.1067): `.panel--danger`, `run.failure_reason` shown, **no** `/regenerate`
    form.
  - `test_a_failed_runs_poll_fragment_shows_the_reason_with_no_hx_trigger`
    (l.823): keep the reason + no-`hx-trigger` asserts; add the failed node
    (`stage-track__node--failed`) renders.
  - Add `# --- Story 9.5: the stage track` cases: the running-state fragment
    renders six `.stage-track__node`s with the six Italian labels and the
    active node + Italian caption; a `gate_passed` fragment has no `hx-trigger`;
    an `exported` fragment shows all-done + no `hx-trigger`. (Audit
    `test_polling_an_already_completed_run…` l.391 and
    `test_the_poll_view_links_to_the_report…` l.1454 for any `hx-trigger`
    presence assumption and adjust.)
  - Add `# --- Story 9.5: POST /report-runs/{run_id}/regenerate`: anonymous →
    401; unknown → 404; `failed_at is None` → 404; non-Gate failure (no failing
    `StoredGateResult`) → 404; Gate-failed run (build one like
    `_a_bound_exhausted_run` + its `StoredGateResult`) → 303 to
    `/report-runs/{id}`, then `run.failed_at is None`,
    `run.failure_reason is None`, `run.stage == "payload_ready"`,
    `run.regeneration_count == 4` (unchanged); one `fake_advance`-style poll
    afterward runs `draft_ready`.
- `tests/test_http_shell.py` — `_render_poll` (l.196) fake `_Run` needs
  `regeneration_count`/`failure_reason` attrs and the render call must pass
  `stage_track` / `stage_caption` / `poll_active` (import from
  `shell.http.stage_view`). Update
  `test_an_htmx_poll_renders_only_the_fragment_no_document_skeleton` and
  `test_a_full_page_poll_renders_through_base_html` to assert on the Italian
  caption / `.stage-track` instead of the raw `"transits_ready"` string. The
  `_MIGRATED_ROUTES` tuple is unchanged (`/report-runs/*` stay covered by their
  own suite — they need a seeded run).

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/stage_view.py` — new pure module: `STAGE_NODES`,
  `_STAGE_CAPTIONS`, `VIOLATION_KIND_LABELS`, `build_stage_track`,
  `stage_caption`, `violation_kind_label`. No I/O; bound to `_STAGE_SEQUENCE`.
- [x] `shell/http/routes/report_runs.py` — `poll_report_run`: pass
  `stage_track` / `stage_caption` / `gate_failed` / `poll_active` into the
  template context, computing `gate_failed` with the review-loop-1 current
  -cycle discriminator (not a failing-`StoredGateResult` existence check —
  see Code Map / Design Notes). `view_report_draft`: derive its `gate_failed`
  and `violations` the same way, not `bool(context["violations"])`. Add
  `POST /report-runs/{run_id}/regenerate` (guards: 404 unknown / 404
  not-current-cycle-Gate-failed; then clear `failed_at`/`failure_reason`, set
  `stage="payload_ready"`, `updated_at=now`, commit, 303). No other contract
  change; `ALLOWLIST` untouched.
- [x] `shell/http/templates/report_run_poll.html` — render the six-node
  `.stage-track` + `.stage-caption` (`role="status"`/`aria-live="polite"`) +
  hidden `[data-poll-error]` `role="alert"` banner inside `#run-status`; gate
  the `hx-*` polling attrs on `poll_active`; keep/relabel the ready-state links
  in Italian (`Vedi bozza` on a Gate failure).
- [x] `shell/http/templates/report_draft.html` — Gate-failure `.panel--danger`
  (heading `Verifica di fondatezza non superata`, one `.violation-card` per
  violation with Italian kind label, `SECTION_TITLES` Sezione, `<blockquote>`
  sentence, detail, `.badge-mono` chips or `nessuna`, `#sezione-{section}`
  anchor link), `Rigenera` form + inline confirm modal, `Vedi Payload`
  secondary; a distinct non-Gate `.panel--danger` (no Rigenera); add
  `id="sezione-{{ section_name }}"` to the section loop.
- [x] `shell/http/static/shell.js` — section 6 (pause polling while
  `document.hidden`; toggle the `[data-poll-error]` banner on
  `htmx:responseError`/`htmx:sendError` / next 2xx); section 7
  (regenerate-confirm modal, cancel-focused, no typed-name gate); extract a
  shared `trapFocus` helper for drawer + delete modal + regen modal; docstring
  → "Seven jobs".
- [x] `shell/http/static/tokens.css` — append the `PROVISIONAL — Story 9.5`
  block (`.stage-track*`, `.stage-caption`, `.violation-card*`); extend the
  `prefers-reduced-motion` block to kill the active-dot pulse. Semantic tokens
  only; both-theme contrast (dot ≥ 3:1 non-text, text ≥ 4.5:1).
- [x] `tests/test_stage_view.py` — new unit suite over the I/O Matrix stage
  states + the `STAGE_NODES` ⇄ `_STAGE_SEQUENCE` binding.
- [x] `tests/test_http_report_runs.py` — amend the Story 5.5 / generic-failure
  draft-view assertions to Italian + the panel/card/anchor/Rigenera-form
  structure; add stage-track fragment cases and the `POST …/regenerate` route
  cases; audit poll-view tests for stale `hx-trigger` assumptions. Add the
  review-loop-1 case from the I/O Matrix: a run with a failing
  `StoredGateResult` from an earlier cycle, rewound via `/regenerate`, then
  terminally failed again for a non-Gate reason this cycle — assert the poll
  fragment and `/draft` both show the non-Gate panel (no stale violation
  cards, no `Rigenera`), and that a direct `POST …/regenerate` on that run
  404s.
- [x] `tests/test_http_shell.py` — update `_render_poll` (fake run attrs +
  pass the new context) and the two poll-render assertions to the Italian
  caption / `.stage-track`.

**Acceptance Criteria:**
- Given `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`,
  when the story is done, then all pass (ruff format: see the Story 9.4
  Verification note — the pinned 0.16.3 flags ~72 pre-existing files repo-wide;
  new lines here are conformed, no repo-wide reformat).
- Given `/report-runs/{id}` for an authenticated caller at any non-terminal
  stage, when rendered full-page, then the response has exactly one
  `<html lang="it">`, exactly one `<h1>`, the sidebar `Clienti` item
  `is-active`, six `.stage-track__node`s in `_STAGE_SEQUENCE` order with Italian
  labels, and a `role="status"` caption; when rendered as an `hx-request`
  fragment, then no `<html>`/`<head>`/`htmx.min.js` and `id="run-status"` is
  present.
- Given a run at `gate_passed` or `exported`, when the poll fragment renders,
  then it contains no `hx-trigger` (polling stopped).
- Given `shell.http.auth.ALLOWLIST`, when the story is done, then it is still
  exactly `{"/healthz", "/login"}` and every pre-existing `/report-runs/*`
  status-code / 404 / redirect / fragment-split test passes unchanged (only the
  Gate-failure copy and the two `test_http_shell` poll assertions change).
- Given a Gate-failed run, when `POST /report-runs/{id}/regenerate` is called,
  then it 303-redirects to `/report-runs/{id}`, the run has
  `failed_at is None` / `failure_reason is None` / `stage == "payload_ready"` /
  unchanged `regeneration_count`, and no `advance()` ran inside the request.
- Given `prefers-reduced-motion`, when the stage view renders, then the
  active-dot pulse animation is `none` and no scripted animation runs; when the
  regenerate confirm modal opens, then no transition runs.
- Given JavaScript disabled, when a Gate-failed run's `/draft` renders, then
  `Rigenera` is a working full-page `<form method="post">` and the stage track
  still shows the true current stage.

## Spec Change Log

**Review-loop 1 (intent_gap).** Triggering finding (blind-hunter review of
the review-loop-0 diff): `gate_failed` / `_has_failing_gate_result` /
`regenerate_report_run`'s guard all determined "is this a Gate failure" by
whether a failing `StoredGateResult` has **ever** existed for `run.id` — not
whether the Gate caused *this* `failed_at`. The frozen I/O Matrix's own
"Non-Gate terminal failure" row and the Boundaries/Design-Notes discriminator
description baked in the same existence-only check, so this was an intent gap
(the frozen intent never disambiguated the case a `/regenerate` rewind makes
possible for the first time in the app: an old resolved Gate failure sitting
in history while the run's *current* failure is unrelated), not an
implementation slip.

Known-bad state avoided: a non-Gate-failed run — after an earlier,
Rigenera-resolved Gate failure — showing the Gate-failure panel with stale
violation cards from the earlier cycle and an actionable `Rigenera` button
(itself exploitable by a direct `POST` even with the button hidden, since the
route's own 404 guard used the same broken check).

Amended (all outside `<frozen-after-approval>` except the Boundaries note and
the new I/O Matrix row, which the human explicitly authorized renegotiating
when choosing to loop back rather than defer): Boundaries & Constraints (new
"Always" bullet), I/O & Edge-Case Matrix (new row), Code Map (`poll_report_run`,
`view_report_draft`, `regenerate_report_run` bullets), Design Notes (the
`gate_failed` note), Tasks & Acceptance (unchecked all — code was reverted;
sharpened the `report_runs.py` and `test_http_report_runs.py` bullets).

KEEP — everything else from review-loop 0 held up and must survive
re-derivation unchanged: the six-node `stage_view.py` module shape
(`STAGE_NODES` / `_STAGE_CAPTIONS` / `build_stage_track` / `stage_caption` /
`violation_kind_label`, bound to `_STAGE_SEQUENCE` by a test); the
`poll_active` gating; the `Rigenera` route's shape (404-unknown, 404-wrong
-state, no `advance()` call, `regeneration_count` untouched, 303 redirect);
the violation-card markup (`kind_label` pre-mapped in the view, `Sezione`
anchor, `.badge-mono`/`nessuna` chips); the `trapFocus` extraction for
drawer + delete modal + regen modal; the `id="sezione-{name}"` anchors; the
stage-track `<ol>` semantics and reduced-motion handling. None of these were
implicated by the finding.

## Design Notes

**One more real attempt per Rigenera click, with no driver change.** On a
bound-exhausted Gate failure the driver leaves `run.stage == "draft_ready"`,
`run.regeneration_count == _MAX_REGENERATIONS + 1` (4), and a failing
`StoredGateResult`. The regenerate route rewinds `stage` to `payload_ready` and
clears `failed_at`; the next poll's `advance()` (which early-returns only on
`failed_at`) runs `_run_draft_ready` — a fresh `GeneratedDraft` persisted at
`attempt=run.regeneration_count` (4, no unique-index collision with attempts
0-3) — then `_run_gate_passed` on the poll after. If that Gate passes, a
`Report` + passing `StoredGateResult` are written and `run.stage` reaches
`gate_passed`. If it fails again, the driver's own `except GateFailedError`
branch writes a failing `StoredGateResult` (`regeneration_count=4`), then
`run.regeneration_count += 1` → 5 (> `_MAX_REGENERATIONS`) → terminal again,
`stage` back at `draft_ready`. So the count still only ever moves inside the
driver, monotonically, and each manual click buys exactly one cycle. The route
never calls `advance()` — same shape as `start_report_run`.

**Why a wrong-state 404, not 409.** Every "not ready / no such run" branch in
`report_runs.py` (`view_report`, `view_report_payload`, `view_report_draft`,
the export routes) collapses to 404. Matching that keeps the module's error
surface uniform; the confirm modal + redirect makes a stale POST rare, and a
double-submit second hit simply 404s (the first already cleared `failed_at`).

**`gate_failed` is not a plain existence check (review-loop 1).** A Gate
failure and a generic terminal failure both set `run.failed_at`; a persisted
failing `StoredGateResult` is necessary but, once `/regenerate` can rewind a
run and let it fail again for an unrelated reason, no longer *sufficient* —
"has this run ever failed the Gate" and "did the Gate cause *this*
`failed_at`" are different questions, and only the second is the one the UI
needs answered. The existence-only version of this check shipped in
review-loop 0 and was caught by the blind-hunter review before merge.
`_current_cycle_gate_failure` (Code Map) fixes this with a
`created_at`-to-`failed_at` correlation window instead of a new column: a
real Gate check and the terminal `failed_at` it produces are written in the
same `advance()` call (sub-second gap, well inside the 2s window); a stale
row from an earlier, Rigenera-superseded cycle is always separated from a
later `failed_at` by well over that window — not because the next
`advance()` waits for a timed poll (it doesn't: `/regenerate`'s `303`
redirects straight to `/report-runs/{id}`, so the first `advance()` for the
rewound run fires immediately, on that redirect's own page load), but
because `_MAX_STAGE_FAILURES` (`shell/runner/driver.py`, 5) requires 5
*consecutive* stage-failure exhaustions across separate, ~2s-apart polls
before a fresh non-Gate terminal failure can occur — several poll intervals
of real margin, not one (review-loop 2 corrected this reasoning; review-loop
1's original "next poll" framing was inaccurate about *when* the first
post-rewind `advance()` runs, though its conclusion — that the margin is
comfortably over 2s — still held). `tests/test_http_report_runs.py`'s new
review-loop-1 case must construct the stale row with an explicitly backdated
`created_at` (not rely on real elapsed time) so the test is deterministic
regardless of how
fast it executes.

**Kind → Italian label lives in `stage_view.py`, surfaced to Jinja.** Either
register `violation_kind_label` as a template global in the `Jinja2Templates`
env (one `_templates.env.globals[...] =` line, mirrors nothing yet but is the
least-surprising), or map the violations to `{**v, "kind_label": …}` dicts in
`view_report_draft` before render. Prefer the pre-mapped list — it keeps the
template logic-free and needs no env mutation. `SECTION_TITLES` is already
imported in `report_runs.py` and already in the draft context.

**Stage-track markup is an `<ol>`.** The lifecycle is an ordered sequence; an
ordered list is the honest semantics and gives screen-reader users position
info for free. Connectors are decorative `<span>`s (`aria-hidden`).

## Verification

**Commands:**
- `uv run pytest tests/test_stage_view.py tests/test_http_report_runs.py tests/test_http_shell.py`
  — expected: green, including the new stage-track, Gate-panel, and
  `/regenerate` cases.
- `uv run pytest` — expected: full suite green.
- `uv run ruff check .` — expected: clean.
- `uv run ruff format --check .` — expected: no *new* flags in files this story
  touched (pre-existing repo-wide flags per the Story 9.4 note stand).

**Manual checks:**
- Load `/report-runs/{id}` for a mid-run, a `gate_passed`, an `exported`, a
  Gate-failed, and a non-Gate-failed run; confirm node states, the Italian
  caption, that polling stops on the three terminal states, and that the
  Gate-failed `/draft` panel's violation cards jump to the right Sezione.
- Toggle the OS reduced-motion setting and reload a running run — the active
  dot must not pulse.
- With JS off (devtools), confirm the stage track still shows the true stage and
  `Rigenera` submits as a full-page form that lands back on the stage view.

## Suggested Review Order

**The review-loop-1 discriminator (start here — the intent-gap fix)**

- The correlation-window constant and its safety argument — read this comment first, the rest of the fix follows from it.
  [`report_runs.py:112`](../../shell/http/routes/report_runs.py#L112)

- `_current_cycle_gate_failure` — replaces the old existence-only check with a `created_at`-to-`failed_at` window, used by all three call sites below.
  [`report_runs.py:124`](../../shell/http/routes/report_runs.py#L124)

- `poll_report_run` — `gate_failed` now derived from the corrected discriminator.
  [`report_runs.py:328`](../../shell/http/routes/report_runs.py#L328)

- `regenerate_report_run` — its 404 guard uses the same discriminator, closing the direct-POST bypass a stale check would allow.
  [`report_runs.py:362`](../../shell/http/routes/report_runs.py#L362)

- `view_report_draft` — `violations`/`gate_failed` no longer fetched unconditionally on failed-run history.
  [`report_runs.py:432`](../../shell/http/routes/report_runs.py#L432)

- The boundary tests pinning down the window's `>` vs `>=` edge, plus the stale-cycle scenario itself.
  [`test_http_report_runs.py:1436`](../../tests/test_http_report_runs.py#L1436)
  [`test_http_report_runs.py:1514`](../../tests/test_http_report_runs.py#L1514)

**The stage-track view model (pure core)**

- `STAGE_NODES` / `_STAGE_CAPTIONS` / `VIOLATION_KIND_LABELS` — the Italian data tables, bound to `_STAGE_SEQUENCE` by a test.
  [`stage_view.py:34`](../../shell/http/stage_view.py#L34)

- `build_stage_track` — the pending/active/done/failed state machine per node.
  [`stage_view.py:85`](../../shell/http/stage_view.py#L85)

- `stage_caption` — the single Italian line under the track.
  [`stage_view.py:124`](../../shell/http/stage_view.py#L124)

- The full I/O-matrix-state unit suite.
  [`test_stage_view.py:23`](../../tests/test_stage_view.py#L23)

**The rendered surfaces**

- The six-node track + gated polling + poll-error banner.
  [`report_run_poll.html:9`](../../shell/http/templates/report_run_poll.html#L9)

- The Gate-failure panel — violation cards, Sezione anchors, the Rigenera form + confirm modal (copy corrected in review-loop 1's patch pass).
  [`report_draft.html:6`](../../shell/http/templates/report_draft.html#L6)

- The distinct non-Gate failure panel (no Rigenera).
  [`report_draft.html:48`](../../shell/http/templates/report_draft.html#L48)

**Shell JS and styling**

- `trapFocus` — the shared helper the drawer, delete modal, and regen modal now all route through.
  [`shell.js:84`](../../shell/http/static/shell.js#L84)

- Job 6 (poll pause while hidden, error banner) and job 7 (regen-confirm modal).
  [`shell.js:445`](../../shell/http/static/shell.js#L445)
  [`shell.js:498`](../../shell/http/static/shell.js#L498)

- The provisional Story 9.5 CSS block — semantic tokens, reduced-motion.
  [`tokens.css:1168`](../../shell/http/static/tokens.css#L1168)

**Peripherals**

- The remaining `test_http_report_runs.py` amendments (Italian copy, stage-track fragment cases, `/regenerate` route cases).
  [`test_http_report_runs.py:1`](../../tests/test_http_report_runs.py#L1)

- The `test_http_shell.py` poll-render assertions updated off the raw stage token.
  [`test_http_shell.py:1`](../../tests/test_http_shell.py#L1)
