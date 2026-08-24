"""``export_report()``: the single, structural path to an exportable
``Report`` (Story 5.3, AD-1).

The only function anywhere in this codebase that reads a persisted
``Report`` row (``shell/adapters/postgres/report.py``) to produce an
exportable result -- enforced by a static AST scan
(``tests/test_export_boundary.py``), not merely by convention. A ``Report``
row is written only on a passing Groundedness Gate result
(``shell/runner/driver.py``'s ``gate_passed`` stage), so refusing when no row
exists for ``report_id`` is also how "the Gate has not passed" refuses
export -- there is no separate "gate not passed" check here, because the
row's mere existence already encodes it.

Actual PDF/Markdown rendering is Story 6.2's job; this function is the
structural gate, not the renderer.
"""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session

from core.errors import ReportNotFoundError
from shell.adapters.postgres.report import Report

__all__ = ["export_report"]


def export_report(session: Session, report_id: UUID) -> Report:
    """Read the passed ``Report`` row for ``report_id``, or refuse.

    Raises:
        ReportNotFoundError: naming ``report_id`` -- no ``Report`` row exists
            for it, meaning the Groundedness Gate has never passed for
            whatever ``ReportRun`` would have produced it (or ``report_id``
            is simply unknown/already deleted via the FR-29 Client-deletion
            cascade).
    """
    report = session.get(Report, report_id)
    if report is None:
        raise ReportNotFoundError(report_id)
    return report
