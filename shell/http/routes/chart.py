"""``GET /clients/{client_id}/chart``: Francesco's own verification tool
(Story 2.6, ARCHITECTURE-SPINE.md FR-5) -- renders a Client's stored Natal
Chart as an inline SVG wheel via Kerykeion, so planetary positions, house
cusps and natal Aspects can be eyeballed against Astro.com before trusting
anything built on the stored chart.

Reads only: no Client, no Natal Chart and no other row is ever written here.
An unknown Client id, or a Client with no stored chart, is a plain 404 --
no new domain error type (the story's Boundaries & Constraints). The
``create_client`` / ``correct_client`` success pages now link here as a
one-click verification shortcut (epic-2-retro-item-14); FR-5 still holds --
no Report or export artifact ever links to this route.

Authenticated by default: nothing here is named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards this route
before a request ever reaches this module, mirroring
``shell/http/routes/clients.py``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from kerykeion.chart_data_factory import ChartDataFactory
from kerykeion.charts.chart_drawer import ChartDrawer
from sqlmodel import Session, select

from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.http import chart_wheel
from shell.http.app import get_session

__all__ = ["router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/clients/{client_id}/chart", include_in_schema=False)
def chart_wheel_view(
    client_id: UUID, request: Request, session: Session = Depends(get_session)
) -> Response:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404)

    stored_chart = session.exec(
        select(StoredNatalChart).where(
            StoredNatalChart.client_id == client_id,
            StoredNatalChart.superseded_at.is_(None),
        )
    ).first()
    if stored_chart is None:
        raise HTTPException(status_code=404)

    # Warn (never refuse) when the chart was computed under a different
    # `computation.toml` than the one now running: stored planetary positions
    # are shown as-is, but natal aspects are recomputed below at today's
    # `orbs.natal`, so a config edit since the chart was stored can make the
    # rendered aspects disagree with the stored ones. The frozen Report keeps
    # its own hash in `ReportPayload`; this wheel is only a verification aid,
    # so a non-blocking banner (`chart_wheel.html`) is the right signal
    # (epic-2-retro-item-11). The equal-hash path renders exactly as before.
    config_stale = (
        stored_chart.computation_config_content_hash
        != request.app.state.computation_config.content_hash
    )

    subject = chart_wheel.build_subject(client, stored_chart)
    orb = request.app.state.computation_config.orbs.natal
    chart_data = ChartDataFactory.create_natal_chart_data(
        subject, active_aspects=chart_wheel.active_aspects(orb)
    )
    svg = ChartDrawer(chart_data).generate_svg_string()

    return _templates.TemplateResponse(
        request,
        "chart_wheel.html",
        {"client": client, "active_tab": "tema", "svg": svg, "config_stale": config_stale},
    )
