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

  Story 2.2 is natal-only: Epic 3's transit engine does not exist yet, so
  the three month fixtures (``birth_data`` keyed by ``anchor_natal_fixture``/
  ``month``/``transit_snapshot_utc``, not a birth instant) are not something
  ``compute_output_for()`` can produce output for. Rather than let those
  three error out now that the blanket ``xfail`` is gone, each fixture is
  parametrized individually: a natal fixture runs for real, a non-natal one
  keeps the same ``xfail(raises=NotImplementedError)`` shape Story 1.6 used
  for every fixture -- still the visible "flip to XPASS the day this is
  wired in" signal ``xfail_strict`` was set up for, just scoped to the
  fixtures actually still unimplemented.

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

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.chart import NatalChart
from shell.computation import load_computation_config
from tests.conformance.runner import Fixture, compare, discover_fixtures, load_fixture

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


def compute_output_for(fixture: Fixture) -> dict[str, Any]:
    """Compute the output a real chart engine produces for ``fixture``,
    shaped to match ``fixture.expected``'s dict/list format.

    The single, clearly-named call site real Epic 2/3 computation plugs into
    (see the story's Design Notes): Story 2.2 wires in
    ``compute_natal_chart()`` for natal fixtures; a future Epic 3 story adds
    transit events for month fixtures, which still raise here.
    """
    if not _is_natal_fixture(fixture):
        raise NotImplementedError(
            f"real transit computation is not wired in yet (Epic 3): fixture {fixture.name!r}"
        )

    birth_instant_utc = _birth_instant_utc(fixture.birth_data)
    latitude = Decimal(fixture.birth_data["latitude"])
    longitude = Decimal(fixture.birth_data["longitude"])

    chart = compute_natal_chart(birth_instant_utc, latitude, longitude, _COMPUTATION_CONFIG)

    return _shape_chart_for_conformance(chart)


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
    """One ``pytest.param`` per discovered fixture: a natal fixture (Story
    2.2) runs for real; a month/transit fixture (still Epic 3) keeps the
    ``xfail(raises=NotImplementedError)`` shape Story 1.6 gave every fixture,
    scoped down to only the ones actually still unimplemented."""
    params = []
    for path in discover_fixtures():
        fixture = load_fixture(path)
        marks = (
            ()
            if _is_natal_fixture(fixture)
            else (
                pytest.mark.xfail(
                    raises=NotImplementedError,
                    reason=(
                        "real transit computation is not wired in yet (Epic 3) -- "
                        "see compute_output_for()"
                    ),
                ),
            )
        )
        params.append(pytest.param(path, id=path.stem, marks=marks))
    return params


@pytest.mark.parametrize("fixture_path", _fixture_params())
def test_computed_output_matches_conformance_fixture(fixture_path: Path) -> None:
    fixture = load_fixture(fixture_path)
    computed = compute_output_for(fixture)

    mismatches = compare(fixture.name, fixture.expected, computed)

    assert not mismatches, "; ".join(
        f"{mismatch.field}: expected {mismatch.expected!r}, computed {mismatch.computed!r}"
        for mismatch in mismatches
    )
