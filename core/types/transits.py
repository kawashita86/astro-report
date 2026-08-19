"""Pure result shape for a transit-to-natal Aspect Event (Story 3.1).

Living in ``core/types/`` rather than ``core/transits/`` for the same reason
``core/types/chart.py`` sits apart from ``core/ephemeris/chart.py`` (AD-1): a
future ``core/`` function (Report Payload assembly) can type-hint on
:class:`TransitAspectEvent` without importing anything from
``core/transits/``. Pure data: no I/O, no computation, no logic beyond the
dataclass machinery itself -- the computation that produces these lives in
``core/transits/aspects.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

__all__ = ["Station", "StandingRetrograde", "TransitAspectEvent"]


@dataclass(frozen=True)
class TransitAspectEvent:
    """One transit-to-natal Aspect detected within an analyzed month
    (Story 3.1): a transiting body forming one of the five major Aspects
    (conjunction, sextile, square, trine, opposition) with a fixed natal
    point, within ``ComputationConfig.orbs.transit``.

    ``perfected_at`` is the bisected UTC instant separation exactly equals
    the aspect's target angle, or ``None`` when the pair stayed in orb
    without ever exactly crossing it (``never_perfected=True``) --
    ``perfected_at`` and ``never_perfected`` are always consistent
    (``never_perfected`` is exactly ``perfected_at is None``).

    ``orb_entry_at`` is always set: clamped to the analyzed month's start
    when the pair was already in orb at that boundary (its true entry lies
    outside this pure function's one-month view). ``orb_exit_at`` is
    ``None`` when the pair is still in orb as the analyzed month ends (an
    unresolved, still-open interval) -- the only case ``None`` is used.

    A body re-entering orb after having separated (e.g. a retrograde loop)
    produces a second, distinct event -- events are never merged or
    deduplicated across separate in-orb intervals within the month.
    """

    transiting_body: str
    natal_point: str
    aspect: str
    perfected_at: datetime | None
    never_perfected: bool
    orb_entry_at: datetime
    orb_exit_at: datetime | None


@dataclass(frozen=True)
class Station:
    """One retrograde/direct turn located within an analyzed month (Story
    3.2): the instant a transiting body's longitudinal velocity (dλ/dt, the
    same ``speed`` value ``core/ephemeris/positions.py``'s ``_calc_body``
    already returns) changes sign, bisected to sub-second precision by the
    same coarse-grid-plus-bisection method ``core/transits/aspects.py`` uses
    for Aspect perfection instants.

    ``direction`` is the motion the body *entered* at ``station_at`` --
    always exactly one of ``"retrograde"`` (dλ/dt crossed from positive to
    negative) or ``"direct"`` (dλ/dt crossed from negative to positive).
    ``longitude`` is the body's zodiacal degree at that same instant.
    """

    body: str
    direction: str
    station_at: datetime
    longitude: Decimal


@dataclass(frozen=True)
class StandingRetrograde:
    """A body retrograde across an analyzed month's entire span, with no
    Station (direction change) inside it (Story 3.2) -- recorded rather than
    silently omitted, since a whole month of retrograde motion with no turn
    to report is still a real fact about the month. A body *direct* the
    whole month is never recorded at all: there is nothing to report.

    ``retrograde_start_utc``/``retrograde_end_utc`` are the analyzed month's
    own boundaries, clamped exactly like ``TransitAspectEvent.orb_entry_at``
    clamps to a boundary already in view -- the body's true retrograde span
    may extend beyond this one-month window in either direction, but that is
    outside what this pure function's single-month view can see.
    """

    body: str
    retrograde_start_utc: datetime
    retrograde_end_utc: datetime
