"""The CI-visible conformance entry point (Story 1.6).

Two tests, matching the story's own AC2/AC3 split:

- ``test_reports_zero_fixtures_without_failing`` proves AC2 explicitly. An
  empty fixture set must be *reported*, not merely absent: a parametrized
  test over zero fixtures contributes zero cases and would pass vacuously,
  which satisfies "doesn't fail" but not "reports."
- ``test_computed_output_matches_conformance_fixture`` is the parametrized
  entry point real fixtures (Story 1.7) will run under. It calls
  ``compute_output_for()`` -- the single, clearly-named call site where real
  Epic 2/3 computation eventually plugs in. That function raises
  ``NotImplementedError`` until then, and is never reached while
  ``tests/conformance/fixtures/`` is empty: a parametrize over zero
  discovered fixtures contributes zero cases and never executes the test
  body (AC2/AC3's synthetic-mismatch proof lives instead in
  ``tests/test_conformance_runner.py``, which does not depend on this).
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
    """AC2: an empty fixture set is reported, not silently absorbed."""
    fixtures = discover_fixtures()

    assert isinstance(fixtures, list)
    assert fixtures == [], (
        "tests/conformance/fixtures/ ships empty until Story 1.7 adds the "
        "first transcribed reference charts"
    )


@pytest.mark.parametrize("fixture_path", discover_fixtures(), ids=lambda path: path.stem)
def test_computed_output_matches_conformance_fixture(fixture_path: Path) -> None:
    fixture = load_fixture(fixture_path)
    computed = compute_output_for(fixture)

    mismatches = compare(fixture.name, fixture.expected, computed)

    assert not mismatches, "; ".join(
        f"{mismatch.field}: expected {mismatch.expected!r}, computed {mismatch.computed!r}"
        for mismatch in mismatches
    )
