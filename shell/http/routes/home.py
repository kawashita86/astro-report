"""``GET /``: the operator's home dashboard (Story 9.2).

Fills the gap where ``/`` resolved to nothing -- an authenticated request
404'd, so opening the app landed nowhere and there was no surface showing
which report runs are in flight or whether the backup is behind. Story 9.1
shipped the shell with a "Home" nav item pointing at this dead route; this
module is the route.

Surfaces only what already exists: the recent ``ReportRun`` rows across every
Client (newest-updated first, capped at :data:`_RECENT_LIMIT`), each with its
Client name, its month as a mono chip, an Italian status badge for its
current stage or terminal state, and its last-updated timestamp; plus the
global backup-stale ``warning`` banner (AD-17) and quick-action links to
Clienti and the Guida di stile. No ``core/`` change, no data-model change,
no new behaviour -- the run state and the staleness rule already exist and
are only read here.

Authenticated by default: ``/`` is not named in
``shell.http.auth.ALLOWLIST``, so ``AuthMiddleware`` guards it exactly like
every other route -- an anonymous ``GET /`` is the uniform empty-body 401,
mirroring ``shell/http/routes/backup.py``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from shell.adapters.postgres.backup_record import backup_is_stale
from shell.adapters.postgres.client import Client
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_run import ReportRun
from shell.http.app import get_session
from shell.http.flash import _flash_context_processor

__all__ = ["router"]

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_templates = Jinja2Templates(
    directory=_TEMPLATES_DIR, context_processors=[_flash_context_processor]
)

#: How many recent runs the dashboard lists, newest-updated first. A named
#: module constant so the cap is one edit and one thing to assert against.
_RECENT_LIMIT = 20

#: Fixed, total map from a run's ``stage`` to ``(badge text, badge variant)``
#: -- the Italian "what happens next" phrasing from EXPERIENCE.md's stage
#: labels. ``stage`` is written only by
#: ``shell/runner/driver.py::_STAGE_SEQUENCE`` (``natal_ready -> ... ->
#: exported``) plus the ``None`` "not advanced yet" state, so this covers
#: every persisted value. A terminally-failed run (``failed_at`` set) wins
#: over ``stage`` -- see :func:`_badge_for`. Kept local to this module:
#: Story 9.5 owns the full stage track and may generalise it later.
_STAGE_BADGES: dict[str | None, tuple[str, str]] = {
    None: ("In coda", "neutral"),
    "natal_ready": ("Ricerca dei transiti", "running"),
    "transits_ready": ("Assemblaggio del Payload", "running"),
    "payload_ready": ("Generazione della bozza", "running"),
    "draft_ready": ("Verifica di fondatezza", "running"),
    "gate_passed": ("Pronto per l'esportazione", "running"),
    "exported": ("Esportato", "success"),
}

#: A terminally-failed run, regardless of the stage it failed at.
_FAILED_BADGE: tuple[str, str] = ("Verifica non superata", "danger")


def _badge_for(run: ReportRun) -> tuple[str, str]:
    """The ``(text, variant)`` badge pair for one run's current state.

    ``failed_at`` wins over ``stage`` -- a run can be marked terminally
    failed at any stage. ``_STAGE_BADGES`` is a total map over every stage
    the driver persists; the ``.get`` fallback only guards the impossible
    case of a legacy/restored row carrying an unmapped ``stage``, so the
    landing page degrades to the neutral "In coda" badge rather than 500.
    """
    if run.failed_at is not None:
        return _FAILED_BADGE
    return _STAGE_BADGES.get(run.stage, ("In coda", "neutral"))


@router.get("/", include_in_schema=False)
def home_dashboard(request: Request, session: Session = Depends(get_session)) -> Response:
    """Render the dashboard: recent runs across every Client, the
    backup-stale banner, and the quick actions.

    The run list is ``select(ReportRun, Client)`` joined on
    ``ReportRun.client_id == Client.id``, ordered by ``ReportRun.updated_at``
    descending with ``ReportRun.id`` descending as the tie-break, capped at
    :data:`_RECENT_LIMIT`. An empty result renders the one-line empty state;
    the quick actions show either way. The badges are point-in-time on page
    load -- Story 9.5 owns live polling.
    """
    rows = session.exec(
        select(ReportRun, Client)
        .join(Client, ReportRun.client_id == Client.id)
        .order_by(ReportRun.updated_at.desc(), ReportRun.id.desc())
        .limit(_RECENT_LIMIT)
    ).all()

    # Which of the listed runs actually have a passed `Report` row -- the
    # same existence check `view_report` itself gates on (`_load_passed_
    # report_bundle`, `shell/http/routes/report_runs.py`), not a re-derived
    # guess from `stage`/`failed_at` (review-loop 1: those two can drift
    # apart, e.g. a `gate_passed` run whose Report was somehow removed, or a
    # stage added between `gate_passed` and `exported` later). Keyed to each
    # Report's own `accepted_violation_count` (Story 5.7) too, so a Report
    # closed via accepted exceptions can carry its own warning badge here,
    # not just on the reading sheet and Report History.
    run_ids = [run.id for run, _client in rows]
    reported_rows = session.exec(
        select(Report.report_run_id, Report.accepted_violation_count).where(
            Report.report_run_id.in_(run_ids)
        )
    ).all()
    accepted_violation_counts_by_run = {
        report_run_id: count for report_run_id, count in reported_rows
    }

    runs = []
    for run, client in rows:
        badge_text, badge_variant = _badge_for(run)
        report_ready = run.id in accepted_violation_counts_by_run
        runs.append(
            {
                "client_name": client.name,
                "month": run.month,
                "badge_text": badge_text,
                "badge_variant": badge_variant,
                "accepted_violation_count": accepted_violation_counts_by_run.get(run.id, 0),
                "failure_reason": run.failure_reason,
                "updated_at": run.updated_at.strftime("%d/%m/%Y %H:%M"),
                # Story 9.2 amendment (correct-course 2026-08-31): a passed
                # run opens the Report directly; anything without one yet
                # (still running, or terminally failed before ever passing)
                # opens the stage view instead. `link_label` gives the link
                # an accessible name a screen reader can tell apart from its
                # neighbours without following it (review-loop 1) -- the
                # visible badge text already conveys this to a sighted user.
                "href": f"/report-runs/{run.id}/report"
                if report_ready
                else f"/report-runs/{run.id}",
                "link_label": (
                    f"{client.name} — apri il report"
                    if report_ready
                    else f"{client.name} — apri l'avanzamento"
                ),
            }
        )

    return _templates.TemplateResponse(
        request,
        "home.html",
        {"runs": runs, "backup_stale": backup_is_stale(session)},
    )
