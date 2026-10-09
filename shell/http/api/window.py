"""The transit window a request names, and its conversion to one UTC interval.

A window is two local dates in the subject place's zone, half-open: the first
local midnight to the second. Everything that can be wrong with it is decided
here, before any ephemeris work, so an over-long window costs nothing. The
13-month ceiling is a code constant rather than configuration: it bounds the
work one request can ask for, which is a property of the API and not a tuning
value.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, time

from pydantic import BaseModel, field_validator

from core.ephemeris.positions import EPHEMERIS_FIRST_YEAR, EPHEMERIS_LAST_YEAR
from shell.http.api.errors import ApiError, ErrorCode
from shell.local_time import local_to_utc

__all__ = ["MAX_WINDOW_MONTHS", "ParsedWindow", "WindowModel", "parse_window"]

#: The longest window one request may name, in calendar months.
MAX_WINDOW_MONTHS = 13

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIDNIGHT = time(0, 0)


class WindowModel(BaseModel):
    """``{start_date, end_date}``: local ISO dates, ``end_date`` exclusive."""

    start_date: str
    end_date: str

    @field_validator("start_date", "end_date")
    @classmethod
    def _date_must_be_iso(cls, value: str) -> str:
        if not _DATE_PATTERN.match(value):
            raise ValueError("expected YYYY-MM-DD")
        date.fromisoformat(value)
        return value


@dataclass(frozen=True)
class ParsedWindow:
    """The window as one half-open UTC interval."""

    start_utc: datetime
    end_utc: datetime


def _add_months(day: date, months: int) -> date:
    """``day`` plus whole calendar months, clamped to the target month's last day."""
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def parse_window(model: WindowModel, iana_zone: str) -> ParsedWindow:
    """Validate the window and convert it to UTC in ``iana_zone``.

    Raises:
        ApiError: ``invalid_request`` when ``end_date`` is not after
            ``start_date``; ``window_too_long`` beyond 13 calendar months;
            ``ephemeris_out_of_range`` when a date is outside the vendored span.
    """
    start = date.fromisoformat(model.start_date)
    end = date.fromisoformat(model.end_date)
    for field, value in (("window.start_date", start), ("window.end_date", end)):
        if not EPHEMERIS_FIRST_YEAR <= value.year <= EPHEMERIS_LAST_YEAR:
            raise ApiError(ErrorCode.EPHEMERIS_OUT_OF_RANGE, field)
    if end <= start:
        raise ApiError(ErrorCode.INVALID_REQUEST, "window.end_date")
    if end > _add_months(start, MAX_WINDOW_MONTHS):
        raise ApiError(ErrorCode.WINDOW_TOO_LONG, "window.end_date")
    start_utc = local_to_utc(datetime.combine(start, _MIDNIGHT), iana_zone, strict=False).utc
    end_utc = local_to_utc(datetime.combine(end, _MIDNIGHT), iana_zone, strict=False).utc
    return ParsedWindow(start_utc=start_utc, end_utc=end_utc)
