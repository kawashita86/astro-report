"""``/style-guide``: current + history, ``/style-guide/{version}``: a
read-only historical version, and ``/style-guide/edit``: save a new version
(Story 4.2).

A save never overwrites or deletes -- it always inserts ``version = max + 1``
(``shell/adapters/postgres/style_guide.py::create_style_guide_version()``),
so every prior version stays readable at its own URL. Unlike
``shell/http/routes/clients.py``'s correction route, there is no confirm gate
here: nothing is ever destroyed by a save, so normal form handling is enough.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards every route in
this module before a request ever reaches it, mirroring
``shell/http/routes/clients.py``/``shell/http/routes/report_runs.py``.

Route registration order matters: ``/style-guide/edit`` (a literal path) is
registered before ``/style-guide/{version}`` (a parameterized one), so a
request for the literal path is never mistakenly routed to the version view
with ``version="edit"``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from shell.adapters.postgres.style_guide import (
    StyleGuide,
    StyleGuideMissingError,
    create_style_guide_version,
    current_style_guide,
)
from shell.http.app import get_session
from shell.http.flash import _flash_context_processor, set_flash
from shell.http.form import FormNotUtf8, FormTooLarge, parse_form

__all__ = ["router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(
    directory=_TEMPLATES_DIR, context_processors=[_flash_context_processor]
)

#: A generous ceiling on the /style-guide/edit POST body. The Style Guide
#: itself (see data/style-guide.seed.md) runs to several thousand words of
#: prose, so this is sized well above
#: shell/http/routes/clients.py's own _MAX_CLIENT_FORM_BODY_BYTES (65536),
#: while still rejecting a garbage-sized body before reading it.
_MAX_STYLE_GUIDE_FORM_BODY_BYTES = 1_048_576

#: Fixed Italian copy for every ``error`` site below (Story 9.9,
#: EXPERIENCE.md's Voice and Tone) -- mirrors
#: ``shell/http/routes/clients.py``'s own fixed-message convention.
_ERROR_FORM_TOO_LARGE = "Il modulo inviato è troppo grande."
_ERROR_FORM_NOT_UTF8 = "Il modulo inviato non è in una codifica UTF-8 valida."
_ERROR_CONTENT_REQUIRED = "Il contenuto è obbligatorio."
_ERROR_CONCURRENT_SAVE = (
    "È stata salvata una nuova versione nel frattempo — rivedi la versione attuale "
    "e riprova a salvare."
)


def _history(session: Session, *, exclude_version: int) -> list[StyleGuide]:
    """Every version except ``exclude_version`` (the current one), so
    "Current" and "History" stay disjoint on the ``/style-guide`` page --
    the current version already has its own section above."""
    return list(
        session.exec(
            select(StyleGuide)
            .where(StyleGuide.version != exclude_version)
            .order_by(StyleGuide.version.desc())
        )
    )


@router.get("/style-guide", include_in_schema=False)
def style_guide_history(request: Request, session: Session = Depends(get_session)) -> Response:
    """Current version plus the full history (Story 4.2).

    ``StyleGuideMissingError`` is caught and rendered here rather than left to
    bubble into a bare 500: the I/O & Edge-Case Matrix requires it, even
    though every deploy from migration 0007 onward seeds version 1 and this
    branch is not expected to be reachable in production.
    """
    try:
        current = current_style_guide(session)
    except StyleGuideMissingError as error:
        return _templates.TemplateResponse(
            request,
            "style_guide_list.html",
            {"current": None, "history": [], "error": str(error)},
            status_code=503,
        )

    return _templates.TemplateResponse(
        request,
        "style_guide_list.html",
        {
            "current": current,
            "history": _history(session, exclude_version=current.version),
            "error": None,
        },
    )


@router.get("/style-guide/edit", include_in_schema=False)
def style_guide_edit_form(request: Request, session: Session = Depends(get_session)) -> Response:
    """The editor, prefilled with the current version's content."""
    try:
        current = current_style_guide(session)
    except StyleGuideMissingError as error:
        return _templates.TemplateResponse(
            request,
            "style_guide_edit.html",
            {"content": "", "error": str(error)},
            status_code=503,
        )

    return _templates.TemplateResponse(
        request, "style_guide_edit.html", {"content": current.content, "error": None}
    )


@router.post("/style-guide/edit", include_in_schema=False)
async def save_style_guide(
    request: Request, session: Session = Depends(get_session)
) -> Response:
    """Save a new Style Guide version -- always an insert, never an update."""
    try:
        fields = await parse_form(request, max_bytes=_MAX_STYLE_GUIDE_FORM_BODY_BYTES)
    except FormTooLarge:
        return _templates.TemplateResponse(
            request,
            "style_guide_edit.html",
            {"content": "", "error": _ERROR_FORM_TOO_LARGE},
            status_code=422,
        )
    except FormNotUtf8:
        return _templates.TemplateResponse(
            request,
            "style_guide_edit.html",
            {"content": "", "error": _ERROR_FORM_NOT_UTF8},
            status_code=422,
        )

    content = fields.get("content", "")
    if not content.strip():
        return _templates.TemplateResponse(
            request,
            "style_guide_edit.html",
            {"content": content, "error": _ERROR_CONTENT_REQUIRED},
            status_code=422,
        )

    style_guide = create_style_guide_version(session, content)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _templates.TemplateResponse(
            request,
            "style_guide_edit.html",
            {
                "content": content,
                "error": _ERROR_CONCURRENT_SAVE,
            },
            status_code=409,
        )

    response = RedirectResponse(f"/style-guide/{style_guide.version}", status_code=303)
    set_flash(
        response,
        "success",
        "Nuova versione salvata.",
        environment=request.app.state.settings.environment,
    )
    return response


@router.get("/style-guide/{version}", include_in_schema=False)
def style_guide_view(
    version: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    """One historical version, read-only -- no edit affordance."""
    stored = session.exec(select(StyleGuide).where(StyleGuide.version == version)).first()
    if stored is None:
        raise HTTPException(status_code=404)

    return _templates.TemplateResponse(request, "style_guide_view.html", {"style_guide": stored})
