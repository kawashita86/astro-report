"""The FastAPI application: factory, and the module-level instance the server runs.

The only route here is liveness. It is deliberately unauthenticated and returns
no body; when Story 1.4 makes every route authenticated by default, this is the
first and — for now — only entry in the one-place allowlist. It must not grow a
payload in the meantime.

Importing this module is also where the ephemeris identity is asserted: like
``shell/config.py``'s own ``settings: Settings = load_settings()``, the check
runs eagerly at import time so a missing or mismatched vendored file aborts
startup — non-zero exit, naming the offender — before the app can serve
anything. See ``core/ephemeris/identity.py``.
"""

from __future__ import annotations

from fastapi import FastAPI, Response, status

from core.ephemeris.identity import EphemerisIdentity, verify_ephemeris_identity
from shell import config
from shell.config import Environment, Settings

__all__ = ["app", "create_app", "ephemeris_identity"]


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

    @application.get("/healthz", include_in_schema=False)
    def healthz() -> Response:
        """Liveness only: the process is up and serving. No data, ever."""
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


#: The ephemeris this process is computing against, verified once at import
#: time. Nothing persists it yet — Epic 3's Report Payload does that — but it
#: is available here for any component that must record it later.
ephemeris_identity: EphemerisIdentity = verify_ephemeris_identity()

#: The instance the ASGI server imports (``shell.http.app:app``).
app = create_app(config.settings)
