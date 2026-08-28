---
title: 'Retro F: test-coverage hardening — real-geocoder create_client path + N=2 superseded-chart chain (items 10, 12)'
type: 'chore'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '8929fddcb7bea4f101b938ee8151d4d0c3e4d6c9'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Two epic-2 retrospective action items are still `open`, both pure test-coverage gaps in the client HTTP routes. **Item 10:** every HTTP-layer test of `create_client` overrides `get_geocoder` with a wholesale fake, so the real `NominatimGeocoder` + real `PLACE_CACHE` write-through has never run through the `POST /clients` request/session lifecycle (the `correct_client` half of this item is already covered — `test_http_client_correction.py` grew `_use_real_geocoder` + two real-geocoder tests during the epic-2 place-cache fix). **Item 12:** the superseded-chart chain is exercised only at depth N=1 (one correction); the "exactly one current chart" invariant — enforced by `correct_client_and_chart`'s `.one()` on the non-superseded row — is never tested at N=2 through the chart-wheel (`GET /clients/{id}/chart`) or delete (`GET`/`POST /clients/{id}/delete`) routes.

**Approach:** Add focused tests only, no production change. For item 10, add one real-`NominatimGeocoder` override (fake `geolocator`/`timezone_finder`, no network) bound to the live request session, and two `POST /clients` tests proving the fresh place is written through to `PLACE_CACHE` inside the Client's own transaction and that a second create of the same place is served from cache. For item 12, reach N=2 the same way each target file already reaches N=1 (a helper calling `correct_client_and_chart` twice), then assert the chart-wheel and delete routes both behave correctly with two superseded rows present.

## Boundaries & Constraints

**Always:**
- Test files only, plus the `sprint-status.yaml` tracker reconciliation. No change to any `shell/`, `core/`, or `migrations/` file, `conftest.py`, CI config, or pytest markers.
- No real network and no real timezone dataset: inject fake `geolocator`/`timezone_finder` into `NominatimGeocoder`, exactly as `tests/test_geocoder_nominatim.py` and `tests/test_http_client_correction.py` already do.
- Reuse each target file's existing fixtures, seed helpers, and fake classes. Do not import fakes across test modules — each file keeps its own copy, per the established convention.
- Bind the real geocoder to the live per-request session via `Depends(get_session)`, never a session captured at override time.
- Item 12 corrections go through a helper that calls `correct_client_and_chart(...)` then `commit()` — matching `test_http_client_deletion.py`'s existing `_supersede` — not by hand-building `StoredNatalChart` rows. Use a distinct birth instant per correction so the three charts have visibly different positions.
- Every new test carries a vacuous-guard assertion where a fixture could silently become empty (`assert len(...) == N` before the behavioural assertion), matching the "fixture is vacuous" guards already in these files.
- Update `tests/test_http_clients.py`'s module docstring ("The `Geocoder` is a fake throughout") to record the one real-adapter exception.

**Ask First:**
- If wiring the real `NominatimGeocoder` through `create_client` surfaces an actual route defect (e.g. the cache write not sharing the Client's transaction), HALT and report — do not fix the route under this test-only spec.

**Never:**
- No new shared test-utility module, no cross-file fixture extraction.
- No "one real-adapter integration test per port" convention rollout — that standing question stays open (item 3); this spec covers only `create_client`.
- No N>2 depth, no production refactor.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Item 10 — fresh place via real geocoder | Authenticated `POST /clients`, valid new-client form; `get_geocoder` → real `NominatimGeocoder` with fake geolocator returning one unambiguous match; place not yet cached | Client + chart persisted; `lookup_cached_place(session, birthplace)` returns the resolved lat/lon/zone on the same session that holds the new Client; fake geolocator called exactly once | N/A |
| Item 10 — cache hit on second create | Two sequential `POST /clients` for different people, same birthplace text, real geocoder | Both succeed; the second resolves from `PLACE_CACHE`; fake geolocator called exactly once in total | N/A |
| Item 12 — chart-wheel route at N=2 | Client seeded, then two corrections via the `_supersede` helper (distinct instants); `GET /clients/{id}/chart` | 200; exactly one non-superseded `StoredNatalChart` row and two superseded; rendered Sun position matches the third (current) chart and neither earlier one | N/A |
| Item 12 — delete route at N=2 | Same N=2 state; `GET` then `POST /clients/{id}/delete` with `confirmed=1` | GET confirmation page names the superseded chart(s); POST removes the Client and all three chart rows in one transaction | N/A |
| Item 12 — `.one()` invariant at depth | Second `_supersede` call after the first correction | `correct_client_and_chart`'s `select(...superseded_at.is_(None)).one()` finds exactly one row; no `MultipleResultsFound` | N/A |

</frozen-after-approval>

## Code Map

- `tests/test_http_clients.py` -- item 10 lands here. Reuse: `db_session`/`client`/`authenticated_client`/`app_instance` fixtures (132-164), `_use_geocoder` (166-167), `_clients`/`_charts` (170-175), `fake_chart_computation` (178-191), `_VALID_FORM` (72-77), `_RESOLVED_PLACE` (65-70). Update the module docstring (lines 4-9). NOTE: this file's `db_session` shares one session across requests — fine for the `PLACE_CACHE` assertion (single session sees the write) — but still wire the real geocoder through `Depends(get_session)`.
- `tests/test_http_client_correction.py` -- reference implementation to copy from, **not modified**: `_use_real_geocoder` (295-310), `_FakeGeolocator` (270-281), `_FakeLocation` (259-267), `_FakeTimezoneFinder` (284-292); its per-request-session `client` fixture (221-235) is the correct model. Existing item-10 `correct_client` coverage: tests at lines 617, 655.
- `tests/test_geocoder_nominatim.py` -- canonical no-network fakes: `_FakeGeolocator`/`_FakeTimezoneFinder`/`_FakeLocation` (24-54).
- `tests/test_http_chart_wheel.py` -- item 12 chart-wheel half. Reuse `_seed_client_with_chart` (121-133), `_rendered_abs_pos` (102-114), `_natal_chart` (117-118), fixtures (136-164). No superseded-chart test exists here yet. Add a `_supersede`-style helper (import `correct_client_and_chart`).
- `tests/test_http_client_deletion.py` -- item 12 delete half. Reuse `_seed_client_with_chart` (103-115), `_supersede` (118-131), `_charts_for` (134-137). Existing N=1 superseded tests: 170-208, 264-277.
- `shell/adapters/postgres/client.py:272-322` -- `correct_client_and_chart`; the `.one()` on the non-superseded row (297-303) is the invariant item 12 exercises. READ-ONLY.
- `shell/http/routes/chart.py:44-60` -- `chart_wheel_view`; `.where(superseded_at.is_(None)).first()`. READ-ONLY.
- `shell/http/routes/clients.py:205-347` -- `get_geocoder` (205-218), `create_client` (225+), `correct_client` (350+). READ-ONLY.
- `shell/adapters/postgres/place_cache.py` -- `lookup_cached_place`, `store_resolved_place` (nested SAVEPOINT, flush not commit). READ-ONLY.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_http_clients.py` -- add local `_FakeLocation`/`_FakeGeolocator`/`_FakeTimezoneFinder` classes and a `_use_real_geocoder` helper (mirrors `test_http_client_correction.py:295-310`, bound via `Depends(get_session)`); add the two item-10 matrix tests (fresh-place `PLACE_CACHE` write-through inside the Client's transaction; second create of the same place served from cache, geolocator called once total); revise the "fake throughout" module docstring to note the real-adapter exception.
- [x] `tests/test_http_chart_wheel.py` -- add a `_supersede(db_session, client, *, instant)` helper (`correct_client_and_chart` + `commit`, distinct instant per call); add a test that after two corrections `GET /clients/{id}/chart` returns 200, exactly one non-superseded row exists (with two superseded), and the rendered Sun position matches the third chart and neither earlier one.
- [x] `tests/test_http_client_deletion.py` -- add a test reaching N=2 (call `_supersede` twice) asserting the delete confirmation `GET` names the superseded chart(s) and `POST /clients/{id}/delete` with `confirmed=1` removes the Client and all three `StoredNatalChart` rows.
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- set the `action_items` entries `epic-2-retro-item-10-add-at-least-one-http-level-test-that-wi` and `epic-2-retro-item-12-add-a-test-exercising-the-superseded-cha` to `status: done` with `ref` pointing at this spec.

**Acceptance Criteria:**
- Given a fresh birthplace and the real `NominatimGeocoder`, when `POST /clients` completes, then the birthplace is retrievable via `lookup_cached_place` on the same session holding the new Client — proving the cache write shares the request transaction and is not rolled back.
- Given a client corrected twice, when either the chart-wheel or the delete route is hit, then exactly one `StoredNatalChart` row is non-superseded and the route renders / deletes the full set without error.
- Given the full suite, when `uv run ruff check .` and `uv run pytest` run, then both pass (xfail_strict: no XPASS) with no new warnings.
- No file outside `tests/` and `_bmad-output/implementation-artifacts/sprint-status.yaml` is modified.

## Design Notes

No-network pattern (copy verbatim into `test_http_clients.py`, keep local): `_FakeLocation` dataclass (`address: str`, `latitude`/`longitude: float`); `_FakeGeolocator` records `.calls` and returns a canned `list[_FakeLocation] | None` from `geocode(query, exactly_one)`; `_FakeTimezoneFinder.timezone_at(*, lat, lng)` returns a fixed IANA zone. Override:

```python
def _use_real_geocoder(app, geolocator, timezone_finder):
    def _get_real_geocoder(session: Session = Depends(get_session)) -> Geocoder:
        return NominatimGeocoder(session, geolocator=geolocator, timezone_finder=timezone_finder)
    app.dependency_overrides[get_geocoder] = _get_real_geocoder
```

Item 12 reaches N=2 the way `test_http_client_deletion.py` already reaches N=1: a helper calling `correct_client_and_chart(...)` then `session.commit()`, called twice. `correct_client_and_chart` selects the non-superseded row with `.one()` (`shell/adapters/postgres/client.py:297-303`) — the second call is what exercises that invariant at depth; a prior correction that left two current rows would make `.one()` raise `MultipleResultsFound` and fail the test loudly. Give each correction a distinct `birth_time` (and matching UTC instant for `compute_natal_chart`) so the three stored charts have different Sun longitudes and "the route rendered the *current* chart" is provable rather than assumed.

## Verification

**Commands:**
- `uv run pytest tests/test_http_clients.py tests/test_http_chart_wheel.py tests/test_http_client_deletion.py` -- expected: all pass, new tests included.
- `uv run ruff check .` -- expected: clean.
- `uv run pytest` -- expected: full suite green, no XPASS.

## Suggested Review Order

**Item 10 — real `NominatimGeocoder` wired through `create_client`**

- Entry point: the override that swaps the wholesale fake for the real adapter (fake geolocator/tz, no network) bound to the live request session.
  [`test_http_clients.py:214`](../../tests/test_http_clients.py#L214)
- Local fake trio (geolocator records calls; tz returns a fixed zone) — copied per this project's no-cross-import convention.
  [`test_http_clients.py:189`](../../tests/test_http_clients.py#L189)
- Fresh place: `POST /clients` writes lat/lon/zone through to `PLACE_CACHE` in the Client's own transaction; Client row carries the resolved values.
  [`test_http_clients.py:308`](../../tests/test_http_clients.py#L308)
- Cache hit: a second create of the same place text is served from `PLACE_CACHE`; geolocator called once in total.
  [`test_http_clients.py:350`](../../tests/test_http_clients.py#L350)
- Module docstring revised from "fake throughout" to name the real-adapter exception.
  [`test_http_clients.py:1`](../../tests/test_http_clients.py#L1)

**Item 12 — superseded-chart chain at N=2**

- Chart-wheel half: after two corrections, `GET /chart` renders the current (third) chart's Sun and neither superseded one; exactly one non-superseded row.
  [`test_http_chart_wheel.py:268`](../../tests/test_http_chart_wheel.py#L268)
- Its `_supersede` helper — `correct_client_and_chart` + `commit`, only `natal_chart` varies with `instant`; twice ⇒ N=2, exercising `.one()` on the non-superseded row at depth.
  [`test_http_chart_wheel.py:141`](../../tests/test_http_chart_wheel.py#L141)
- Delete half: at N=2 the confirmation `GET` names the superseded chart(s) and `POST …/delete` removes the Client and all three chart rows.
  [`test_http_client_deletion.py:295`](../../tests/test_http_client_deletion.py#L295)
- Its `_supersede` gained an optional `instant` kwarg (default keeps the N=1 callers unchanged).
  [`test_http_client_deletion.py:118`](../../tests/test_http_client_deletion.py#L118)

**Peripheral**

- Tracker: retro action items 10 and 12 marked `done`, `ref` repointed at this spec.
  [`sprint-status.yaml:182`](sprint-status.yaml#L182)
