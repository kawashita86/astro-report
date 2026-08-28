"""The shared coarse-grid-plus-bisection scaffolding for the four
``core/transits`` month scans (epic-3-retro-item-19).

``core/transits/{aspects,stations,ingresses,lunations}.py`` each locate their
events the same way: sample a quantity on a fixed 6-hour grid across the
analyzed month, then bisect any grid step that brackets a sign change to
sub-second precision. The grid cadence, the fixed halving count, the
half-open-interval grid builder, the UTC-interval precondition check and the
bisection loop itself are generic -- identical (AST-normalized) across all
four modules, and independent of *which* quantity each module is finding a
zero of. They live here once; every module keeps its own ``offset_at`` /
``speed_fn`` / target logic.

**Why a 6-hour grid never hides an event.** The fastest configured
transiting body (Mercury, up to ~2.2 degrees/day) sweeps a full orb window
(``2 * config.orbs.transit``, at most 5 degrees) in a bit under two days --
well above ``_GRID_STEP``'s 6-hour cadence. The Moon, the fastest body any
scan here touches (``lunations.py``'s Delta-lambda), still moves under ~3.5
degrees in 6 hours against a target spacing of 180 degrees. So no orb entry,
orb exit, perfection, direction change or cusp crossing is ever hidden inside
a single grid step. ``_build_grid`` also appends ``end`` itself as a final
probe point, so an event in the last partial step before the month closes is
caught too (``end`` is excluded from the analyzed half-open interval; each
caller guards it back out).

**Why a fixed halving count.** ``_BISECTION_ITERATIONS`` is not a
tolerance-based loop, so runtime and precision are both bounded regardless of
the input interval's width. Over a full calendar month (~31 days) 40 halvings
narrow the bracket to well under a second.

Pure (AD-1): stdlib only (``datetime``, ``decimal``, ``collections.abc``) --
no I/O, clock, network or randomness.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

__all__ = [
    "_BISECTION_ITERATIONS",
    "_GRID_STEP",
    "_bisect",
    "_build_grid",
    "_require_utc_interval",
]

#: Sampling cadence for the coarse pre-scan -- see this module's docstring for
#: why it is fine-grained enough to never miss an event inside one step.
_GRID_STEP = timedelta(hours=6)

#: Fixed halving count for every bisection -- see this module's docstring.
_BISECTION_ITERATIONS = 40

_ZERO_OFFSET = timedelta(0)


def _require_utc_interval(start: datetime, end: datetime) -> None:
    for label, value in (("month_start_utc", start), ("month_end_utc", end)):
        if value.tzinfo is None or value.utcoffset() != _ZERO_OFFSET:
            raise ValueError(
                f"{label} must be timezone-aware UTC (utcoffset() == 0); got {value!r}."
            )
    if start >= end:
        raise ValueError(
            f"month_start_utc ({start!r}) must be strictly before month_end_utc ({end!r})."
        )


def _build_grid(start: datetime, end: datetime) -> list[datetime]:
    """Sample instants covering ``[start, end)`` at ``_GRID_STEP`` cadence,
    plus ``end`` itself as a final probe point -- used only to tell whether a
    scanned interval is still open as the month closes (``end`` is excluded
    from the analyzed interval itself)."""
    times = []
    instant = start
    while instant < end:
        times.append(instant)
        instant += _GRID_STEP
    times.append(end)
    return times


def _bisect(f: Callable[[datetime], Decimal], lo: datetime, hi: datetime) -> datetime:
    """Standard bisection for a continuous, sign-changing ``f`` on
    ``[lo, hi]``. The caller guarantees ``f(lo)`` and ``f(hi)`` either are
    zero or have opposite signs -- that guarantee is the sign-change checks in
    each caller before this is ever invoked."""
    f_lo = f(lo)
    if f_lo == 0:
        return lo
    f_hi = f(hi)
    if f_hi == 0:
        return hi

    for _ in range(_BISECTION_ITERATIONS):
        mid = lo + (hi - lo) / 2
        f_mid = f(mid)
        if f_mid == 0:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return lo + (hi - lo) / 2
