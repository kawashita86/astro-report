"""Compute a Natal Chart as a pure function (Story 2.2).

Calls ``pyswisseph`` directly -- no Kerykeion -- for planetary positions,
Placidus cusps and natal Aspects. Purity (AD-1): no I/O, clock, network or
randomness; imports only ``swisseph``, ``core/ephemeris/positions.py``'s
shared low-level helpers (Story 3.1), ``core/ephemeris/identity.py``'s
per-thread path bind, and ``core/types/``. This module assumes
``core.ephemeris.identity.verify_ephemeris_identity()`` has already run
(normally at shell import time, see ``shell/http/app.py``) and does not
re-verify the vendored files; it does re-bind the verified path to the
calling thread (``bind_verified_ephemeris_path_to_current_thread()``), since
pyswisseph's ephemeris path is thread-local in this build and ``swe.houses()``
needs it too.

**Ascendant/midheaven are cusps 1 and 10, not separate lookups.** For
Placidus, ``swe.houses()``'s ``ascmc`` output and its ``cusps[0]``/``cusps[9]``
are definitionally the same values; the fixtures never record them as
separate fields, only as ``houses[0]``/``houses[9]``.

**Orb is unsigned with a separate ``applying`` flag.** ``orb`` stays an
unsigned magnitude matching conformance fixture values; ``applying`` carries
the applying/separating sign as its own field.

**Chiron is out of scope** (see the story's Design Notes) -- the vendored
ephemeris ships only ``sepl_18.se1``/``semo_18.se1``, no asteroid file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import swisseph as swe

from core.ephemeris.identity import bind_verified_ephemeris_path_to_current_thread
from core.ephemeris.positions import (
    FULL_CIRCLE,
    HALF_CIRCLE,
    QUANTUM,
    _angular_separation,
    _calc_body,
    _julian_day_ut,
    _normalize_decimal,
    _to_normalized_decimal,
)
from core.types.chart import Aspect, HouseCusp, NatalChart, PlanetPosition
from core.types.computation import ComputationConfig

__all__ = ["compute_natal_chart"]

#: Fixed body order this module iterates in throughout: the ``planets``
#: field's order, and -- alongside the True Node but never the South Node --
#: the pair-generation order Aspect detection walks. Matches the order
#: Astro.com reference charts list bodies in (conformance fixtures, Story
#: 1.7), which is itself just ``swe``'s own body-constant order.
_PLANET_BODIES: tuple[tuple[str, int], ...] = (
    ("sun", swe.SUN),
    ("moon", swe.MOON),
    ("mercury", swe.MERCURY),
    ("venus", swe.VENUS),
    ("mars", swe.MARS),
    ("jupiter", swe.JUPITER),
    ("saturn", swe.SATURN),
    ("uranus", swe.URANUS),
    ("neptune", swe.NEPTUNE),
    ("pluto", swe.PLUTO),
    ("true_node", swe.TRUE_NODE),
)

_ZODIAC_SIGNS: tuple[str, ...] = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)

#: The five natal Aspects this story detects, and the exact angle each one
#: is measured against. Order matters only in that it is checked in this
#: order; given the configured orb's permitted range (6.0-8.0 degrees,
#: `shell/computation.py`) is well under half the 30-degree minimum gap
#: between these angles, a pair can never match more than one.
_ASPECTS: tuple[tuple[str, Decimal], ...] = (
    ("conjunction", Decimal(0)),
    ("sextile", Decimal(60)),
    ("square", Decimal(90)),
    ("trine", Decimal(120)),
    ("opposition", Decimal(180)),
)

_DEGREES_PER_SIGN = Decimal(30)
_ZERO_OFFSET = timedelta(0)

_HOUSE_SYSTEM = b"P"


def compute_natal_chart(
    birth_instant_utc: datetime,
    latitude: Decimal,
    longitude: Decimal,
    config: ComputationConfig,
) -> NatalChart:
    """Compute a full Natal Chart for a UTC birth instant and place.

    Pure: consults no clock, no default timezone, no network or database.
    Ten planets (Sun-Pluto) plus the True and South Lunar Nodes, the
    ascendant, midheaven and all twelve Placidus cusps, and natal Aspects
    within ``config.orbs.natal``. Every longitude/cusp/orb is a ``Decimal``
    quantized to 4 decimal places, normalized to ``[0, 360)``.

    Raises:
        ValueError: ``birth_instant_utc`` is not timezone-aware UTC.
        EphemerisIntegrityError: a planet/node position from ``swe.calc_ut()``
            was not confirmed as coming from the Swiss Ephemeris (the return
            flags did not carry ``SEFLG_SWIEPH``) -- a silent Moshier
            fallback is never accepted. ``swe.houses()`` has no equivalent
            per-call flag to check; house/cusp accuracy instead depends on
            the ephemeris path pinned by ``verify_ephemeris_identity()`` in
            this process and re-bound to this thread at the top of this
            function.
    """
    _require_utc(birth_instant_utc)

    # swe.houses() below reads the thread-local ephemeris path too, and unlike
    # _calc_body it cannot report a Moshier fallback -- bind the verified path
    # to this thread explicitly, not just via the first _calc_body call.
    bind_verified_ephemeris_path_to_current_thread()

    jd_ut = _julian_day_ut(birth_instant_utc)

    positions = {name: _calc_body(jd_ut, body_id) for name, body_id in _PLANET_BODIES}

    cusps_raw, _ascmc_raw = swe.houses(jd_ut, float(latitude), float(longitude), _HOUSE_SYSTEM)
    cusp_longitudes = [_to_normalized_decimal(value) for value in cusps_raw]
    houses = tuple(
        HouseCusp(number=number, longitude=cusp_longitudes[number - 1]) for number in range(1, 13)
    )
    ascendant = cusp_longitudes[0]
    midheaven = cusp_longitudes[9]

    planets = [
        _planet_position(name, positions[name][0], positions[name][1], cusp_longitudes)
        for name, _body_id in _PLANET_BODIES
    ]
    true_node_longitude, true_node_speed = positions["true_node"]
    south_node_longitude = _normalize_decimal(true_node_longitude + HALF_CIRCLE)
    planets.append(
        _planet_position("south_node", south_node_longitude, true_node_speed, cusp_longitudes)
    )

    aspect_bodies = [(name, positions[name][0], positions[name][1]) for name, _ in _PLANET_BODIES]
    aspects = _detect_aspects(aspect_bodies, config.orbs.natal)

    return NatalChart(
        ascendant=ascendant,
        midheaven=midheaven,
        planets=tuple(planets),
        houses=houses,
        aspects=aspects,
    )


def _require_utc(instant: datetime) -> None:
    if instant.tzinfo is None or instant.utcoffset() != _ZERO_OFFSET:
        raise ValueError(
            "birth_instant_utc must be timezone-aware UTC (utcoffset() == 0); "
            f"got {instant!r}."
        )


def _sign_and_degree(longitude: Decimal) -> tuple[str, Decimal]:
    sign_index = int(longitude // _DEGREES_PER_SIGN)
    degree = (longitude - sign_index * _DEGREES_PER_SIGN).quantize(QUANTUM)
    return _ZODIAC_SIGNS[sign_index], degree


def _house_for_longitude(longitude: Decimal, cusp_longitudes: list[Decimal]) -> int:
    """Which of the twelve (generally unevenly spaced, Placidus) house spans
    ``longitude`` falls within. Exactly one house's span crosses 0 degrees;
    every other span is a simple ascending range."""
    for number in range(1, 13):
        start = cusp_longitudes[number - 1]
        end = cusp_longitudes[number % 12]
        if start <= end:
            if start <= longitude < end:
                return number
        elif longitude >= start or longitude < end:
            return number
    raise AssertionError(f"longitude {longitude} fell within no house span in {cusp_longitudes}")


def _planet_position(
    name: str,
    longitude: Decimal,
    speed: Decimal,
    cusp_longitudes: list[Decimal],
) -> PlanetPosition:
    sign, degree = _sign_and_degree(longitude)
    house = _house_for_longitude(longitude, cusp_longitudes)
    return PlanetPosition(
        name=name,
        longitude=longitude,
        sign=sign,
        degree=degree,
        house=house,
        retrograde=speed < 0,
    )


def _match_aspect(lon1: Decimal, lon2: Decimal, orb_limit: Decimal) -> tuple[str, Decimal] | None:
    separation = _angular_separation(lon1, lon2)
    for aspect_name, target_degrees in _ASPECTS:
        orb = abs(separation - target_degrees)
        if orb <= orb_limit:
            return aspect_name, orb.quantize(QUANTUM)
    return None


def _is_applying(
    lon1: Decimal, lon2: Decimal, speed1: Decimal, speed2: Decimal, target: Decimal
) -> bool:
    """True when the pair's orb (distance from ``target``) is closing, not
    widening, given each body's daily motion (signed for retrograde).

    ``diff`` is the signed angular difference in ``(-180, 180]``; its rate of
    change is ``sign(diff) * (speed1 - speed2)``. The orb is closing when
    that rate moves the absolute angle toward ``target`` -- decreasing while
    above it, increasing while below it. An exact hit (orb already zero) is
    treated as applying by convention; it is never exercised by a
    conformance fixture either way.
    """
    diff = (lon1 - lon2) % FULL_CIRCLE
    if diff > HALF_CIRCLE:
        diff -= FULL_CIRCLE
    angle = abs(diff)
    relative_speed = speed1 - speed2
    rate_of_change = relative_speed if diff >= 0 else -relative_speed
    if angle > target:
        return rate_of_change < 0
    if angle < target:
        return rate_of_change > 0
    return True


def _detect_aspects(
    bodies: list[tuple[str, Decimal, Decimal]], orb_limit: Decimal
) -> tuple[Aspect, ...]:
    """Every natal Aspect within ``orb_limit`` (``ComputationConfig.orbs.natal``,
    never a hardcoded value) among ``bodies``, walked as all ``i < j`` pairs
    in ``bodies``'s own order -- this is what fixes the emitted order to
    match the conformance fixtures.
    """
    aspects: list[Aspect] = []
    for i in range(len(bodies)):
        name1, lon1, speed1 = bodies[i]
        for j in range(i + 1, len(bodies)):
            name2, lon2, speed2 = bodies[j]
            match = _match_aspect(lon1, lon2, orb_limit)
            if match is None:
                continue
            aspect_name, orb = match
            target = dict(_ASPECTS)[aspect_name]
            applying = _is_applying(lon1, lon2, speed1, speed2, target)
            aspects.append(
                Aspect(body1=name1, body2=name2, aspect=aspect_name, orb=orb, applying=applying)
            )
    return tuple(aspects)
