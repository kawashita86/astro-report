"""``core/transits/_month_grid.py`` -- the shared grid/bisection scaffolding
lifted out of the four ``core/transits`` scans (epic-3-retro-item-19).

Covers the I/O & Edge-Case Matrix rows for ``_require_utc_interval``,
``_build_grid`` and ``_bisect`` directly, so a regression in the extracted
code is caught here and not only through a full conformance run.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.transits._month_grid import (
    _BISECTION_ITERATIONS,
    _GRID_STEP,
    _bisect,
    _build_grid,
    _require_utc_interval,
)

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = datetime(2026, 2, 1, tzinfo=UTC)


def test_shared_constants_keep_the_values_the_four_modules_relied_on() -> None:
    assert _GRID_STEP.total_seconds() == 6 * 60 * 60
    assert _BISECTION_ITERATIONS == 40


def test_require_utc_interval_accepts_a_valid_aware_utc_interval() -> None:
    _require_utc_interval(_START, _END)  # no raise


def test_require_utc_interval_rejects_a_naive_boundary() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _require_utc_interval(_START.replace(tzinfo=None), _END)


def test_require_utc_interval_rejects_a_non_zero_utcoffset() -> None:
    plus_two = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    with pytest.raises(ValueError, match="utcoffset"):
        _require_utc_interval(plus_two, _END)


@pytest.mark.parametrize("start", [_END, _START])
def test_require_utc_interval_rejects_start_not_strictly_before_end(start: datetime) -> None:
    with pytest.raises(ValueError, match="strictly before"):
        _require_utc_interval(start, _START)


def test_build_grid_steps_at_grid_step_then_appends_end_verbatim() -> None:
    end = _START + timedelta(days=1)
    grid = _build_grid(_START, end)

    assert grid[0] == _START
    assert grid[-1] == end
    interior = grid[:-1]
    assert all(instant < end for instant in interior)
    assert all(
        later - earlier == _GRID_STEP
        for earlier, later in zip(interior, interior[1:], strict=False)
    )
    # 24h / 6h == 4 interior samples, plus the appended end probe.
    assert grid == [
        _START,
        _START + timedelta(hours=6),
        _START + timedelta(hours=12),
        _START + timedelta(hours=18),
        end,
    ]


def test_build_grid_appends_end_when_the_interval_is_not_a_whole_number_of_steps() -> None:
    # 20 hours: two full 6h steps (00:00, 06:00, 12:00, 18:00), then a 2h
    # remainder up to `end` -- the "crossing in the last partial grid step"
    # case _month_grid.py's docstring justifies.
    end = _START + timedelta(hours=20)
    grid = _build_grid(_START, end)

    assert grid == [
        _START,
        _START + timedelta(hours=6),
        _START + timedelta(hours=12),
        _START + timedelta(hours=18),
        end,
    ]
    assert grid[-1] == end
    assert all(instant < end for instant in grid[:-1])
    assert grid[-1] - grid[-2] == timedelta(hours=2)  # partial final remainder


def test_build_grid_on_an_interval_shorter_than_one_step_is_just_start_then_end() -> None:
    end = _START + timedelta(hours=1)
    grid = _build_grid(_START, end)

    assert grid == [_START, end]
    assert grid[-1] == end
    assert all(instant < end for instant in grid[:-1])


def test_bisect_returns_lo_when_f_lo_is_zero() -> None:
    assert _bisect(lambda _instant: Decimal(0), _START, _END) == _START


def test_bisect_returns_hi_when_only_f_hi_is_zero() -> None:
    def f(instant: datetime) -> Decimal:
        return Decimal(0) if instant == _END else Decimal(-1)

    assert _bisect(f, _START, _END) == _END


def test_bisect_narrows_an_opposite_sign_bracket_to_sub_second_precision() -> None:
    root = datetime(2026, 1, 15, 7, 0, tzinfo=UTC)

    def f(instant: datetime) -> Decimal:
        return Decimal((instant - root).total_seconds())

    result = _bisect(f, _START, _END)

    assert abs((result - root).total_seconds()) < 1
