"""``POST /clients/{client_id}/report-runs`` (start) and
``GET /report-runs/{run_id}`` (HTMX poll) -- Francesco starts a month's
computation and watches it finish (Story 3.5).

Both routes call ``shell/runner/driver.py::drive()`` -- the start route once,
right after creating the row, so a fast run can finish inside the same
request; the poll route again on every poll, so an interrupted or still-
running run keeps advancing on whichever request -- start or poll -- reaches
it next. No background task, no queue: see ``shell/runner/driver.py``'s
Design Notes.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards both routes
before a request ever reaches this module, mirroring
``shell/http/routes/chart.py``/``shell/http/routes/clients.py``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from shell.adapters.gemini.generator import GeminiGenerator
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.adapters.postgres.client import Client, StoredNatalChart, deserialize_natal_chart
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.config import Environment
from shell.http.app import get_session
from shell.http.draft_view import (
    LIST_SECTION_NAMES,
    SECTION_ORDER,
    deserialize_generated_draft,
    render_draft,
)
from shell.http.payload_view import localize_payload
from shell.ports.generator import Generator
from shell.runner.driver import drive

__all__ = ["get_generator", "router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)

#: "YYYY-MM", zero-padded -- the one shape ``shell/runner/month.py``'s
#: ``client_month_interval_utc`` is contracted to accept. Checked here so a
#: malformed month is a plain 422 at submission time, never handed to
#: ``drive()`` where ``with_backoff`` would retry a permanent input error as
#: if it were a transient one and quietly leave the run un-advanced.
_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _current_chart(session: Session, client_id: UUID) -> StoredNatalChart | None:
    return session.exec(
        select(StoredNatalChart).where(
            StoredNatalChart.client_id == client_id,
            StoredNatalChart.superseded_at.is_(None),
        )
    ).first()


def get_generator(request: Request) -> Generator:
    """The ``Generator`` this route calls at the ``draft_ready`` stage.

    A dependency of its own, not a bare call inline in the handler, so tests
    can substitute a fake without a real network call or a real Gemini API
    key -- mirrors ``get_geocoder()`` (``shell/http/routes/clients.py``).
    Constructed per-request, never cached on ``app.state``: this avoids
    constructing a real ``genai.Client`` for every one of the many HTTP
    tests that build the app but never touch report runs (this story's
    Design Notes).

    Under ``Environment.LOCAL`` this returns ``RecordedResponseGenerator``
    instead of a real ``GeminiGenerator`` (Story 4.9) -- mirrors the
    ``settings.environment is Environment.LOCAL`` idiom ``shell/http/app.py``
    already uses twice, so ``docker compose up`` against a local Postgres
    never spends real Gemini quota. Production behavior is unchanged.
    """
    if request.app.state.settings.environment is Environment.LOCAL:
        return RecordedResponseGenerator()
    return GeminiGenerator(request.app.state.settings.gemini_api_key)


def _drive_run(
    request: Request, session: Session, run: ReportRun, client: Client, generator: Generator
) -> ReportRun:
    """Deserialize ``client``'s current stored chart and call ``drive()``
    once -- shared by both routes below."""
    stored_chart = _current_chart(session, client.id)
    if stored_chart is None:
        raise HTTPException(status_code=404)
    natal_chart = deserialize_natal_chart(stored_chart)
    return drive(
        session,
        run,
        natal_chart=natal_chart,
        config=request.app.state.computation_config,
        ephemeris_identity=request.app.state.ephemeris_identity,
        sections_config=request.app.state.sections_config,
        generator=generator,
    )


@router.post("/clients/{client_id}/report-runs", include_in_schema=False)
def start_report_run(
    client_id: UUID,
    request: Request,
    month: str = Form(...),
    session: Session = Depends(get_session),
    generator: Generator = Depends(get_generator),
) -> Response:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    if not _MONTH_PATTERN.match(month):
        raise HTTPException(status_code=422, detail="month must be 'YYYY-MM'.")

    now = datetime.now(UTC)
    run = ReportRun(client_id=client_id, month=month, created_at=now, updated_at=now)
    session.add(run)
    session.commit()

    _drive_run(request, session, run, client, generator)

    return RedirectResponse(f"/report-runs/{run.id}", status_code=303)


@router.get("/report-runs/{run_id}", include_in_schema=False)
def poll_report_run(
    run_id: UUID,
    request: Request,
    session: Session = Depends(get_session),
    generator: Generator = Depends(get_generator),
) -> Response:
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    client = session.get(Client, run.client_id)
    if client is None:
        raise RuntimeError(f"ReportRun {run.id} references a missing Client.")

    _drive_run(request, session, run, client, generator)

    return _templates.TemplateResponse(request, "report_run_poll.html", {"run": run})


@router.get("/report-runs/{run_id}/payload", include_in_schema=False)
def view_report_payload(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Read the frozen Payload behind ``run_id``'s Report, entry by entry
    (Story 3.9, PRD FR-15).

    404 covers both "no such ``ReportRun``" and "that run hasn't reached
    ``payload_ready`` yet" -- both collapse to the same query finding no
    ``ReportPayload`` row for ``run_id``, so no separate ``ReportRun`` lookup
    is needed first.
    """
    stored = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run_id)
    ).first()
    if stored is None:
        raise HTTPException(status_code=404)

    client = session.get(Client, stored.client_id)
    if client is None:
        raise RuntimeError(f"ReportPayload {stored.id} references a missing Client.")

    localized = localize_payload(stored.payload, iana_zone=client.iana_zone)

    return _templates.TemplateResponse(request, "report_payload.html", {"payload": localized})


@router.get("/report-runs/{run_id}/draft", include_in_schema=False)
def view_report_draft(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    """Read the persisted ``GeneratedDraft`` behind ``run_id``'s Report,
    rendered into prose Sections 1-5/8 and dated-list Sections 6-7, in the
    draft's own fixed 1-8 order (Story 4.6, AD-6).

    404 covers both "no such ``ReportRun``" and "that run hasn't reached
    ``draft_ready`` yet" -- both collapse to the same query finding no
    ``ReportDraft`` row for ``run_id``, mirroring ``view_report_payload``'s
    own 404 collapse.
    """
    stored_draft = session.exec(
        select(ReportDraft).where(ReportDraft.report_run_id == run_id)
    ).first()
    if stored_draft is None:
        raise HTTPException(status_code=404)

    stored_payload = session.exec(
        select(ReportPayload).where(ReportPayload.report_run_id == run_id)
    ).first()
    if stored_payload is None:
        raise RuntimeError(f"ReportDraft {stored_draft.id} has no matching ReportPayload.")

    client = session.get(Client, stored_draft.client_id)
    if client is None:
        raise RuntimeError(f"ReportDraft {stored_draft.id} references a missing Client.")

    draft = deserialize_generated_draft(stored_draft.draft)
    rendered = render_draft(draft, stored_payload.payload, iana_zone=client.iana_zone)

    return _templates.TemplateResponse(
        request,
        "report_draft.html",
        {
            "draft": rendered,
            "section_order": SECTION_ORDER,
            "list_section_names": LIST_SECTION_NAMES,
        },
    )
