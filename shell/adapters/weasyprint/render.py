"""``html_to_pdf()``: the one place an already-rendered HTML string is turned
into PDF bytes (Story 6.2).

A thin wrapper around WeasyPrint -- ``shell/http/routes/report_runs.py``'s
``download_report_pdf`` route renders ``shell/http/templates/report_export.html``
to a string first (the same ``Jinja2Templates`` instance every other route in
that module already uses), then hands the result here. No template
knowledge, no Section/Client shape lives in this module -- it only converts
whatever HTML it is given.
"""

from __future__ import annotations

from weasyprint import HTML

__all__ = ["html_to_pdf"]


def html_to_pdf(html: str) -> bytes:
    """Render ``html`` to a PDF file's bytes."""
    return HTML(string=html).write_pdf()
