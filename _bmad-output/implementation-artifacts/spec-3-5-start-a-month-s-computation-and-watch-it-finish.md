---
title: "Start a month's computation and watch it finish"
type: 'feature'
created: '2026-08-19'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '7c393be57fd105c754659b24b6e796d754a83086'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing today turns "a Client and a month" into a driven computation. Client-local month
boundaries are never resolved to UTC outside test fixtures (deferred explicitly by Stories 3.1-3.4), and
there is no persisted execution frame — a spin-down, redeploy or future rate-limit stall would lose an
entire run, and Francesco has nothing to watch while it works.

**Approach:** A `ReportRun` row (new `shell/adapters/postgres/report_run.py`) advances forward-only
through the six named AD-10 stages, persisting each stage's output before the next begins. A new
`shell/runner/` package resolves the Client's local month to `[month_start_utc, month_end_utc)`, drives
`natal_ready` (already-computed chart, deserialized) then `transits_ready` (the four Story 3.1-3.4 scan
functions) through a generic bounded-backoff wrapper, and is re-invoked by both the start route and the
HTMX poll route — so re-driving after any interruption just means calling it again. `payload_ready`
onward stay named in the sequence but have no registered stage function yet (Story 3.6+).

## Boundaries & Constraints

**Always:**
- `report_run` table: `id`, `client_id` (FK `client.id`), `month` (`"YYYY-MM"`), `stage` (nullable —
  `None` until `natal_ready` first completes), `month_start_utc`/`month_end_utc` (nullable, set by
  `natal_ready`), `transit_events` (nullable JSON, set by `transits_ready`), `created_at`, `updated_at`.
  Joins the FR-29 cascade: add `"report_run"` to `_CLIENT_CASCADE_TABLES` and delete its rows in
  `delete_client_and_derived` before the `Client` row, alongside `StoredNatalChart`.
- `shell/runner/driver.py::drive(session, run, *, natal_chart, config, ephemeris_identity) -> ReportRun`
  advances through every stage present in an ordered `_STAGE_FUNCTIONS` registry (only `natal_ready`,
  `transits_ready` are registered this story), committing after each; stops cleanly the moment the next
  named AD-10 stage has no registered function. Never re-runs a stage `run.stage` already passed —
  idempotent by construction, not by re-checking output equality.
  `shell/runner/backoff.py::with_backoff(fn, *, max_attempts=3)` wraps each stage call generically
  (bounded exponential, no jitter requirement); a stage that keeps failing leaves `run.stage` unchanged
  for the next drive to retry — never marks the run failed (no failure state exists in this story's
  scope).
  `shell/runner/month.py::client_month_interval_utc(client, month) -> tuple[datetime, datetime]`
  resolves `"YYYY-MM"` against `client.iana_zone`'s local calendar-month boundaries via `zoneinfo`.
- Every log line the runner emits carries `run.id` (`%s`-interpolated, mirroring
  `shell/http/auth.py::log_client_deleted`'s bare-call shape — no birth data, no Client name).
- `shell/adapters/postgres/client.py::deserialize_natal_chart(stored: StoredNatalChart) -> NatalChart`
  (new) reverses `_serialize`'s `Decimal`-to-`str` JSON encoding back into the frozen dataclasses.
- `POST /clients/{client_id}/report-runs` creates the `ReportRun`, calls `drive()` once, redirects to the
  poll view. `GET /report-runs/{run_id}` (HTMX poll target) calls `drive()` again before rendering —
  the only two call sites `drive()` needs; no background task, no queue.

**Ask First:** None identified.

**Never:**
- No `payload_ready`/`draft_ready`/`gate_passed`/`exported` stage function or table — declared in the
  sequence constant only (Story 3.6+ registers them into `_STAGE_FUNCTIONS`, unchanged).
- No failure/error state on `ReportRun` — a persistently failing stage simply stays un-advanced;
  surfacing failure to Francesco is out of scope here.
- No change to `core/` — `core/transits/*`, `core/ephemeris/*` are called, never modified.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|-----------------|
| Fresh run, both stages succeed | New `ReportRun`, Client has a current chart | `stage` ends at `transits_ready`; `month_start_utc/end_utc` and `transit_events` populated | N/A |
| Re-drive after `natal_ready` alone | `run.stage == "natal_ready"` | `transits_ready` runs next; `natal_ready` is not recomputed | N/A |
| Re-drive after full completion | `run.stage == "transits_ready"` | `drive()` is a no-op; returns `run` unchanged | N/A |
| Stage raises past backoff's attempts | Injected always-failing stage function | `run.stage` stays at its last successful value | Logged with `run.id`; no exception escapes `drive()` |
| Process killed between stages | `run.stage == "natal_ready"` row already committed | Next `drive()` call (poll or restart) resumes at `transits_ready`, reading `month_start_utc/end_utc` back from the row | N/A |
| `Client.iana_zone`'s local month has no matching data (DST edge) | A month boundary local time that a zone shifts | `client_month_interval_utc` still returns a valid, unambiguous UTC pair (zoneinfo resolves it) | N/A |

</frozen-after-approval>

## Code Map

- `shell/adapters/postgres/client.py` -- `_CLIENT_CASCADE_TABLES:41` (add `"report_run"`),
  `delete_client_and_derived:216` (delete `ReportRun` rows first), `_serialize:108`/`_json_safe:99`
  (mirror for the new `deserialize_natal_chart`), `StoredNatalChart:64` (source fields to reverse).
- `shell/adapters/postgres/report_run.py` (new) -- `ReportRun(SQLModel, table=True)`, mirroring
  `Client`'s UUIDv7-pk style (`client.py:44-61`).
- `migrations/versions/0005_report_run.py` (new) -- mirror `0002_place_cache.py`'s shape
  (`op.create_table`, forward-only `downgrade()` that raises); `down_revision = "0004_supersede_natal_chart"`.
- `core/types/chart.py` -- `NatalChart:87`/`PlanetPosition:21`/`HouseCusp:42`/`Aspect:70` -- exact
  fields `deserialize_natal_chart` reconstructs.
- `core/transits/aspects.py::find_transit_aspects:94`, `core/transits/stations.py::find_stations:67`,
  `core/transits/ingresses.py::find_ingresses:73`, `core/transits/lunations.py::find_lunations:88` --
  the four calls `transits_ready` makes, in this order, each taking the already-resolved
  `(month_start_utc, month_end_utc)` plus (all but Lunations) `config: ComputationConfig`.
- `core/types/transits.py` -- `TransitAspectEvent:22`/`Station:55`/`StandingRetrograde:76`/`Ingress:96`/
  `Lunation:123` -- the five result shapes serialized (tagged by kind) into `report_run.transit_events`.
- `shell/runner/__init__.py`, `shell/runner/month.py`, `shell/runner/backoff.py`, `shell/runner/driver.py`
  (all new) -- per Boundaries & Constraints above.
- `shell/http/app.py` -- `create_app:74` (register the new router the same deferred-import way
  `chart_router`/`clients_router` are wired, `app.py:79-80`), `get_session:61` (dependency reused
  unchanged).
- `shell/http/routes/` (new `report_runs.py`) -- the two routes, mirroring
  `shell/http/routes/chart.py::chart_wheel_view:44`'s `session.get`/404/`_templates.TemplateResponse`
  shape.
- `shell/http/templates/` (new `report_run_poll.html`) -- HTMX `hx-get`/`hx-trigger="every 2s"` polling
  the same route, mirroring `_TEMPLATES_DIR:51`'s existing Jinja2 setup.
- `tests/test_client_store.py` -- `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant:282`
  (already generic; passes once `report_run` is added correctly).

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0005_report_run.py` -- create `report_run` table per Boundaries.
- [x] `shell/adapters/postgres/report_run.py` -- `ReportRun` SQLModel.
- [x] `shell/adapters/postgres/client.py` -- add `"report_run"` to `_CLIENT_CASCADE_TABLES`, delete its
  rows in `delete_client_and_derived`, add `deserialize_natal_chart`.
- [x] `shell/runner/month.py` -- `client_month_interval_utc`.
- [x] `shell/runner/backoff.py` -- `with_backoff`.
- [x] `shell/runner/driver.py` -- `_STAGE_SEQUENCE` (all six names), `_STAGE_FUNCTIONS` (two entries),
  `drive()`.
- [x] `shell/http/routes/report_runs.py` + `shell/http/templates/report_run_poll.html` -- start + poll.
- [x] `shell/http/app.py` -- wire the new router.
- [x] `tests/test_runner_driver.py`, `tests/test_runner_month.py`, `tests/test_runner_backoff.py`,
  `tests/test_report_run_store.py`, `tests/test_http_report_runs.py` (new) -- I/O matrix rows above plus
  the cascade/deserialization round-trip.

**Acceptance Criteria:**
- Given a Client and a requested month, when Francesco starts a run, then a `ReportRun` row is created
  and advances forward only through `natal_ready → transits_ready → payload_ready → draft_ready →
  gate_passed → exported`, each stage persisting before the next begins, with stages beyond
  `transits_ready` declared but not yet reachable.
- Given a run interrupted partway, when it is re-driven, then it resumes at the first incomplete
  registered stage and recomputes nothing already succeeded; every stage function is idempotent.
- Given the process killed mid-run, when the application restarts and the run is re-driven, then the
  completed stages are read back from Postgres — nothing depended on the container filesystem.
- Given a running job, when Francesco watches it, then the HTMX poll view shows the current stage and
  updates as it advances.
- Given a stage call, when it raises, then `with_backoff` absorbs it up to its bound and every log line
  carries the `ReportRun` id.
- Given the `report_run` table, when it is created, then it joins the FR-29 Client deletion cascade.

## Spec Change Log

_None yet._

## Design Notes

**Why `drive()` is called from both the start POST and the poll GET, with no background task or queue.**
BUILD-ORDER.md's E5 explicitly rejects an in-process background task ("run state lives only in memory,
lost silently on restart") and a blocking synchronous request ("a stall loses the whole run"). Making
`drive()` a cheap, idempotent, re-entrant function that any request handler can call reduces to "the next
HTTP request in either role continues the run" — the browser's own poll cadence is the drain, matching the
architecture note "no queue infrastructure needed."

**Why only `natal_ready`/`transits_ready` get real stage functions.** BUILD-ORDER.md: "the runner
introduced once two real stages exist." Payload assembly is Story 3.6's job (`core/payload/` does not
exist yet); registering a stage before its implementation exists would mean stubbing a lie. The AC's own
phrase "stages beyond those implemented so far are declared but not yet reachable" is read literally:
`_STAGE_SEQUENCE` names all six for display/ordering, `_STAGE_FUNCTIONS` only the two real ones.

**Why no live external call demonstrates the backoff.** Both registered stages read local state (the
already-persisted chart, the local ephemeris) — nothing rate-limited exists yet (that arrives with the
Generator, Story 4.8, sized for its own 10 RPM ceiling). `with_backoff` is proven here with an injected
fake failing stage function; it becomes the same wrapper future stages reuse, per AD-10's rule against
"two builders inventing incompatible retry semantics."

**`transit_events` as one JSON column, not four new tables.** Story 3.6 will read these events to
assemble the Payload and may reshape how they're consumed; committing to per-kind tables now risks a
schema this story can't justify. Serialized the same `_serialize`-style way `StoredNatalChart` already
uses (`Decimal` → `str`), each entry tagged `"kind"` (`aspect`/`station`/`standing_retrograde`/
`ingress`/`lunation`) since the four scan functions return different dataclasses.

## Verification

**Commands:**
- `uv run pytest tests/test_runner_driver.py tests/test_runner_month.py tests/test_runner_backoff.py tests/test_report_run_store.py tests/test_http_report_runs.py tests/test_client_store.py -q`
  -- expected: all pass, including the existing cascade-invariant test.
- `uv run alembic upgrade head` against a scratch database -- expected: `0005_report_run` applies cleanly
  after `0004_supersede_natal_chart`.

## Suggested Review Order

**Stage driver — the execution frame**

- Entry point: advances a `ReportRun` through registered stages, backoff-wrapped, stopping cleanly at the first unregistered stage.
  [`driver.py:197`](../../shell/runner/driver.py#L197)

- Only two of six AD-10 stages get a real function this story; the rest wait for Story 3.6+.
  [`driver.py:151`](../../shell/runner/driver.py#L151)

- All six stage names, ordered -- display/ordering only, independent of which are implemented.
  [`driver.py:71`](../../shell/runner/driver.py#L71)

- Resolves the Client-local month boundary Stories 3.1-3.4 deliberately deferred.
  [`driver.py:87`](../../shell/runner/driver.py#L87)

- Calls the four Story 3.1-3.4 scan functions and tags each event by kind for storage.
  [`driver.py:110`](../../shell/runner/driver.py#L110)

- A genuine field-name collision between `Lunation`'s own `kind` and this wrapper's outer tag.
  [`driver.py:178`](../../shell/runner/driver.py#L178)

**Bounded backoff**

- Generic retry wrapper reused unchanged once a real rate-limited call exists (the Generator, Story 4.8).
  [`backoff.py:28`](../../shell/runner/backoff.py#L28)

**Month resolution**

- The one place a Client's local calendar month becomes a UTC interval, via `zoneinfo`.
  [`month.py:29`](../../shell/runner/month.py#L29)

**Persistence: the ReportRun row**

- The persisted execution frame's shape: nullable stage/boundaries/events until their producing stage runs.
  [`report_run.py:52`](../../shell/adapters/postgres/report_run.py#L52)

- SQLite drops `tzinfo` on read; re-attaches UTC so tests and Postgres behave identically.
  [`report_run.py:28`](../../shell/adapters/postgres/report_run.py#L28)

- New table, forward-only migration, no downgrade path (matches project convention).
  [`0005_report_run.py:29`](../../migrations/versions/0005_report_run.py#L29)

**Chart deserialization & the FR-29 cascade**

- Reverses `_serialize`'s `Decimal`-to-`str` encoding back into the real `NatalChart` dataclasses.
  [`client.py:115`](../../shell/adapters/postgres/client.py#L115)

- `ReportRun` joins the Client-deletion cascade alongside `StoredNatalChart`.
  [`client.py:261`](../../shell/adapters/postgres/client.py#L261)

- `report_run` added to the single source of truth the cascade-invariant test checks against.
  [`client.py:43`](../../shell/adapters/postgres/client.py#L43)

**HTTP routes & the HTMX poll view**

- Start route: creates the run, drives it once, redirects to the poll view. Sync `def` (not `async`) so a blocking retry never stalls the event loop.
  [`report_runs.py:76`](../../shell/http/routes/report_runs.py#L76)

- Poll route: drives again on every poll, so an interrupted run resumes on whichever request reaches it next.
  [`report_runs.py:100`](../../shell/http/routes/report_runs.py#L100)

- Router wired the same deferred-import way `chart`/`clients` routers already are.
  [`app.py:88`](../../shell/http/app.py#L88)

- Polls every 2 seconds; splits fragment vs. full page via the `HX-Request` header.
  [`report_run_poll.html:17`](../../shell/http/templates/report_run_poll.html#L17)

**Peripherals**

- Proves a stage failing once then succeeding on retry still advances the run normally within one `drive()` call.
  [`test_runner_driver.py:221`](../../tests/test_runner_driver.py#L221)

- New dependency `python-multipart`, which FastAPI's `Form()` needs regardless of body encoding.
  [`pyproject.toml:14`](../../pyproject.toml#L14)
