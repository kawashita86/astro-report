"""``html_to_pdf()``: the one place an already-rendered HTML string is turned
into PDF bytes (Story 6.2).

A thin wrapper around WeasyPrint -- ``shell/http/routes/report_runs.py``'s
``download_report_pdf`` route renders ``shell/http/templates/report_export.html``
to a string first (the same ``Jinja2Templates`` instance every other route in
that module already uses), then hands the result here. No template
knowledge, no Section/Client shape lives in this module -- it only converts
whatever HTML it is given.

``base_url`` is required (spec-pdf-export-redesign): ``report_export.html``
now loads its two font families via file-based ``@font-face`` (no runtime
network fetch, per this story's Boundaries), and WeasyPrint resolves any
relative ``url(...)`` in the rendered HTML against ``base_url`` -- without
it, WeasyPrint has no base to resolve ``fonts/*.woff2`` against and the
``@font-face`` rules silently fail to load.
"""

from __future__ import annotations

from weasyprint import HTML

__all__ = ["html_to_pdf"]


def html_to_pdf(html: str, *, base_url: str) -> bytes:
    """Render ``html`` to a PDF file's bytes. ``base_url`` is the directory
    relative ``url(...)`` references in ``html`` (fonts, images) resolve
    against -- callers pass the directory the template that produced
    ``html`` lives in."""
    return HTML(string=html, base_url=base_url).write_pdf()
