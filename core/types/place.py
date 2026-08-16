"""Pure result shapes for birthplace resolution (FR-2).

Living in ``core/types/`` rather than ``shell/`` lets a future ``core/``
function type-hint on ``ResolvedPlace`` without importing anything from
``shell/`` (AD-1), mirroring ``core/types/computation.py``. Resolution itself
-- geocoding, timezone lookup, the Postgres cache -- is all I/O and stays in
``shell/adapters/``; these types are pure data with no logic beyond the
dataclass machinery itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

__all__ = ["PlaceCandidate", "ResolvedPlace"]


@dataclass(frozen=True)
class PlaceCandidate:
    """One ambiguous match, offered for an explicit human choice (FR-2).

    Carries only what distinguishes candidates from each other -- resolving a
    zone and historical offset for every candidate would query the geocoder
    for matches that may never be chosen.
    """

    display_name: str
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class ResolvedPlace:
    """A birthplace resolved to coordinates and the UTC offset in force at a
    specific birth instant -- never today's offset (FR-2).

    ``utc_offset`` is specific to the birth instant that produced it, not a
    property of the place alone: the same coordinates yield a different
    offset for a different date under that zone's historical DST rules.
    """

    latitude: Decimal
    longitude: Decimal
    iana_zone: str
    utc_offset: timedelta
