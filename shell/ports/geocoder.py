"""``Geocoder``: the port a birthplace-resolution adapter implements.

Resolution needs the birth date and time because the UTC offset it returns is
specific to that instant, not to the place alone (a 1975-06-15 Italian birth
is CEST; a 2026-01-15 one at the same coordinates is CET). ``birth_local_time``
is the wall-clock time as entered -- deliberately naive, since the zone it
belongs to is exactly what resolution determines; it is never itself a stored
or computed instant crossing a boundary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from core.types.place import PlaceCandidate, ResolvedPlace

__all__ = ["Geocoder"]


class Geocoder(Protocol):
    def resolve(
        self, place_text: str, birth_local_time: datetime
    ) -> ResolvedPlace | list[PlaceCandidate]:
        """Resolve free-text ``place_text`` to coordinates and the UTC offset
        in force at ``birth_local_time`` there.

        Returns a single :class:`ResolvedPlace` for an unambiguous match, or a
        non-empty list of :class:`PlaceCandidate` when more than one place
        matches -- never silently picking one.

        Raises:
            PlaceResolutionError: naming the step that failed -- geocoding,
                historical offset/zone lookup, or the cache read. Never
                returns ``None`` to mean failure.
        """
        ...
