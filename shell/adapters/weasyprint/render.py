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

import logging

from weasyprint import HTML
from weasyprint.logger import LOGGER as _WEASYPRINT_LOGGER

__all__ = ["html_to_pdf"]

#: SVG presentation properties (lowercased) that Kerykeion's natal-wheel SVG
#: (spec-pdf-export-redesign's ``report_export.html`` wheel card) sets via
#: `style="..."` on nearly every element it draws. WeasyPrint 69's general
#: CSS validator does not recognize *any* of these as a known CSS property
#: -- confirmed by reading its source (``weasyprint.css.validation
#: .validate_non_shorthand``, whose ``KNOWN_PROPERTIES`` set excludes them
#: entirely) -- so every one of them logs an "Ignored ... unknown property"
#: warning regardless of whether its value is a literal color or an
#: unresolved `var(...)`. WeasyPrint's own dedicated SVG rendering path
#: (separate from this CSS validator) still reads and applies these
#: correctly, so the warning reflects no actual rendering defect -- it is
#: pure log noise, reported at production volume (one PDF export logs
#: several hundred lines) against the Docker deployment.
_SVG_PRESENTATION_PROPERTIES = frozenset(
    {
        "fill",
        "fill-opacity",
        "fill-rule",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "stroke-linecap",
        "stroke-linejoin",
        "stroke-miterlimit",
        "stroke-dasharray",
        "clip-rule",
        "vector-effect",
    }
)


class _SvgPresentationPropertyNoiseFilter(logging.Filter):
    """Drops exactly the "Ignored `<svg-presentation-property>:...`,
    unknown property." warnings WeasyPrint's CSS validator logs for
    Kerykeion's SVG markup (see ``_SVG_PRESENTATION_PROPERTIES``) --
    matched on the log record's own ``args`` (the validator's
    ``(name, value, line, col, reason)`` tuple), never on the formatted
    message text, so any other WeasyPrint warning -- a real font problem,
    a mistake in this project's own template CSS -- still comes through
    unfiltered."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) != 5:
            return True
        name, _value, _line, _col, reason = args
        if reason not in ("unknown property", "property not supported yet"):
            return True
        return str(name).lower() not in _SVG_PRESENTATION_PROPERTIES


_WEASYPRINT_LOGGER.addFilter(_SvgPresentationPropertyNoiseFilter())


def html_to_pdf(html: str, *, base_url: str) -> bytes:
    """Render ``html`` to a PDF file's bytes. ``base_url`` is the directory
    relative ``url(...)`` references in ``html`` (fonts, images) resolve
    against -- callers pass the directory the template that produced
    ``html`` lives in."""
    return HTML(string=html, base_url=base_url).write_pdf()
