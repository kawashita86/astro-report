"""Maps a stored Natal Chart into Kerykeion's chart-drawing model (Story 2.6,
ARCHITECTURE-SPINE.md FR-5).

Isolates the Kerykeion-shape translation from ``shell/http/routes/chart.py``'s
route handler. Every ``KerykeionPointModel`` here is built directly from the
Client's stored fields via ``kerykeion.utilities.get_kerykeion_point_from_degree()``
-- Kerykeion never recomputes a position, cusp, ascendant or midheaven. The
only thing this module lets Kerykeion recompute is its own natal Aspect pass,
which ``active_aspects()`` configures to this project's five-aspect set and
orb (see the story's Design Notes on why that recomputation is geometrically
equivalent to ``chart.aspects``, not a re-serialization of it).
"""

from __future__ import annotations

import html
from datetime import datetime
from decimal import Decimal
from typing import Any

from kerykeion.schemas.kr_models import (
    ActiveAspect,
    AstrologicalSubjectModel,
    KerykeionPointModel,
)
from kerykeion.utilities import get_house_name, get_kerykeion_point_from_degree

from shell.adapters.postgres.client import Client, StoredNatalChart

__all__ = ["active_aspects", "build_subject"]

#: ``AstrologicalSubjectModel``'s twelve house-cusp keyword fields, in house
#: number order: ``_HOUSE_FIELDS[number - 1]`` is the keyword one stored
#: ``HouseCusp`` maps onto.
_HOUSE_FIELDS: tuple[str, ...] = (
    "first_house",
    "second_house",
    "third_house",
    "fourth_house",
    "fifth_house",
    "sixth_house",
    "seventh_house",
    "eighth_house",
    "ninth_house",
    "tenth_house",
    "eleventh_house",
    "twelfth_house",
)

#: The five natal Aspects ``core/ephemeris/chart.py`` detects (FR-3).
#: Kerykeion's own default active-aspect set also includes quintile, which
#: this project's Natal Chart never computes -- so the default is never used
#: here; ``active_aspects()`` always states this exact five explicitly.
_ASPECT_NAMES: tuple[str, ...] = ("conjunction", "sextile", "square", "trine", "opposition")


def _kerykeion_point_name(stored_name: str) -> str:
    """The stored body name's Kerykeion ``AstrologicalPoint`` literal (the
    story's body-name mapping).

    The True Node and South Node are named differently in Kerykeion than in
    ``core/types/chart.py``; every other stored name -- the ten planets --
    matches Kerykeion's literal by capitalization alone.
    """
    if stored_name == "true_node":
        return "True_North_Lunar_Node"
    if stored_name == "south_node":
        return "True_South_Lunar_Node"
    return stored_name.capitalize()


def build_subject(client: Client, chart: StoredNatalChart) -> AstrologicalSubjectModel:
    """The stored Client + Natal Chart, mapped into a Kerykeion
    ``AstrologicalSubjectModel`` -- built directly from stored fields, never
    recomputed via Kerykeion's own subject factory (ARCHITECTURE-SPINE.md
    FR-5; the story's Boundaries & Constraints).

    ``city`` carries the Client's stored ``birthplace_name`` (AD-16, amended
    2026-09-01); ``nation`` stays empty because Kerykeion's own header
    renders ``f"{city}, {nation}"`` and the stored name is already the
    geocoder's full place string -- splitting it into two fields would only
    reconstruct what it already was. This view is Francesco's own
    verification tool, never Client-facing.
    """
    planet_points: dict[str, KerykeionPointModel] = {}
    active_points: list[str] = []
    sun_house = 1
    for planet in chart.planets:
        stored_name = str(planet["name"])
        longitude = Decimal(planet["longitude"])
        house_number = int(planet["house"])
        retrograde = bool(planet["retrograde"])
        point_name = _kerykeion_point_name(stored_name)

        point = get_kerykeion_point_from_degree(
            float(longitude),
            point_name,
            "AstrologicalPoint",
            # Kerykeion's own retrograde convention (the I/O matrix's
            # "Retrograde planet" row): a negative speed, not a separate flag.
            speed=-1.0 if retrograde else 1.0,
        )
        point.house = get_house_name(house_number)
        planet_points[point_name.lower()] = point
        active_points.append(point_name)

        if stored_name == "sun":
            sun_house = house_number

    house_points: dict[str, KerykeionPointModel] = {}
    for house in chart.houses:
        number = int(house["number"])
        longitude = Decimal(house["longitude"])
        house_points[_HOUSE_FIELDS[number - 1]] = get_kerykeion_point_from_degree(
            float(longitude), get_house_name(number), "House"
        )

    ascendant = get_kerykeion_point_from_degree(
        float(chart.ascendant), "Ascendant", "AstrologicalPoint"
    )
    medium_coeli = get_kerykeion_point_from_degree(
        float(chart.midheaven), "Medium_Coeli", "AstrologicalPoint"
    )
    active_points += ["Ascendant", "Medium_Coeli"]

    local_datetime = datetime.combine(client.birth_date, client.birth_time)

    subject_kwargs: dict[str, Any] = {
        # Kerykeion embeds this value verbatim, unescaped, into the
        # generated SVG's own `<title>` element -- and the route renders
        # that SVG via `{{ svg | safe }}`, bypassing Jinja's autoescaping.
        # Escaping here is the only place in this pipeline that can stop a
        # Client name from becoming a stored-XSS payload in the browser.
        "name": html.escape(client.name, quote=True),
        "city": html.escape(client.birthplace_name or "", quote=True),
        "nation": "",
        "lng": float(client.longitude),
        "lat": float(client.latitude),
        "tz_str": client.iana_zone,
        "iso_formatted_local_datetime": local_datetime.isoformat(),
        # No UTC birth instant is stored on `Client` -- only the local
        # civil time and the IANA zone that resolved it (Story 2.1/2.3).
        # This label is cosmetic only (Kerykeion's SVG renderer never reads
        # it back into a computation), so the local instant stands in
        # rather than re-deriving a UTC offset here.
        "iso_formatted_utc_datetime": local_datetime.isoformat(),
        # Unused by Kerykeion's SVG renderer; required by the model only.
        "julian_day": 0.0,
        "day_of_week": client.birth_date.strftime("%A"),
        "zodiac_type": "Tropical",
        "sidereal_mode": None,
        # Placidus is the only house system this project ever configures
        # (`core/types/computation.py`'s `HouseSystem` docstring) -- not
        # read from `ComputationConfig` here since `build_subject()` takes
        # only the Client and its stored chart.
        "houses_system_identifier": "P",
        "houses_system_name": "Placidus",
        "perspective_type": "Apparent Geocentric",
        "ascendant": ascendant,
        "medium_coeli": medium_coeli,
        "descendant": None,
        "imum_coeli": None,
        "houses_names_list": list(_get_house_names()),
        "active_points": active_points,
        "lunar_phase": None,
        "year": local_datetime.year,
        "month": local_datetime.month,
        "day": local_datetime.day,
        "hour": local_datetime.hour,
        "minute": local_datetime.minute,
        # Traditional day/night split on the stored Sun's house: houses 7-12
        # are above the horizon (the Ascendant-Descendant axis), 1-6 below
        # it. Cosmetic only -- Kerykeion's SVG renderer never reads this
        # value back into a computation either.
        "is_diurnal": sun_house >= 7,
        **planet_points,
        **house_points,
    }

    return AstrologicalSubjectModel(**subject_kwargs)


def _get_house_names() -> tuple[str, ...]:
    return tuple(get_house_name(number) for number in range(1, 13))


def active_aspects(orb: Decimal) -> list[ActiveAspect]:
    """This project's five-Aspect set (FR-3), each configured with the same
    ``orb`` -- ``ComputationConfig.orbs.natal`` -- Story 2.2's own Aspect
    detection uses, so Kerykeion's recomputed set is geometrically
    equivalent to ``chart.aspects`` (the story's Design Notes)."""
    return [ActiveAspect(name=name, orb=float(orb)) for name in _ASPECT_NAMES]
