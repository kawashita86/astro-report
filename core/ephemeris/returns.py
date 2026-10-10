"""The instant the transiting Sun returns to a natal longitude.

A solar return is the Sun's first crossing of its own natal longitude at or
after a search start the caller chooses, so the caller (who knows the civil
calendar and the birthplace zone) decides which return is "nearest the
birthday" and this module only does the astronomy. It calls Swiss Ephemeris
directly, so it binds the verified ephemeris path to the calling thread first
(a known pitfall, missed twice). ``swe.solcross_ut`` takes a flags argument but
cannot report a Moshier fallback, so the crossing is confirmed afterwards
through the checked ``_calc_body`` path: the Sun there must sit on the target.

The target is the natal Sun straight from the ephemeris, not its 4-place
decimal, which could move the instant by seconds. The result is rounded to
whole seconds, the precision the API reports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import swisseph as swe

from core.ephemeris.identity import bind_verified_ephemeris_path_to_current_thread
from core.ephemeris.positions import (
    EPHEMERIS_LAST_YEAR,
    _angular_separation,
    _calc_body,
    _julian_day_ut,
)
from core.errors import EphemerisIntegrityError, EphemerisRangeError

__all__ = ["solar_return_instant"]

#: How far the Sun may sit from its target at the returned (second-rounded)
#: instant, in degrees. Half a second of rounding moves the Sun about 0.000006
#: degrees, so 0.0002 (under an arc-second) leaves ample room and still sits
#: far below the 4-place longitudes the API reports.
_VERIFY_TOLERANCE = Decimal("0.0002")

_SUN_FLAGS = swe.FLG_SWIEPH
_HALF_SECOND = timedelta(milliseconds=500)


def solar_return_instant(birth_instant_utc: datetime, search_start_utc: datetime) -> datetime:
    """The first UTC instant at or after ``search_start_utc`` when the Sun is on
    its ``birth_instant_utc`` longitude, to the whole second.

    Raises:
        ValueError: either instant is not timezone-aware UTC.
        EphemerisRangeError: the crossing falls beyond the last covered year
            (or Swiss Ephemeris cannot search that far).
        EphemerisIntegrityError: the crossing was not computed via the Swiss
            Ephemeris, or the Sun is not on the target there.
    """
    for instant in (birth_instant_utc, search_start_utc):
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise ValueError(f"instants must be timezone-aware UTC; got {instant!r}.")
    bind_verified_ephemeris_path_to_current_thread()

    target_xx, target_flags = swe.calc_ut(_julian_day_ut(birth_instant_utc), swe.SUN, _SUN_FLAGS)
    if target_flags < 0 or not target_flags & swe.FLG_SWIEPH:
        raise EphemerisIntegrityError("The natal Sun was not computed via the Swiss Ephemeris.")
    target = target_xx[0]
    try:
        jd_cross = swe.solcross_ut(target, _julian_day_ut(search_start_utc), _SUN_FLAGS)
    except swe.Error as error:
        raise EphemerisRangeError("The solar return lies beyond the ephemeris.") from error

    year, month, day, hour, minute, second = swe.jdut1_to_utc(jd_cross, swe.GREG_CAL)
    raw = datetime(year, month, day, hour, minute, tzinfo=UTC) + timedelta(seconds=second)
    instant = (raw + _HALF_SECOND).replace(microsecond=0)
    if instant.year > EPHEMERIS_LAST_YEAR:
        raise EphemerisRangeError("The solar return lies beyond the ephemeris.")

    sun_longitude, _speed = _calc_body(_julian_day_ut(instant), swe.SUN)
    if _angular_separation(sun_longitude, Decimal(str(target))) > _VERIFY_TOLERANCE:
        raise EphemerisIntegrityError("The solar return crossing did not land on the natal Sun.")
    return instant
