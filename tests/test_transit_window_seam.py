"""Story 11.3 seam test: a long window is the union of its monthly scans.

A 12-month window across a Mercury station is scanned once and again as twelve
contiguous intervals. The intervals start at UTC midnight and the window does
too, so both runs share the 6 h grid phase and every bisection bracket, and the
results must agree exactly: no perfection, station, ingress or lunation missing
or duplicated at a seam. A pair in orb across a seam is two monthly events but
one window event, so aspect orb intervals are compared after merging the
clamped monthly pieces. Standing retrogrades are excluded: each interval clamps
them to itself by design.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.ephemeris.chart import compute_natal_chart
from core.transits.aspects import find_transit_aspects
from core.transits.ingresses import find_ingresses
from core.transits.lunations import find_lunations
from core.transits.stations import find_stations
from core.types.chart import NatalChart
from core.types.transits import Station
from shell.http.app import computation_config

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2027, 1, 1, tzinfo=UTC)
MONTHS = [
    (datetime(2026, m, 1, tzinfo=UTC), datetime(2026 + m // 12, m % 12 + 1, 1, tzinfo=UTC))
    for m in range(1, 13)
]


@pytest.fixture(scope="module")
def chart() -> NatalChart:
    return compute_natal_chart(
        datetime(1985, 3, 12, 13, 30, tzinfo=UTC),
        Decimal("45.4642"),
        Decimal("9.1900"),
        computation_config,
    )


def test_the_months_tile_the_window_with_no_gap_or_overlap() -> None:
    assert MONTHS[0][0] == START and MONTHS[-1][1] == END
    assert all(a[1] == b[0] for a, b in zip(MONTHS, MONTHS[1:], strict=False))


def test_stations_equal_the_union_of_the_monthly_scans() -> None:
    whole = [s for s in find_stations(START, END, computation_config) if isinstance(s, Station)]
    parts = [
        s
        for lo, hi in MONTHS
        for s in find_stations(lo, hi, computation_config)
        if isinstance(s, Station)
    ]

    assert any(s.body == "mercury" for s in whole)
    assert sorted(parts, key=lambda s: (s.station_at, s.body)) == sorted(
        whole, key=lambda s: (s.station_at, s.body)
    )


def test_lunations_equal_the_union_of_the_monthly_scans(chart: NatalChart) -> None:
    whole = find_lunations(chart, START, END)
    parts = [m for lo, hi in MONTHS for m in find_lunations(chart, lo, hi)]

    assert len(whole) >= 24
    assert sorted(parts, key=lambda m: m.occurred_at) == sorted(whole, key=lambda m: m.occurred_at)


def test_ingresses_equal_the_union_of_the_monthly_scans(chart: NatalChart) -> None:
    whole = find_ingresses(chart, START, END, computation_config)
    parts = [i for lo, hi in MONTHS for i in find_ingresses(chart, lo, hi, computation_config)]

    assert whole
    key = lambda i: (i.crossed_at, i.body)  # noqa: E731
    assert sorted(parts, key=key) == sorted(whole, key=key)


def test_aspect_perfections_and_orb_intervals_equal_the_union_of_the_monthly_scans(
    chart: NatalChart,
) -> None:
    whole = find_transit_aspects(chart, START, END, computation_config, split_perfections=True)
    parts = [
        a
        for lo, hi in MONTHS
        for a in find_transit_aspects(chart, lo, hi, computation_config, split_perfections=True)
    ]

    def perfections(events: tuple[object, ...] | list[object]) -> list[tuple[object, ...]]:
        return sorted(
            (e.transiting_body, e.natal_point, e.aspect, e.perfected_at)  # type: ignore[attr-defined]
            for e in events
            if e.perfected_at is not None  # type: ignore[attr-defined]
        )

    assert perfections(whole)
    assert perfections(parts) == perfections(whole)

    def intervals(events: list[object], months: bool) -> list[tuple[object, ...]]:
        by_pair: dict[tuple[str, str, str], list[tuple[datetime, datetime | None]]] = {}
        for e in sorted(events, key=lambda e: e.orb_entry_at):  # type: ignore[attr-defined]
            pair = (e.transiting_body, e.natal_point, e.aspect)  # type: ignore[attr-defined]
            spans = by_pair.setdefault(pair, [])
            if spans and spans[-1] == (e.orb_entry_at, e.orb_exit_at):  # type: ignore[attr-defined]
                continue  # a further perfection of the same orb interval
            if (
                months
                and spans
                and spans[-1][1] is None
                and e.orb_entry_at in {hi for _, hi in MONTHS}
            ):  # type: ignore[attr-defined]
                spans[-1] = (spans[-1][0], e.orb_exit_at)  # type: ignore[attr-defined]
            else:
                spans.append((e.orb_entry_at, e.orb_exit_at))  # type: ignore[attr-defined]
        return sorted(
            (pair, entry, exit_) for pair, spans in by_pair.items() for entry, exit_ in spans
        )

    assert intervals(parts, True) == intervals(list(whole), False)
