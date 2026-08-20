"""Derive a ``ReportTheme`` from a ``Payload`` (Story 4.3, AD-14).

Pure and model-free (AD-1): reads only the passed arguments, no I/O, clock,
network, randomness or Generator call -- identical inputs produce a
byte-identical (``==``) ``ReportTheme`` every call, which is what lets Story
4.4's diffing trust that two runs of the same month never seed different
continuity the following month.

Every slow-planet Aspect, Lunation and StandingRetrograde is collected across
all six of a ``Payload``'s ``SectionPayload``s -- a fact belonging to more
than one Section (e.g. Saturn square Sun matched by both ``amore`` and
``lavoro``) appears once per Section's tuple of raw event objects, but those
objects are frozen dataclasses, so the same underlying event repeated across
Sections is ``==``. Each collection loop below fills a ``dict`` keyed on
these event objects (values unused) as it walks the six Sections -- a
repeat occurrence overwrites the same key rather than adding a new one -- so
the dict's keys, read back afterward, are already deduplicated before any
deterministic re-sorting happens (Design Notes).
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from core.types.computation import ComputationConfig
from core.types.memory import ReportTheme, ThemeAspect, ThemeLunation
from core.types.payload import Payload, SectionPayload
from core.types.transits import Lunation, StandingRetrograde, TransitAspectEvent

__all__ = ["derive_theme"]


def _section_payloads(payload: Payload) -> tuple[SectionPayload, ...]:
    return tuple(getattr(payload, field.name) for field in dataclass_fields(payload))


def _to_theme_aspect(event: TransitAspectEvent) -> ThemeAspect:
    return ThemeAspect(
        transiting_body=event.transiting_body,
        natal_point=event.natal_point,
        aspect=event.aspect,
        perfected_at=event.perfected_at,
        never_perfected=event.never_perfected,
        orb_entry_at=event.orb_entry_at,
        orb_exit_at=event.orb_exit_at,
    )


def _aspect_tightness_key(event: TransitAspectEvent) -> tuple[int, bool, float]:
    """Ask First's default tightness order: still-in-orb-at-month-end
    Aspects (``orb_exit_at is None``) first, by ``perfected_at`` descending
    (``None`` last); separated ones follow, by ``orb_exit_at`` descending.

    No event carries a numeric orb-degree, so ``perfected_at``/
    ``orb_exit_at`` are the only signals available. Returns an ascending sort
    key: group 0 (still open) before group 1 (separated); within a group, a
    negated timestamp sorts a later instant first (descending), and a
    boolean ``True`` (a missing ``perfected_at``) sorts after ``False``
    (``None`` last).
    """
    if event.orb_exit_at is None:
        perfected_at_missing = event.perfected_at is None
        timestamp = 0.0 if perfected_at_missing else -event.perfected_at.timestamp()
        return (0, perfected_at_missing, timestamp)
    return (1, False, -event.orb_exit_at.timestamp())


def derive_theme(payload: Payload, config: ComputationConfig) -> ReportTheme:
    """Collect every slow-planet Aspect, Lunation and StandingRetrograde
    across ``payload``'s six ``SectionPayload``s, dedupe each, and return the
    ``ReportTheme`` Story 4.4's diffing and the Generator port both need.

    Only Aspects whose ``transiting_body`` is one of ``config.bodies.slow``
    are kept -- ``dominant_aspects`` is a slow-planet reading by definition
    (AD-14). No top-N truncation: every deduplicated slow Aspect, Lunation
    and StandingRetrograde is kept, in full.
    """
    sections = _section_payloads(payload)
    slow_bodies = frozenset(config.bodies.slow)

    aspect_events: dict[TransitAspectEvent, None] = {}
    lunation_events: dict[Lunation, None] = {}
    standing_retrograde_events: dict[StandingRetrograde, None] = {}

    for section in sections:
        for aspect_event in section.aspects:
            if aspect_event.transiting_body in slow_bodies:
                aspect_events[aspect_event] = None
        for lunation in section.lunations:
            lunation_events[lunation] = None
        for standing_retrograde in section.standing_retrogrades:
            standing_retrograde_events[standing_retrograde] = None

    dominant_aspects = tuple(
        _to_theme_aspect(event)
        for event in sorted(aspect_events, key=_aspect_tightness_key)
    )
    lunations = tuple(
        ThemeLunation(kind=lunation.kind, natal_house=lunation.natal_house)
        for lunation in sorted(
            lunation_events, key=lambda item: (item.occurred_at, item.kind, item.natal_house)
        )
    )
    standing_retrogrades = tuple(
        sorted(
            standing_retrograde_events,
            key=lambda item: (item.body, item.retrograde_start_utc),
        )
    )

    return ReportTheme(
        dominant_aspects=dominant_aspects,
        lunations=lunations,
        standing_retrogrades=standing_retrogrades,
    )
