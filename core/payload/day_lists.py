"""Project the two day-lists (Sections 6/7, PRD FR-13) from an already
assembled ``Payload`` (Story 3.7).

Pure (AD-1): reads only the passed arguments, no I/O, clock, network or
randomness -- identical inputs produce an equal ``DayLists`` every call.
Reads only ``payload.consiglio_finale`` (the unfiltered ``SectionPayload``)
so Sections 6/7 stay downstream of the one assembled Payload like every
other Section, never re-deriving from raw scan output.

``chart`` is accepted alongside ``payload`` because ``assemble_payload()``
(Story 3.6) discards the ``NatalChart`` and ``SectionPayload`` never stores
it, but Lunation favorability needs the fourteen fixed natal targets
(``core/transits/aspects.py::_natal_targets()``) to re-test against.
"""

from __future__ import annotations

from core.ephemeris.chart import _match_aspect
from core.transits.aspects import _natal_targets
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig, HarmonicRule
from core.types.day_lists import DayLists
from core.types.payload import Payload
from core.types.transits import Lunation, TransitAspectEvent

__all__ = ["project_day_lists"]

#: Aspect types a Lunation qualifies as favorable on, regardless of which
#: natal point it forms them with.
_FAVORABLE_LUNATION_ASPECTS = frozenset({"trine", "sextile"})

#: Natal points a conjunct Lunation qualifies as favorable on -- conjunction
#: to any other natal point does not (mirrors ``HarmonicRule``'s conjunction
#: bodies being the exception to plain aspect-type classification).
_FAVORABLE_LUNATION_CONJUNCTION_POINTS = frozenset({"venus", "jupiter"})


def project_day_lists(payload: Payload, chart: NatalChart, config: ComputationConfig) -> DayLists:
    """Classify ``payload.consiglio_finale``'s dated Aspect Perfections,
    favorable Lunations and retrograde Stations into the two day lists.

    Only ``TransitAspectEvent``s with ``perfected_at is not None`` are
    eligible ("dated" excludes ``never_perfected=True``); an aspect matching
    neither ``config.harmonic``'s harmonic nor disharmonic rule is neutral,
    added to neither tuple. Only ``Station``s with ``direction ==
    "retrograde"`` enter ``giorni_di_attenzione`` -- ``StandingRetrograde``
    never does, having no Station to classify. Entries keep
    ``payload.consiglio_finale``'s own relative order within each source
    kind -- never re-sorted by date.
    """
    section = payload.consiglio_finale
    harmonic = config.harmonic

    dated_classifications = [
        (event, _classify_aspect(event, harmonic))
        for event in section.aspects
        if event.perfected_at is not None
    ]
    favorable_aspects = tuple(
        event for event, classification in dated_classifications if classification == "harmonic"
    )
    attention_aspects = tuple(
        event for event, classification in dated_classifications if classification == "disharmonic"
    )
    favorable_lunations = tuple(
        lunation
        for lunation in section.lunations
        if _is_favorable_lunation(lunation, chart, config)
    )
    attention_stations = tuple(
        station for station in section.stations if station.direction == "retrograde"
    )

    return DayLists(
        giorni_favorevoli=favorable_aspects + favorable_lunations,
        giorni_di_attenzione=attention_aspects + attention_stations,
    )


def _classify_aspect(event: TransitAspectEvent, harmonic: HarmonicRule) -> str | None:
    """``"harmonic"``, ``"disharmonic"`` or ``None`` (neutral) for one
    Aspect Perfection.

    Conjunction classifies by ``event.transiting_body`` against
    ``harmonic.harmonic_conjunction_bodies``/``disharmonic_conjunction_bodies``;
    every other aspect by membership in ``harmonic.harmonic_aspects``/
    ``disharmonic_aspects``.
    """
    if event.aspect == "conjunction":
        if event.transiting_body in harmonic.harmonic_conjunction_bodies:
            return "harmonic"
        if event.transiting_body in harmonic.disharmonic_conjunction_bodies:
            return "disharmonic"
        return None
    if event.aspect in harmonic.harmonic_aspects:
        return "harmonic"
    if event.aspect in harmonic.disharmonic_aspects:
        return "disharmonic"
    return None


def _is_favorable_lunation(
    lunation: Lunation, chart: NatalChart, config: ComputationConfig
) -> bool:
    """True when ``lunation.longitude`` trines/sextiles any of the chart's
    fourteen fixed natal targets within ``config.orbs.transit``, or is
    conjunct natal Venus or Jupiter within that same Orb."""
    for name, target_longitude in _natal_targets(chart):
        match = _match_aspect(lunation.longitude, target_longitude, config.orbs.transit)
        if match is None:
            continue
        aspect_name, _orb = match
        if aspect_name in _FAVORABLE_LUNATION_ASPECTS:
            return True
        if aspect_name == "conjunction" and name in _FAVORABLE_LUNATION_CONJUNCTION_POINTS:
            return True
    return False
