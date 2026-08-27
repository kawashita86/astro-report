"""``/corpus``: the list of every past report added so far, ``/corpus/new``:
the paste-in form, and ``POST /corpus``: store one past report as plain text
(Story 7.1).

One report is stored as plain text regardless of its origin -- email,
messaging or a folder -- with no per-source parsing, no file upload, no
format handling, and no edit or delete of an entry (this story's
Boundaries). Setting ``client_id`` and the paired/unpaired marking are
Story 7.2.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards every route in
this module before a request ever reaches it, mirroring
``shell/http/routes/style_guide.py``.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from shell.adapters.postgres.corpus_entry import add_corpus_entry, list_corpus_entries
from shell.http.app import get_session

__all__ = ["router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)

#: Whole-body ceiling on the POST /corpus body. A pasted past report is
#: prose -- sized exactly like
#: shell/http/routes/style_guide.py's own _MAX_STYLE_GUIDE_FORM_BODY_BYTES,
#: well above shell/http/routes/clients.py's _MAX_CLIENT_FORM_BODY_BYTES
#: (65536), while still rejecting a garbage-sized body before reading it.
_MAX_CORPUS_FORM_BODY_BYTES = 1_048_576


class _FormTooLarge(Exception):
    """The declared or actual body size exceeds ``_MAX_CORPUS_FORM_BODY_BYTES``."""


class _FormNotUtf8(Exception):
    """The body could not be decoded as UTF-8."""


async def _parse_form(request: Request) -> dict[str, str]:
    """Hand-parsed, urlencoded body -- mirrors
    ``shell/http/routes/style_guide.py``'s ``_parse_form``, which reads the
    raw body rather than pulling in ``python-multipart`` for FastAPI's
    ``Form()``.
    """
    declared_length = request.headers.get("content-length")
    try:
        body_too_large = (
            declared_length is None or int(declared_length) > _MAX_CORPUS_FORM_BODY_BYTES
        )
    except ValueError:
        body_too_large = True
    if body_too_large:
        raise _FormTooLarge

    raw_body = await request.body()
    try:
        body = raw_body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _FormNotUtf8 from error
    return dict(parse_qsl(body))


@router.get("/corpus", include_in_schema=False)
def corpus_list(request: Request, session: Session = Depends(get_session)) -> Response:
    """Every stored entry, most-recent-first (Story 7.1). An empty corpus
    renders its own empty-state text and a link to ``/corpus/new``."""
    return _templates.TemplateResponse(
        request, "corpus_list.html", {"entries": list_corpus_entries(session)}
    )


@router.get("/corpus/new", include_in_schema=False)
def corpus_new_form(request: Request) -> Response:
    """The paste-in form."""
    return _templates.TemplateResponse(
        request, "corpus_new.html", {"content": "", "error": None}
    )


@router.post("/corpus", include_in_schema=False)
async def add_corpus(request: Request, session: Session = Depends(get_session)) -> Response:
    """Store one pasted past report as plain text, then redirect to the list.

    An oversized or non-UTF-8 body, or empty/whitespace-only ``content``,
    inserts nothing and re-renders the form with a ``role="alert"`` message
    and a ``422``.
    """
    try:
        fields = await _parse_form(request)
    except _FormTooLarge:
        return _templates.TemplateResponse(
            request,
            "corpus_new.html",
            {"content": "", "error": "the submitted form is too large."},
            status_code=422,
        )
    except _FormNotUtf8:
        return _templates.TemplateResponse(
            request,
            "corpus_new.html",
            {"content": "", "error": "the submitted form is not valid UTF-8."},
            status_code=422,
        )

    content = fields.get("content", "")
    if not content.strip():
        return _templates.TemplateResponse(
            request,
            "corpus_new.html",
            {"content": content, "error": "content is required."},
            status_code=422,
        )

    add_corpus_entry(session, content=content)
    session.commit()
    return RedirectResponse("/corpus", status_code=303)
