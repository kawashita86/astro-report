"""``Generator``: the port a Section-generation adapter implements (Story
4.5, AD-3; one Section per call since Stories 10.3/10.4).

Fixed to ``(section, payload, style_guide, theme_previous, theme_current)``
plus, for Consiglio finale only, the text of the Sections already written --
and never Prior Report prose (continuity travels only as ``ReportTheme``,
Story 4.3/4.4). An implementing adapter holds no database handle, no
filesystem access and no tool definitions: it is a pure function of its
arguments plus whatever network call it makes to the configured provider.

``StyleGuideVersion`` is defined here, not imported from
``shell/adapters/postgres/style_guide.py``, so this port never imports the
ORM ``StyleGuide`` row -- mirrors how ``Geocoder`` (``shell/ports/geocoder.py``)
takes only ``core.types.place`` value objects, never a database row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from core.types.generation import Sentence
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
    def generate_section(
        self,
        section: str,
        payload: dict,
        style_guide: StyleGuideVersion,
        theme_previous: ReportTheme | None,
        theme_current: ReportTheme,
        written_sections: Mapping[str, tuple[Sentence, ...]] | None = None,
    ) -> tuple[Sentence, ...]:
        """Write one Section (a ``GeneratedDraft`` field name) as cited
        sentences, so Sections can be written in parallel and rewritten
        individually (Story 10.3).

        ``written_sections`` is read only by ``consiglio_finale``, which is
        shown Sections 1-7's sentence *texts* (never their ids) and still
        cites only ``payload`` ids. Validation (alias leak, citations, and
        for the two day-list Sections date tokens and coverage) is scoped to
        this one Section.

        Raises:
            ValueError: ``section`` is not one of the eight Section names.
            GenerationError: a step name from the failing stage -- the request itself, parsing the
                response, citation validation (a returned ``entry_id`` absent from
                ``payload``), or date-token validation (a date-shaped token inside
                ``giorni_favorevoli``/``giorni_di_attenzione``), scoped to this
                Section. Date-token validation is a best-effort regex heuristic,
                not a completeness guarantee.
        """
        ...
