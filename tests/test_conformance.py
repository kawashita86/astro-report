"""The CI-visible conformance entry point (Story 1.6, populated by Story 1.7,
wired to real computation by Story 2.2).

Two tests, matching the story's own AC2/AC3 split:

- ``test_reports_zero_fixtures_without_failing`` proves AC2: fixture
  discovery is reported, not merely absent -- a parametrized test over zero
  fixtures would contribute zero cases and pass vacuously, which satisfies
  "doesn't fail" but not "reports." Story 1.6 shipped this directory empty
  and asserted exactly that; Story 1.7 transcribed the first real reference
  charts here, so the assertion now proves the opposite state -- that
  discovery finds them and is never silently empty by accident. Either
  direction is a real, visible report; the low-level "empty dir stays empty"
  behavior itself is still covered independently in
  ``tests/test_conformance_runner.py``.
- ``test_computed_output_matches_conformance_fixture`` is the parametrized
  entry point real fixtures (Story 1.7) run under. It calls
  ``compute_output_for()``, which now (Story 2.2) shapes
  ``compute_natal_chart()``'s result into the fixture's dict format --
  Chiron is out of scope (see spec-2-2's Design Notes), so it is not part of
  that shape, and the four natal fixtures have had their ``chiron`` entries
  trimmed to match.

  Story 2.2 is natal-only: Epic 3's transit engine did not exist yet, so the
  three month fixtures (``birth_data`` keyed by ``anchor_natal_fixture``/
  ``month``/``transit_snapshot_utc``, not a birth instant) were not
  something ``compute_output_for()`` could produce output for. Each fixture
  was parametrized individually: a natal fixture ran for real, a non-natal
  one kept an ``xfail(raises=NotImplementedError)`` shape -- still the
  visible "flip to XPASS the day this is wired in" signal ``xfail_strict``
  was set up for, just scoped to the fixtures actually still unimplemented.

  Story 3.1 narrows that scope further, per fixture *section* rather than
  per fixture: a month fixture's own ``expected.transit_events`` now runs
  for real against ``find_transit_aspects()`` (narrowed to whichever events
  are in orb at the fixture's ``transit_snapshot_utc``), while
  ``expected.lunations``/``expected.transit_positions``/``expected.stations``
  stay behind the same ``xfail(raises=NotImplementedError)`` shape until
  Stories 3.2-3.4 wire those in. A month fixture is therefore parametrized
  *twice* -- once per section, each with its own pass/xfail signal -- so a
  real defect in transit-Aspect detection can never be masked by (nor
  mistaken for) the still-missing Lunation/Station/position sections.

Reading ``data/computation.toml`` and asserting the ephemeris identity here,
rather than in ``core/``, mirrors ``shell/http/app.py``'s own eager-load
shape (AD-1/AD-18): this test module -- like the rest of ``tests/`` -- is
exempt from the purity boundary the way ``tests/conformance/runner.py``
already documents, but ``compute_natal_chart()`` itself still never reads
either ambiently.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from core.ephemeris.chart import _ASPECTS, compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.ephemeris.positions import QUANTUM, _angular_separation, _calc_body, _julian_day_ut
from core.transits.aspects import _TRANSIT_BODY_IDS, _natal_targets, find_transit_aspects
from core.types.chart import NatalChart
from shell.computation import load_computation_config
from tests.conformance.runner import (
    FIXTURES_DIR,
    Fixture,
    FixtureFormatError,
    compare,
    discover_fixtures,
    load_fixture,
)

# Mirrors shell/http/app.py's own import-time eager load: a test session that
# imports this module has the vendored ephemeris pinned and the tuning
# values loaded exactly once, before any fixture computes against them.
verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

# The autouse fixture re-pinning the real vendored ephemeris before every
# test in the session lives in tests/conftest.py (shared across modules).


#: Key a month/transit fixture's ``birth_data`` carries in place of an actual
#: birth instant (Epic 3, not yet implemented) -- checking for its absence,
#: rather than for a natal fixture's own key set, avoids misrouting a future
#: fixture that happens to carry both shapes' keys.
_MONTH_FIXTURE_ANCHOR_KEY = "anchor_natal_fixture"


def _is_natal_fixture(fixture: Fixture) -> bool:
    return _MONTH_FIXTURE_ANCHOR_KEY not in fixture.birth_data


def _birth_instant_utc(birth_data: dict[str, Any]) -> datetime:
    """The fixture's local birth date/time, shifted to UTC by its recorded
    ``utc_offset_hours`` -- never re-derived from ``timezone`` here, since
    that historical-offset resolution is Story 2.1's job, already exercised
    elsewhere; a fixture already records the offset that was in force."""
    naive = datetime.fromisoformat(f"{birth_data['date']}T{birth_data['time']}")
    offset_hours = Decimal(birth_data["utc_offset_hours"])
    return (naive - timedelta(hours=float(offset_hours))).replace(tzinfo=UTC)


def _shape_chart_for_conformance(chart: NatalChart) -> dict[str, Any]:
    """``NatalChart`` shaped into the fixture's plain dict/list format
    (``tests/conformance/runner.py``'s Design Notes). The South Node is
    computed and present on ``chart.planets`` (AC1) but omitted here -- it
    is not itself fixture-checked (spec-2-2 Design Notes), and including it
    would make the ``planets`` list longer than ``expected.planets``."""
    return {
        "planets": [
            {
                "name": planet.name,
                "longitude": str(planet.longitude),
                "retrograde": planet.retrograde,
            }
            for planet in chart.planets
            if planet.name != "south_node"
        ],
        "houses": [
            {"number": cusp.number, "cusp_longitude": str(cusp.longitude)}
            for cusp in chart.houses
        ],
        "aspects": [
            {
                "body1": aspect.body1,
                "body2": aspect.body2,
                "aspect": aspect.aspect,
                "orb": str(aspect.orb),
            }
            for aspect in chart.aspects
        ],
    }


#: Target degrees for each of the five Aspects, keyed by name -- reused
#: (not reinvented) from ``core/ephemeris/chart.py``'s own matching table,
#: since a month fixture's snapshot-moment orb value has to be measured
#: against the exact same angles ``find_transit_aspects()`` itself scans.
_TARGET_DEGREES_BY_ASPECT: dict[str, Decimal] = dict(_ASPECTS)


def _month_interval_utc(fixture: Fixture) -> tuple[datetime, datetime]:
    """A plain UTC calendar-month interval for ``fixture.birth_data["month"]``
    (``"YYYY-MM"``).

    Deriving the analyzed month from a Client's *local* calendar boundaries
    (``Client.iana_zone``) is explicitly out of this story's scope (see the
    story's Design Notes) -- ``find_transit_aspects()`` only ever consumes
    an already-resolved ``[month_start_utc, month_end_utc)``, wherever it
    comes from. Every month fixture's own ``transit_snapshot_utc`` is
    recorded at 00:00 UTC on the stated month's first calendar day, so this
    simpler UTC-calendar interval already contains it -- no zone lookup
    needed here.

    Raises:
        FixtureFormatError: naming ``fixture`` and the malformed
            ``birth_data.month`` value -- mirrors ``tests/conformance/runner.py``'s
            own "fail loudly, name the offender" convention, rather than
            letting a raw ``ValueError``/``KeyError`` escape unattributed.
    """
    month = fixture.birth_data.get("month")
    if not isinstance(month, str):
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.month is required and must be a string, got {month!r}."
        )
    try:
        year_str, month_str = month.split("-")
        year, month_number = int(year_str), int(month_str)
        start = datetime(year, month_number, 1, tzinfo=UTC)
        end = (
            datetime(year + 1, 1, 1, tzinfo=UTC)
            if month_number == 12
            else datetime(year, month_number + 1, 1, tzinfo=UTC)
        )
    except ValueError as error:
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.month {month!r} is not a valid 'YYYY-MM' string: "
            f"{error}."
        ) from error
    return start, end


def _anchor_natal_chart(fixture: Fixture) -> NatalChart:
    """The real ``NatalChart`` a month fixture's transits are measured
    against -- computed from its ``anchor_natal_fixture``'s own birth data,
    exactly like a natal fixture's own chart (``_birth_instant_utc()``),
    not a second, independent computation path.

    Raises:
        FixtureFormatError: naming ``fixture`` when ``birth_data`` has no
            ``anchor_natal_fixture`` key, or when that key names a fixture
            file that doesn't exist -- mirrors ``tests/conformance/runner.py``'s
            own "fail loudly, name the offender" convention, rather than
            letting a raw ``KeyError``/``FileNotFoundError`` escape
            unattributed.
    """
    anchor_name = fixture.birth_data.get("anchor_natal_fixture")
    if not isinstance(anchor_name, str) or not anchor_name:
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.anchor_natal_fixture is required and must be a "
            f"non-empty string, got {anchor_name!r}."
        )
    anchor_path = FIXTURES_DIR / f"{anchor_name}.toml"
    if not anchor_path.is_file():
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.anchor_natal_fixture {anchor_name!r} does not name "
            f"an existing fixture file ({anchor_path})."
        )
    anchor_fixture = load_fixture(anchor_path)
    birth_instant_utc = _birth_instant_utc(anchor_fixture.birth_data)
    latitude = Decimal(anchor_fixture.birth_data["latitude"])
    longitude = Decimal(anchor_fixture.birth_data["longitude"])
    return compute_natal_chart(birth_instant_utc, latitude, longitude, _COMPUTATION_CONFIG)


def _transit_snapshot_utc(fixture: Fixture) -> datetime:
    """``fixture.birth_data["transit_snapshot_utc"]``, parsed and confirmed
    timezone-aware UTC.

    Raises:
        FixtureFormatError: naming ``fixture`` and the malformed/non-UTC
            ``birth_data.transit_snapshot_utc`` value -- mirrors
            ``tests/conformance/runner.py``'s own "fail loudly, name the
            offender" convention, rather than letting a raw
            ``ValueError``/``TypeError`` escape unattributed, or silently
            treating a naive/non-UTC instant as UTC.
    """
    raw = fixture.birth_data.get("transit_snapshot_utc")
    if not isinstance(raw, str):
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.transit_snapshot_utc is required and must be a "
            f"string, got {raw!r}."
        )
    try:
        snapshot = datetime.fromisoformat(raw)
    except ValueError as error:
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.transit_snapshot_utc {raw!r} is not a valid ISO 8601 "
            f"datetime: {error}."
        ) from error
    if snapshot.tzinfo is None or snapshot.utcoffset() != timedelta(0):
        raise FixtureFormatError(
            f"{fixture.path}: birth_data.transit_snapshot_utc {raw!r} must be timezone-aware "
            "UTC (utcoffset() == 0)."
        )
    return snapshot


#: Natal targets Story 3.1's frozen spec requires ``find_transit_aspects()``
#: to scan (fourteen: the ten planets, ascendant, midheaven, true node and
#: south node -- exercised directly in ``tests/test_transit_aspects.py``)
#: but that no fixture's own transcribed Astro.com data ever checks an
#: Aspect against: exactly the same precedent ``_shape_chart_for_conformance``
#: already sets for the South Node on natal fixtures ("it is not itself
#: fixture-checked", spec-2-2's Design Notes) -- Astro.com's own aspect grid
#: never lists a house cusp or the South Node as an aspect partner either.
#: Filtered out here so the conformance check compares only what the
#: fixtures actually transcribe; ``find_transit_aspects()`` itself is
#: unaffected and still scans all fourteen.
_NATAL_POINTS_NOT_FIXTURE_CHECKED = frozenset({"ascendant", "midheaven", "south_node"})


def _transit_events_for_month_fixture(fixture: Fixture) -> list[dict[str, Any]]:
    """``find_transit_aspects()``'s real output for ``fixture``'s month,
    narrowed to whichever events are in orb at ``transit_snapshot_utc`` and
    shaped to the fixture's own ``transiting``/``natal``/``aspect``/``orb``
    dict format.

    The orb *value* itself isn't a ``TransitAspectEvent`` field (only the
    entry/exit/perfection instants are -- see ``core/types/transits.py``),
    so it is recomputed directly at the snapshot instant from the same
    low-level position math ``find_transit_aspects()`` itself uses, not
    invented separately.
    """
    chart = _anchor_natal_chart(fixture)
    month_start_utc, month_end_utc = _month_interval_utc(fixture)
    snapshot_utc = _transit_snapshot_utc(fixture)

    events = find_transit_aspects(chart, month_start_utc, month_end_utc, _COMPUTATION_CONFIG)
    natal_longitudes = dict(_natal_targets(chart))

    rows: list[dict[str, Any]] = []
    for event in events:
        if event.natal_point in _NATAL_POINTS_NOT_FIXTURE_CHECKED:
            continue
        exit_bound = event.orb_exit_at if event.orb_exit_at is not None else month_end_utc
        if not (event.orb_entry_at <= snapshot_utc <= exit_bound):
            continue
        body_id = _TRANSIT_BODY_IDS[event.transiting_body]
        transiting_longitude = _calc_body(_julian_day_ut(snapshot_utc), body_id)[0]
        separation = _angular_separation(transiting_longitude, natal_longitudes[event.natal_point])
        orb = abs(separation - _TARGET_DEGREES_BY_ASPECT[event.aspect]).quantize(QUANTUM)
        rows.append(
            {
                "transiting": event.transiting_body,
                "natal": event.natal_point,
                "aspect": event.aspect,
                "orb": str(orb),
            }
        )
    return rows


#: The one month-fixture section real computation produces today (Story
#: 3.1). Every other top-level ``expected`` key for a month fixture --
#: ``lunations``, ``transit_positions``, ``stations`` -- is still Stories
#: 3.2-3.4's job.
_IMPLEMENTED_MONTH_SCOPE = "transit_events"


def compute_output_for(fixture: Fixture, scope: str | None = None) -> dict[str, Any]:
    """Compute the output a real chart/transit engine produces for
    ``fixture``, shaped to match ``fixture.expected``'s dict/list format.

    The single, clearly-named call site real Epic 2/3 computation plugs into
    (see the story's Design Notes): Story 2.2 wired in
    ``compute_natal_chart()`` for natal fixtures (``scope`` is always
    ``None`` there -- a natal fixture is never split into sections). Story
    3.1 wires in ``find_transit_aspects()`` for a month fixture's
    ``scope="transit_events"`` only; any other ``scope`` for a month fixture
    (``"remainder"``, standing in for lunations/positions/stations) still
    raises, exactly as the whole fixture used to before this story.
    """
    if _is_natal_fixture(fixture):
        birth_instant_utc = _birth_instant_utc(fixture.birth_data)
        latitude = Decimal(fixture.birth_data["latitude"])
        longitude = Decimal(fixture.birth_data["longitude"])

        chart = compute_natal_chart(birth_instant_utc, latitude, longitude, _COMPUTATION_CONFIG)

        return _shape_chart_for_conformance(chart)

    if scope == _IMPLEMENTED_MONTH_SCOPE:
        return {"transit_events": _transit_events_for_month_fixture(fixture)}

    raise NotImplementedError(
        "real Lunation/Station/position computation is not wired in yet "
        f"(Stories 3.2-3.4): fixture {fixture.name!r}, scope {scope!r}"
    )


def _expected_for_scope(fixture: Fixture, scope: str | None) -> dict[str, Any]:
    """The slice of ``fixture.expected`` a given parametrized test case
    checks. ``scope=None`` (every natal fixture) is the whole table,
    unchanged. A month fixture is checked in two disjoint slices -- see
    ``_fixture_params()``."""
    if scope is None:
        return fixture.expected
    if scope == _IMPLEMENTED_MONTH_SCOPE:
        return {_IMPLEMENTED_MONTH_SCOPE: fixture.expected.get(_IMPLEMENTED_MONTH_SCOPE, [])}
    return {
        key: value for key, value in fixture.expected.items() if key != _IMPLEMENTED_MONTH_SCOPE
    }


def test_reports_zero_fixtures_without_failing() -> None:
    """AC2: fixture discovery is reported, not silently absorbed."""
    fixtures = discover_fixtures()

    assert isinstance(fixtures, list)
    assert fixtures != [], (
        "tests/conformance/fixtures/ has shipped real reference charts since "
        "Story 1.7 -- an empty result here would mean discovery silently "
        "stopped finding them, not that none exist"
    )


def _fixture_params() -> list[Any]:
    """One ``pytest.param`` per discovered natal fixture (real, Story 2.2)
    and *two* per discovered month fixture: ``transit_events`` (real, Story
    3.1) and ``remainder`` -- lunations/positions/stations, still behind the
    same ``xfail(raises=NotImplementedError)`` shape Story 1.6 gave every
    fixture, now scoped to only the sections actually still unimplemented.
    Each ``pytest.param`` carries ``(fixture_path, scope)``."""
    params: list[Any] = []
    for path in discover_fixtures():
        fixture = load_fixture(path)
        if _is_natal_fixture(fixture):
            params.append(pytest.param(path, None, id=path.stem))
            continue
        params.append(
            pytest.param(path, _IMPLEMENTED_MONTH_SCOPE, id=f"{path.stem}-transit_events")
        )
        params.append(
            pytest.param(
                path,
                "remainder",
                id=f"{path.stem}-remainder",
                marks=pytest.mark.xfail(
                    raises=NotImplementedError,
                    reason=(
                        "real Lunation/Station/position computation is not wired in yet "
                        "(Stories 3.2-3.4) -- see compute_output_for()"
                    ),
                ),
            )
        )
    return params


@pytest.mark.parametrize("fixture_path, scope", _fixture_params())
def test_computed_output_matches_conformance_fixture(fixture_path: Path, scope: str | None) -> None:
    fixture = load_fixture(fixture_path)
    computed = compute_output_for(fixture, scope)
    expected = _expected_for_scope(fixture, scope)

    mismatches = compare(fixture.name, expected, computed)

    assert not mismatches, "; ".join(
        f"{mismatch.field}: expected {mismatch.expected!r}, computed {mismatch.computed!r}"
        for mismatch in mismatches
    )
