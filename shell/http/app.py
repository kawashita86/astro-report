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
startup the same way. Story 2.3's ``/clients`` route is the first consumer,
reading it from ``application.state`` rather than this module's global, so a
future second consumer never has to import this module. See
``shell/computation.py``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, Response, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine
from sqlmodel import Session

from core.ephemeris.identity import EphemerisIdentity, verify_ephemeris_identity
from core.types.computation import ComputationConfig
from core.types.gate import GateVocabulary
from core.types.sections import SectionsConfig
from shell import config
from shell.computation import load_computation_config
from shell.config import Environment, Settings
from shell.gate import load_gate_vocabulary
from shell.http.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    AuthMiddleware,
    log_failed_login_attempt,
    sign_session,
    verify_password,
)
from shell.sections import load_sections_config

__all__ = [
    "app",
    "computation_config",
    "create_app",
    "ephemeris_identity",
    "gate_vocabulary",
    "get_session",
    "sections_config",
]

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

#: The vendored, committed front-end assets the shell serves: `tokens.css`
#: (the DESIGN.md token set), `htmx.min.js` (the 2.0.4 build, formerly a CDN
#: `<script>` in one template), and `shell.js` (the theme toggle + drawer).
#: Mounted at `/static` and reachable anonymously via
#: ``shell.http.auth.ALLOWLIST_PREFIXES`` so pre-auth `/login` loads styled.
_STATIC_DIR = Path(__file__).resolve().parent / "static"

#: A generous ceiling on the /login POST body: no legitimate password needs
#: anywhere near this many bytes. Rejecting an oversized body before reading
#: it keeps a garbage-body request cheap instead of feeding megabytes into
#: Argon2's 64 MiB-per-verify memory cost -- the one endpoint reachable
#: without a session is not the place to skip this.
_MAX_LOGIN_BODY_BYTES = 4096


def get_session(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session against the shared engine.

    Not auto-committing: each route decides its own transaction boundary --
    Story 2.3's ``/clients`` route must commit a Client and its Natal Chart
    together, or not at all (AD-16). Closing the session without an explicit
    ``commit()`` rolls back any pending work, including a nested
    ``PLACE_CACHE`` write (``shell/adapters/postgres/place_cache.py``).
    """
    with Session(request.app.state.engine) as session:
        yield session


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Dispose the app's engine on shutdown only.

    Reads ``application.state.engine`` off ``application`` rather than closing
    over a local variable. That attribute is assigned synchronously inside
    ``create_app()`` before the app is ever handed to an ASGI server, so it is
    already set by the time this lifespan is invoked at all -- both before
    ``yield`` (startup) and after it (shutdown), not merely by the time this
    generator resumes post-``yield``.
    """
    yield
    application.state.engine.dispose()


def create_app(settings: Settings) -> FastAPI:
    """Build the application from an already-validated :class:`Settings`.

    Settings are passed in rather than read here, so the environment has exactly
    one reader (``shell/config.py``) and tests can build an app against any
    configuration without touching the process environment.
    """
    # Deferred, not a top-of-file import: `shell.http.routes.clients` imports
    # `get_session` back from this module, so the router is only resolvable
    # once `get_session` (defined above) already exists in this module's
    # namespace -- guaranteed by the time `create_app()` is actually called,
    # never by the time this module merely starts executing.
    from shell.http.routes.backup import router as backup_router
    from shell.http.routes.chart import router as chart_router
    from shell.http.routes.clients import router as clients_router
    from shell.http.routes.corpus import router as corpus_router
    from shell.http.routes.report_runs import router as report_runs_router
    from shell.http.routes.style_guide import router as style_guide_router

    application = FastAPI(
        title="astro-report",
        debug=settings.environment is Environment.LOCAL,
        # No interactive docs: every surface this application exposes is
        # authenticated from Story 1.4 onward, and a schema endpoint is not.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    application.state.settings = settings
    application.state.engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    application.state.computation_config = computation_config
    application.state.sections_config = sections_config
    application.state.ephemeris_identity = ephemeris_identity
    application.state.gate_vocabulary = gate_vocabulary
    application.add_middleware(AuthMiddleware)
    application.include_router(clients_router)
    application.include_router(chart_router)
    application.include_router(report_runs_router)
    application.include_router(style_guide_router)
    application.include_router(backup_router)
    application.include_router(corpus_router)
    application.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    templates = Jinja2Templates(directory=_TEMPLATES_DIR)

    @application.api_route(
        "/healthz", methods=["GET", "HEAD"], include_in_schema=False
    )
    def healthz() -> Response:
        """Liveness only: the process is up and serving. No data, ever.

        Answers ``HEAD`` as well as ``GET``: some health checkers and uptime
        monitors probe with ``HEAD``, and a ``GET``-only route would 405 them
        rather than report the process up."""
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
#: time. Story 2.3's ``/clients`` route records it on every stored Natal
#: Chart; Epic 3's Report Payload will read it too.
ephemeris_identity: EphemerisIdentity = verify_ephemeris_identity()

#: The one home for every astronomical tuning value (AD-18), loaded once at
#: import time. Story 2.3's ``/clients`` route is the first consumer.
computation_config: ComputationConfig = load_computation_config()

#: The declarative Section-to-Payload mapping (AD-13), loaded once at import
#: time exactly like ``computation_config``. Story 3.8's ``payload_ready``
#: stage (``shell/runner/driver.py``) is the first consumer, via
#: ``shell/http/routes/report_runs.py``'s ``_advance_run``.
sections_config: SectionsConfig = load_sections_config()

#: The versioned closed Italian vocabulary that decides what counts as a
#: Claim (Story 5.1, AD-8), loaded once at import time exactly like
#: ``computation_config``/``sections_config``. ``shell/runner/driver.py``'s
#: ``gate_passed`` stage (via ``shell/http/routes/report_runs.py``'s
#: ``_advance_run``) is the first consumer.
gate_vocabulary: GateVocabulary = load_gate_vocabulary()

#: The instance the ASGI server imports (``shell.http.app:app``).
app = create_app(config.settings)
