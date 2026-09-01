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
    ``display_name`` is the geocoder's own name for the match -- the same
    field an ambiguous match already returns as ``PlaceCandidate.display_name``
    -- carried through so a resolved place can be shown back to Francesco
    later without a second lookup (AD-16, amended 2026-09-01). Defaults to
    ``None``, both for a ``PLACE_CACHE`` hit against a row cached before this
    field existed and for the many fixtures across this codebase that build a
    ``ResolvedPlace`` to exercise something else entirely; every freshly
    geocoded or candidate-resolved place in production always supplies one
    explicitly.
    """

    latitude: Decimal
    longitude: Decimal
    iana_zone: str
    utc_offset: timedelta
    display_name: str | None = None
