"""The FastAPI application: factory, and the module-level instance the server runs.

Two routes are unauthenticated here: liveness, and sign-in itself -- both, and
only both, are named in ``shell.http.auth.ALLOWLIST``. Every other route this
application ever grows is authenticated by default, by ``AuthMiddleware``
running ahead of any handler, rather than by the next author remembering a
per-route guard.

Importing this module is also where the ephemeris identity is asserted: like
``shell/config.py``'s own ``settings: Settings = load_settings()``, the check
runs eagerly at import time so a missing or mismatched vendored file aborts
startup — non-zero exit, naming the offender — before the app can serve
anything. See ``core/ephemeris/identity.py``.

The same eager-load shape loads ``data/computation.toml`` (Story 1.5, AD-18)
into ``computation_config`` -- a malformed file or an out-of-range orb aborts
startup the same way, even though nothing reads the value yet. See
``shell/computation.py``.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, Response, status
from fastapi.templating import Jinja2Templates

from core.ephemeris.identity import EphemerisIdentity, verify_ephemeris_identity
from core.types.computation import ComputationConfig
from shell import config
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.http.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthMiddleware,
    log_failed_login_attempt,
    sign_session,
    verify_password,
)

__all__ = ["app", "computation_config", "create_app", "ephemeris_identity"]

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

#: A generous ceiling on the /login POST body: no legitimate password needs
#: anywhere near this many bytes. Rejecting an oversized body before reading
#: it keeps a garbage-body request cheap instead of feeding megabytes into
#: Argon2's 64 MiB-per-verify memory cost -- the one endpoint reachable
#: without a session is not the place to skip this.
_MAX_LOGIN_BODY_BYTES = 4096


def create_app(settings: Settings) -> FastAPI:
    """Build the application from an already-validated :class:`Settings`.

    Settings are passed in rather than read here, so the environment has exactly
    one reader (``shell/config.py``) and tests can build an app against any
    configuration without touching the process environment.
    """
    application = FastAPI(
        title="astro-report",
        debug=settings.environment is Environment.LOCAL,
        # No interactive docs: every surface this application exposes is
        # authenticated from Story 1.4 onward, and a schema endpoint is not.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.settings = settings
    application.add_middleware(AuthMiddleware)

    templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    @application.get("/healthz", include_in_schema=False)
    def healthz() -> Response:
        """Liveness only: the process is up and serving. No data, ever."""
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/login", include_in_schema=False)
    def login_form(request: Request) -> Response:
        """The sign-in form. Unauthenticated by design -- it is how one becomes
        authenticated -- and it is the only entry in the allowlist besides
        ``/healthz``."""
        return templates.TemplateResponse(request, "login.html", {"error": False})

    @application.post("/login", include_in_schema=False)
    async def login_submit(request: Request) -> Response:
        """Verify the single configured password and, on success, set the
        signed session cookie.

        Parsed by hand from the raw body rather than via FastAPI's ``Form()``,
        which pulls in ``python-multipart`` for a single field this login form
        never needs multipart encoding for. An oversized or non-UTF-8 body is
        exactly as much "wrong credentials" as any other failed attempt --
        this endpoint's whole job is rejecting bad input safely, not choosing
        which malformed input deserves a clean response and which gets a
        traceback.
        """
        declared_length = request.headers.get("content-length")
        try:
            body_too_large = declared_length is None or int(declared_length) > _MAX_LOGIN_BODY_BYTES
        except ValueError:
            body_too_large = True
        if body_too_large:
            log_failed_login_attempt()
            return templates.TemplateResponse(
                request, "login.html", {"error": True}, status_code=401
            )

        raw_body = await request.body()
        try:
            body = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            log_failed_login_attempt()
            return templates.TemplateResponse(
                request, "login.html", {"error": True}, status_code=401
            )
        password = dict(parse_qsl(body)).get("password", "")

        if not verify_password(password, settings.auth_password_hash):
            log_failed_login_attempt()
            return templates.TemplateResponse(
                request, "login.html", {"error": True}, status_code=401
            )

        expires_at = int(time.time()) + SESSION_MAX_AGE_SECONDS
        token = sign_session(expires_at, settings.session_secret_key)
        response = Response(content="Signed in.", media_type="text/plain")
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=settings.environment is Environment.PRODUCTION,
            path="/",
        )
        return response

    return application


#: The ephemeris this process is computing against, verified once at import
#: time. Nothing persists it yet — Epic 3's Report Payload does that — but it
#: is available here for any component that must record it later.
ephemeris_identity: EphemerisIdentity = verify_ephemeris_identity()

#: The one home for every astronomical tuning value (AD-18), loaded once at
#: import time. Nothing in this story consumes it yet — Epic 2+ does — but a
#: malformed file must still abort startup before anything can serve.
computation_config: ComputationConfig = load_computation_config()

#: The instance the ASGI server imports (``shell.http.app:app``).
app = create_app(config.settings)
