---
title: 'Bind the verified ephemeris path on whatever thread computes'
type: 'bugfix'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '5df712c806b09c032d49a6f4afcc10c10b7eb08c'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `verify_ephemeris_identity()` calls `swe.set_ephe_path()` once, at
shell import, on the main thread. In the vendored `pyswisseph` build that path
is **thread-local**, so every computation that runs on another thread starts
with no ephemeris path and `swe.calc_ut` silently falls back to Moshier —
`_calc_body` then raises `EphemerisIntegrityError`. FastAPI runs sync route
handlers (`poll_report_run`, `start_report_run`) in an anyio worker threadpool,
so the entire monthly-report pipeline (`transits_ready` and every stage after
it) fails in the deployed app for every run. Natal chart creation works only
because `create_client` is `async` (event-loop / main thread); the test suite
is green only because pytest is single-threaded. Found and root-caused by the
2026-08-28 manual browser check (epic-3-retro item 22); already half-known
(`tests/test_http_clients.py:246-256`).

**Approach:** Make `core.ephemeris.identity` remember the directory it last
verified, and expose a function that re-applies that already-verified path to
the current thread, once, cheaply (a `threading.local` guard so the `.se1`
files are not reopened on every call). Call it at the single `swe.calc_ut`
chokepoint (`_calc_body`) and at the top of `compute_natal_chart` (for
`swe.houses`). No route, no runner, and no computation signature changes.

## Boundaries & Constraints

**Always:**
- The "computation never proceeds against an unverified ephemeris" invariant
  holds on every thread: if `verify_ephemeris_identity()` has never run in the
  process, the new function raises `EphemerisIntegrityError`, it does not
  silently set a default path.
- The bind is idempotent and cheap after the first call per thread — it must
  not call `swe.set_ephe_path()` again once the current thread already holds
  the currently-verified directory (reopening ephemeris files per `_calc_body`
  call is a real perf regression on a month scan).
- If `verify_ephemeris_identity()` is later called again with a *different*
  directory, threads re-bind to the new one on their next computation (guard
  keyed on the directory string, not a bare bool). This keeps the existing
  `tests/conftest.py::_ephemeris_pinned_to_the_real_vendored_files` autouse
  re-pin behaviour correct.
- `core/ephemeris/` stays the only part of `core/` that touches this — the
  import-boundary carve-out already covers it.

**Ask First:**
- Making `poll_report_run` / `start_report_run` `async` and dispatching
  `drive()` through an explicit threadpool instead (larger change — `drive()`
  is sync DB work; the threadpool dispatch is correct, only the path binding
  is missing).

**Never:**
- Calling `swe.set_ephe_path()` unconditionally inside `_calc_body` with no
  guard (perf).
- Re-running the checksum verification (`_sha256` over every file) per thread
  or per call — only the *path bind* is repeated, never the integrity check.
- Changing `_CALC_FLAGS`, the Moshier guard in `_calc_body`, or the
  `EphemerisIntegrityError` raised when `swe.calc_ut` returns non-`SWIEPH`
  flags.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Compute on the import/main thread | `verify_ephemeris_identity()` ran at import; `_calc_body` called on same thread | Position returned via Swiss Ephemeris, exactly as today | N/A |
| Compute on a fresh worker thread | `verify_ephemeris_identity()` ran on the main thread only; `_calc_body` (or `compute_natal_chart`, `find_transit_aspects`, …) called from another thread | Bind re-applies the verified path on that thread; position returned via Swiss Ephemeris; **no** Moshier fallback, **no** `EphemerisIntegrityError` | N/A |
| Repeated calls on the same worker thread | Thread already bound to the current verified dir | `swe.set_ephe_path()` is **not** called again; position returned | N/A |
| Compute before any verify | `verify_ephemeris_identity()` never called in this process; `_calc_body` invoked | `EphemerisIntegrityError` naming that the ephemeris was never verified | Raised, not swallowed |
| Verified dir changed then compute | `verify_ephemeris_identity(dir_a)` then `verify_ephemeris_identity(dir_b)` on main thread; `_calc_body` on a worker thread previously bound to `dir_a` | Worker re-binds to `dir_b`, computes against `dir_b` | N/A |

</frozen-after-approval>

## Code Map

- `core/ephemeris/identity.py` -- **primary change.** `verify_ephemeris_identity()`
  (line 161) currently calls `swe.set_ephe_path(str(ephemeris_dir))` at line 198
  and returns. Add a module-level record of the verified directory (set right
  after line 198), a module-level `threading.local()`, and a new public function
  `bind_verified_ephemeris_path_to_current_thread()` (add to `__all__`).
  `EphemerisIntegrityError` is already imported from `core.errors`.
- `core/ephemeris/positions.py` -- `_calc_body` (line 67) is the **single
  `swe.calc_ut` chokepoint**: every natal *and* transit body position
  (`chart.py:127`, `core/transits/{aspects,ingresses,lunations,stations}.py`
  all via `_calc_body` / `_longitude_at`) funnels here. Add the bind call as the
  first line of `_calc_body`, before `swe.calc_ut` at line 68. Import the new
  function from `core.ephemeris.identity` (same package, no import cycle —
  `identity.py` imports only `hashlib`, `dataclass`, `Path`, `swisseph`,
  `core.errors`).
- `core/ephemeris/chart.py` -- `compute_natal_chart` (line 99) calls `_calc_body`
  at line 127 *then* `swe.houses()` at line 129 on the same thread. Add an
  explicit bind call right after `_require_utc(...)` (line 123) so `swe.houses`
  is covered independently of statement order. Import the new function.
- `tests/test_http_clients.py:246-256` -- `fake_chart_computation`'s docstring
  already describes this exact per-thread `set_ephe_path` fact; no change here,
  but it is the corroborating evidence.
- `tests/conftest.py:46-55` -- `_ephemeris_pinned_to_the_real_vendored_files`
  autouse fixture re-runs `verify_ephemeris_identity()` before every test; the
  directory-keyed guard must not defeat it (it will not: that fixture calls the
  real `swe.set_ephe_path` every test regardless of the guard).
- `tests/test_ephemeris_identity.py` -- home for the new unit tests of the bind
  function (thread behaviour, unverified-process error, re-bind on dir change).
- `docs/release-validation/manual-browser-checks.md` and
  `_bmad-output/implementation-artifacts/deferred-work.md` -- the finding is
  recorded in both; update the deferred-work entry's status once this lands.

## Tasks & Acceptance

**Execution:**
- [x] `core/ephemeris/identity.py` -- add module state `_verified_ephemeris_dir: str | None`
  (set to `str(ephemeris_dir)` immediately after the successful
  `swe.set_ephe_path` call), a module-level `threading.local`, and
  `bind_verified_ephemeris_path_to_current_thread()`: raise
  `EphemerisIntegrityError` if `_verified_ephemeris_dir is None`; return early
  if `getattr(_local, "bound_dir", None) == _verified_ephemeris_dir`; else call
  `swe.set_ephe_path(_verified_ephemeris_dir)` and record `_local.bound_dir`.
  Also set `_local.bound_dir` inside `verify_ephemeris_identity()` itself (it
  just pinned the path on its own thread). Add the name to `__all__` and give
  it a docstring explaining the thread-local `swed` in this `pyswisseph` build.
- [x] `core/ephemeris/positions.py` -- call
  `bind_verified_ephemeris_path_to_current_thread()` as the first statement of
  `_calc_body`, before `swe.calc_ut`. Update the module docstring's "assumes
  verify_ephemeris_identity() has run" note to "…has run in this process; the
  path is re-bound to the calling thread here".
- [x] `core/ephemeris/chart.py` -- call the bind function right after
  `_require_utc(birth_instant_utc)` in `compute_natal_chart`; update the
  docstring lines 7-9 / 118-121 that claim the module never touches the path.
- [x] `tests/test_ephemeris_identity.py` -- unit-test the I/O matrix rows: bind
  succeeds and lets `_calc_body` compute from a `threading.Thread` worker that
  never called `verify_ephemeris_identity()`; repeated calls on one thread call
  `swe.set_ephe_path` once (spy/monkeypatch count); a process state with
  `_verified_ephemeris_dir is None` raises; changing the verified dir re-binds.
  Restore real module state in a fixture/finalizer so later tests are unaffected.
- [x] `tests/test_transit_aspects.py` (or `test_natal_chart.py`) -- one
  end-to-end test: `find_transit_aspects(...)` (and `compute_natal_chart(...)`)
  run inside a `concurrent.futures.ThreadPoolExecutor` worker return the same
  result as on the main thread — the regression test that would have caught the
  shipped bug.

**Acceptance Criteria:**
- Given the running `docker compose` stack, when a report run is started and
  polled, then it advances past `transits_ready` to `payload_ready` (and the
  Story 3.9 Payload view at `GET /report-runs/{id}/payload` renders instead of
  404) — the check that failed on 2026-08-28.
- Given the full suite, when `uv run pytest` runs, then it stays green with the
  new thread tests passing and no change to any conformance fixture value.
- Given a month scan, when `find_transit_aspects` runs on a worker thread, then
  `swe.set_ephe_path` is invoked at most once for that thread (not once per
  `_calc_body`).

## Spec Change Log

## Design Notes

Root cause (verified in-container 2026-08-28): set the path on the main thread
→ `_calc_body` for the same date succeeds there and raises
`EphemerisIntegrityError` on a `threading.Thread` / `anyio.to_thread` worker;
calling `swe.set_ephe_path()` inside that worker fixes it. `pyswisseph`'s
`swed` struct is `__thread`-local in this build.

Guard shape (keyed on the directory, self-correcting):

```python
_verified_ephemeris_dir: str | None = None
_thread_state = threading.local()

def bind_verified_ephemeris_path_to_current_thread() -> None:
    if _verified_ephemeris_dir is None:
        raise EphemerisIntegrityError(
            "Refusing to compute: verify_ephemeris_identity() has not run in "
            "this process; there is no verified ephemeris path to bind."
        )
    if getattr(_thread_state, "bound_dir", None) == _verified_ephemeris_dir:
        return
    swe.set_ephe_path(_verified_ephemeris_dir)
    _thread_state.bound_dir = _verified_ephemeris_dir
```

Why not thread `EphemerisIdentity` through the call chain: `drive()` already
receives it, but `core/transits/*` and `_calc_body` do not, and adding a
parameter to every position lookup for a process-global concern is heavier than
a module-scoped rebind. Why not make the routes async: `drive()` is blocking
sync DB work; the threadpool dispatch is correct — only the path bind is
missing.

## Verification

**Commands:**
- `uv run pytest tests/test_ephemeris_identity.py tests/test_transit_aspects.py tests/test_natal_chart.py -q` -- new thread tests green
- `uv run pytest` -- full suite green, 0 conformance fixture changes
- `uv run ruff check .` -- clean

**Manual checks (if no CLI):**
- `docker compose up -d --build`; sign in; create a client; `POST
  /clients/{id}/report-runs` with a `month`; poll `GET /report-runs/{id}` — it
  reaches `payload_ready`; `GET /report-runs/{id}/payload` renders the frozen
  payload (no `transits_ready` Moshier failure). Record the result in
  `docs/release-validation/manual-browser-checks.md`.

## Suggested Review Order

**The design — one function, called from the two swisseph chokepoints**

- Entry point: why re-binding is needed at all (thread-local `swed`) and the cheap per-thread guard.
  [`identity.py:241`](../../core/ephemeris/identity.py#L241)

- Verified-dir is recorded here after the checksum pass, and this thread is marked bound.
  [`identity.py:200`](../../core/ephemeris/identity.py#L200)

- Module state: the process-wide verified dir and the per-thread bind marker.
  [`identity.py:61`](../../core/ephemeris/identity.py#L61)

**Call sites — every `swe.calc_ut` / `swe.houses` path**

- The single `swe.calc_ut` chokepoint (natal + all transit scans funnel here); bind is the first line.
  [`positions.py:81`](../../core/ephemeris/positions.py#L81)

- Belt-and-braces for `swe.houses`, which cannot self-report a Moshier fallback.
  [`chart.py:134`](../../core/ephemeris/chart.py#L134)

**Tests — proven to fail without the fix**

- Unit: bind is a no-op once bound, sets the path once per fresh worker thread, refuses when unverified, re-binds on dir change.
  [`test_ephemeris_identity.py:328`](../../tests/test_ephemeris_identity.py#L328)

- Regression: `_calc_body` on a `ThreadPoolExecutor` worker matches the main thread (raised `EphemerisIntegrityError` before the fix).
  [`test_ephemeris_identity.py:425`](../../tests/test_ephemeris_identity.py#L425)

- End-to-end, real ephemeris: `find_transit_aspects` off the main thread.
  [`test_transit_aspects.py:435`](../../tests/test_transit_aspects.py#L435)

- End-to-end: `compute_natal_chart` off the main thread (covers the `swe.houses` bind).
  [`test_natal_chart.py:254`](../../tests/test_natal_chart.py#L254)
