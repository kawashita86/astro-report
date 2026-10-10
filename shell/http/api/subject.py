"""The subject a chart request describes, and its conversion to UTC.

Stories 11.3-11.5 take the same subject, so parsing and the local-to-UTC step
live here once. Shape and range problems surface as pydantic validation errors,
which ``handle_validation_error`` already turns into ``invalid_request`` naming
the JSON path; the checks that need the whole subject (a birth time is required
when it is known, the birth year must lie inside the ephemeris) are
:func:`parse_subject`. Nothing here logs or stores a value it is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, StrictBool, field_validator

from core.ephemeris.positions import EPHEMERIS_FIRST_YEAR, EPHEMERIS_LAST_YEAR
from shell.http.api.errors import ApiError, ErrorCode
from shell.local_time import LocalInstant, local_to_utc

__all__ = [
    "ParsedSubject",
    "PlaceModel",
    "SubjectModel",
    "UnknownTimeInstants",
    "format_utc_offset",
    "format_utc_instant",
    "known_time_instant",
    "parse_subject",
    "quantize_coordinate",
    "unknown_time_instants",
]

#: Coordinates are reported to 4 decimal places (about 11 m), so a cache hit
#: (stored at full precision) and a fresh geocode give identical bytes.
_COORDINATE_QUANTUM = Decimal("0.0001")

_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}(:\d{2})?$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NOON = time(12, 0)
_MIDNIGHT = time(0, 0)


class PlaceModel(BaseModel):
    """A resolved birthplace, as ``/places/resolve`` returns it."""

    latitude: Decimal = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: Decimal = Field(ge=-180, le=180, allow_inf_nan=False)
    iana_zone: str = Field(min_length=1, max_length=64)
    display_name: str = Field(max_length=500)

    @field_validator("iana_zone")
    @classmethod
    def _zone_must_exist(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (KeyError, ValueError, OSError) as error:
            raise ValueError("not a known IANA zone") from error
        return value


class SubjectModel(BaseModel):
    """Whose chart: a label the caller keeps, the local birth date and time, and
    the place. ``birth_time`` is ignored when ``time_known`` is false."""

    label: str = Field(max_length=200)
    birth_date: str
    birth_time: str | None = None
    time_known: StrictBool
    place: PlaceModel

    @field_validator("birth_date")
    @classmethod
    def _date_must_be_iso(cls, value: str) -> str:
        if not _DATE_PATTERN.match(value):
            raise ValueError("expected YYYY-MM-DD")
        date.fromisoformat(value)
        return value

    @field_validator("birth_time")
    @classmethod
    def _time_must_be_iso(cls, value: str | None) -> str | None:
        if value is not None:
            if not _TIME_PATTERN.match(value):
                raise ValueError("expected HH:MM or HH:MM:SS")
            time.fromisoformat(value)
        return value


@dataclass(frozen=True)
class ParsedSubject:
    """A validated subject: the local civil date, the local time when known,
    and the place as exact decimals."""

    label: str
    birth_date: date
    birth_time: time | None
    time_known: bool
    latitude: Decimal
    longitude: Decimal
    iana_zone: str
    display_name: str


@dataclass(frozen=True)
class UnknownTimeInstants:
    """The three UTC instants an unknown-time chart is computed from, plus the
    offset in force at local noon."""

    noon: LocalInstant
    day_start: LocalInstant
    day_end: LocalInstant


def parse_subject(model: SubjectModel, field_prefix: str = "subject") -> ParsedSubject:
    """The subject with its cross-field rules applied.

    Raises:
        ApiError: ``invalid_request`` on ``<field_prefix>.birth_time`` when the
            time is known but absent; ``ephemeris_out_of_range`` on
            ``<field_prefix>.birth_date`` when the year is outside the vendored
            span. ``field_prefix`` is ``subject`` except where a request carries
            two subjects (``subject_a`` / ``subject_b``).
    """
    birth_date = date.fromisoformat(model.birth_date)
    if not EPHEMERIS_FIRST_YEAR <= birth_date.year <= EPHEMERIS_LAST_YEAR:
        raise ApiError(ErrorCode.EPHEMERIS_OUT_OF_RANGE, f"{field_prefix}.birth_date")
    birth_time: time | None = None
    if model.time_known:
        if model.birth_time is None:
            raise ApiError(ErrorCode.INVALID_REQUEST, f"{field_prefix}.birth_time")
        birth_time = time.fromisoformat(model.birth_time)
    return ParsedSubject(
        label=model.label,
        birth_date=birth_date,
        birth_time=birth_time,
        time_known=model.time_known,
        latitude=model.place.latitude,
        longitude=model.place.longitude,
        iana_zone=model.place.iana_zone,
        display_name=model.place.display_name,
    )


def known_time_instant(subject: ParsedSubject) -> LocalInstant:
    """The subject's birth instant in UTC, with the offset in force then.

    Raises:
        LocalTimeError: the birth time falls in a DST gap or fold.
    """
    assert subject.birth_time is not None
    return local_to_utc(datetime.combine(subject.birth_date, subject.birth_time), subject.iana_zone)


def unknown_time_instants(subject: ParsedSubject) -> UnknownTimeInstants:
    """Local noon (strict about a gap or fold) and the day's two boundaries
    (lenient: a boundary inside a gap is the transition instant itself)."""
    next_day = subject.birth_date + timedelta(days=1)
    return UnknownTimeInstants(
        noon=local_to_utc(datetime.combine(subject.birth_date, _NOON), subject.iana_zone),
        day_start=local_to_utc(
            datetime.combine(subject.birth_date, _MIDNIGHT), subject.iana_zone, strict=False
        ),
        day_end=local_to_utc(
            datetime.combine(next_day, _MIDNIGHT), subject.iana_zone, strict=False
        ),
    )


def quantize_coordinate(value: Decimal) -> str:
    """A latitude or longitude as a 4-place decimal string."""
    return str(value.quantize(_COORDINATE_QUANTUM))


def format_utc_instant(instant: datetime) -> str:
    """ISO-8601 with a ``Z`` suffix."""
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_utc_offset(offset: timedelta) -> str:
    """``+HH:MM``; seconds are appended only for the sub-minute local mean time
    offsets of dates before the 20th century, which cannot be written as ``HH:MM``
    without changing the instant."""
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    hours, remainder = divmod(abs(total), 3600)
    minutes, seconds = divmod(remainder, 60)
    text = f"{sign}{hours:02d}:{minutes:02d}"
    return f"{text}:{seconds:02d}" if seconds else text
