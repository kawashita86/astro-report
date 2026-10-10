"""``POST /api/v1/charts/synastry``: two people's charts and what lies between them.

Both subjects are resolved exactly as for a natal chart; this module then asks
``core/synastry`` for the inter-aspects, the house overlays each way and the
midpoint composite, and serialises everything next to the two natal charts.
A subject with an unknown birth time contributes a noon chart with no angles,
and every output that needs its houses or angles is ``null`` rather than absent
so the response shape is stable. The composite house method comes from the
ComputationConfig, never from the request. The handler is synchronous, writes
no row and logs nothing about the subjects; the body is canonical JSON so a
repeat request gives identical bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.composite_houses import derive_composite_houses
from core.ephemeris.time_unknown import compute_time_unknown_chart
from core.errors import LocalTimeError
from core.payload.freeze import canonical_json_bytes
from core.synastry.composite import composite_chart, midpoint, midpoint_cusps
from core.synastry.inter_aspects import Point, inter_aspects, known_points, unknown_points
from core.synastry.overlays import overlay
from core.types.chart import HouseCusp, NatalChart, TimeUnknownChart
from core.types.computation import ComputationConfig
from shell.http.api.charts import jsonable, known_chart_json, subject_json, unknown_chart_json
from shell.http.api.errors import ApiError, ErrorCode
from shell.http.api.meta import build_meta
from shell.http.api.router import router
from shell.http.api.subject import (
    ParsedSubject,
    SubjectModel,
    format_utc_instant,
    known_time_instant,
    parse_subject,
    unknown_time_instants,
)

__all__ = ["SynastryRequest", "synastry"]


class SynastryRequest(BaseModel):
    subject_a: SubjectModel
    subject_b: SubjectModel


@dataclass(frozen=True)
class _Side:
    """One subject, computed: its serialised parts and the inputs the pure
    synastry functions need."""

    subject_part: dict[str, Any]
    chart_part: dict[str, Any]
    bodies: dict[str, Decimal]
    points: tuple[Point, ...]
    houses: tuple[HouseCusp, ...] | None
    angles: tuple[Decimal, Decimal] | None
    latitude: Decimal
    birth_utc: datetime | None


def _compute_side(subject: ParsedSubject, prefix: str, config: ComputationConfig) -> _Side:
    try:
        if subject.time_known:
            birth = known_time_instant(subject)
            chart: NatalChart = compute_natal_chart(
                birth.utc, subject.latitude, subject.longitude, config
            )
            return _Side(
                subject_part=subject_json(
                    subject,
                    utc_offset=birth.offset,
                    chart_instant=format_utc_instant(birth.utc),
                    birth_instant=format_utc_instant(birth.utc),
                ),
                chart_part=known_chart_json(chart, config),
                bodies={planet.name: planet.longitude for planet in chart.planets},
                points=known_points(chart),
                houses=chart.houses,
                angles=(chart.ascendant, chart.midheaven),
                latitude=subject.latitude,
                birth_utc=birth.utc,
            )
        instants = unknown_time_instants(subject)
    except LocalTimeError as error:
        raise ApiError(ErrorCode.INVALID_REQUEST, f"{prefix}.birth_time") from error
    unknown: TimeUnknownChart = compute_time_unknown_chart(
        instants.noon.utc, instants.day_start.utc, instants.day_end.utc, config
    )
    return _Side(
        subject_part=subject_json(
            subject,
            utc_offset=instants.noon.offset,
            chart_instant=format_utc_instant(instants.noon.utc),
            birth_instant=None,
        ),
        chart_part=unknown_chart_json(unknown),
        bodies={planet.name: planet.longitude for planet in unknown.planets},
        points=unknown_points(unknown),
        houses=None,
        angles=None,
        latitude=subject.latitude,
        birth_utc=None,
    )


def _composite_houses(
    side_a: _Side, side_b: _Side, config: ComputationConfig
) -> tuple[HouseCusp, ...] | None:
    """The composite cusps by the configured method, or ``None`` unless both
    birth times are known."""
    if side_a.houses is None or side_b.houses is None:
        return None
    if config.composite.houses == "derived_from_mc":
        assert side_a.angles is not None and side_b.angles is not None
        assert side_a.birth_utc is not None and side_b.birth_utc is not None
        return derive_composite_houses(
            midpoint(side_a.angles[1], side_b.angles[1]),
            side_a.latitude,
            side_b.latitude,
            side_a.birth_utc,
            side_b.birth_utc,
        )
    return midpoint_cusps(side_a.houses, side_b.houses)


def _overlay_bodies(side: _Side) -> tuple[tuple[str, Decimal], ...]:
    return tuple(side.bodies.items())


@router.post("/charts/synastry")
def synastry(body: SynastryRequest, request: Request) -> Response:
    config: ComputationConfig = request.app.state.computation_config
    meta = build_meta(config, request.app.state.ephemeris_identity)
    subject_a = parse_subject(body.subject_a, "subject_a")
    subject_b = parse_subject(body.subject_b, "subject_b")
    side_a = _compute_side(subject_a, "subject_a", config)
    side_b = _compute_side(subject_b, "subject_b", config)

    composite = composite_chart(
        side_a.bodies,
        side_b.bodies,
        side_a.angles,
        side_b.angles,
        _composite_houses(side_a, side_b, config),
        config.orbs.natal,
    )
    payload = {
        "meta": meta,
        "subjects": [side_a.subject_part, side_b.subject_part],
        "natal_a": side_a.chart_part,
        "natal_b": side_b.chart_part,
        "inter_aspects": jsonable(
            inter_aspects(side_a.points, side_b.points, config.orbs.synastry)
        ),
        "overlays": {
            "a_in_b": jsonable(overlay(_overlay_bodies(side_a), side_b.houses)),
            "b_in_a": jsonable(overlay(_overlay_bodies(side_b), side_a.houses)),
        },
        "composite": jsonable(composite),
    }
    return Response(canonical_json_bytes(payload), media_type="application/json")
