"""Shared low-level Swiss Ephemeris helpers (Story 3.1).

Extracted from ``core/ephemeris/chart.py``: natal computation and the
transit-to-natal Aspect scan (``core/transits/aspects.py``) both need
identical Julian-day conversion, body-position lookup, decimal
normalization and angular-separation math -- duplicating it in two places
would risk silent divergence between the two engines. Pure (AD-1): no I/O,
clock, network or randomness, only ``swisseph`` and what is passed in.

``core/ephemeris/chart.py`` re-exports nothing from here beyond importing
what it needs; its own public behavior (``compute_natal_chart()``) is
unchanged by this extraction.

``_calc_body`` assumes ``core.ephemeris.identity.verify_ephemeris_identity()``
has run *in this process*, and re-binds the verified path to the calling
thread (``bind_verified_ephemeris_path_to_current_thread()``) before every
``swe.calc_ut`` -- pyswisseph's ephemeris path is thread-local in this build,
so a computation dispatched to a worker thread would otherwise fall back to
Moshier.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import swisseph as swe

from core.ephemeris.identity import bind_verified_ephemeris_path_to_current_thread
from core.errors import EphemerisIntegrityError

#: Only the genuinely public surface: the three shared constants. The
#: underscore-prefixed helpers below (``_angular_separation``, ``_calc_body``,
#: ``_julian_day_ut``, ``_normalize_decimal``, ``_to_normalized_decimal``)
#: are private by convention, exactly like every other helper in
#: ``core/ephemeris/chart.py`` -- ``core/ephemeris/chart.py`` and
#: ``core/transits/aspects.py`` still import them explicitly by name (as
#: this module's whole reason to exist, see the module docstring), but
#: declaring them in ``__all__`` would claim them as this module's public
#: API, which contradicts it existing purely as an internal shared module.
__all__ = [
    "FULL_CIRCLE",
    "HALF_CIRCLE",
    "QUANTUM",
]

#: Degrees in a full circle / half circle, and the quantization step every
#: longitude/cusp/orb is rounded to (matching the precision Astro.com's
#: values were transcribed at). Shared by natal and transit computation.
FULL_CIRCLE = Decimal(360)
HALF_CIRCLE = Decimal(180)
QUANTUM = Decimal("0.0001")

#: Swiss Ephemeris, with daily motion so retrograde/applying can be derived.
#: The returned flags are checked against ``FLG_SWIEPH`` on every call -- a
#: Moshier fallback is never silently accepted (mirrors the same rule
#: already enforced at boot by ``core/ephemeris/identity.py``).
_CALC_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED


def _julian_day_ut(instant: datetime) -> float:
    seconds = instant.second + instant.microsecond / 1_000_000
    _jd_et, jd_ut = swe.utc_to_jd(
        instant.year,
        instant.month,
        instant.day,
        instant.hour,
        instant.minute,
        seconds,
        swe.GREG_CAL,
    )
    return jd_ut


def _calc_body(jd_ut: float, body_id: int) -> tuple[Decimal, Decimal]:
    # pyswisseph's ephemeris path is thread-local in this build; re-pin the
    # already-verified path on whatever thread is computing before the first
    # calc_ut on it (idempotent and free thereafter). Without this, a scan
    # running on a worker thread gets a Moshier fallback and the check below
    # rejects every body.
    bind_verified_ephemeris_path_to_current_thread()
    xx, retflag = swe.calc_ut(jd_ut, body_id, _CALC_FLAGS)
    # A negative retflag is pyswisseph's own error signal. Checked before the
    # bitwise SEFLG_SWIEPH test below: in two's-complement, a negative int
    # has high bits set, so `retflag & swe.FLG_SWIEPH` can be truthy even on
    # error and would otherwise let a failed computation through unnoticed.
    if retflag < 0 or not retflag & swe.FLG_SWIEPH:
        raise EphemerisIntegrityError(
            f"Refusing to compute: body {body_id} was not computed via the Swiss "
            f"Ephemeris (calc_ut returned flags {retflag}); "
            "a Moshier fallback is never acceptable."
        )
    longitude = _to_normalized_decimal(xx[0])
    speed = Decimal(str(xx[3]))
    return longitude, speed


def _to_normalized_decimal(value: float) -> Decimal:
    """``Decimal(str(value))`` -- never ``Decimal(value)`` on the raw float,
    which would compound binary-float imprecision rather than merely
    preserving it (mirrors ``shell/adapters/nominatim/geocoder.py``'s
    ``_to_decimal()``) -- then normalized into ``[0, 360)`` and quantized to
    4 decimal places.
    """
    return _normalize_decimal(Decimal(str(value)))


def _normalize_decimal(value: Decimal) -> Decimal:
    normalized = value % FULL_CIRCLE
    if normalized < 0:
        normalized += FULL_CIRCLE
    quantized = normalized.quantize(QUANTUM)
    # Quantizing can round a value just under 360 up to exactly 360.0000
    # (e.g. 359.99996), which would violate the [0, 360) invariant every
    # caller relies on (house lookup, sign index). 360 degrees is 0 degrees.
    if quantized >= FULL_CIRCLE:
        quantized -= FULL_CIRCLE
    return quantized


def _angular_separation(lon1: Decimal, lon2: Decimal) -> Decimal:
    """The shortest angular distance between two longitudes, in ``[0, 180]``."""
    diff = abs(lon1 - lon2) % FULL_CIRCLE
    if diff > HALF_CIRCLE:
        diff = FULL_CIRCLE - diff
    return diff
