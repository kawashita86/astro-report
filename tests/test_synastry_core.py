"""Story 11.4: the pure synastry arithmetic -- midpoints, inter-aspects, overlays,
the composite for both house methods -- and the Astro.com composite fixture that
decided which house method ships."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.composite_houses import derive_composite_houses
from core.ephemeris.positions import _angular_separation
from core.synastry.composite import composite_chart, midpoint, midpoint_cusps
from core.synastry.inter_aspects import inter_aspects, known_points, unknown_points
from core.synastry.overlays import overlay
from core.types.chart import HouseCusp, NatalChart, TimeUnknownChart, TimeUnknownPlanet
from shell.computation import load_computation_config
from tests.conformance.runner import FIXTURES_DIR, load_fixture

CONFIG = load_computation_config()
D = Decimal


# --- Midpoint ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("10", "50", "30"),
        ("350", "20", "5"),
        ("20", "350", "5"),
        ("10", "190", "100"),  # exact opposition: A + 90
        ("190", "10", "280"),  # ... asymmetric by design
        ("0", "180", "90"),
        ("359", "181", "270"),
        ("10", "190.0002", "280.0001"),  # just past 180: the shorter arc runs backwards
        ("10", "189.9998", "99.9999"),  # just short of 180: the shorter arc
        ("5", "5", "5"),
    ],
)
def test_midpoint(a: str, b: str, expected: str) -> None:
    assert midpoint(D(a), D(b)) == D(expected)


def test_near_opposition_is_deterministic_on_both_sides_of_the_rule() -> None:
    assert midpoint(D("10"), D("190")) == D("100")
    assert midpoint(D("10"), D("190.0002")) != D("100")
    assert midpoint(D("10"), D("189.9998")) != D("100")


def test_a_midpoint_lies_inside_the_normalised_range() -> None:
    for a in range(0, 360, 37):
        for b in range(0, 360, 41):
            assert D(0) <= midpoint(D(a), D(b)) < D(360)


# --- Inter-aspects ----------------------------------------------------------------


def test_inter_aspects_pair_every_point_and_have_no_applying_flag() -> None:
    found = inter_aspects(
        (("sun", D("0")), ("moon", D("100"))), (("venus", D("180")), ("mars", D("90"))), D("7")
    )

    assert [(f.body_a, f.body_b, f.aspect, f.orb) for f in found] == [
        ("sun", "venus", "opposition", D("0")),
        ("sun", "mars", "square", D("0")),
    ]
    assert not hasattr(found[0], "applying")


def test_the_orb_edge_is_included_and_just_beyond_is_excluded() -> None:
    at_edge = inter_aspects((("sun", D("0")),), (("moon", D("7.0000")),), D("7.0"))
    beyond = inter_aspects((("sun", D("0")),), (("moon", D("7.0001")),), D("7.0"))

    assert [(a.aspect, a.orb) for a in at_edge] == [("conjunction", D("7.0000"))]
    assert beyond == ()


def _unknown_chart() -> TimeUnknownChart:
    def planet(name: str, longitude: str) -> TimeUnknownPlanet:
        return TimeUnknownPlanet(
            name=name,
            longitude=D(longitude),
            sign="aries",
            degree=D(longitude),
            retrograde=False,
            range_from=D(longitude),
            range_to=D(longitude),
            sign_uncertain=False,
        )

    return TimeUnknownChart(
        planets=(planet("sun", "10"), planet("moon", "20"), planet("south_node", "30")),
        aspects=(),
    )


def test_an_unknown_subject_contributes_no_angles_and_no_moon() -> None:
    assert [name for name, _ in unknown_points(_unknown_chart())] == ["sun", "south_node"]


def test_a_known_subject_contributes_nodes_and_angles(known_chart: NatalChart) -> None:
    names = [name for name, _ in known_points(known_chart)]

    assert names[-2:] == ["ascendant", "midheaven"]
    assert {"true_node", "south_node", "moon"} <= set(names)


# --- Overlays ---------------------------------------------------------------------


def test_overlay_places_bodies_in_the_receiving_houses_and_is_none_without_them() -> None:
    houses = tuple(HouseCusp(number=n, longitude=D(30 * (n - 1))) for n in range(1, 13))

    placed = overlay((("sun", D("45")), ("ascendant", D("10")), ("moon", D("359"))), houses)

    assert placed is not None
    assert [(e.body, e.house) for e in placed] == [("sun", 2), ("moon", 12)]
    assert overlay((("sun", D("45")),), None) is None


# --- Composite --------------------------------------------------------------------


@pytest.fixture(scope="module")
def known_chart() -> NatalChart:
    return compute_natal_chart(
        datetime(1985, 3, 12, 13, 30, tzinfo=UTC), D("45.4642"), D("9.19"), CONFIG
    )


@pytest.fixture(scope="module")
def other_chart() -> NatalChart:
    return compute_natal_chart(
        datetime(1990, 7, 4, 3, 15, tzinfo=UTC), D("41.9028"), D("12.4964"), CONFIG
    )


def _bodies(chart: NatalChart) -> dict[str, Decimal]:
    return {p.name: p.longitude for p in chart.planets}


def test_known_composite_has_midpoint_bodies_angles_houses_and_planet_houses(
    known_chart: NatalChart, other_chart: NatalChart
) -> None:
    houses = midpoint_cusps(known_chart.houses, other_chart.houses)

    composite = composite_chart(
        _bodies(known_chart),
        _bodies(other_chart),
        (known_chart.ascendant, known_chart.midheaven),
        (other_chart.ascendant, other_chart.midheaven),
        houses,
        CONFIG.orbs.natal,
    )

    assert composite.ascendant == midpoint(known_chart.ascendant, other_chart.ascendant)
    assert composite.midheaven == midpoint(known_chart.midheaven, other_chart.midheaven)
    assert composite.houses == houses
    assert [p.name for p in composite.planets][-1] == "south_node"
    assert all(p.house is not None for p in composite.planets)
    sun = next(p for p in composite.planets if p.name == "sun")
    assert sun.longitude == midpoint(_bodies(known_chart)["sun"], _bodies(other_chart)["sun"])
    assert all(a.applying is None for a in composite.aspects)


@pytest.mark.parametrize("unknown_side", ["a", "b"])
def test_either_time_unknown_nulls_angles_houses_and_excludes_the_moon(
    known_chart: NatalChart, other_chart: NatalChart, unknown_side: str
) -> None:
    angles = (known_chart.ascendant, known_chart.midheaven)
    composite = composite_chart(
        _bodies(known_chart),
        _bodies(other_chart),
        None if unknown_side == "a" else angles,
        None if unknown_side == "b" else angles,
        midpoint_cusps(known_chart.houses, other_chart.houses),
        CONFIG.orbs.natal,
    )

    assert composite.ascendant is None and composite.midheaven is None
    assert composite.houses is None
    assert all(p.house is None for p in composite.planets)
    assert any(p.name == "moon" for p in composite.planets)
    assert not any("moon" in (a.body1, a.body2) for a in composite.aspects)


def test_known_times_require_the_composite_houses(
    known_chart: NatalChart, other_chart: NatalChart
) -> None:
    angles = (known_chart.ascendant, known_chart.midheaven)
    with pytest.raises(ValueError):
        composite_chart(
            _bodies(known_chart), _bodies(other_chart), angles, angles, None, CONFIG.orbs.natal
        )


def test_composite_aspects_use_the_natal_orb() -> None:
    bodies_a = {name: D(0) for name in _names()}
    bodies_b = {name: D(0) for name in _names()}
    bodies_a["sun"], bodies_b["sun"] = D("0"), D("0")
    bodies_a["mars"], bodies_b["mars"] = D("7.0"), D("7.0")
    bodies_a["venus"], bodies_b["venus"] = D("14.0002"), D("14.0002")
    angles = (D(0), D(0))
    cusps = tuple(HouseCusp(number=n, longitude=D(30 * (n - 1))) for n in range(1, 13))

    composite = composite_chart(bodies_a, bodies_b, angles, angles, cusps, D("7.0"))

    found = {(a.body1, a.body2, a.aspect) for a in composite.aspects}
    assert ("sun", "mars", "conjunction") in found
    assert ("mars", "venus", "conjunction") not in found
    assert ("sun", "venus", "conjunction") not in found


def _names() -> list[str]:
    return [
        "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune",
        "pluto", "true_node", "south_node",
    ]  # fmt: skip


# --- derived_from_mc --------------------------------------------------------------


def test_derived_houses_put_the_composite_midheaven_on_the_tenth_cusp() -> None:
    houses = derive_composite_houses(
        D("164.2197"),
        D("36.0"),
        D("32.7358"),
        datetime(2024, 2, 29, 10, 12, tzinfo=UTC),
        datetime(2026, 1, 1, 6, 0, tzinfo=UTC),
    )

    assert [h.number for h in houses] == list(range(1, 13))
    assert houses[9].longitude == D("164.2197")
    assert houses[0].longitude != houses[6].longitude


# --- The Astro.com composite fixture ----------------------------------------------


def _natal_from_fixture(name: str) -> tuple[NatalChart, dict[str, str], datetime]:
    data = load_fixture(FIXTURES_DIR / f"{name}.toml").birth_data
    local = datetime.fromisoformat(f"{data['date']}T{data['time']}")
    instant = local.replace(tzinfo=UTC) - timedelta(hours=float(data["utc_offset_hours"]))
    chart = compute_natal_chart(instant, D(data["latitude"]), D(data["longitude"]), CONFIG)
    return chart, data, instant


def _circular(a: Decimal, b: Decimal) -> Decimal:
    return _angular_separation(a, b)


@pytest.mark.parametrize(
    "fixture_name", ["composite-midpoint-houses", "composite-near-opposition-nodes"]
)
def test_the_shipped_house_method_matches_the_astro_com_composite_fixture(
    fixture_name: str,
) -> None:
    fixture = load_fixture(FIXTURES_DIR / f"{fixture_name}.toml")
    tolerance = D(fixture.metadata["tolerance_degrees"])
    name_a, name_b = fixture.birth_data["composite_of"]
    chart_a, data_a, instant_a = _natal_from_fixture(name_a)
    chart_b, data_b, instant_b = _natal_from_fixture(name_b)
    angles_a = (chart_a.ascendant, chart_a.midheaven)
    angles_b = (chart_b.ascendant, chart_b.midheaven)
    if CONFIG.composite.houses == "midpoint_cusps":
        houses = midpoint_cusps(chart_a.houses, chart_b.houses)
    else:
        houses = derive_composite_houses(
            midpoint(chart_a.midheaven, chart_b.midheaven),
            D(data_a["latitude"]),
            D(data_b["latitude"]),
            instant_a,
            instant_b,
        )
    composite = composite_chart(
        _bodies(chart_a), _bodies(chart_b), angles_a, angles_b, houses, CONFIG.orbs.natal
    )
    expected = fixture.expected["composite"]

    assert composite.ascendant is not None and composite.midheaven is not None
    assert _circular(composite.ascendant, D(expected["ascendant"])) <= tolerance
    assert _circular(composite.midheaven, D(expected["midheaven"])) <= tolerance
    assert composite.houses is not None
    for cusp in expected["houses"]:
        computed = composite.houses[cusp["number"] - 1]
        assert _circular(computed.longitude, D(cusp["longitude"])) <= tolerance, cusp
    by_name = {p.name: p for p in composite.planets}
    for planet in expected["planets"]:
        if "house" in planet:
            assert by_name[planet["name"]].house == planet["house"], planet
        if "longitude" in planet:
            assert _circular(by_name[planet["name"]].longitude, D(planet["longitude"])) <= tolerance


def test_the_other_method_would_miss_the_fixture() -> None:
    """Proof the fixture discriminates: MC-derived cusps miss by more than a degree."""
    fixture = load_fixture(FIXTURES_DIR / "composite-midpoint-houses.toml")
    name_a, name_b = fixture.birth_data["composite_of"]
    chart_a, data_a, instant_a = _natal_from_fixture(name_a)
    chart_b, data_b, instant_b = _natal_from_fixture(name_b)
    derived = derive_composite_houses(
        midpoint(chart_a.midheaven, chart_b.midheaven),
        D(data_a["latitude"]),
        D(data_b["latitude"]),
        instant_a,
        instant_b,
    )
    expected = {c["number"]: D(c["longitude"]) for c in fixture.expected["composite"]["houses"]}

    assert max(_circular(derived[n - 1].longitude, v) for n, v in expected.items()) > D("1")


# --- The Astro.com synastry fixture -----------------------------------------------


def test_synastry_matches_the_astro_com_partner_comparison_fixture() -> None:
    fixture = load_fixture(FIXTURES_DIR / "synastry-leap-day-and-midnight.toml")
    name_a, name_b = fixture.birth_data["synastry_of"]
    chart_a, _, _ = _natal_from_fixture(name_a)
    chart_b, _, _ = _natal_from_fixture(name_b)
    found = {
        (a.body_a, a.body_b): a
        for a in inter_aspects(
            known_points(chart_a), known_points(chart_b), D(fixture.metadata["orb_limit"])
        )
    }

    for expected in fixture.expected["inter_aspects"]:
        computed = found[(expected["body_a"], expected["body_b"])]
        assert computed.aspect == expected["aspect"], expected
        assert abs(computed.orb - D(expected["orb"])) <= D("0.002"), expected

    def bodies(chart: NatalChart) -> tuple[tuple[str, Decimal], ...]:
        return tuple((p.name, p.longitude) for p in chart.planets)

    for key, bodies_of, receiving in (
        ("a_in_b", bodies(chart_a), chart_b.houses),
        ("b_in_a", bodies(chart_b), chart_a.houses),
    ):
        placed = {entry.body: entry.house for entry in overlay(bodies_of, receiving)}
        for expected in fixture.expected["overlays"][key]:
            assert placed[expected["body"]] == expected["house"], (key, expected)
