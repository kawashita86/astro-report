"""``core/memory/diff.py::diff_themes()`` (Story 4.4, AD-14): pure,
model-free comparison of two consecutive months' ``ReportTheme``s. Covers
the story's I/O & Edge-Case Matrix plus the accepted same-identity-duplicate
limitation and ordering rules.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.memory.diff import diff_themes
from core.types.memory import AspectChange, ReportTheme, RetrogradeChange, ThemeAspect, ThemeDiff
from core.types.transits import StandingRetrograde

_T0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 10, 6, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 1, 15, 18, 0, 0, tzinfo=UTC)


def _theme_aspect(
    *,
    transiting_body: str = "saturn",
    natal_point: str = "sun",
    aspect: str = "square",
    perfected_at: datetime | None = _T1,
    never_perfected: bool = False,
    orb_entry_at: datetime = _T0,
    orb_exit_at: datetime | None = None,
) -> ThemeAspect:
    return ThemeAspect(
        transiting_body=transiting_body,
        natal_point=natal_point,
        aspect=aspect,
        perfected_at=perfected_at,
        never_perfected=never_perfected,
        orb_entry_at=orb_entry_at,
        orb_exit_at=orb_exit_at,
    )


def _retrograde(
    *, body: str = "saturn", start: datetime = _T0, end: datetime = _T2
) -> StandingRetrograde:
    return StandingRetrograde(body=body, retrograde_start_utc=start, retrograde_end_utc=end)


def _theme(
    *,
    aspects: tuple[ThemeAspect, ...] = (),
    retrogrades: tuple[StandingRetrograde, ...] = (),
) -> ReportTheme:
    return ReportTheme(dominant_aspects=aspects, lunations=(), standing_retrogrades=retrogrades)


# --- First month: no comparison attempted ---------------------------------------


def test_previous_none_returns_none() -> None:
    current = _theme(aspects=(_theme_aspect(),))

    assert diff_themes(None, current) is None


# --- Aspect classification: matched pairs -----------------------------------------


def test_still_active_aspect() -> None:
    previous = _theme(
        aspects=(_theme_aspect(perfected_at=_T0, never_perfected=False, orb_exit_at=None),)
    )
    current = _theme(
        aspects=(_theme_aspect(perfected_at=_T0, never_perfected=False, orb_exit_at=None),)
    )

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (
        AspectChange(aspect=current.dominant_aspects[0], status="still_active"),
    )


def test_tightened_aspect() -> None:
    previous = _theme(
        aspects=(_theme_aspect(perfected_at=None, never_perfected=True, orb_exit_at=None),)
    )
    current = _theme(
        aspects=(_theme_aspect(perfected_at=_T1, never_perfected=False, orb_exit_at=None),)
    )

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (
        AspectChange(aspect=current.dominant_aspects[0], status="tightened"),
    )


def test_resolved_aspect_separates_this_month() -> None:
    previous = _theme(aspects=(_theme_aspect(orb_exit_at=None),))
    current = _theme(aspects=(_theme_aspect(orb_exit_at=_T2),))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (
        AspectChange(aspect=current.dominant_aspects[0], status="resolved"),
    )


def test_fresh_pass_after_prior_separation_is_new_regardless_of_current_state() -> None:
    previous = _theme(aspects=(_theme_aspect(orb_exit_at=_T1),))
    # current's own state would otherwise read as tightened, but the prior
    # separation means this is a fresh pass, not a continuation.
    current = _theme(
        aspects=(_theme_aspect(perfected_at=_T2, never_perfected=False, orb_exit_at=None),)
    )

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (AspectChange(aspect=current.dominant_aspects[0], status="new"),)


# --- Aspect classification: unmatched ---------------------------------------------


def test_new_aspect_absent_from_previous() -> None:
    previous = _theme(aspects=())
    current = _theme(aspects=(_theme_aspect(),))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (AspectChange(aspect=current.dominant_aspects[0], status="new"),)


def test_resolved_aspect_absent_from_current() -> None:
    previous = _theme(aspects=(_theme_aspect(),))
    current = _theme(aspects=())

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (
        AspectChange(aspect=previous.dominant_aspects[0], status="resolved"),
    )


# --- Retrograde classification -----------------------------------------------------


def test_new_still_active_and_resolved_retrogrades() -> None:
    previous = _theme(
        retrogrades=(_retrograde(body="saturn"), _retrograde(body="jupiter"))
    )
    current = _theme(
        retrogrades=(_retrograde(body="saturn"), _retrograde(body="pluto"))
    )

    diff = diff_themes(previous, current)

    assert diff is not None
    changes_by_body = {change.retrograde.body: change.status for change in diff.retrograde_changes}
    assert changes_by_body == {"saturn": "still_active", "pluto": "new", "jupiter": "resolved"}


# --- Ordering -----------------------------------------------------------------------


def test_aspect_changes_ordering() -> None:
    new_in_current = _theme_aspect(transiting_body="mars", natal_point="sun", aspect="trine")
    matched_current = _theme_aspect(transiting_body="saturn", natal_point="moon", aspect="square")
    matched_previous = _theme_aspect(
        transiting_body="saturn", natal_point="moon", aspect="square", orb_exit_at=None
    )
    resolved_first = _theme_aspect(
        transiting_body="jupiter", natal_point="venus", aspect="opposition"
    )
    resolved_second = _theme_aspect(
        transiting_body="pluto", natal_point="mars", aspect="sextile"
    )

    previous = _theme(aspects=(resolved_first, matched_previous, resolved_second))
    current = _theme(aspects=(new_in_current, matched_current))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.aspect_changes == (
        AspectChange(aspect=new_in_current, status="new"),
        AspectChange(aspect=matched_current, status="still_active"),
        AspectChange(aspect=resolved_first, status="resolved"),
        AspectChange(aspect=resolved_second, status="resolved"),
    )


def test_retrograde_changes_ordering() -> None:
    new_in_current = _retrograde(body="mars")
    matched_current = _retrograde(body="saturn")
    matched_previous = _retrograde(body="saturn")
    resolved_first = _retrograde(body="jupiter")
    resolved_second = _retrograde(body="pluto")

    previous = _theme(retrogrades=(resolved_first, matched_previous, resolved_second))
    current = _theme(retrogrades=(new_in_current, matched_current))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.retrograde_changes == (
        RetrogradeChange(retrograde=new_in_current, status="new"),
        RetrogradeChange(retrograde=matched_current, status="still_active"),
        RetrogradeChange(retrograde=resolved_first, status="resolved"),
        RetrogradeChange(retrograde=resolved_second, status="resolved"),
    )


# --- Accepted limitation: same-identity duplicates within one ReportTheme --------


def test_duplicate_identity_on_current_side_keeps_last_representative() -> None:
    first = _theme_aspect(orb_exit_at=None)
    second = _theme_aspect(orb_exit_at=_T2)
    previous = _theme(aspects=())
    current = _theme(aspects=(first, second))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert len(diff.aspect_changes) == 1
    assert diff.aspect_changes[0] == AspectChange(aspect=second, status="new")


def test_duplicate_identity_on_previous_side_keeps_last_representative() -> None:
    first = _theme_aspect(orb_exit_at=None)
    second = _theme_aspect(orb_exit_at=_T2)
    previous = _theme(aspects=(first, second))
    current = _theme(aspects=())

    diff = diff_themes(previous, current)

    assert diff is not None
    assert len(diff.aspect_changes) == 1
    assert diff.aspect_changes[0] == AspectChange(aspect=second, status="resolved")


def test_duplicate_identity_on_both_sides_keeps_last_representative_of_each() -> None:
    previous_first = _theme_aspect(orb_exit_at=None)
    previous_second = _theme_aspect(orb_exit_at=None, perfected_at=None, never_perfected=True)
    current_first = _theme_aspect(perfected_at=_T2, never_perfected=False, orb_exit_at=None)
    current_second = _theme_aspect(orb_exit_at=_T2)

    previous = _theme(aspects=(previous_first, previous_second))
    current = _theme(aspects=(current_first, current_second))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert len(diff.aspect_changes) == 1
    # previous's kept representative (previous_second, never_perfected=True,
    # orb_exit_at=None) vs current's kept representative (current_second,
    # orb_exit_at=_T2): resolved takes priority over tightened.
    assert diff.aspect_changes[0] == AspectChange(aspect=current_second, status="resolved")


# --- nothing_significant_changed ---------------------------------------------------


def test_nothing_significant_changed_true_when_all_still_active() -> None:
    aspect_previous = _theme_aspect(perfected_at=_T0, orb_exit_at=None)
    aspect_current = _theme_aspect(perfected_at=_T0, orb_exit_at=None)
    retrograde = _retrograde()

    previous = _theme(aspects=(aspect_previous,), retrogrades=(retrograde,))
    current = _theme(aspects=(aspect_current,), retrogrades=(retrograde,))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.nothing_significant_changed is True


def test_nothing_significant_changed_true_when_both_diffs_empty() -> None:
    previous = _theme()
    current = _theme()

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.nothing_significant_changed is True


def test_nothing_significant_changed_false_driven_by_retrograde_alone() -> None:
    aspect_previous = _theme_aspect(perfected_at=_T0, orb_exit_at=None)
    aspect_current = _theme_aspect(perfected_at=_T0, orb_exit_at=None)

    previous = _theme(aspects=(aspect_previous,), retrogrades=())
    current = _theme(aspects=(aspect_current,), retrogrades=(_retrograde(),))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.nothing_significant_changed is False


def test_nothing_significant_changed_false_driven_by_tightened_aspect() -> None:
    previous = _theme(
        aspects=(_theme_aspect(perfected_at=None, never_perfected=True, orb_exit_at=None),)
    )
    current = _theme(
        aspects=(_theme_aspect(perfected_at=_T1, never_perfected=False, orb_exit_at=None),)
    )

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.nothing_significant_changed is False


def test_nothing_significant_changed_false_driven_by_resolved_aspect() -> None:
    previous = _theme(aspects=(_theme_aspect(orb_exit_at=None),))
    current = _theme(aspects=(_theme_aspect(orb_exit_at=_T2),))

    diff = diff_themes(previous, current)

    assert diff is not None
    assert diff.nothing_significant_changed is False


# --- Purity / determinism ----------------------------------------------------------


def test_same_pair_deterministic_rerun_is_byte_identical() -> None:
    previous = _theme(
        aspects=(_theme_aspect(orb_exit_at=None),), retrogrades=(_retrograde(),)
    )
    current = _theme(
        aspects=(_theme_aspect(perfected_at=_T2, orb_exit_at=None),),
        retrogrades=(_retrograde(),),
    )

    first = diff_themes(previous, current)
    second = diff_themes(previous, current)

    assert first is not None
    assert second is not None
    assert first == second
    assert isinstance(first, ThemeDiff)
