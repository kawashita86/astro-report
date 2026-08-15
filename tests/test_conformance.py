"""The CI-visible conformance entry point (Story 1.6, populated by Story 1.7).

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
  ``compute_output_for()`` -- the single, clearly-named call site where real
  Epic 2/3 computation eventually plugs in. That function raises
  ``NotImplementedError`` until then; every discovered fixture is marked
  ``xfail(raises=NotImplementedError)`` for the same reason, so CI stays
  green pre-Epic-2/3 without hiding a real regression -- the moment
  ``compute_output_for`` is wired in, any fixture that now matches flips to
  XPASS, which is the visible signal to remove that fixture's xfail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.conformance.runner import Fixture, compare, discover_fixtures, load_fixture


def compute_output_for(fixture: Fixture) -> dict[str, Any]:
    """Compute the output a real chart engine would produce for ``fixture``.

    Not implemented: Epic 2 (natal core) and Epic 3 (transits/payload) do
    not exist yet. Wiring this in later is meant to be writing this one
    function, not redesigning the harness (see the story's Design Notes).
    """
    raise NotImplementedError(
        f"real computation is not wired in yet (Epic 2/3): fixture {fixture.name!r}"
    )


def test_reports_zero_fixtures_without_failing() -> None:
    """AC2: fixture discovery is reported, not silently absorbed."""
    fixtures = discover_fixtures()

    assert isinstance(fixtures, list)
    assert fixtures != [], (
        "tests/conformance/fixtures/ has shipped real reference charts since "
        "Story 1.7 -- an empty result here would mean discovery silently "
        "stopped finding them, not that none exist"
    )


@pytest.mark.parametrize("fixture_path", discover_fixtures(), ids=lambda path: path.stem)
@pytest.mark.xfail(
    raises=NotImplementedError,
    reason="real computation is not wired in yet (Epic 2/3) -- see compute_output_for()",
)
def test_computed_output_matches_conformance_fixture(fixture_path: Path) -> None:
    fixture = load_fixture(fixture_path)
    computed = compute_output_for(fixture)

    mismatches = compare(fixture.name, fixture.expected, computed)

    assert not mismatches, "; ".join(
        f"{mismatch.field}: expected {mismatch.expected!r}, computed {mismatch.computed!r}"
        for mismatch in mismatches
    )
