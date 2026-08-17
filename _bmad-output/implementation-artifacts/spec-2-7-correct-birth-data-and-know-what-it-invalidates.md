---
title: 'Correct birth data, and know what it invalidates'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'a45f79229a4b6d2f7a1cdfb12637f62240f8bf3b'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.3 persists a Client's birth data and chart once, with no way to correct a
mistaken entry. A correction risks silently invalidating anything already generated against the old
chart, or destroying the chart that work depended on.

**Approach:** A new authenticated edit route re-runs Story 2.1's resolution and Story 2.2's
computation against corrected input, gated by an explicit warning the human must acknowledge before
anything is written. The previous `StoredNatalChart` row is kept and marked superseded rather than
overwritten; the Client's coordinate/zone snapshot is replaced by the new resolution.

## Boundaries & Constraints

**Always:**
- Correction resubmits all four fields (name, birth_date, birth_time, birthplace) -- mirrors Story
  2.3's "no partial record" rule; there is no per-field patch endpoint.
- The edit form prefills name/birth_date/birth_time from the Client row. Birthplace has no stored
  free-text form to prefill from (only resolved lat/lon/zone are stored), so it starts blank and must
  be retyped even to reconfirm the same place -- `PLACE_CACHE` makes that cheap.
- Before persisting, the response shows an acknowledgment gate: applying this will supersede the
  current chart. The change applies only once confirmed by resubmitting the form with `confirmed=1`.
- On confirmed apply, in one transaction: the current `StoredNatalChart` row gets `superseded_at` set
  (UTC now), a new `StoredNatalChart` row is inserted with `superseded_at=None`, and the `Client`
  row's name/birth_date/birth_time/latitude/longitude/iana_zone are updated in place. Commit only
  after all three steps succeed.
- Birthplace re-resolution reuses `Geocoder.resolve()`/`resolve_candidate()` exactly as the create
  route does, including the ambiguous-candidate picker.
- `shell/http/routes/chart.py`'s chart-wheel query must filter to the current (non-superseded) chart
  -- once a Client can have more than one chart row, its unfiltered `.first()` becomes wrong.
- Authenticated by default via the existing `AuthMiddleware`.

**Ask First:** none anticipated.

**Never:**
- No soft-delete or overwrite of the superseded `StoredNatalChart` row -- it stays queryable by its
  own id.
- No recomputation triggered by anything other than a confirmed correction (viewing a chart, listing
  clients, etc. never recomputes).
- No new domain error type -- resolution/computation failures reuse `PlaceResolutionError` and
  whatever `compute_natal_chart()` raises, exactly like the create route.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Unconfirmed correction | Valid form, no `confirmed` field | 200; warning page, hidden fields carry the submission forward, nothing persisted | N/A |
| Confirmed correction | Same form + `confirmed=1` | 200; old chart marked superseded, new chart + updated Client committed | N/A |
| Ambiguous birthplace | Birthplace text matches >1 place | 200; candidate picker (mirrors `/clients` create), nothing persisted, warning not yet shown | N/A |
| Unknown client id | `GET`/`POST /clients/{id}/edit`, id not in DB | 404 | plain 404, no row touched |
| Resolution failure | Geocoder raises `PlaceResolutionError` | 422, error naming the step, nothing persisted | existing pattern |
| Chart computation failure | `compute_natal_chart()` raises | 422, nothing persisted -- old chart stays current | existing pattern |
| Unchanged birthplace text | Resubmitted birthplace resolves via `PLACE_CACHE` | Resolves normally (cache hit), correction still applies | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/routes/clients.py:151-261` -- read-only reference: `_parse_form`, `_missing_fields`,
  `_decode_candidate`, `get_geocoder`, and `create_client`'s resolve -> compute -> persist -> commit
  sequence -- the new routes reuse every helper and mirror this orchestration, adding a confirm gate
  before persistence.
- `shell/adapters/postgres/client.py:31-137` -- `Client`, `StoredNatalChart`, `create_client_with_chart`
  -- add `StoredNatalChart.superseded_at: datetime | None` and a new `correct_client_and_chart(session,
  *, client, name, birth_date, birth_time, resolved_place, natal_chart, computation_config,
  ephemeris_identity) -> None` that supersedes the current chart, inserts the new one, and updates
  `client`'s fields in place -- `add()`/`flush()` only, caller commits, exactly like
  `create_client_with_chart`.
- `shell/http/routes/chart.py:51-53` -- current query selects any `StoredNatalChart` for the client;
  add `.where(StoredNatalChart.superseded_at.is_(None))`.
- `migrations/versions/0003_client_and_natal_chart.py` -- pattern for the new migration
  `0004_supersede_natal_chart.py`: `op.add_column("natal_chart", sa.Column("superseded_at",
  sa.DateTime(timezone=True), nullable=True))`.
- `shell/http/templates/client_new.html` -- template convention (plain HTML, candidate `<fieldset>`)
  the new `client_edit.html` follows, adding a warning state with hidden name/birth_date/birth_time/
  birthplace/candidate inputs plus `confirmed=1`.
- `shell/http/app.py:86-104` -- deferred router import + `include_router()` pattern; no new router
  needed, the edit routes join the existing `clients_router`.
- `core/errors.py:53-69` -- `PlaceResolutionError` -- reused as-is, no new error type.
- `tests/test_http_clients.py:1-165` -- fixture pattern (`_FakeGeocoder`, `db_session`, `client`,
  `authenticated_client`) to duplicate in the new test file.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0004_supersede_natal_chart.py` -- create -- adds nullable `superseded_at`
  to `natal_chart`
- [x] `shell/adapters/postgres/client.py` -- add `superseded_at` field + `correct_client_and_chart()`
  -- persists a correction as supersede-old/insert-new/update-client in one flush
- [x] `shell/http/routes/chart.py` -- filter the chart query to `superseded_at.is_(None)` -- keeps the
  chart wheel showing the current chart once corrections exist
- [x] `shell/http/routes/clients.py` -- add `GET`/`POST /clients/{id}/edit` -- resolve, warn, confirm,
  recompute, persist
- [x] `shell/http/templates/client_edit.html` -- create -- prefilled form, candidate picker, warning +
  confirm state
- [x] `tests/test_http_client_correction.py` -- create -- one test per I/O matrix row plus the
  cross-story regression: after a confirmed correction, `GET /clients/{id}/chart` reflects the new
  chart

**Acceptance Criteria:**
- Given a Client with a stored chart, when a correction is submitted without `confirmed=1`, then the
  warning is shown and no row changes.
- Given an acknowledged correction, when it applies, then the old `StoredNatalChart` row still exists
  with `superseded_at` set, and the new current row is what `chart.py`'s route reads.
- Given a correction that changes birthplace, when it applies, then `Client.latitude`/`longitude`/
  `iana_zone` are the newly resolved values, not the old ones.
- Given no correction was ever submitted, when any route runs, then no second `StoredNatalChart` row
  is ever created for that Client.

## Spec Change Log

## Design Notes

Resolution is re-run on every submission rather than threading a serialized `ResolvedPlace` through
the warning step's hidden fields -- `PLACE_CACHE` makes a repeat lookup cheap, and it avoids a second
serialization format alongside the existing `candidate` JSON hidden-field pattern `client_new.html`
already uses for the ambiguous-match case. The warning step reuses that same `candidate` hidden field
when a candidate was chosen, so confirmation re-resolves through `resolve_candidate()` exactly as the
first pass did.

## Verification

**Commands:**
- `uv run pytest tests/test_http_client_correction.py` -- new tests green
- `uv run pytest` -- full suite green, including `tests/test_http_chart_wheel.py` (chart route still
  finds the right chart) and `tests/test_migration_chain.py` (new revision stays linear)
- `uv run ruff check .` -- clean
- `uv run alembic upgrade head` -- new migration applies cleanly against a local Postgres

**Manual checks (if no CLI):**
- Create a Client, open `/clients/{id}/edit`, submit a changed birth time without confirming -- verify
  the warning appears and `/clients/{id}/chart` still shows the original chart. Confirm, then reload
  `/clients/{id}/chart` and verify it now reflects the corrected time.

## Suggested Review Order

**Persistence: supersede-and-replace**

- Entry point: marks the current chart superseded, inserts the new one, updates the Client row in
  place -- all in one flush, exactly like the create path.
  [`client.py:146`](../../shell/adapters/postgres/client.py#L146)

- The invariant the whole feature depends on: exactly one non-superseded chart row per Client.
  [`client.py:170`](../../shell/adapters/postgres/client.py#L170)

- The nullable column whose `NULL`/timestamp state distinguishes current from superseded.
  [`client.py:81`](../../shell/adapters/postgres/client.py#L81)

**Route orchestration: warn, then confirm**

- The confirm gate: identical resolve/compute path as `create_client`, but nothing persists until
  this check passes.
  [`clients.py:442`](../../shell/http/routes/clients.py#L442)

- Correction POST handler: mirrors the create route's validation/resolution/computation sequence.
  [`clients.py:327`](../../shell/http/routes/clients.py#L327)

- Prefilled GET form; birthplace intentionally starts blank (no stored free-text to prefill from).
  [`clients.py:304`](../../shell/http/routes/clients.py#L304)

**Cross-story consistency: the chart wheel must track the current chart**

- The one-line fix that keeps Story 2.6's chart route correct once a Client can have >1 chart row.
  [`chart.py:52`](../../shell/http/routes/chart.py#L52)

**Schema change**

- Adds the nullable `superseded_at` column this whole story depends on.
  [`0004_supersede_natal_chart.py:28`](../../migrations/versions/0004_supersede_natal_chart.py#L28)

**Peripherals**

- Warning/confirm UI states, including the `candidate` hidden-field carry-over.
  [`client_edit.html:16`](../../shell/http/templates/client_edit.html#L16)

- Proves the unconfirmed path persists nothing.
  [`test_http_client_correction.py:323`](../../tests/test_http_client_correction.py#L323)

- Proves a confirmed correction supersedes the old chart and updates the Client.
  [`test_http_client_correction.py:349`](../../tests/test_http_client_correction.py#L349)

- Cross-story regression: `GET /clients/{id}/chart` reflects a confirmed correction.
  [`test_http_client_correction.py:506`](../../tests/test_http_client_correction.py#L506)
