"""Serialize a rendered, Gate-passed Report draft into a standalone Markdown
document (epic-6 retrospective item 47 / ``spec-6-2b-markdown-export.md``).

The plain-text counterpart of ``shell/http/templates/report_export.html``:
the same section set in the same ``SECTION_ORDER`` order plus the Client's
name, nothing else -- no chart wheel, no Payload, no Gate result, no run
identifier, no internal metadata. The two are not line-for-line equivalent
(see :func:`render_report_markdown` on uncited day entries). Pure string
assembly, no I/O; the route
(``shell/http/routes/report_runs.py::download_report_markdown``) owns the
gate, the ``ExportRecord`` write and the one-time ``run.stage`` advance.

Named ``render_report_markdown`` (not ``export_*``) and taking the already
``render_draft``-rendered structure (not a ``GeneratedDraft``) so the static
export-shape invariant in ``tests/test_export_boundary.py`` stays green.
"""

from __future__ import annotations

from typing import Any

__all__ = ["render_report_markdown"]


def render_report_markdown(
    rendered: dict[str, Any],
    *,
    client_name: str,
    section_order: tuple[str, ...],
    list_section_names: tuple[str, ...],
    section_titles: dict[str, str],
) -> str:
    """``rendered`` (a ``shell/http/draft_view.py::render_draft`` output) plus
    ``client_name`` as one Markdown string.

    An ``#`` title with the Client's name, then one ``##`` section per
    ``section_order`` name, titled from ``section_titles`` (a missing key is a
    ``KeyError`` -- ``SECTION_TITLES`` is bound to ``SECTION_ORDER`` by a unit
    test). The section set and order match ``report_export.html``; the
    per-entry layout does not have to. A prose section renders as its single
    joined paragraph string (an empty section is its heading alone). A list
    section (named in ``list_section_names``) renders as one ``-`` bullet per
    day entry: a cited entry as ``- {date} \N{EM DASH} {text}``, and an
    uncited entry (``text`` is ``None``) as ``- {date}`` -- date-only, never
    dropped (``report_export.html`` instead keeps a trailing ``\N{EM DASH}``
    on an uncited entry; the Markdown drops it).
    """
    lines: list[str] = [f"# {client_name}", ""]
    for name in section_order:
        lines.append(f"## {section_titles[name]}")
        lines.append("")
        if name in list_section_names:
            for item in rendered[name]:
                text = item["text"]
                lines.append(
                    f"- {item['date']} \N{EM DASH} {text}" if text else f"- {item['date']}"
                )
        else:
            prose = rendered[name]["text"]
            if prose:
                lines.append(prose)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
