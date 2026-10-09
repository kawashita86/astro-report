---
title: '11-1 An authenticated, stateless API skeleton'
type: 'feature'
created: '2026-10-09'
status: 'done'
baseline_commit: '045e06779ad862e68253d32d28d252c49c14cb1c'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-11-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** astro-report has no machine interface: every route is HTML behind the operator's session cookie, so the alerenzi plugin cannot call the engine.

**Approach:** Mount an empty, versioned `/api/v1` surface (AD-22) guarded by a bearer token checked against `API_TOKEN_HASH`, with a JSON error envelope, a `meta` builder, a no-birth-data logging guard and an access log line. No chart endpoint yet; Stories 11.2–11.6 add them on this skeleton.

## Boundaries & Constraints

**Always:** `AuthMiddleware` branches on `/api/` before the cookie check: bearer only, Argon2 verify, `401 {code:"unauthorized", message:<Italian>, field:null}` JSON, never a redirect. Off `/api/` the bearer header is ignored and a cookie-only request to `/api/*` is 401. `API_TOKEN_HASH` is read only in `shell/config.py`: unset → `Settings.api_token_hash is None` → every `/api/` call 401; present but not a well-formed Argon2 hash → `ConfigError` at startup. Error codes are exactly `invalid_request`, `birth_time_required`, `place_unresolved`, `window_too_long`, `ephemeris_out_of_range`, `unauthorized`, `internal_error`; typed core errors map to them in one module. Under `/api/` unknown paths (404), body validation (422 → `invalid_request`) and unhandled exceptions (`internal_error`) also use the envelope; HTML routes keep today's handlers. Bodies are `canonical_json_bytes` from `core/payload/freeze.py`. The API appears in no OpenAPI or docs page. One log line per `/api/` request: method, path, status, duration, ComputationConfig version — nothing else.

**Ask First:** Any change to the allowlist (`ALLOWLIST`, `ALLOWLIST_PREFIXES`) or to the cookie path.

**Never:** Add a chart/place/vocabulary endpoint, a table, a migration, or any write. Create a thread, executor or task. Read the environment outside `shell/config.py`. Log or echo a request body, birth date/time or coordinate. Treat the token as a principal or a session.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid token | `Authorization: Bearer <t>`, hash set | Reaches the route | N/A |
| No / wrong / non-Bearer header | missing, bad token, `Basic …` | 401 envelope | uniform, no hint which |
| Cookie only | valid session cookie, no token on `/api/v1/x` | 401 envelope | N/A |
| Token on HTML route | valid token, no cookie, `GET /clients` | Same as today (302 login / bare 401) | N/A |
| Hash unset | `API_TOKEN_HASH` absent | Every `/api/` request 401 | app still starts |
| Hash malformed | `API_TOKEN_HASH=nope` | startup `ConfigError` naming it | N/A |
| Unknown API path | valid token, `/api/v1/nope` | 404 envelope `invalid_request` | N/A |
| Docs probes | `/openapi.json`, `/docs`, `/api/docs` | no API listing | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/auth.py` -- `AuthMiddleware.dispatch` (l.225-284), `verify_password` (reuse the Argon2 hasher for the token); add the `/api/` branch before the allowlist/cookie logic.
- `shell/config.py` -- `Settings` (l.100), `_read_auth_password_hash` (l.276) as the model for an *optional* `_read_api_token_hash`, `load_settings` (l.412), `__repr__` redaction (add `api_token_hash`; give the field a default `None` so test-built `Settings(...)` keep working).
- `shell/http/app.py` -- `create_app` (l.171): include the API router, register the `/api/`-scoped exception handlers; `docs_url`/`openapi_url` already `None`.
- `core/payload/freeze.py:51` -- `canonical_json_bytes`, the serialiser to reuse.
- `core/ephemeris/identity.py:80` -- `EphemerisIdentity.files` (`filename`, `sha256`): derive `manifest_sha256` from it; `core/types/computation.py:100` -- `ComputationConfig` (`version`, `content_hash`, `orbs.natal/transit`, `house_system`).
- `core/errors.py` -- typed errors; the mapper lives in `shell/http/api/errors.py`.
- `tests/test_auth.py:189` -- route-walk test (`test_every_route_is_authenticated_unless_allowlisted`) must stay green with `/api/v1` mounted; `tests/test_env_access_is_centralized.py`, `tests/test_concurrency_boundary.py` -- guards the new package must pass; `tests/conftest.py` -- app/Settings fixtures.
- `README.md:42`, `.env.example:26` -- variable table and sample; `compose.yaml:39` -- local dev env (add a throwaway local-dev hash).

## Tasks & Acceptance

**Execution:**
- [x] `shell/config.py` -- add optional `api_token_hash` + `_read_api_token_hash`, redacted in `__repr__` -- single env reader
- [x] `shell/http/api/__init__.py`, `router.py`, `errors.py`, `meta.py`, `boundary.py` -- `/api/v1` `APIRouter`; `ErrorCode` + envelope builder + core-error mapper; `build_meta(config, identity)`; the access-log middleware; module docstrings explain why
- [x] `shell/http/auth.py` -- `/api/` bearer branch returning the Italian 401 envelope; cookie ignored there, bearer ignored elsewhere
- [x] `shell/http/app.py` -- mount router and `/api/`-scoped handlers (404/422/500)
- [x] `README.md`, `.env.example`, `compose.yaml` -- document `API_TOKEN_HASH` (optional; unset disables the API)
- [x] `tests/test_api_skeleton.py` (+ `tests/test_config.py` cases) -- every matrix row; meta keys and determinism (same call twice → same bytes); the logging guard with `test_the_guard_detects_a_logged_request_body`; no OpenAPI/docs exposure; error-envelope mapping covers all seven codes
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 11-1 to `review` when done

**Acceptance Criteria:**
- Given the full suite, when `uv run pytest` runs, then it is green including the import, env-access, concurrency and route-walk guards.
- Given a request body carrying a birth date, time and coordinates sent to `/api/v1/*`, when it is handled, then no log record contains any of them.

## Spec Change Log

## Design Notes

`meta.ephemeris.manifest_sha256` is SHA-256 of `canonical_json_bytes` over the sorted `[filename, sha256]` pairs of `EphemerisIdentity.files` — derived from data already verified at startup, so `core/` needs no new file read. `meta.computation.orbs` carries `natal` and `transit` now; Story 11.4 adds `synastry` with the version-2 config.

Tests exercise the authenticated path with a test-only probe router included on a built app, so the skeleton ships no placeholder endpoint.

## Verification

**Commands:**
- `uv run pytest tests/test_api_skeleton.py tests/test_auth.py tests/test_config.py tests/test_env_access_is_centralized.py tests/test_concurrency_boundary.py` -- expected: pass
- `uv run pytest` -- expected: green

## Suggested Review Order

**Authentication boundary**

- The `/api/` branch runs before any cookie or allowlist logic; bearer only, JSON 401.
  [`auth.py:251`](../../shell/http/auth.py#L251)

- Token check: closed when the hash is unset, cookie never consulted.
  [`auth.py:236`](../../shell/http/auth.py#L236)

- Optional `API_TOKEN_HASH`; a malformed value fails startup instead of disabling the API.
  [`config.py:312`](../../shell/config.py#L312)

**Error envelope and logging**

- Closed code set and the one envelope builder.
  [`errors.py:35`](../../shell/http/api/errors.py#L35)

- The single exception-to-code mapping.
  [`errors.py:93`](../../shell/http/api/errors.py#L93)

- Outermost layer: one body-free log line, and unhandled errors become `internal_error` even under debug.
  [`boundary.py:31`](../../shell/http/api/boundary.py#L31)

**Meta and wiring**

- `meta` block, with the manifest hash derived from already-verified ephemeris identity.
  [`meta.py:37`](../../shell/http/api/meta.py#L37)

- Middleware order, handlers and router mount.
  [`app.py:232`](../../shell/http/app.py#L232)

**Tests and docs**

- Logging guard and its negative test.
  [`test_api_skeleton.py:349`](../../tests/test_api_skeleton.py#L349)

- Setting, README table, `.env.example` and compose local-dev hash.
  [`config.py:138`](../../shell/config.py#L138)
