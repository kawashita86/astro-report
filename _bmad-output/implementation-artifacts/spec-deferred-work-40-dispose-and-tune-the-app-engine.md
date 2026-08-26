---
title: 'deferred-work item 40 — Dispose the app''s SQLAlchemy engine on shutdown and tune it with pool_pre_ping'
type: 'bugfix'
created: '2026-08-26'
status: 'done'
review_loop_iteration: 0
baseline_commit: '00978ce465965554f1a1eb959ef61f26f9e2c15e'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `create_app()` (`shell/http/app.py:113`) builds the application's long-lived engine with
`create_engine(settings.sqlalchemy_url)` -- no `dispose()`/shutdown hook and no `pool_pre_ping`.
`migrations/env.py`'s own engine is disposed in a `try/finally` right after use (line 44-53), but the
app's engine, which lives for the process's whole lifetime, has no equivalent teardown or
connection-health tuning. On Render's free tier a dropped idle connection or a container restart is
currently invisible until a request fails against it.

**Approach:** Add `pool_pre_ping=True` to the existing `create_engine(...)` call so a stale pooled
connection is detected and transparently replaced before use. Give the app a lifespan handler --
FastAPI's current mechanism, `on_event` is deprecated -- that disposes `application.state.engine`
after `yield`, i.e. on shutdown only.

## Boundaries & Constraints

**Always:**
- `create_engine(settings.sqlalchemy_url, pool_pre_ping=True)` -- add `pool_pre_ping=True` to the
  existing call; no other `create_engine` kwarg changes, no change to `sqlalchemy_url` itself.
- `application.state.engine` is still set exactly once per `create_app()` call, before the lifespan
  runs, so `get_session` (`shell/http/app.py:73-83`) is unaffected.
- The lifespan function does nothing before `yield`; it disposes `application.state.engine` only after
  `yield`, i.e. only on shutdown.
- `migrations/env.py`'s own engine and its existing `dispose()` call stay untouched -- a separate,
  already-correct short-lived engine.

**Ask First:** None.

**Never:**
- No `pool_size` / `max_overflow` / `pool_recycle` tuning beyond `pool_pre_ping` -- out of scope for
  this item.
- No change to `get_session`'s per-request `Session` usage or transaction boundaries.
- No change to any route, or to any test that doesn't touch `create_app()`/`app.py` directly.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Engine construction | `create_app(LOCAL)` | `create_engine` receives `pool_pre_ping=True` | N/A |
| App used without entering the lifespan (today's existing test pattern, e.g. `TestClient(create_app(LOCAL))` with no `with`) | Plain requests, no context-manager entry | Unchanged from today; `dispose()` is never called | N/A |
| App run as a lifespan context and shut down | `with TestClient(create_app(LOCAL)) as client: ...` | `application.state.engine.dispose()` is called exactly once, after the block exits | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/app.py:23-33,86-123` -- `create_app()`'s imports and engine construction. Add
  `from contextlib import asynccontextmanager` and `from collections.abc import AsyncIterator` to the
  import block (`Iterator` is already imported at line 26); define an `@asynccontextmanager` lifespan
  function; wire it via `FastAPI(..., lifespan=_lifespan)`; add `pool_pre_ping=True` to the existing
  `create_engine(settings.sqlalchemy_url)` call at line 113.
- `migrations/env.py:44-53` (`run_migrations_online`) -- existing precedent for disposing an engine in
  a `try/finally`; read-only reference, not touched by this change.
- `tests/test_http_app.py:70-89` (the `# --- The factory` section, after
  `test_the_module_level_app_exists_for_the_server_to_import` at line 86-88) -- add the new tests here.
  `TestClient` is already imported at line 20.

## Tasks & Acceptance

**Execution:**
- [x] `shell/http/app.py` -- wrap engine construction in an `@asynccontextmanager` lifespan function
  that disposes `application.state.engine` after `yield`; pass it as `FastAPI(..., lifespan=_lifespan)`;
  add `pool_pre_ping=True` to the `create_engine(settings.sqlalchemy_url)` call.
- [x] `tests/test_http_app.py` -- add three tests covering the I/O matrix: `create_engine` receives
  `pool_pre_ping=True`; `dispose()` is called exactly once when the app is run as a lifespan context and
  torn down; `dispose()` is never called when the app is used without entering the lifespan.

**Acceptance Criteria:**
- Given `create_app(LOCAL)` is called, when the engine is constructed, then `create_engine` receives
  `pool_pre_ping=True`.
- Given an app built with `create_app(...)` is run as an ASGI lifespan context (`with TestClient(app) as
  client: ...`), when the context exits, then `application.state.engine.dispose()` has been called
  exactly once.
- Given an app built with `create_app(...)` is used without entering the lifespan context (today's
  existing test pattern across the suite), when requests are made, then behavior is unchanged and
  `dispose()` is never called.

## Spec Change Log

## Design Notes

FastAPI's `@app.on_event("shutdown")` is deprecated in favor of a `lifespan` context manager passed to
`FastAPI(...)`. Because `application.state.engine` is set *after* `FastAPI(...)` is constructed, the
lifespan function must read `application.state.engine` at shutdown time (not close over a local
variable) -- by then `create_app()` has already assigned it:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    yield
    application.state.engine.dispose()

application = FastAPI(..., lifespan=_lifespan)
application.state.engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
```

`TestClient` only dispatches ASGI lifespan startup/shutdown events when used as a context manager
(`with TestClient(app) as client:`). Every existing test in the suite builds a bare
`TestClient(create_app(...))` without `with`, so this change is additive: none of them will trigger
`dispose()`, and none needs updating.

## Verification

**Commands:**
- `uv run pytest tests/test_http_app.py -q` -- expected: all pass, including the three new tests.
- `uv run pytest -q` -- expected: full suite passes unaffected.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Engine lifecycle: dispose on shutdown, ping before use**

- The lifespan handler -- reads `application.state.engine` at call time, disposes only after `yield`.
  [`app.py:88`](../../shell/http/app.py#L88)

- Where it's wired in and where `pool_pre_ping=True` was added to the existing `create_engine` call.
  [`app.py:127`](../../shell/http/app.py#L127)

**Tests**

- `create_engine` is called with `pool_pre_ping=True`.
  [`test_http_app.py:92`](../../tests/test_http_app.py#L92)

- `dispose()` fires exactly once when the app is run as a lifespan context and torn down.
  [`test_http_app.py:110`](../../tests/test_http_app.py#L110)

- `dispose()` never fires under today's existing bare-`TestClient` pattern used across the rest of the suite.
  [`test_http_app.py:126`](../../tests/test_http_app.py#L126)
