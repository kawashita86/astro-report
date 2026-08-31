"""The single principal's authentication: allowlist, session cookie, middleware.

Story 1.4. There is exactly one configured principal (``AUTH_PASSWORD_HASH`` in
:mod:`shell.config`), so there is no session store: a "session" is nothing but an
expiry timestamp the cookie's signature protects from tampering. Losing the
process loses no session state, because there was never any to lose.

The allowlist below is the *only* place unauthenticated routes are declared:
two exact paths (``/healthz``, ``/login``) plus the ``/static/`` path-prefix
that lets the vendored shell assets load before sign-in. ``AuthMiddleware``
reads both directly, and so does the test that walks ``app.routes`` to prove
nothing outside them is reachable anonymously -- a route is authenticated by
default, not by the next author remembering a guard.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode
from uuid import UUID

import argon2
from argon2.exceptions import Argon2Error, InvalidHashError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from shell.config import Settings

__all__ = [
    "ALLOWLIST",
    "ALLOWLIST_PREFIXES",
    "SESSION_COOKIE_NAME",
    "SESSION_MAX_AGE_SECONDS",
    "AuthMiddleware",
    "log_client_deleted",
    "log_failed_login_attempt",
    "safe_next_path",
    "sign_session",
    "verify_password",
    "verify_session",
]

#: The one and only declared set of routes servable without a session. Extend
#: this, not a second list somewhere else, to expose a new unauthenticated route.
ALLOWLIST: frozenset[str] = frozenset({"/healthz", "/login"})

#: Path *prefixes* servable without a session -- separate from the exact-match
#: ``ALLOWLIST`` above. Only the vendored shell assets live here, so ``/login``
#: is styled before anyone signs in. The trailing slash is load-bearing: the
#: match needs ``/static/`` followed by a path segment, so the bare ``/static``
#: mount path itself stays behind auth like any other route.
ALLOWLIST_PREFIXES: tuple[str, ...] = ("/static/",)

#: The cookie the session token travels in.
SESSION_COOKIE_NAME = "session"

#: How long a session survives without re-authentication. Long enough that a
#: multi-hour working batch never re-prompts (AC4), short of forever because
#: this is still the only thing standing between the internet and Client data.
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60  # 24 hours

_SEPARATOR = "."

#: A generous ceiling on the expiry field's digit count -- room for epoch
#: timestamps far beyond any plausible date, but well short of the point
#: (thousands of digits) where Python's own int-from-string conversion
#: refuses to convert at all and raises instead of just failing verification.
_MAX_EXPIRY_DIGITS = 20

_logger = logging.getLogger(__name__)

_password_hasher = argon2.PasswordHasher()


def sign_session(expires_at: int, session_secret_key: str) -> str:
    """Build a session token: an expiry epoch plus its HMAC-SHA256 signature.

    The payload is a bare integer -- never a dot-joined ISO datetime, whose own
    ``.`` in microseconds would break a naive split on the separator.
    """
    return f"{expires_at}{_SEPARATOR}{_signature(expires_at, session_secret_key)}"


def verify_session(
    token: str, session_secret_key: str, *, now: int | None = None
) -> bool:
    """Verify a session token: well-formed, correctly signed, and not expired.

    Every failure mode -- malformed token, bad signature, expired timestamp --
    returns the same ``False``. The caller must not, and cannot from this
    return value alone, distinguish one from another; that distinction is for
    a log line, never a response.
    """
    expires_at_raw, _, signature = token.partition(_SEPARATOR)
    # isdecimal(), not isdigit(): isdigit() accepts Unicode digit characters
    # (e.g. superscripts) that int() cannot parse, which would raise instead
    # of returning False -- isdecimal() is the subset int() always accepts.
    if not signature or not expires_at_raw.isdecimal():
        return False
    if len(expires_at_raw) > _MAX_EXPIRY_DIGITS:
        return False
    expires_at = int(expires_at_raw)
    expected_signature = _signature(expires_at, session_secret_key)
    if not hmac.compare_digest(expected_signature, signature):
        return False
    current = int(time.time()) if now is None else now
    return current < expires_at


def _signature(expires_at: int, session_secret_key: str) -> str:
    return hmac.new(
        session_secret_key.encode("utf-8"),
        str(expires_at).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_password(password: str, auth_password_hash: str) -> bool:
    """Check ``password`` against the single configured Argon2 hash."""
    try:
        return _password_hasher.verify(auth_password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


def log_failed_login_attempt() -> None:
    """The first log line this codebase writes -- deliberately bare.

    No password, no hash, no interpolated data of any kind: this project's
    no-secrets-in-logs rule (epic-1-context.md) starts being honored here.
    """
    _logger.warning("failed login attempt")


def log_client_deleted(client_id: UUID) -> None:
    """Story 2.8's deletion log line -- carries the Client's UUID and nothing
    else, mirroring :func:`log_failed_login_attempt`'s bare-call shape.

    Only the id is interpolated -- never a name or birth data: this project's
    no-secrets-in-logs rule (epic-1-context.md) applies here exactly as it
    does to a failed login attempt.
    """
    _logger.info("client deleted: %s", client_id)


#: A generous ceiling on an accepted ``next`` value -- well under any real
#: proxy header-size limit, and no legitimate in-app path needs anywhere
#: near this many characters (review-loop 1: an unbounded ``next`` round-
#: trips through the ``Location`` header and the login page's hidden field
#: on every re-render for no benefit).
_NEXT_MAX_LENGTH = 2048


def safe_next_path(value: str | None) -> str:
    """A ``next`` value safe to redirect a signed-in browser to: an on-site,
    path-absolute destination only, defaulting to ``"/"``.

    ``next`` is attacker-controlled -- it arrives as a plain query parameter
    on ``/login``, never something this app already vetted -- so this
    rejects anything that could send the browser off-site or corrupt the
    response: a scheme-relative path (``//evil.example``, which browsers
    resolve against the current scheme, not this origin), a backslash
    (browsers and some proxies treat ``\\`` as a path separator, the same
    trick as ``//`` under a different character), a tab (review-loop 1: the
    WHATWG URL parser strips embedded tabs before resolving a URL, so
    ``/\t/evil.example`` is *also* ``//evil.example`` by the time a browser
    acts on it -- the same bypass class as the backslash check, one
    character over), and raw ``\\r``/``\\n`` (header-injection payload).
    Also rejects ``/login`` itself (redirecting a freshly signed-in visitor
    straight back to sign-in is never a meaningful destination) and anything
    over :data:`_NEXT_MAX_LENGTH`. Anything else that starts with a single
    ``/`` is accepted as-is.
    """
    if (
        not value
        or len(value) > _NEXT_MAX_LENGTH
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\t" in value
        or "\r" in value
        or "\n" in value
    ):
        return "/"
    if value.split("?", 1)[0].rstrip("/") == "/login":
        return "/"
    return value


def _wants_html_navigation(request: Request) -> bool:
    """Whether ``request`` looks like a browser loading a page, rather than
    an HTMX poll or a JSON-shaped/API caller.

    Used only to choose *how* an unauthenticated request is told "no" (a
    redirect a human can act on, vs. the uniform empty-body 401 every
    non-navigational caller must keep getting) -- it never changes *whether*
    the request is authenticated.

    Two guards beyond the ``Accept`` sniff itself:

    - **Method.** Only ``GET``/``HEAD`` redirect. A redirect can't carry a
      ``POST`` body forward -- ``/login``'s own success response is a 303,
      which always turns into a ``GET`` -- so redirecting a guarded ``POST``
      (a plain, no-JS form submission also sends ``Accept: text/html`` with
      no ``HX-Request``) would silently drop the action the user meant to
      take instead of completing it after sign-in (review-loop 1). Those
      calls keep the bare 401 exactly as before.
    - **Substring, not a full media-type parse.** ``"text/html" in accept``
      is deliberately loose: the only two outcomes it drives are "redirect"
      or "401," and a false positive (a caller that merely lists
      ``text/html`` alongside a preferred type) just gets a friendlier
      response to the same denial, never a change in whether it's denied.
    """
    if request.method not in ("GET", "HEAD"):
        return False
    if request.headers.get("hx-request", "").lower() == "true":
        return False
    return "text/html" in request.headers.get("accept", "")


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject any request outside :data:`ALLOWLIST` without a valid session.

    HTTP middleware, not a per-route ``Depends()``: it runs before any route
    handler, including for paths no route registers, so a new route is
    authenticated the moment it exists rather than by the next author
    remembering to guard it.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Match the allowlist against the path with any trailing slash
        # trimmed: a health checker (Render's own included) or a hand-typed
        # probe routinely hits `/healthz/`, and Starlette's slash-redirect
        # runs in the router -- *after* this middleware -- so `/healthz/`
        # would get a 401 here before it could ever redirect to `/healthz`.
        # `ALLOWLIST` itself stays canonical (no trailing slash).
        normalized_path = request.url.path.rstrip("/") or "/"
        if (
            request.url.path in ALLOWLIST
            or normalized_path in ALLOWLIST
            or request.url.path.startswith(ALLOWLIST_PREFIXES)
        ):
            return await call_next(request)

        settings: Settings = request.app.state.settings
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token is None or not verify_session(token, settings.session_secret_key):
            if _wants_html_navigation(request):
                # A human hit a guarded URL with no session -- send them to
                # the sign-in screen instead of a page that renders nothing
                # (correct-course 2026-08-31: Story 9.2's own AC already said
                # "redirected to sign-in," but this returned the bare 401
                # below to every caller, browser included, until now).
                #
                # Echoing the path into `Location` (and, from `/login`, the
                # hidden `next` field) does not weaken the 401 branch's own
                # "no hint the path exists" property below: this branch is
                # reached identically for a real guarded route and a
                # nonexistent one (this middleware runs before routing), and
                # the requested path is already the request path an access
                # log records regardless of which response follows it. What
                # this echoes back is only the path the caller already typed
                # or clicked -- never data from elsewhere in the app
                # (review-loop 1).
                target = request.url.path
                if request.url.query:
                    target = f"{target}?{request.url.query}"
                return RedirectResponse(
                    f"/login?{urlencode({'next': target})}", status_code=302
                )
            # Uniform, empty-body, always 401 for every non-navigational
            # caller (HTMX polls, JSON-shaped requests): missing cookie,
            # tampered signature and expired timestamp are indistinguishable
            # to the caller, and no application data -- not even a hint
            # that the path exists -- rides along.
            return Response(status_code=401)

        return await call_next(request)
