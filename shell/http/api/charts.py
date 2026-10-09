"""``POST /api/v1/charts/natal``: a natal chart computed on request, stored nowhere.

A known birth time returns exactly what the operator UI's Client flow computes
(``compute_natal_chart`` plus the house rulers), converted from local civil time
with the offset in force at that instant. An unknown birth time returns the noon
chart from ``compute_time_unknown_chart``: no angles or houses, every body a
range across the local day. The handler is synchronous, writes no row and logs
nothing about the subject; the body is canonical JSON so a repeat request gives
identical bytes.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

from core.domains.rulers import resolve_house_rulers
from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.time_unknown import compute_time_unknown_chart
from core.payload.freeze import canonical_json_bytes
from core.types.chart import NatalChart, TimeUnknownChart, TimeUnknownPlanet
from core.types.computation import ComputationConfig
from shell.http.api.meta import build_meta
from shell.http.api.router import router
from shell.http.api.subject import (
    ParsedSubject,
    SubjectModel,
    format_utc_instant,
    format_utc_offset,
    known_time_instant,
    parse_subject,
    quantize_coordinate,
    unknown_time_instants,
)

__all__ = ["NatalRequest", "jsonable", "natal_chart", "subject_json"]


class NatalRequest(BaseModel):
    subject: SubjectModel


def jsonable(value: Any) -> Any:
    """Decimals as strings, instants as ISO-8601 ``Z`` and dataclasses as dicts, recursively."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return format_utc_instant(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    return value


def subject_json(
    subject: ParsedSubject, *, utc_offset: timedelta, chart_instant: str, birth_instant: str | None
) -> dict[str, Any]:
    return {
        "label": subject.label,
        "birth_date": subject.birth_date.isoformat(),
        "birth_time": subject.birth_time.isoformat(timespec="auto") if subject.birth_time else None,
        "time_known": subject.time_known,
        "birth_instant_utc": birth_instant,
        "chart_instant_utc": chart_instant,
        "utc_offset": format_utc_offset(utc_offset),
        "place": {
            "latitude": quantize_coordinate(subject.latitude),
            "longitude": quantize_coordinate(subject.longitude),
            "iana_zone": subject.iana_zone,
            "display_name": subject.display_name,
        },
    }


def _known_chart_json(chart: NatalChart, config: ComputationConfig) -> dict[str, Any]:
    return {
        "ascendant": str(chart.ascendant),
        "midheaven": str(chart.midheaven),
        "planets": jsonable(chart.planets),
        "houses": jsonable(chart.houses),
        "house_rulers": jsonable(resolve_house_rulers(chart, config)),
        "aspects": jsonable(chart.aspects),
    }


def _unknown_planet_json(planet: TimeUnknownPlanet) -> dict[str, Any]:
    return {
        "name": planet.name,
        "longitude": str(planet.longitude),
        "sign": planet.sign,
        "degree": str(planet.degree),
        "house": None,
        "retrograde": planet.retrograde,
        "range": {"from": str(planet.range_from), "to": str(planet.range_to)},
        "sign_uncertain": planet.sign_uncertain,
    }


def _unknown_chart_json(chart: TimeUnknownChart) -> dict[str, Any]:
    return {
        "ascendant": None,
        "midheaven": None,
        "planets": [_unknown_planet_json(planet) for planet in chart.planets],
        "houses": None,
        "house_rulers": None,
        "aspects": jsonable(chart.aspects),
    }


@router.post("/charts/natal")
def natal_chart(body: NatalRequest, request: Request) -> Response:
    config: ComputationConfig = request.app.state.computation_config
    meta = build_meta(config, request.app.state.ephemeris_identity)
    subject = parse_subject(body.subject)

    if subject.time_known:
        birth = known_time_instant(subject)
        chart = compute_natal_chart(birth.utc, subject.latitude, subject.longitude, config)
        payload = {
            "meta": meta,
            "subject": subject_json(
                subject,
                utc_offset=birth.offset,
                chart_instant=format_utc_instant(birth.utc),
                birth_instant=format_utc_instant(birth.utc),
            ),
            "chart": _known_chart_json(chart, config),
        }
    else:
        instants = unknown_time_instants(subject)
        unknown = compute_time_unknown_chart(
            instants.noon.utc, instants.day_start.utc, instants.day_end.utc, config
        )
        payload = {
            "meta": meta,
            "subject": subject_json(
                subject,
                utc_offset=instants.noon.offset,
                chart_instant=format_utc_instant(instants.noon.utc),
                birth_instant=None,
            ),
            "chart": _unknown_chart_json(unknown),
        }
    return Response(canonical_json_bytes(payload), media_type="application/json")
