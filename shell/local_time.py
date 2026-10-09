"""Local civil time to a UTC instant, using the offset in force at that instant.

One conversion with two consumers: the Nominatim geocoder (which resolves the
operator-UI birthplace flow) and the chart data API (which converts a subject's
birth time and the day boundaries of an unknown-time chart). Keeping it here
means a DST gap or fold is judged by one rule everywhere instead of two copies
drifting apart. It lives in ``shell/`` because it reads the system tz database;
``core/`` receives only the finished UTC instants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from core.errors import LocalTimeError

__all__ = ["LocalInstant", "local_to_utc"]


@dataclass(frozen=True)
class LocalInstant:
    """A local wall-clock time resolved to UTC, with the offset that was used."""

    utc: datetime
    offset: timedelta


def local_to_utc(local: datetime, iana_zone: str, *, strict: bool = True) -> LocalInstant:
    """Resolve naive ``local`` in ``iana_zone`` to a UTC instant.

    With ``strict`` (the default) a time skipped by a spring-forward gap or
    repeated by a fall-back fold raises :class:`LocalTimeError`. With
    ``strict=False`` the first reading is used (PEP 495 ``fold=0``): the
    right choice for a day boundary, where a gap yields the transition instant
    itself and a fold yields the first occurrence.

    Raises:
        ValueError: ``local`` is timezone-aware.
        zoneinfo.ZoneInfoNotFoundError: ``iana_zone`` is not a known zone.
        LocalTimeError: strict, and ``local`` falls in a gap or a fold.
    """
    if local.tzinfo is not None:
        raise ValueError("local must be naive: it is the wall-clock time as entered.")
    zone = ZoneInfo(iana_zone)

    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    offset_first, offset_second = first.utcoffset(), second.utcoffset()
    assert offset_first is not None and offset_second is not None

    if strict and offset_first != offset_second:
        # Per PEP 495 a fold-0 reading round-trips only when the time really
        # occurred (a repeated hour); a skipped time comes back shifted.
        round_trip = first.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        raise LocalTimeError("fold" if round_trip == local else "gap", local, iana_zone)
    return LocalInstant(utc=(local - offset_first).replace(tzinfo=UTC), offset=offset_first)
