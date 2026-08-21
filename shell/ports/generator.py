"""``Generator``: the port a Section-generation adapter implements (Story
4.5, AD-3).

Fixed to exactly ``(payload, style_guide, theme_previous, theme_current)`` --
nothing else, and never Prior Report prose (continuity travels only as
``ReportTheme``, Story 4.3/4.4). An implementing adapter holds no database
handle, no filesystem access and no tool definitions: it is a pure function
of its four arguments plus whatever network call it makes to the configured
provider.

``StyleGuideVersion`` is defined here, not imported from
``shell/adapters/postgres/style_guide.py``, so this port never imports the
ORM ``StyleGuide`` row -- mirrors how ``Geocoder`` (``shell/ports/geocoder.py``)
takes only ``core.types.place`` value objects, never a database row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.types.generation import GeneratedDraft
from core.types.memory import ReportTheme

__all__ = ["Generator", "StyleGuideVersion"]


@dataclass(frozen=True)
class StyleGuideVersion:
    """The Style Guide version in force for one generation call -- the two
    fields the port needs from ``shell.adapters.postgres.style_guide.StyleGuide``
    (``.version``, ``.content``), without importing that ORM row. The caller
    builds this from ``current_style_guide(session)``."""

    version: int
    content: str


class Generator(Protocol):
    def generate(
        self,
        payload: dict,
        style_guide: StyleGuideVersion,
        theme_previous: ReportTheme | None,
        theme_current: ReportTheme,
    ) -> GeneratedDraft:
        """Turn one month's Report ``payload`` into a ``GeneratedDraft``:
        eight cited Sections in Italian, conditioned on ``style_guide`` and
        the continuity carried by ``theme_previous``/``theme_current``.

        ``style_guide`` is required, never optional -- a call cannot be
        constructed without the Style Guide version in force. ``theme_previous``
        is ``None`` for a Client's first Report (mirrors
        ``core/memory/diff.py::diff_themes()``'s own ``previous is None``
        handling); never a zero-valued ``ReportTheme``. Prior Report prose
        is never an input.

        Raises:
            GenerationError: naming the step that failed -- the request
                itself, parsing the response, citation validation (a
                returned ``entry_id`` absent from ``payload``), or
                date-token validation (a date-shaped token inside
                ``giorni_favorevoli``/``giorni_di_attenzione``). Date-token
                validation is a best-effort regex heuristic, not a
                completeness guarantee -- it catches the token shapes the
                adapter knows about, not every way a date could be written.
        """
        ...
