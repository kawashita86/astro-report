"""``shell/http/form.py`` -- the shared hand-rolled urlencoded body parser
extracted from ``clients.py`` / ``style_guide.py`` / ``corpus.py``
(epic-7-retro-item-58).

Exercises ``parse_form``'s three Matrix rows -- oversized/unstated body,
non-UTF-8 body, and a well-formed body -- directly against a minimal ASGI
request, without standing up the whole app.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import Request

from shell.http.form import FormNotUtf8, FormTooLarge, parse_form


def _make_request(body: bytes, *, content_length: bytes | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if content_length is not None:
        headers.append((b"content-length", content_length))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def test_parse_form_returns_parse_qsl_dict_for_a_well_formed_body() -> None:
    body = b"name=Ada+Lovelace&birth_time=03%3A00"
    request = _make_request(body, content_length=str(len(body)).encode())

    result = asyncio.run(parse_form(request, max_bytes=1024))

    assert result == {"name": "Ada Lovelace", "birth_time": "03:00"}


def test_parse_form_raises_form_too_large_when_declared_length_exceeds_max_bytes() -> None:
    request = _make_request(b"x=1", content_length=b"999999")

    with pytest.raises(FormTooLarge):
        asyncio.run(parse_form(request, max_bytes=10))


def test_parse_form_raises_form_too_large_when_content_length_is_absent() -> None:
    request = _make_request(b"x=1", content_length=None)

    with pytest.raises(FormTooLarge):
        asyncio.run(parse_form(request, max_bytes=1024))


def test_parse_form_raises_form_too_large_when_content_length_is_not_an_integer() -> None:
    request = _make_request(b"x=1", content_length=b"not-a-number")

    with pytest.raises(FormTooLarge):
        asyncio.run(parse_form(request, max_bytes=1024))


def test_parse_form_raises_form_not_utf8_for_an_undecodable_body() -> None:
    body = b"\xff\xfe\xfa"
    request = _make_request(body, content_length=str(len(body)).encode())

    with pytest.raises(FormNotUtf8):
        asyncio.run(parse_form(request, max_bytes=1024))
