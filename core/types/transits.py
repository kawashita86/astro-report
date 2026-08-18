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

__all__ = ["TransitAspectEvent"]


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
