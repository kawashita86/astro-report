"""One-shot flash messages for redirect-based writes (Story 9.8).

Three of this application's write routes (client create/correct/delete)
respond directly with a ``200`` and a real template -- the outcome is right
there in the response, so their flash travels in the template context
(``shell/http/routes/clients.py``'s ``client_action_result.html`` renders).
Every other write this story touches (corpus/style-guide/report-run actions)
responds with a ``303 See Other`` -- the outcome has to survive one more
round trip, from the ``RedirectResponse`` to the ``GET`` it points at. That
round trip is what this module carries: :func:`set_flash` writes a small
JSON cookie on the redirect response; :func:`_flash_context_processor` reads
it back into the next request's Jinja context; :class:`FlashClearMiddleware`
deletes it from whatever response comes back, so the message is shown
exactly once.

No session framework, no ``itsdangerous``/``SessionMiddleware`` dependency
(this story's Boundaries) -- the cookie is plain JSON, not signed. Nothing
security-sensitive rides in it: a tampered value only ever fails to parse
(rendering no banner at all, via the ``try/except`` below) or displays
attacker-chosen *display* text on the tamperer's own next page load -- never
a privilege, a redirect target, or another user's data (there is exactly one
principal, ``shell/http/auth.py``).

``RedirectResponse`` is a ``Response`` subclass, so :func:`set_flash` takes a
plain ``Response`` and calls ``.set_cookie()`` on it directly -- no new
response type.
"""

from __future__ import annotations

import json
from typing import Literal

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shell.config import Environment

__all__ = [
    "FLASH_COOKIE_NAME",
    "FlashClearMiddleware",
    "FlashKind",
    "set_flash",
]

#: The cookie one-shot flash messages travel in. Deliberately not
#: HTTP-signed/encrypted (see module docstring) -- only ever displayed back,
#: never trusted for authorization.
FLASH_COOKIE_NAME = "flash"

#: The only three severities ``base.html``'s shared banner block (and its
#: JS-promoted toast) render a variant for -- mirrors ``.banner--success``/
#: ``.banner--warning``/``.banner--danger`` in ``tokens.css``.
FlashKind = Literal["success", "warning", "danger"]


def set_flash(
    response: Response, kind: FlashKind, message: str, *, environment: Environment
) -> None:
    """Set the one-shot flash cookie on ``response``.

    Called on a ``RedirectResponse`` before it is returned, right after the
    write it announces has committed -- ``shell/http/routes/corpus.py``,
    ``style_guide.py`` and ``report_runs.py``'s five ``303`` sites (each
    passes ``request.app.state.settings.environment``, mirroring how
    ``get_generator()`` in ``report_runs.py`` already reaches settings off
    ``request.app.state``). The cookie carries no ``max_age``: it is meant
    to survive exactly one request (the redirect's destination ``GET``), and
    :class:`FlashClearMiddleware` deletes it from that response regardless,
    so an unusually long-lived browser session is never the thing standing
    between a stale flash and it actually going away.

    ``secure=environment is Environment.PRODUCTION`` mirrors
    ``shell/http/app.py``'s own session cookie exactly -- ``secure`` would
    otherwise never ride along on a cookie that is HTTP-only and
    ``SameSite=Lax`` in every other respect, silently letting it travel over
    a plain-HTTP connection in production.
    """
    response.set_cookie(
        FLASH_COOKIE_NAME,
        json.dumps({"kind": kind, "message": message}),
        httponly=True,
        samesite="lax",
        secure=environment is Environment.PRODUCTION,
        path="/",
    )


def _flash_context_processor(request: Request) -> dict[str, dict[str, str]]:
    """Jinja context processor: the flash cookie (if any and well-formed) as
    ``{"flash": {"kind": ..., "message": ...}}``, for ``base.html``'s shared
    banner block.

    Returns an *empty* dict -- not ``{"flash": None}`` -- whenever no valid
    cookie is present. Starlette's ``Jinja2Templates.TemplateResponse``
    applies every context processor with ``context.update(...)`` *after* the
    caller's own explicit context (see its source), so a processor that
    always contributed a ``"flash"`` key would silently clobber the three
    client-mutation success responses that pass ``flash`` straight in their
    template context (``shell/http/routes/clients.py``) with ``None`` on
    every request that happens not to carry a cookie -- which is all of
    them, since those three responses are never reached via a redirect.
    Omitting the key here instead of setting it to ``None`` leaves whatever
    the route itself already put in the context untouched.

    Malformed JSON (a tampered or truncated cookie), or well-formed JSON that
    is not the ``{"kind": str, "message": str}`` shape :func:`set_flash`
    always writes, is treated exactly like "no cookie" -- a flash banner is
    decoration, never something a broken cookie should be able to break the
    page over.
    """
    raw = request.cookies.get(FLASH_COOKIE_NAME)
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("kind"), str)
        or not isinstance(parsed.get("message"), str)
    ):
        return {}
    return {"flash": {"kind": parsed["kind"], "message": parsed["message"]}}


class FlashClearMiddleware(BaseHTTPMiddleware):
    """Delete the flash cookie on the outgoing response whenever the
    incoming request carried one.

    Runs for every request/response, not scoped to any one route: the flash
    cookie's redirect can land on any of this application's authenticated
    pages, so the request that reads it -- whichever route that turns out to
    be -- is also the one that must clear it. Registered on the application
    directly (``shell/http/app.py``, alongside ``AuthMiddleware``), never on
    a per-module basis.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        carried_flash = FLASH_COOKIE_NAME in request.cookies
        response = await call_next(request)
        if carried_flash:
            response.delete_cookie(FLASH_COOKIE_NAME, path="/")
        return response
