"""The single principal's authentication: allowlist, session cookie, middleware.

Story 1.4. There is exactly one configured principal (``AUTH_PASSWORD_HASH`` in
:mod:`shell.config`), so there is no session store: a "session" is nothing but an
expiry timestamp the cookie's signature protects from tampering. Losing the
process loses no session state, because there was never any to lose.

The allowlist below is the *only* place unauthenticated routes are declared.
``AuthMiddleware`` reads it directly, and so does the test that walks
``app.routes`` to prove nothing outside it is reachable anonymously -- a route
is authenticated by default, not by the next author remembering a guard.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from uuid import UUID

import argon2
from argon2.exceptions import Argon2Error, InvalidHashError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shell.config import Settings

__all__ = [
    "ALLOWLIST",
    "SESSION_COOKIE_NAME",
    "SESSION_MAX_AGE_SECONDS",
    "AuthMiddleware",
    "log_client_deleted",
    "log_failed_login_attempt",
    "sign_session",
    "verify_password",
    "verify_session",
]

#: The one and only declared set of routes servable without a session. Extend
#: this, not a second list somewhere else, to expose a new unauthenticated route.
ALLOWLIST: frozenset[str] = frozenset({"/healthz", "/login"})

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
        if request.url.path in ALLOWLIST:
            return await call_next(request)

        settings: Settings = request.app.state.settings
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token is None or not verify_session(token, settings.session_secret_key):
            # Uniform, empty-body, always 401: missing cookie, tampered
            # signature and expired timestamp are indistinguishable to the
            # caller, and no application data -- not even a hint that the
            # path exists -- rides along.
            return Response(status_code=401)

        return await call_next(request)
