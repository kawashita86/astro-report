"""``/corpus``: the list of every past report added so far, ``/corpus/new``:
the paste-in form, and ``POST /corpus``: store one past report as plain text
with its paired/unpaired marking (Story 7.1, extended by Story 7.2).

One report is stored as plain text regardless of its origin -- email,
messaging or a folder -- with no per-source parsing, no file upload, no
format handling, and no edit or delete of an entry (Story 7.1's Boundaries).

Story 7.2 adds, at record time only: a paired/unpaired radio (default
unpaired), and -- for a paired entry -- an optional existing-Client picker
and an optional ``YYYY-MM`` month. Pairing is Francesco's assertion that he
knows the chart behind the entry; the Client link and the month are both
optional even for a paired entry. There is no retroactive re-marking route.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards every route in
this module before a request ever reaches it, mirroring
``shell/http/routes/style_guide.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from shell.adapters.postgres.client import Client, list_clients
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

#: "YYYY-MM", zero-padded -- the same shape ``shell/runner/month.py`` is
#: contracted to accept, re-declared here (per this story's Code Map: do not
#: import the route module that also defines it) so a malformed month on a
#: paired entry is a plain 422 at submission time.
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


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


def _render_new_form(
    request: Request,
    session: Session,
    *,
    content: str,
    error: str | None,
    paired: str,
    client_id: str,
    month: str,
    status_code: int = 200,
) -> Response:
    """The ``/corpus/new`` form -- shared by ``GET /corpus/new`` and every
    ``422`` re-render. Always carries the full Client list for the picker and
    echoes the three marking fields back alongside ``content``/``error``.
    """
    return _templates.TemplateResponse(
        request,
        "corpus_new.html",
        {
            "content": content,
            "error": error,
            "paired": paired,
            "client_id": client_id,
            "month": month,
            "clients": list_clients(session),
        },
        status_code=status_code,
    )


@router.get("/corpus", include_in_schema=False)
def corpus_list(request: Request, session: Session = Depends(get_session)) -> Response:
    """Every stored entry, most-recent-first (Story 7.1), each paired with its
    resolved ``Client`` or ``None`` (Story 7.2) so the template can show the
    Client name without an ORM relationship. An empty corpus renders its own
    empty-state text and a link to ``/corpus/new``.

    The linked Clients are fetched in one ``IN`` query, not one ``get()`` per
    entry -- a paste-heavy corpus would otherwise issue N round trips to
    render one page."""
    stored_entries = list_corpus_entries(session)
    linked_ids = {entry.client_id for entry in stored_entries if entry.client_id}
    clients_by_id = (
        {
            client.id: client
            for client in session.exec(
                select(Client).where(Client.id.in_(linked_ids))
            )
        }
        if linked_ids
        else {}
    )
    entries = [
        (entry, clients_by_id.get(entry.client_id) if entry.client_id else None)
        for entry in stored_entries
    ]
    return _templates.TemplateResponse(
        request, "corpus_list.html", {"entries": entries}
    )


@router.get("/corpus/new", include_in_schema=False)
def corpus_new_form(
    request: Request, session: Session = Depends(get_session)
) -> Response:
    """The paste-in form, with the paired/unpaired radio (default unpaired),
    the existing-Client picker and the month input."""
    return _render_new_form(
        request,
        session,
        content="",
        error=None,
        paired="unpaired",
        client_id="",
        month="",
    )


@router.post("/corpus", include_in_schema=False)
async def add_corpus(request: Request, session: Session = Depends(get_session)) -> Response:
    """Store one pasted past report as plain text with its marking, then
    redirect to the list.

    An oversized or non-UTF-8 body, or empty/whitespace-only ``content``,
    inserts nothing and re-renders the form with a ``role="alert"`` message
    and a ``422``. For a paired entry, a non-empty ``client_id`` that is not
    a UUID naming an existing ``Client``, or a non-empty ``month`` that is
    not ``YYYY-MM``, does the same. An unpaired entry stores ``paired=False``
    with ``client_id``/``month`` forced to ``NULL`` whatever was submitted.
    """
    try:
        fields = await _parse_form(request)
    except _FormTooLarge:
        return _render_new_form(
            request,
            session,
            content="",
            error="the submitted form is too large.",
            paired="unpaired",
            client_id="",
            month="",
            status_code=422,
        )
    except _FormNotUtf8:
        return _render_new_form(
            request,
            session,
            content="",
            error="the submitted form is not valid UTF-8.",
            paired="unpaired",
            client_id="",
            month="",
            status_code=422,
        )

    content = fields.get("content", "")
    paired_field = fields.get("paired", "unpaired")
    client_id_field = fields.get("client_id", "")
    month_field = fields.get("month", "")
    is_paired = paired_field == "paired"

    def _reject(error: str) -> Response:
        return _render_new_form(
            request,
            session,
            content=content,
            error=error,
            paired=paired_field,
            client_id=client_id_field,
            month=month_field,
            status_code=422,
        )

    if not content.strip():
        return _reject("content is required.")

    linked_client_id: UUID | None = None
    linked_month: str | None = None

    if is_paired:
        if client_id_field:
            try:
                candidate = UUID(client_id_field)
            except ValueError:
                return _reject("that Client id is not valid.")
            if session.get(Client, candidate) is None:
                return _reject("that Client is not in the application.")
            linked_client_id = candidate
        if month_field:
            if not _MONTH_PATTERN.match(month_field):
                return _reject("month must be 'YYYY-MM'.")
            linked_month = month_field

    add_corpus_entry(
        session,
        content=content,
        paired=is_paired,
        client_id=linked_client_id,
        month=linked_month,
    )
    session.commit()
    return RedirectResponse("/corpus", status_code=303)
