"""``POST /api/v1/charts/transits``: every transit event over a window, stored nowhere.

The four month scans in ``core/transits`` already take any half-open UTC
interval, so a window of up to 13 months is the same code over a longer span;
this module only resolves the subject and the window, picks the natal targets
and serialises what the scans return. A known birth time scans against the full
natal chart. An unknown one scans against the noon chart's planets and nodes --
no angles, no natal Moon, and no house-dependent output, which is ``null``
rather than absent so the response shape is stable. The handler is synchronous,
writes no row and logs nothing about the subject.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.time_unknown import compute_time_unknown_chart
from core.payload.freeze import canonical_json_bytes
from core.transits.aspects import find_transit_aspects, find_transit_aspects_to_targets
from core.transits.ingresses import find_ingresses
from core.transits.lunations import find_lunation_moments, find_lunations
from core.transits.stations import find_stations
from core.types.computation import ComputationConfig
from core.types.transits import StandingRetrograde, Station
from shell.http.api.charts import jsonable, subject_json
from shell.http.api.meta import build_meta
from shell.http.api.router import router
from shell.http.api.subject import (
    SubjectModel,
    format_utc_instant,
    known_time_instant,
    parse_subject,
    unknown_time_instants,
)
from shell.http.api.window import ParsedWindow, WindowModel, parse_window

__all__ = ["TransitsRequest", "transits"]

_MOON = "moon"


class TransitsRequest(BaseModel):
    subject: SubjectModel
    window: WindowModel


def _events(window: ParsedWindow, config: ComputationConfig, **scans: Any) -> dict[str, Any]:
    stations = find_stations(window.start_utc, window.end_utc, config)
    return {
        "stations": jsonable([item for item in stations if isinstance(item, Station)]),
        "standing_retrogrades": jsonable(
            [item for item in stations if isinstance(item, StandingRetrograde)]
        ),
        **scans,
    }


@router.post("/charts/transits")
def transits(body: TransitsRequest, request: Request) -> Response:
    config: ComputationConfig = request.app.state.computation_config
    meta = build_meta(config, request.app.state.ephemeris_identity)
    subject = parse_subject(body.subject)
    window = parse_window(body.window, subject.iana_zone)
    start, end = window.start_utc, window.end_utc

    if subject.time_known:
        birth = known_time_instant(subject)
        chart = compute_natal_chart(birth.utc, subject.latitude, subject.longitude, config)
        subject_part = subject_json(
            subject,
            utc_offset=birth.offset,
            chart_instant=format_utc_instant(birth.utc),
            birth_instant=format_utc_instant(birth.utc),
        )
        events = _events(
            window,
            config,
            aspects=jsonable(
                find_transit_aspects(chart, start, end, config, split_perfections=True)
            ),
            ingresses=jsonable(find_ingresses(chart, start, end, config)),
            lunations=jsonable(find_lunations(chart, start, end)),
        )
    else:
        instants = unknown_time_instants(subject)
        unknown = compute_time_unknown_chart(
            instants.noon.utc, instants.day_start.utc, instants.day_end.utc, config
        )
        targets = tuple(
            (planet.name, planet.longitude) for planet in unknown.planets if planet.name != _MOON
        )
        subject_part = subject_json(
            subject,
            utc_offset=instants.noon.offset,
            chart_instant=format_utc_instant(instants.noon.utc),
            birth_instant=None,
        )
        events = _events(
            window,
            config,
            aspects=jsonable(
                find_transit_aspects_to_targets(targets, start, end, config, split_perfections=True)
            ),
            ingresses=None,
            lunations=[
                {**jsonable(moment), "natal_house": None}
                for moment in find_lunation_moments(start, end)
            ],
        )

    payload = {
        "meta": meta,
        "subject": subject_part,
        "window_utc": {"start": format_utc_instant(start), "end": format_utc_instant(end)},
        "aspects": events["aspects"],
        "stations": events["stations"],
        "standing_retrogrades": events["standing_retrogrades"],
        "ingresses": events["ingresses"],
        "lunations": events["lunations"],
    }
    return Response(canonical_json_bytes(payload), media_type="application/json")
