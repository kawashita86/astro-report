"""``shell/http/flash.py`` -- the one-shot flash-cookie mechanism (Story
9.8), unit-tested in isolation: ``set_flash``'s cookie shape,
``_flash_context_processor``'s parse/graceful-failure behavior, and
``FlashClearMiddleware``'s clear-on-any-response behavior -- all without
standing up the whole astro-report app. The end-to-end round trip through a
real route is ``tests/test_http_corpus.py``'s
``test_the_flash_cookie_is_set_on_the_redirect_and_cleared_after_the_next_page``.
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.testclient import TestClient

from shell.config import Environment
from shell.http.flash import (
    FLASH_COOKIE_NAME,
    FlashClearMiddleware,
    _flash_context_processor,
    set_flash,
)


def _make_request(*, cookie: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


# --- set_flash -------------------------------------------------------------------


def test_set_flash_sets_a_json_cookie_on_a_redirect_response() -> None:
    """``RedirectResponse`` is a ``Response`` subclass -- ``set_flash`` calls
    it directly, no new response type."""
    response = RedirectResponse("/corpus", status_code=303)

    set_flash(response, "success", "Voce aggiunta.", environment=Environment.LOCAL)

    set_cookie_header = response.headers["set-cookie"]
    assert f"{FLASH_COOKIE_NAME}=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header
    assert "samesite=lax" in set_cookie_header.lower()


def test_set_flash_marks_the_cookie_secure_only_in_production() -> None:
    """Mirrors ``shell/http/app.py``'s own session cookie:
    ``secure=environment is Environment.PRODUCTION``."""
    local_response = RedirectResponse("/corpus", status_code=303)
    set_flash(local_response, "success", "hi", environment=Environment.LOCAL)
    assert "secure" not in local_response.headers["set-cookie"].lower()

    production_response = RedirectResponse("/corpus", status_code=303)
    set_flash(production_response, "success", "hi", environment=Environment.PRODUCTION)
    assert "secure" in production_response.headers["set-cookie"].lower()


# --- _flash_context_processor -----------------------------------------------------


def test_the_context_processor_parses_a_well_formed_cookie() -> None:
    raw = json.dumps({"kind": "warning", "message": "Attenzione."})
    request = _make_request(cookie=f"{FLASH_COOKIE_NAME}={raw}")

    context = _flash_context_processor(request)

    assert context == {"flash": {"kind": "warning", "message": "Attenzione."}}


def test_the_context_processor_returns_empty_with_no_cookie() -> None:
    """Not ``{"flash": None}`` -- an empty dict, so
    ``Jinja2Templates.TemplateResponse``'s ``context.update(...)`` (applied
    *after* the caller's own explicit context) never clobbers a route's own
    explicit ``flash`` (the three client-mutation success responses,
    ``shell/http/routes/clients.py``) on a request that carries no cookie."""
    request = _make_request(cookie=None)

    assert _flash_context_processor(request) == {}


def test_the_context_processor_treats_malformed_json_as_no_cookie() -> None:
    request = _make_request(cookie=f"{FLASH_COOKIE_NAME}=not-json-at-all")

    assert _flash_context_processor(request) == {}


def test_the_context_processor_treats_the_wrong_shape_as_no_cookie() -> None:
    """Well-formed JSON that is not ``{"kind": str, "message": str}`` -- a
    bare string, a list, or a dict missing/mistyping a key -- degrades the
    same as no cookie at all, never a 500."""
    for malformed in (
        '"just a string"',
        "[1, 2, 3]",
        '{"kind": "success"}',
        '{"kind": 1, "message": "x"}',
    ):
        request = _make_request(cookie=f"{FLASH_COOKIE_NAME}={malformed}")
        assert _flash_context_processor(request) == {}


# --- FlashClearMiddleware ----------------------------------------------------------


def _tiny_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(FlashClearMiddleware)

    @app.get("/set")
    def set_route() -> Response:
        response = Response(content="set", media_type="text/plain")
        set_flash(response, "success", "hi", environment=Environment.LOCAL)
        return response

    @app.get("/plain")
    def plain() -> Response:
        return Response(content="ok", media_type="text/plain")

    return app


def test_the_middleware_clears_the_cookie_when_the_request_carried_one() -> None:
    # A real Set-Cookie round trip (via set_flash, not a jar poked directly),
    # mirroring how a redirect-based write actually delivers the cookie.
    app = _tiny_app()
    client = TestClient(app)

    carrying_flash = client.get("/set")
    assert FLASH_COOKIE_NAME in carrying_flash.cookies

    response = client.get("/plain")

    assert response.status_code == 200
    set_cookie_header = response.headers.get("set-cookie", "")
    assert f"{FLASH_COOKIE_NAME}=" in set_cookie_header
    # A cleared cookie carries an immediate expiry, not a fresh value.
    assert "hi" not in set_cookie_header
    assert client.cookies.get(FLASH_COOKIE_NAME) is None


def test_the_middleware_leaves_no_set_cookie_when_the_request_carried_none() -> None:
    app = _tiny_app()
    client = TestClient(app)

    response = client.get("/plain")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
