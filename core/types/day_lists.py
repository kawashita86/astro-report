"""``DayLists``: Sections 6/7's day-level classification of a month's
computed facts (Story 3.7, PRD FR-13).

Living in ``core/types/`` rather than ``core/payload/`` mirrors every other
``core/types/`` module: this is pure data, projected by
``core/payload/day_lists.py::project_day_lists()`` from an already-assembled
``Payload``, with no logic beyond the dataclass machinery itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.types.transits import Lunation, Station, TransitAspectEvent

__all__ = ["DayLists"]


@dataclass(frozen=True)
class DayLists:
    """The two client-visible day lists (*Giorni favorevoli*/*Giorni di
    attenzione*): dated harmonic Aspect Perfections plus favorable
    Lunations, and dated disharmonic Aspect Perfections plus retrograde
    Stations.

    Entries keep ``payload.consiglio_finale``'s own relative order within
    each source kind -- never re-sorted by date (Story 3.7 Boundaries).
    """

    giorni_favorevoli: tuple[TransitAspectEvent | Lunation, ...]
    giorni_di_attenzione: tuple[TransitAspectEvent | Station, ...]
