---
title: 'Story 4.6 — Render cited sentences into prose I could read aloud'
type: 'feature'
created: '2026-08-21'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'b62a8ac1d8981eb63cf18676abd5716a8913c6d2'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 4.5's Generator returns eight Sections as cited sentences, never free prose, but nothing yet calls it from a `ReportRun` or turns its output into something Francesco can read aloud on a call — `draft_ready` is the first stage in `_STAGE_SEQUENCE` with no registered function.

**Approach:** Add a `draft_ready` stage that calls the Generator port with the already-persisted Payload, Style Guide and current `ReportTheme` (`theme_previous` stays `None` — Story 4.7 wires continuity), persists the returned `GeneratedDraft` verbatim in a new immutable, cascade-joined table, and adds a shell-side render step + view route that turns Sections 1–5/8 into continuous prose and Sections 6–7 into the code-projected dated list, citations retained.

## Boundaries & Constraints

**Always:** `_run_draft_ready` reads `payload`/`theme_current` back from `ReportPayload`/`StoredReportTheme`, never recomputes them (mirrors every other stage function). What's persisted at `draft_ready` is the raw `GeneratedDraft` (`entry_ids` intact) — rendering to prose happens only in `shell/http/`, at view time, never baked into storage. `ReportDraft` is immutable once persisted and joins `_CLIENT_CASCADE_TABLES`. The Gemini adapter is constructed per-request via a `Depends()` provider, mirroring `get_geocoder()` — never cached on `app.state`.

**Ask First:** none identified.

**Never:** Fetching a prior month's `ReportTheme` or feeding a theme diff into generation — `theme_previous` stays `None` unconditionally; that wiring is Story 4.7's job. Changing the Generator port's four-argument signature.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Prose Sections | `GeneratedDraft` sentences in the six prose Sections | One continuous string per Section, no bullets, `entry_ids` still present in the returned structure | N/A |
| List Sections | `giorni_favorevoli`/`giorni_di_attenzione` Sentences + matching `payload["day_lists"]` entries | One item per day-list entry (real, localized date), enriched with any citing Sentence text, list form | N/A |
| Uncited day-list entry | Entry in `payload["day_lists"]` no Sentence cites | Still rendered, date only, never dropped | N/A |
| `draft_ready` persistence | Successful `generator.generate()` | `ReportDraft` row records `style_guide_version`, `sections_config_version`, draft JSON | N/A |
| Client deletion | Client with a persisted `ReportDraft` | Removed before its `ReportRun`, via `_CLIENT_CASCADE_TABLES` | N/A |
| Update attempt | Code mutates a persisted `ReportDraft` row | Raises, mirrors `ReportPayload`/`StoredReportTheme` | RuntimeError |

</frozen-after-approval>

## Code Map

- `shell/runner/driver.py:81-96,283-336,339-393` -- `_STAGE_SEQUENCE`/`StageFn`/`_run_payload_ready` (pattern to mirror)/`_STAGE_FUNCTIONS`/`drive()` -- add `_run_draft_ready`, register it, extend `StageFn`/`drive()` with a `generator: Generator` param.
- `shell/runner/driver.py:207-280` -- `_deserialize_transit_events` -- "read back, never recomputed" pattern to mirror for reconstructing `ReportTheme` from `StoredReportTheme.theme`.
- `shell/adapters/postgres/report_theme.py` -- `StoredReportTheme`/`store_report_theme()`/`before_update` listener -- shape `ReportDraft`/`store_report_draft()` mirrors.
- `shell/adapters/postgres/report_payload.py` -- `ReportPayload.payload` -- read back verbatim as the Generator's `payload` argument.
- `shell/adapters/postgres/style_guide.py:82` -- `current_style_guide(session)` -- build `StyleGuideVersion` from it.
- `shell/ports/generator.py`, `core/types/generation.py` -- `Generator`/`StyleGuideVersion`/`GeneratedDraft`/`Sentence` -- port called, shape persisted.
- `shell/adapters/postgres/client.py:45-47,265-316` -- `_CLIENT_CASCADE_TABLES`/`delete_client_and_derived` -- add `report_draft`, delete before `ReportRun`.
- `migrations/versions/0008_report_theme.py` -- template for `0009_report_draft.py`.
- `shell/http/payload_view.py` -- `localize_payload` -- reuse for the draft view's dates (AD-12).
- `shell/http/routes/clients.py:229-240` -- `get_geocoder()` -- per-request `Depends()` pattern to mirror for `get_generator()`.
- `shell/http/routes/report_runs.py:61-75,119-143` -- `_drive_run`/`view_report_payload` -- pass `generator`; pattern for the new `/draft` route.
- `shell/http/templates/report_payload.html`, `report_run_poll.html` -- template conventions to extend (add "View Draft" link at `draft_ready`).
- `shell/adapters/gemini/generator.py:50` -- `_DATE_TOKEN_SECTIONS` -- reuse, don't redefine.
- `tests/test_runner_driver.py:1-90` -- fixture/injection conventions to extend with a fake `Generator`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/report_draft.py` -- new: `ReportDraft` table (`client_id`, `report_run_id` unique FK, `style_guide_version`, `sections_config_version`, `draft: JSON`, `created_at`), immutable, `store_report_draft()`.
- [x] `migrations/versions/0009_report_draft.py` -- new: create `report_draft` table + indexes, mirroring 0008.
- [x] `shell/adapters/postgres/client.py` -- add `report_draft` to `_CLIENT_CASCADE_TABLES` and its deletion loop.
- [x] `shell/runner/driver.py` -- `_deserialize_theme`, `_run_draft_ready`, register in `_STAGE_FUNCTIONS`, thread `generator` through `drive()`.
- [x] `shell/http/draft_view.py` -- new: `render_draft(draft, payload, *, iana_zone)` -- prose Sections join sentence text; list Sections iterate `payload["day_lists"]` entries first, enrich with citing Sentence text via `entry_ids`, localize dates via `localize_payload`'s helper.
- [x] `shell/http/routes/report_runs.py` -- `get_generator()` `Depends()` provider; thread it into both routes and `_drive_run`; new `GET /report-runs/{run_id}/draft` route.
- [x] `shell/http/templates/report_draft.html` -- new: prose Sections as `<p>`, list Sections as `<ul><li>`.
- [x] `shell/http/templates/report_run_poll.html` -- add "View Draft" link at `draft_ready`.
- [x] `tests/test_report_draft_store.py` -- new: store/read round trip, immutability, cascade deletion (mirrors `tests/test_report_theme_store.py`).
- [x] `tests/test_runner_driver.py` -- extend: `_run_draft_ready` with a fake `Generator`, update "advances to"/"first unregistered stage" assertions.
- [x] `tests/test_draft_view.py` -- new: `render_draft()` covering the I/O & Edge-Case Matrix.
- [x] `tests/test_http_report_runs.py` -- extend: `/report-runs/{run_id}/draft` happy path and 404 before `draft_ready`.

**Acceptance Criteria:**
- Given a generated Section of cited sentences, when the shell renders it, then Sections 1–5 and 8 render as continuous prose, never as bullet fragments, and Sections 6–7 render the code-projected dated entries, in list form.
- Given the rendering, when it happens, then it happens in the shell, and citations are retained against the stored draft rather than discarded at render time.
- Given a completed draft, when the run advances, then the cited draft structure is persisted at the `draft_ready` stage, and the `report_draft` row records the Style Guide version and the Section-composition (`SectionsConfig`) version that produced it, and joins the `_CLIENT_CASCADE_TABLES` deletion cascade.

## Spec Change Log

## Design Notes

- **Why `theme_previous` stays `None`:** the Generator port requires it (nullable) to be callable at all, but fetching a prior month's `ReportTheme` and diffing it is Story 4.7's own deliverable (epic Cross-Story Dependencies). Passing `None` uniformly here is correct, first-Report behavior, not a stub — Story 4.7 replaces it.
- **Why the Gemini adapter isn't cached on `app.state`:** `get_geocoder()` (`shell/http/routes/clients.py:229`) already establishes the pattern of constructing a network-touching adapter per-request via `Depends()`, never eagerly at `create_app()` time — this avoids constructing a real `genai.Client` for every one of the many HTTP tests that build the app but never touch report runs.
- **Why list Sections iterate `payload["day_lists"]` first, not the Sentences:** the AC's "code-projected dated entries" are the authoritative, code-computed source (Story 3.7); a Sentence's `entry_ids` only enrich an entry with narrative text, never gate whether it appears.

## Verification

**Commands:**
- `uv run pytest tests/test_report_draft_store.py tests/test_runner_driver.py tests/test_draft_view.py tests/test_http_report_runs.py tests/test_client_store.py -q` -- expected: all pass, including the cascade-invariant test picking up `report_draft`.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**The `draft_ready` stage (AD-3, "read back, never recomputed")**

- Entry point: reads the persisted Payload/Style Guide/Theme back, calls the Generator, persists the raw draft.
  [`driver.py:399`](../../shell/runner/driver.py#L399)

- The reverse of `StoredReportTheme.theme`'s JSON encoding -- mirrors `_deserialize_transit_events`'s own round trip.
  [`driver.py:358`](../../shell/runner/driver.py#L358)

- `generator: Generator` joins every stage function's uniform signature, unused by three of the four.
  [`driver.py:106`](../../shell/runner/driver.py#L106)

**Persistence: `ReportDraft` (immutable, cascade-joined)**

- The row shape: `style_guide_version`/`sections_config_version` traceability, mirrors `ReportPayload`.
  [`report_draft.py:33`](../../shell/adapters/postgres/report_draft.py#L33)

- The `before_update` guard -- a persisted draft can never silently change what a citation points at.
  [`report_draft.py:68`](../../shell/adapters/postgres/report_draft.py#L68)

- `store_report_draft()` -- flush-only, never commits, matching every sibling store function's transaction discipline.
  [`report_draft.py:105`](../../shell/adapters/postgres/report_draft.py#L105)

- FR-29 cascade: `report_draft` joins `_CLIENT_CASCADE_TABLES` and is deleted before its `ReportRun`.
  [`client.py:46`](../../shell/adapters/postgres/client.py#L46)

- The migration creating the table and its unique index.
  [`0009_report_draft.py:31`](../../migrations/versions/0009_report_draft.py#L31)

**Rendering: citations retained, never discarded (this story's Acceptance Criteria)**

- `render_draft()` -- prose Sections join text, list Sections iterate `payload["day_lists"]` first.
  [`draft_view.py:145`](../../shell/http/draft_view.py#L145)

- List rendering's key decision: the code-projected day-list entry is authoritative, a citing Sentence only enriches it.
  [`draft_view.py:120`](../../shell/http/draft_view.py#L120)

- `SECTION_ORDER` -- the draft's true 1-8 field order, so the template never puts Section 8 ahead of 6-7.
  [`draft_view.py:58`](../../shell/http/draft_view.py#L58)

- The template renders one loop over `section_order`, branching `<p>` vs `<ul>` per Section -- not two grouped loops.
  [`report_draft.html:13`](../../shell/http/templates/report_draft.html#L13)

**HTTP wiring: the Gemini adapter, constructed per-request**

- `get_generator()` -- mirrors `get_geocoder()`'s per-request `Depends()` pattern, never cached on `app.state`.
  [`report_runs.py:70`](../../shell/http/routes/report_runs.py#L70)

- The new `/report-runs/{run_id}/draft` view route -- 404 collapse mirrors `view_report_payload`.
  [`report_runs.py:177`](../../shell/http/routes/report_runs.py#L177)

- The poll page's new "View Draft" link, gated on `run.stage == "draft_ready"`.
  [`report_run_poll.html:25`](../../shell/http/templates/report_run_poll.html#L25)

**Tests**

- `draft_ready`'s own I/O row: the Generator is called with the persisted Payload/Style Guide, `theme_previous=None`.
  [`test_runner_driver.py:657`](../../tests/test_runner_driver.py#L657)

- The uncited-day-list-entry edge case: still rendered, date only, never dropped.
  [`test_draft_view.py:135`](../../tests/test_draft_view.py#L135)

- Immutability: mutating and committing a persisted `ReportDraft` row raises.
  [`test_report_draft_store.py:156`](../../tests/test_report_draft_store.py#L156)
