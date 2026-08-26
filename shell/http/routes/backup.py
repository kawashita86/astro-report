"""``GET /backup``: the operator-held export Francesco actually holds (Story
6.5) -- epic-6-context.md is explicit that the hosted Postgres instance's
free-tier point-in-time restore (a roughly six-hour window, no scheduled
backups) does not satisfy the durability requirement on its own.

Reads and serializes every row of every durability-relevant table, in one
downloadable JSON file, in an order a future restore (Story 8.5) can insert
without ever violating a foreign key: ``client`` first (no dependencies),
then ``natal_chart``/``report_run`` (depend only on ``client``), then
``report``/``report_payload``/``report_draft``/``report_theme``/
``gate_result`` (depend on ``report_run``, and transitively on ``client``),
then ``export_record`` (depends on ``report``), and finally ``style_guide``
(global, independent of everything else). See this module's Design Notes in
the story spec for the full dependency reasoning.

Each row is serialized with SQLModel's own ``model_dump(mode="json")`` --
``UUID`` -> ``str``, ``datetime`` -> ISO 8601, and the existing JSON columns
(``planets``, ``payload``, ``theme``, ``violations``, ``draft``,
``transit_events``) pass through unchanged since they are already plain
``dict``/``list`` values. No hand-written per-table serializer anywhere in
this module.

Not added to ``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards this
route exactly like every other route in this application -- zero new auth
code, mirroring ``shell/http/routes/style_guide.py``/
``shell/http/routes/report_runs.py``.

No restore, no pagination, no filtering, no streaming, no UI page here --
this route's only job is producing the export. Restore is Story 8.5's job;
the staleness-warning UI is Story 6.6's, and depends on this route existing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session, select

from shell.adapters.postgres.backup_record import store_backup_record
from shell.adapters.postgres.client import Client, StoredNatalChart
from shell.adapters.postgres.export_record import ExportRecord
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme
from shell.adapters.postgres.style_guide import StyleGuide
from shell.http.app import get_session

__all__ = ["router"]

router = APIRouter()

#: FK-safe table order (this module's own docstring, and the story's Design
#: Notes): each model only after every model it foreign-keys into, so a
#: future restore (Story 8.5) can insert the file's arrays in file order
#: without ever hitting a foreign key that doesn't exist yet.
_BACKUP_MODELS = (
    Client,
    StoredNatalChart,
    ReportRun,
    Report,
    ReportPayload,
    ReportDraft,
    StoredReportTheme,
    StoredGateResult,
    ExportRecord,
    StyleGuide,
)


@router.get("/backup", include_in_schema=False)
def download_backup(session: Session = Depends(get_session)) -> Response:
    """Download every row of every durability-relevant table as one JSON
    file (Story 6.5).

    Built fully in memory, mirroring ``download_report_pdf``'s exact
    ``Response(...)`` shape (``shell/http/routes/report_runs.py``) -- no
    streaming, no pagination, plus a ``Cache-Control: no-store`` header this
    route adds beyond that mirror, since every response here carries every
    Client's PII unfiltered. Each of the ten tables in ``_BACKUP_MODELS`` is
    read with ``select(Model).order_by(Model.id)`` (every row, no filtering,
    ordered for a reproducible/diffable export rather than incidental DB row
    order) and each row serialized with ``.model_dump(mode="json")``, keyed
    by the model's own ``__tablename__`` so the file's top-level keys are
    the ten real table names, in FK-safe order.
    """
    backup: dict[str, list[dict[str, object]]] = {
        model.__tablename__: [
            row.model_dump(mode="json") for row in session.exec(select(model).order_by(model.id))
        ]
        for model in _BACKUP_MODELS
    }

    # Recorded only now that the export body is fully built -- a failure
    # while reading/serializing any table above never records a backup that
    # didn't actually happen (Story 6.6's Boundaries).
    store_backup_record(session)
    session.commit()

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=json.dumps(backup).encode(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="backup-{timestamp}.json"',
            "Cache-Control": "no-store",
        },
    )
