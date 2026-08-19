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

from shell.adapters.postgres.client import Client, StoredNatalChart, deserialize_natal_chart
from shell.adapters.postgres.report_run import ReportRun
from shell.http.app import get_session
from shell.runner.driver import drive

__all__ = ["router"]

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


def _drive_run(request: Request, session: Session, run: ReportRun, client: Client) -> ReportRun:
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
    )


@router.post("/clients/{client_id}/report-runs", include_in_schema=False)
def start_report_run(
    client_id: UUID,
    request: Request,
    month: str = Form(...),
    session: Session = Depends(get_session),
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

    _drive_run(request, session, run, client)

    return RedirectResponse(f"/report-runs/{run.id}", status_code=303)


@router.get("/report-runs/{run_id}", include_in_schema=False)
def poll_report_run(
    run_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    run = session.get(ReportRun, run_id)
    if run is None:
        raise HTTPException(status_code=404)

    client = session.get(Client, run.client_id)
    if client is None:
        raise RuntimeError(f"ReportRun {run.id} references a missing Client.")

    _drive_run(request, session, run, client)

    return _templates.TemplateResponse(request, "report_run_poll.html", {"run": run})
