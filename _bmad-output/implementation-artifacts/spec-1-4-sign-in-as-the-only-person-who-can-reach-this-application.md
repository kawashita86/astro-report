---
title: 'Story 1.4 — Sign in as the only person who can reach this application'
type: 'feature'
created: '2026-08-15'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'afbc5b1a79d54f6d4ec7f321cb23ed1e11b8fa85'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every route the application will ever serve is currently reachable by anyone — `/healthz` is deliberately open, but nothing stops a future route from shipping unauthenticated by accident, and there is no way to sign in at all.

**Approach:** A single Argon2 password hash (`AUTH_PASSWORD_HASH`) and an HMAC-signed session cookie (`SESSION_SECRET_KEY`), both read once by `shell/config.py` like every other setting. A `/login` route verifies the password and sets the cookie; an HTTP middleware — not a per-route dependency — rejects every request whose path isn't in a single declared allowlist and whose cookie doesn't verify, so a new route is authenticated by default rather than by the next author remembering to add a guard.

## Boundaries & Constraints

**Always:**
- `shell/config.py` gains `auth_password_hash: str` and `session_secret_key: str`, validated the same way every other setting is: `AUTH_PASSWORD_HASH` must parse as a valid Argon2 hash (`argon2.extract_parameters()` raising `InvalidHash` is the failure signal — verified empirically, this does not need a password to check format); `SESSION_SECRET_KEY` must be at least 32 characters. Both fail loudly at startup, named, exactly like `DATABASE_URL`/`PORT` today.
- The allowlist (`{"/healthz", "/login"}`) is declared in exactly one place and is what the enforcement test reads — not a second, hand-maintained list in the test itself.
- Enforcement is HTTP middleware wrapping every request, checked against the allowlist before any route handler runs — never a `Depends()` added per-route, which a new route could simply omit.
- The session token is an integer expiry timestamp plus `hmac.compare_digest`-verified HMAC-SHA256 over it, keyed by `session_secret_key` — no server-side session store, matching "no users table." A dot-joined ISO datetime is not an acceptable payload encoding (its own `.` in microseconds breaks a naive split); use the epoch integer.
- Every rejection (missing cookie, bad signature, expired) returns the same uniform empty-body 401 — never a different body or status per reason, and never leaks whether a given path exists to an unauthenticated caller beyond FastAPI's own 404 for genuinely unknown paths.
- Cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` exactly when `settings.environment is Environment.PRODUCTION` — mirroring how `create_app()` already derives `debug` from environment.
- A failed login attempt logs one line via stdlib `logging` carrying no password, no hash, and no other interpolated data — the first log line this codebase writes; it must not become the first violation of the no-secrets-in-logs rule stated since `epic-1-context.md`.
- `argon2-cffi==25.1.0` installs cleanly with no new system packages (verified: no compiled-from-source friction like pyswisseph's, no Dockerfile change needed).

**Ask First:** Generating the real production `AUTH_PASSWORD_HASH` — that needs Francesco's actual password. Produce the mechanism (e.g. a one-line `python -c` invocation using `argon2.PasswordHasher().hash(...)`) and document it; do not choose or embed a real password anywhere.

**Never:**
- No users table, no account creation, no invitation flow, no password-reset flow, no role distinction — a second principal is a PRD revision, not this story.
- No logout route, no dashboard/home route to redirect to after login — neither is asked for by the AC, and no authenticated page exists yet to redirect to.
- No CSRF token machinery — a single-operator, single-form login with `SameSite=Lax` is out of scope for more than that; revisit only if a second state-changing form appears.
- No rate limiting or brute-force lockout on `/login` — not in the AC, and this is not a public multi-tenant service.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Correct password | POST `/login` with the right password | Sets the signed session cookie, no data leaked otherwise | N/A |
| Wrong password | POST `/login` with any other password | No cookie set | Uniform failure response; one log line, no secrets |
| No cookie at all | GET a non-allowlisted route, no cookie | 401, empty body | N/A |
| Tampered cookie | Cookie present, signature doesn't verify | 401, empty body | Same as no cookie — no distinguishing signal |
| Expired cookie | Valid signature, expiry in the past | 401, empty body | Same as no cookie |
| Allowlisted route | GET `/healthz` or `/login`, no cookie | Served normally | N/A |
| Long-running batch | Valid session, hours elapse within the cookie's max-age | Still authenticated, no re-prompt | N/A |

</frozen-after-approval>

## Code Map

**Read-only references:**
- `shell/config.py:58-208` -- the exact pattern to extend: `_read_required` + a validator per field, all errors collected before `ConfigError` is raised, frozen `Settings` with a hand-written `__repr__` that never prints a secret in full.
- `shell/http/app.py:26-49` -- `create_app()`; `debug = settings.environment is Environment.LOCAL` is the precedent for the cookie's `Secure` flag.
- `tests/test_http_app.py:88-92` -- already anticipates this story: "Story 1.4's allowlist starts here."
- `.env.example`, `render.yaml:23-32`, `compose.yaml:28-32` -- the three places every required variable is documented/wired; both new variables join `sync: false` secrets in `render.yaml` like `DATABASE_URL` already does.
- `_bmad-output/planning-artifacts/epics.md:478-507` -- Story 1.4 acceptance criteria verbatim.

**To create:**
- `shell/http/auth.py` -- allowlist constant, `sign_session`/`verify_session`, the auth middleware
- `shell/http/templates/login.html` -- minimal HTML form, no HTMX needed for a full-page login
- `tests/test_auth.py` -- sign/verify round-trip, tamper/expiry rejection, allowlist enforcement walking `app.routes`

**To modify:**
- `shell/config.py` -- two new required settings
- `shell/http/app.py` -- wire `Jinja2Templates`, register the middleware, add `GET`/`POST /login`
- `pyproject.toml`, `uv.lock` -- add `argon2-cffi==25.1.0`
- `.env.example`, `render.yaml`, `compose.yaml` -- document and wire both new variables
- `tests/test_config.py`, `tests/test_http_app.py` -- extend for the new settings and the login route

## Tasks & Acceptance

**Execution:**
- [x] `shell/config.py` -- `auth_password_hash`/`session_secret_key` fields, validated and fail-loud -- AC1
- [x] `shell/http/auth.py` -- allowlist, sign/verify, middleware -- AC2, AC3
- [x] `shell/http/templates/login.html`, `shell/http/app.py` -- `GET`/`POST /login`, `Jinja2Templates` wiring, middleware registered -- AC1, AC4
- [x] `.env.example`, `render.yaml`, `compose.yaml`, `pyproject.toml`, `uv.lock` -- document and wire the two new variables and `argon2-cffi`
- [x] `tests/test_auth.py` -- cover every I/O matrix row, including walking `app.routes` to prove no route outside the allowlist is reachable anonymously
- [x] `tests/test_config.py`, `tests/test_http_app.py` -- extend for the new settings and the login route

**Acceptance Criteria:**
- Given exactly one configured principal, when authentication is set up, then it is a single Argon2 hash plus a signed session cookie, with no users table, account creation, invitation, password-reset or role distinction.
- Given an unauthenticated request to any application route, when it is served, then it returns no application data of any kind, including in error bodies.
- Given the route table, when the authentication test runs, then every route is authenticated by default, the allowlist is declared in exactly one place, and the test fails if any route outside it is reachable anonymously.
- Given a successful sign-in, when Francesco works through a batch over several hours, then the session persists without re-authentication.
- Given any log line the application writes, when inspected, then it is structured and carries no birth data, names or prose — an identifier only.

## Spec Change Log

- **2026-08-15 (review round 1) — six patch findings applied.** All three reviewers
  independently converged on the same shape of gap: paths that were meant to fail
  closed with a clean 401 instead had a raw exception underneath, ready to surface as
  a 500. `login_submit` read the POST body with a bare `.decode("utf-8")` — a
  non-UTF-8 body raised `UnicodeDecodeError` uncaught; fixed with a try/except that
  treats it as any other failed attempt. The same endpoint had no cap on body size
  before that decode, so a large or garbage body would be read in full and, had the
  password field been long enough, spent against Argon2's 64 MiB-per-verify cost —
  fixed with a `Content-Length` check (4096-byte ceiling) before the body is ever
  read. `verify_session` converted the cookie's expiry field with a bare `int(...)`;
  an attacker-controlled digit string past Python's own int-from-string conversion
  limit (thousands of digits) raises `ValueError` instead of just failing
  verification — fixed with a length guard ahead of the conversion. Separately,
  `Settings.redacted_auth_password_hash` unpacked `self.auth_password_hash.split("$")`
  assuming a well-formed hash; `load_settings()` guarantees that on the normal path,
  but `Settings` can be constructed directly (as tests already do), so a malformed
  value would crash the `repr` that exists specifically to keep secrets out of
  tracebacks — fixed with a length guard and a fallback placeholder. Last,
  `session_secret_key` was redacted as a literal string inline in `__repr__` rather
  than through a `redacted_session_secret_key` property like the other two secrets —
  fixed for consistency, no behavior change. Every fix was verified against the
  actual failure it closes: re-ran the exact 5000-digit-expiry and non-UTF-8/oversized
  body cases by hand, both via unit test and against the real running server
  (`docker compose up`), confirming a clean 401 where a 500 would previously have
  fired. **KEEP:** the uniform-401, no-distinguishing-signal response shape for every
  rejection reason — the new guards route through the exact same failure path rather
  than inventing new response shapes, which is why none of this changed AC2's or
  AC3's tests. Not applied, and logged in `deferred-work.md` instead: security
  response headers (CSP/`X-Frame-Options`) — a decision spanning every response, not
  this story's login-only scope; `AuthMiddleware`'s exact-string allowlist matching
  having no path normalization — currently fail-closed and safe, never a bypass;
  and no log line for a *successful* sign-in — AC5 only required the failure line.

## Design Notes

The session token deliberately carries no session ID and touches no database: it is exactly as stateless as the "no users table" constraint implies, so its only content is an expiry the signature protects from tampering. Verification failure must be indistinguishable from absence — resist the temptation to return a different status for "expired" versus "tampered"; that distinction is for the log line, not the response.

## Verification

**Commands:**
- `uv run pytest` -- full suite green, including the new auth tests
- `uv run ruff check .` -- clean
- Manually: `docker compose up`, sign in with the local dev password, confirm the cookie persists across requests and a tampered cookie is rejected

## Suggested Review Order

**Sign-in — the entry point**

- Start here: verify the password, then sign an expiry into a cookie. Everything else in this story exists to protect or gate this one flow.
  [`app.py:83`](../../shell/http/app.py#L83)

- The stateless token: an epoch integer plus its HMAC, `hmac.compare_digest`-checked. No session store because there's nothing to store.
  [`auth.py:65`](../../shell/http/auth.py#L65)
  [`auth.py:74`](../../shell/http/auth.py#L74)

**Authenticated by default — the middleware, and the test that proves it**

- Runs ahead of every route handler; the allowlist here is the only place an unauthenticated path is declared.
  [`auth.py:122`](../../shell/http/auth.py#L122)
  [`auth.py:131`](../../shell/http/auth.py#L131)

- Walks the real `app.routes` rather than a second, hand-maintained list — a new route left off the allowlist fails this test the moment it's registered.
  [`test_auth.py:162`](../../tests/test_auth.py#L162)

**Hardening added after review — three fail-closed paths that used to raise**

- A non-UTF-8 or oversized `/login` body now gets the same clean 401 as a wrong password, instead of a 500. The size check runs before the body is even read, ahead of Argon2's 64 MiB-per-verify cost.
  [`app.py:83`](../../shell/http/app.py#L83)
  [`test_http_app.py:182`](../../tests/test_http_app.py#L182)
  [`test_http_app.py:193`](../../tests/test_http_app.py#L193)

- A cookie with an absurdly long expiry field used to reach Python's own int-conversion digit limit and raise; now it just fails verification.
  [`auth.py:74`](../../shell/http/auth.py#L74)
  [`test_auth.py:105`](../../tests/test_auth.py#L105)

- A redaction helper that itself could crash defeats the point of existing. `redacted_auth_password_hash` now falls back safely; `session_secret_key` gets the same dedicated-property treatment the other two secrets already had.
  [`config.py:96`](../../shell/config.py#L96)
  [`config.py:114`](../../shell/config.py#L114)
