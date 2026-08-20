"""``core/memory/derive.py::derive_theme()`` (Story 4.3, AD-14): pure,
model-free summary of a ``Payload`` into a ``ReportTheme``. Covers the story's
I/O & Edge-Case Matrix plus the Ask First tightness order for
``dominant_aspects``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from core.memory.derive import derive_theme
from core.types.memory import ThemeAspect, ThemeLunation
from core.types.payload import Payload, SectionPayload
from core.types.transits import Lunation, StandingRetrograde, TransitAspectEvent
from shell.computation import load_computation_config

_COMPUTATION_CONFIG = load_computation_config()

# The real data/computation.toml slow/fast sets (Story 1.5): fast excludes
# every slow body and vice versa, so any body drawn from one set is never
# accidentally also in the other.
_A_SLOW_BODY = _COMPUTATION_CONFIG.bodies.slow[0]
_ANOTHER_SLOW_BODY = _COMPUTATION_CONFIG.bodies.slow[1]
_A_FAST_BODY = _COMPUTATION_CONFIG.bodies.fast[0]

_T0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 1, 10, 6, 0, 0, tzinfo=UTC)
_T2 = datetime(2026, 1, 15, 18, 0, 0, tzinfo=UTC)


def _empty_section() -> SectionPayload:
    return SectionPayload(
        profile=None, aspects=(), stations=(), standing_retrogrades=(), ingresses=(), lunations=()
    )


def _payload(
    *,
    amore_aspects: tuple[TransitAspectEvent, ...] = (),
    lavoro_aspects: tuple[TransitAspectEvent, ...] = (),
    lunations: tuple[Lunation, ...] = (),
    lavoro_lunations: tuple[Lunation, ...] | None = None,
    standing_retrogrades: tuple[StandingRetrograde, ...] = (),
    lavoro_standing_retrogrades: tuple[StandingRetrograde, ...] | None = None,
) -> Payload:
    amore = SectionPayload(
        profile=None,
        aspects=amore_aspects,
        stations=(),
        standing_retrogrades=standing_retrogrades,
        ingresses=(),
        lunations=lunations,
    )
    lavoro = SectionPayload(
        profile=None,
        aspects=lavoro_aspects,
        stations=(),
        standing_retrogrades=(
            lavoro_standing_retrogrades
            if lavoro_standing_retrogrades is not None
            else standing_retrogrades
        ),
        ingresses=(),
        lunations=lavoro_lunations if lavoro_lunations is not None else lunations,
    )
    return Payload(
        energia_generale=_empty_section(),
        amore=amore,
        lavoro=lavoro,
        denaro=_empty_section(),
        benessere=_empty_section(),
        consiglio_finale=_empty_section(),
    )


def _slow_aspect(
    *,
    transiting_body: str = _A_SLOW_BODY,
    natal_point: str = "sun",
    aspect: str = "square",
    perfected_at: datetime | None = _T1,
    never_perfected: bool = False,
    orb_entry_at: datetime = _T0,
    orb_exit_at: datetime | None = None,
) -> TransitAspectEvent:
    return TransitAspectEvent(
        transiting_body=transiting_body,
        natal_point=natal_point,
        aspect=aspect,
        perfected_at=perfected_at,
        never_perfected=never_perfected,
        orb_entry_at=orb_entry_at,
        orb_exit_at=orb_exit_at,
    )


# --- I/O Matrix: no slow-planet Aspects -----------------------------------------


def test_only_fast_body_aspects_yields_empty_dominant_aspects() -> None:
    fast_aspect = _slow_aspect(transiting_body=_A_FAST_BODY)
    payload = _payload(amore_aspects=(fast_aspect,))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.dominant_aspects == ()


# --- I/O Matrix: same slow Aspect in multiple Sections dedupes -----------------


def test_same_slow_aspect_in_multiple_sections_dedupes_to_one_theme_aspect() -> None:
    shared_aspect = _slow_aspect()
    payload = _payload(amore_aspects=(shared_aspect,), lavoro_aspects=(shared_aspect,))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert len(theme.dominant_aspects) == 1
    assert theme.dominant_aspects[0] == ThemeAspect(
        transiting_body=shared_aspect.transiting_body,
        natal_point=shared_aspect.natal_point,
        aspect=shared_aspect.aspect,
        perfected_at=shared_aspect.perfected_at,
        never_perfected=shared_aspect.never_perfected,
        orb_entry_at=shared_aspect.orb_entry_at,
        orb_exit_at=shared_aspect.orb_exit_at,
    )


# --- I/O Matrix: no Lunations / Retrogrades -------------------------------------


def test_no_lunations_or_retrogrades_yields_empty_tuples() -> None:
    payload = _payload()

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.lunations == ()
    assert theme.standing_retrogrades == ()


# --- Purity ----------------------------------------------------------------------


def test_the_same_payload_always_yields_an_equal_theme() -> None:
    payload = _payload(
        amore_aspects=(_slow_aspect(),),
        lunations=(
            Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("15"), natal_house=3),
        ),
        standing_retrogrades=(
            StandingRetrograde(
                body=_A_SLOW_BODY, retrograde_start_utc=_T0, retrograde_end_utc=_T2
            ),
        ),
    )

    first = derive_theme(payload, _COMPUTATION_CONFIG)
    second = derive_theme(payload, _COMPUTATION_CONFIG)

    assert first == second


# --- Lunations reduced to kind + natal_house, deduped ---------------------------


def test_lunation_is_reduced_to_kind_and_natal_house() -> None:
    lunation = Lunation(kind="full_moon", occurred_at=_T0, longitude=Decimal("195"), natal_house=9)
    payload = _payload(lunations=(lunation,))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.lunations == (ThemeLunation(kind="full_moon", natal_house=9),)


def test_the_same_lunation_repeated_across_sections_dedupes_to_one() -> None:
    lunation = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("15"), natal_house=3)
    payload = _payload(lunations=(lunation,), lavoro_lunations=(lunation,))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.lunations == (ThemeLunation(kind="new_moon", natal_house=3),)


def test_two_distinct_lunations_both_survive() -> None:
    new_moon = Lunation(kind="new_moon", occurred_at=_T0, longitude=Decimal("15"), natal_house=3)
    full_moon = Lunation(kind="full_moon", occurred_at=_T1, longitude=Decimal("195"), natal_house=9)
    payload = _payload(lunations=(new_moon, full_moon))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert set(theme.lunations) == {
        ThemeLunation(kind="new_moon", natal_house=3),
        ThemeLunation(kind="full_moon", natal_house=9),
    }


# --- StandingRetrogrades deduped, carried through unchanged ---------------------


def test_the_same_standing_retrograde_repeated_across_sections_dedupes_to_one() -> None:
    retrograde = StandingRetrograde(
        body=_A_SLOW_BODY, retrograde_start_utc=_T0, retrograde_end_utc=_T2
    )
    payload = _payload(standing_retrogrades=(retrograde,))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.standing_retrogrades == (retrograde,)


def test_two_distinct_standing_retrogrades_both_survive() -> None:
    first = StandingRetrograde(body=_A_SLOW_BODY, retrograde_start_utc=_T0, retrograde_end_utc=_T2)
    second = StandingRetrograde(
        body=_ANOTHER_SLOW_BODY, retrograde_start_utc=_T0, retrograde_end_utc=_T2
    )
    payload = _payload(standing_retrogrades=(first, second))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert set(theme.standing_retrogrades) == {first, second}


# --- Ask First tightness order for dominant_aspects -----------------------------


def test_still_open_aspects_sort_before_separated_ones() -> None:
    still_open = _slow_aspect(natal_point="sun", perfected_at=_T0, orb_exit_at=None)
    separated = _slow_aspect(natal_point="moon", perfected_at=_T0, orb_exit_at=_T1)
    payload = _payload(amore_aspects=(separated, still_open))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert theme.dominant_aspects[0].natal_point == "sun"
    assert theme.dominant_aspects[1].natal_point == "moon"


def test_still_open_aspects_sort_by_perfected_at_descending() -> None:
    earlier = _slow_aspect(natal_point="sun", perfected_at=_T0, orb_exit_at=None)
    later = _slow_aspect(natal_point="moon", perfected_at=_T1, orb_exit_at=None)
    payload = _payload(amore_aspects=(earlier, later))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert [aspect.natal_point for aspect in theme.dominant_aspects] == ["moon", "sun"]


def test_never_perfected_still_open_aspects_sort_last_within_the_group() -> None:
    perfected = _slow_aspect(natal_point="sun", perfected_at=_T0, orb_exit_at=None)
    never_perfected = _slow_aspect(
        natal_point="moon", perfected_at=None, never_perfected=True, orb_exit_at=None
    )
    payload = _payload(amore_aspects=(never_perfected, perfected))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert [aspect.natal_point for aspect in theme.dominant_aspects] == ["sun", "moon"]


def test_separated_aspects_sort_by_orb_exit_at_descending() -> None:
    exited_earlier = _slow_aspect(natal_point="sun", perfected_at=_T0, orb_exit_at=_T1)
    exited_later = _slow_aspect(natal_point="moon", perfected_at=_T0, orb_exit_at=_T2)
    payload = _payload(amore_aspects=(exited_earlier, exited_later))

    theme = derive_theme(payload, _COMPUTATION_CONFIG)

    assert [aspect.natal_point for aspect in theme.dominant_aspects] == ["moon", "sun"]
