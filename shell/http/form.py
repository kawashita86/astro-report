"""The shared hand-rolled urlencoded form-body parser for the HTMX POST
routes (epic-7-retro-item-58).

``shell/http/routes/{clients,style_guide,corpus}.py`` each read the raw
request body rather than pulling in ``python-multipart`` for FastAPI's
``Form()`` -- the trio ``_FormTooLarge`` / ``_FormNotUtf8`` / ``_parse_form``
was copied verbatim across all three. It lives here once now.

Each route keeps its own ``_MAX_*_FORM_BODY_BYTES`` ceiling and the comment
explaining how it was sized, and passes it in as ``max_bytes``.
``shell/http/app.py::login_submit`` is deliberately *not* a caller: it maps a
bad body to a 401 (not a 422), stays inline, and keeps its own 4096-byte
ceiling.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

from fastapi import Request

__all__ = ["FormNotUtf8", "FormTooLarge", "parse_form"]


class FormTooLarge(Exception):
    """The ``content-length`` header is absent, non-integer, or larger than the
    caller's ``max_bytes`` ceiling. Only the declared length is checked -- the
    body is never read to measure its actual size."""


class FormNotUtf8(Exception):
    """The body could not be decoded as UTF-8."""


async def parse_form(request: Request, *, max_bytes: int) -> dict[str, str]:
    """Hand-parsed, urlencoded body -- reads the raw body rather than pulling
    in ``python-multipart`` for FastAPI's ``Form()``.

    Raises :class:`FormTooLarge` when the ``content-length`` header is absent,
    not an integer, or exceeds ``max_bytes`` -- the check is on the *declared*
    length only, the body itself is never measured -- and :class:`FormNotUtf8`
    for a non-UTF-8 body. Both are intended to fail visibly with a 422 rather
    than a 500, which each caller maps per its own route.
    """
    declared_length = request.headers.get("content-length")
    try:
        body_too_large = declared_length is None or int(declared_length) > max_bytes
    except ValueError:
        body_too_large = True
    if body_too_large:
        raise FormTooLarge

    raw_body = await request.body()
    try:
        body = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormNotUtf8 from error
    return dict(parse_qsl(body))
