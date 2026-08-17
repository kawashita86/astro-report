---
title: 'Fix PLACE_CACHE rollback in the correction warn/confirm flow'
type: 'bugfix'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: '5291b596a07ebd1e7ae4fa69f08093d0f0e3138d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 2's retrospective (`_bmad-output/implementation-artifacts/epic-2-retro-2026-08-17.md`, action items 1–2) found that `POST /clients/{id}/edit`'s warn-then-confirm flow calls `Geocoder.resolve()` on *both* the warning request and the confirming request, but only commits once, after confirmation. A fresh place's `PLACE_CACHE` write-through from the warning-only request is silently rolled back when that request's session closes (`get_session`'s own documented behavior), so the confirming resubmission re-resolves against a cache that was never written and hits Nominatim live a second time — contradicting the route's own docstring ("re-running resolution is cheap -- `PLACE_CACHE` absorbs a repeat lookup"). The existing test suite cannot catch this: `tests/test_http_client_correction.py`'s fixture overrides `get_session` with one shared, never-closed `Session` across every simulated request in a test, which does not reproduce production's per-request session lifecycle.

**Approach:** Commit the session right after a successful resolution (whether via `resolve()` or `resolve_candidate()`) and before `compute_natal_chart()` is attempted, so a fresh place's cache write survives *every* early-return path between resolution and the confirm gate — not only the warning branch — independently of whether the correction is ultimately confirmed. The correction's own persistence step keeps its existing single atomic commit for Client/Chart data, untouched. Fix the test fixture to open a fresh `Session` per simulated request, matching production, and add regression tests using the real `NominatimGeocoder` (fake `geolocator`/`timezone_finder`, no network) proving the cache write survives (a) the warning step and (b) a subsequent `compute_natal_chart()` failure, and that a later confirm/retry gets a cache hit either way.

## Boundaries & Constraints

**Always:** The confirming request's existing "resolution, computation and persistence commit together or not at all" guarantee for **Client/Chart data** (`correct_client_and_chart`'s own docstring) must stay exactly as-is — its dedicated final `session.commit()` is untouched, and `correct_client_and_chart()` is never called before that point. The resolution commit added by this fix persists only whatever `store_resolved_place()`'s nested `SAVEPOINT` staged (a `PlaceCache` row, if any) — nothing else is pending on the session at that point in the function, on any path, so this commit can never leak partial Client/Chart data regardless of which later branch (warning return, compute-failure return, or full confirm) the request takes. `create_client` (Story 2.3, no warn/confirm split) is out of scope — do not touch it even though it has an analogous but distinct gap (noted below). `resolve_candidate()` never touches `PLACE_CACHE`, so this added commit is a no-op on that path — harmless, not a special case to code around.

**Ask First:** None — the fix is fully specified.

**Never:** Do not change `store_resolved_place()`'s own nested-transaction (`SAVEPOINT`) design, or `get_session`'s per-request semantics in production code (`shell/http/app.py`). Do not change any other test file's session-sharing pattern (out of scope — if the same pattern exists elsewhere, log it to `deferred-work.md`, do not fix it).

</frozen-after-approval>

## Code Map

- `shell/http/routes/clients.py:465-481` -- `correct_client()`, right after the resolve try/except block succeeds and before `compute_natal_chart()` is called; add `session.commit()` here (once), covering both the compute-failure early return (`except (ValueError, EphemerisIntegrityError)`) and the warning-branch early return that follow it. Remove the narrower commit previously added inside the warning branch alone.
- `shell/http/app.py:61-71` -- `get_session()`, the production per-request session semantics the test fixture must mirror.
- `shell/adapters/nominatim/geocoder.py:64-112` -- `NominatimGeocoder.resolve()`; the only path that touches `PLACE_CACHE` (`resolve_candidate()` at line 114 does not).
- `shell/adapters/postgres/place_cache.py` -- `store_resolved_place()` (nested-transaction write, flush not commit) and `lookup_cached_place()`, used by the new test's assertion.
- `tests/test_http_client_correction.py:184-225` -- `db_session`/`client`/`_use_geocoder` fixtures; split `db_session` into an `engine` fixture plus a per-request `get_session` override.
- `tests/test_geocoder_nominatim.py:23-52` -- `_FakeLocation`/`_FakeGeolocator`/`_FakeTimezoneFinder`, the pattern to mirror locally for the new test (do not import across test files — mirror, per this file's own docstring convention).

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/routes/clients.py` -- move `session.commit()` to fire once, right after a successful resolve (before `compute_natal_chart()` is attempted), covering both the compute-failure and warning-branch early returns -- makes a fresh place's cache write durable independent of what happens afterward in the request.
- [x] `tests/test_http_client_correction.py` -- split `db_session` into an `engine` fixture (exposed) + `db_session` (a `Session` on it, for seeding/assertions) + change the `client` fixture's `get_session` override to open/close a fresh `Session(engine)` per call, mirroring `shell/http/app.py`'s `get_session`.
- [x] `tests/test_http_client_correction.py` -- add local `_FakeLocation`/`_FakeGeolocator`/`_FakeTimezoneFinder` (mirroring `tests/test_geocoder_nominatim.py`) and a `_use_real_geocoder()` helper (real `NominatimGeocoder(session, geolocator=fake, timezone_finder=fake)` bound to the active per-request session via `Depends(get_session)`).
- [x] `tests/test_http_client_correction.py` -- regression test: seed a Client, POST the warning step for a genuinely new (never-cached) birthplace, assert a `PlaceCache` row now exists (`lookup_cached_place`) and the fake geolocator was called exactly once; then POST the confirming step and assert the geolocator call count is still exactly one.
- [x] `tests/test_http_client_correction.py` -- second regression test: seed a Client, use the real geocoder for a genuinely new birthplace, monkeypatch `compute_natal_chart` to raise `EphemerisIntegrityError` on the warning submission, assert the response is 422 *and* a `PlaceCache` row for that place exists afterward (the compute-failure branch this loopback added).

**Acceptance Criteria:**
- Given a Client correction to a genuinely new (never-cached) birthplace, when the warning step alone is submitted (never confirmed), then a `PlaceCache` row for that place exists in the database afterward.
- Given a genuinely new birthplace resolves successfully but `compute_natal_chart()` then raises, when the request returns its 422, then a `PlaceCache` row for that place exists in the database afterward.
- Given the same correction is then confirmed, when the confirming request resolves the birthplace again, then the real geocoder's underlying `geocode()` call is not invoked a second time (cache hit).
- Given the existing fake-geocoder-based tests in `tests/test_http_client_correction.py`, when the fixture change lands, then they all still pass unmodified (no assertion changes needed in tests that don't touch `PLACE_CACHE`).

## Spec Change Log

- **Finding (step-04 review, blind-hunter + own verification-gap pass):** the first implementation committed only inside `correct_client`'s warning branch, per this spec's original Boundaries ("only the warning-branch early return gains a commit, and only that branch"). Review found a third early-return path between a successful `resolve()` and that commit — `compute_natal_chart()` raising `ValueError`/`EphemerisIntegrityError` (lines 476-479) — which returns 422 without ever reaching the commit, rolling back the same fresh place's cache write via the same mechanism the fix was meant to close. No test exercised this path with the real geocoder (the existing compute-failure test uses a fake geocoder that never touches `PLACE_CACHE`). **Human decision:** move the commit to fire once, immediately after a successful resolve, before `compute_natal_chart()` is attempted — covering both early-return paths uniformly — rather than adding a second, narrower commit specific to the compute-failure branch. **Avoids:** leaving the identical bug class open on an early-return path this fix's own investigation missed; a narrower two-commit patch that would have been harder to reason about than one commit placed at the true point of durability (a successful resolution). **KEEP:** the confirm path's Client/Chart persistence still ends in exactly one final `session.commit()`, unchanged by this loopback — the resolution commit is provably disjoint from it (nothing else is ever pending on the session at the point the new commit fires, on any path).

## Design Notes

`create_client` (Story 2.3) has the same-shaped gap for a different trigger: a resolve-then-cache-write followed by a *validation failure* in `compute_natal_chart()` also rolls back the cache write, since `create_client` has one commit at the very end and no warn/confirm split to bisect. This is real but out of this fix's scope (the retro's action items name only `correct_client` and its test fixture) — log it to `deferred-work.md` with `source_spec` pointing at this spec, once this fix is verified, rather than fixing it here.

## Verification

**Commands:**
- `uv run pytest tests/test_http_client_correction.py -v` -- all existing tests still pass, plus the new regression test, green
- `uv run pytest` -- full suite green (431+ passed, 3 xfailed, 0 failed)
- `uv run ruff check .` -- clean

## Suggested Review Order

**The fix**

- The one-line root cause: this route resolves and computes on every submission, but historically committed only after confirmation, so any earlier work (a fresh place's cache write) was lost on an early return.
  [`clients.py:366`](../../shell/http/routes/clients.py#L366)

- The fix itself: commit right after a successful resolve, before `compute_natal_chart()` is even attempted -- covers both the compute-failure and warning-branch early returns with one commit, leaves the confirm path's own final commit untouched.
  [`clients.py:480`](../../shell/http/routes/clients.py#L480)

- The confirm path's pre-existing, unmodified commit -- resolution, computation and Client/Chart persistence still succeed or fail together as one unit.
  [`clients.py:515`](../../shell/http/routes/clients.py#L515)

**Test infrastructure the fix depends on**

- Per-request session lifecycle now mirrors production instead of sharing one never-closed session across simulated requests -- without this, neither regression test below could distinguish a real fix from a masked bug.
  [`test_http_client_correction.py:219`](../../tests/test_http_client_correction.py#L219)

- Real `NominatimGeocoder` (fake geolocator/timezone_finder, no network) wired through the active per-request session, instead of the file's usual fully-fake `Geocoder` -- needed because the fake never touches `PLACE_CACHE`.
  [`test_http_client_correction.py:293`](../../tests/test_http_client_correction.py#L293)

**Regression tests**

- Proves the warning step's cache write survives and the confirm step gets a cache hit instead of a second live call.
  [`test_http_client_correction.py:576`](../../tests/test_http_client_correction.py#L576)

- Proves the same for the loopback's finding: a `compute_natal_chart()` failure after a successful resolve still leaves the cache write durable.
  [`test_http_client_correction.py:614`](../../tests/test_http_client_correction.py#L614)
