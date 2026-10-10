"""Composite house cusps derived from the composite midheaven.

The alternative to taking the midpoint of each natal cusp pair: treat the
composite midheaven as a real meridian, turn it into a sidereal time (ARMC) and
let Swiss Ephemeris compute Placidus cusps for the mean of the two birth
latitudes. It is kept implemented and tested as the data-edit alternative to
``[composite] houses = "midpoint_cusps"``. It lives here, not in
``core/synastry/``, because it calls Swiss Ephemeris and so must bind the
verified ephemeris path to the calling thread first (a known pitfall).

The obliquity of the ecliptic is the true obliquity at the midpoint of the two
birth instants: a composite has no date of its own.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

import swisseph as swe

from core.ephemeris.identity import bind_verified_ephemeris_path_to_current_thread
from core.ephemeris.positions import _julian_day_ut, _to_normalized_decimal
from core.types.chart import HouseCusp

__all__ = ["derive_composite_houses"]

_HOUSE_SYSTEM = b"P"
_TWO = Decimal(2)


def derive_composite_houses(
    composite_midheaven: Decimal,
    latitude_a: Decimal,
    latitude_b: Decimal,
    birth_a_utc: datetime,
    birth_b_utc: datetime,
) -> tuple[HouseCusp, ...]:
    """Twelve Placidus cusps whose tenth is ``composite_midheaven``, at the
    arithmetic mean of the two latitudes."""
    bind_verified_ephemeris_path_to_current_thread()
    jd_mean = (_julian_day_ut(birth_a_utc) + _julian_day_ut(birth_b_utc)) / 2
    obliquity = swe.calc_ut(jd_mean, swe.ECL_NUT)[0][0]
    mc_radians = math.radians(float(composite_midheaven))
    # The midheaven is the ecliptic point on the meridian: its right ascension
    # follows from tan(RA) = tan(longitude) * cos(obliquity), quadrant-preserved.
    armc = math.degrees(
        math.atan2(math.sin(mc_radians) * math.cos(math.radians(obliquity)), math.cos(mc_radians))
    ) % 360.0
    mean_latitude = float((latitude_a + latitude_b) / _TWO)
    cusps, _ascmc = swe.houses_armc(armc, mean_latitude, obliquity, _HOUSE_SYSTEM)
    return tuple(
        HouseCusp(number=number, longitude=_to_normalized_decimal(cusps[number - 1]))
        for number in range(1, 13)
    )
