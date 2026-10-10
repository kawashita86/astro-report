"""``POST /api/v1/charts/solar-return``: the year's return chart, stored nowhere.

The return instant is the Sun's first crossing of the natal Sun's longitude at
or after local midnight two days before the birthday in the requested year, in
the birthplace zone (a 29 February birthday is 28 February in a non-leap year),
so the nearest return is always the one found. The chart is cast at that instant
for the stated location, the birthplace by default, and read against the natal
chart. A return needs the natal Sun to the arc-minute (a 0.5 degree error moves
the instant by half a day), so an unknown birth time is ``birth_time_required``.
The handler is synchronous, writes no row and logs nothing about the subject;
the body is canonical JSON so a repeat request gives identical bytes.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictInt

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.positions import EPHEMERIS_FIRST_YEAR, EPHEMERIS_LAST_YEAR
from core.ephemeris.returns import solar_return_instant
from core.errors import EphemerisRangeError, LocalTimeError
from core.payload.freeze import canonical_json_bytes
from core.returns.comparison import compare_to_natal
from core.types.computation import ComputationConfig
from shell.http.api.charts import jsonable, known_chart_json, subject_json
from shell.http.api.errors import ApiError, ErrorCode
from shell.http.api.meta import build_meta
from shell.http.api.router import router
from shell.http.api.subject import (
    PlaceModel,
    SubjectModel,
    format_utc_instant,
    known_time_instant,
    parse_subject,
    quantize_coordinate,
)
from shell.local_time import local_to_utc

__all__ = ["SolarReturnRequest", "solar_return"]

#: The search starts this many days before the birthday.
_SEARCH_LEAD = timedelta(days=2)


class SolarReturnRequest(BaseModel):
    subject: SubjectModel
    year: StrictInt = Field(ge=1, le=9999)
    location: PlaceModel | None = None


def _birthday_in(year: int, birth_date: date) -> date:
    """The birthday in ``year``; 28 February for a 29 February birth in a common year."""
    if birth_date.month == 2 and birth_date.day == 29 and not calendar.isleap(year):
        return date(year, 2, 28)
    return birth_date.replace(year=year)


@router.post("/charts/solar-return")
def solar_return(body: SolarReturnRequest, request: Request) -> Response:
    config: ComputationConfig = request.app.state.computation_config
    meta = build_meta(config, request.app.state.ephemeris_identity)
    subject = parse_subject(body.subject)
    if not subject.time_known:
        raise ApiError(ErrorCode.BIRTH_TIME_REQUIRED, "subject.time_known")
    if not EPHEMERIS_FIRST_YEAR <= body.year <= EPHEMERIS_LAST_YEAR:
        raise ApiError(ErrorCode.EPHEMERIS_OUT_OF_RANGE, "year")
    if body.year < subject.birth_date.year:
        raise ApiError(ErrorCode.INVALID_REQUEST, "year")

    try:
        birth = known_time_instant(subject)
    except LocalTimeError as error:
        raise ApiError(ErrorCode.INVALID_REQUEST, "subject.birth_time") from error
    natal = compute_natal_chart(birth.utc, subject.latitude, subject.longitude, config)

    search_day = _birthday_in(body.year, subject.birth_date) - _SEARCH_LEAD
    search_start = local_to_utc(
        datetime.combine(search_day, time(0, 0)), subject.iana_zone, strict=False
    )
    try:
        return_utc = solar_return_instant(birth.utc, search_start.utc)
    except EphemerisRangeError as error:
        raise ApiError(ErrorCode.EPHEMERIS_OUT_OF_RANGE, "year") from error

    place = body.location
    latitude = place.latitude if place else subject.latitude
    longitude = place.longitude if place else subject.longitude
    return_chart = compute_natal_chart(return_utc, latitude, longitude, config)

    location: dict[str, Any] = {
        "latitude": quantize_coordinate(latitude),
        "longitude": quantize_coordinate(longitude),
        "iana_zone": place.iana_zone if place else subject.iana_zone,
        "display_name": place.display_name if place else subject.display_name,
    }
    payload = {
        "meta": meta,
        "subject": subject_json(
            subject,
            utc_offset=birth.offset,
            chart_instant=format_utc_instant(return_utc),
            birth_instant=format_utc_instant(birth.utc),
        ),
        "return_instant_utc": format_utc_instant(return_utc),
        "location": location,
        "chart": known_chart_json(return_chart, config),
        "comparison": jsonable(compare_to_natal(return_chart, natal, config.orbs.natal)),
    }
    return Response(canonical_json_bytes(payload), media_type="application/json")
