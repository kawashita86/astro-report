"""Assemble a ``Payload``: each Section's exact slice of a Natal Chart's
Domain Profiles and a month's Transit Events (Story 3.6).

Pure (AD-1): reads only the passed arguments, no I/O, clock, network or
randomness -- identical inputs produce a byte-identical ``Payload`` every
call. One generic filter, driven entirely by each Section's declarative
``SectionSpec`` (``data/sections.toml`` via ``shell/sections.py``), is
applied per event kind -- no ``if section == "amore"`` branching anywhere.
Adding or adjusting a Section's filter is a ``data/sections.toml`` edit, not
a code change.

``chart`` is accepted for the signature the story specifies but not read
here: every filter is already expressible from ``profiles`` (itself already
assembled from the Natal Chart, Story 2.5) and the Transit Event tuples --
see the story's Code Map note that ``NatalChart`` is "passed through
unfiltered", not duplicated into any ``SectionPayload``.
"""

from __future__ import annotations

from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.domains import DomainProfiles
from core.types.payload import Payload, SectionPayload
from core.types.sections import SectionsConfig, SectionSpec
from core.types.transits import (
    Ingress,
    Lunation,
    StandingRetrograde,
    Station,
    TransitAspectEvent,
)

__all__ = ["assemble_payload"]


def assemble_payload(
    chart: NatalChart,
    profiles: DomainProfiles,
    aspects: tuple[TransitAspectEvent, ...],
    stations: tuple[Station | StandingRetrograde, ...],
    ingresses: tuple[Ingress, ...],
    lunations: tuple[Lunation, ...],
    config: ComputationConfig,
    sections_config: SectionsConfig,
) -> Payload:
    """Build a ``Payload`` with one ``SectionPayload`` per Section named in
    ``sections_config.sections`` (exactly the six ``Payload`` fields).

    ``stations`` is the mixed ``Station | StandingRetrograde`` tuple
    ``find_stations()`` returns -- split here by ``isinstance``, mirroring
    ``shell/runner/driver.py``'s own ``_run_transits_ready`` split.

    Deterministic and side-effect free: no clock, I/O, network or database is
    consulted, so calling this twice with the same arguments returns two
    equal ``Payload`` values.
    """
    del chart

    station_events = tuple(event for event in stations if isinstance(event, Station))
    standing_retrograde_events = tuple(
        event for event in stations if isinstance(event, StandingRetrograde)
    )

    section_payloads = {
        name: _assemble_section(
            spec,
            profiles,
            aspects,
            station_events,
            standing_retrograde_events,
            ingresses,
            lunations,
            config,
        )
        for name, spec in sections_config.sections.items()
    }
    return Payload(**section_payloads)


def _assemble_section(
    spec: SectionSpec,
    profiles: DomainProfiles,
    aspects: tuple[TransitAspectEvent, ...],
    stations: tuple[Station, ...],
    standing_retrogrades: tuple[StandingRetrograde, ...],
    ingresses: tuple[Ingress, ...],
    lunations: tuple[Lunation, ...],
    config: ComputationConfig,
) -> SectionPayload:
    profile = getattr(profiles, spec.domain_profile) if spec.domain_profile is not None else None
    return SectionPayload(
        profile=profile,
        aspects=tuple(event for event in aspects if _matches_aspect(event, spec, config)),
        stations=tuple(event for event in stations if _matches_station(event, spec)),
        standing_retrogrades=tuple(
            event for event in standing_retrogrades if _matches_standing_retrograde(event, spec)
        ),
        ingresses=tuple(event for event in ingresses if _matches_ingress(event, spec, config)),
        lunations=tuple(event for event in lunations if spec.include_all_events),
    )


def _resolve_bodies(selector: str | None, config: ComputationConfig) -> frozenset[str]:
    """The configured body set a ``house_bodies``/``aspect_bodies`` selector
    resolves to: ``config.bodies.fast``, ``.slow``, or -- when ``None`` --
    both, unioned."""
    if selector == "fast":
        return frozenset(config.bodies.fast)
    if selector == "slow":
        return frozenset(config.bodies.slow)
    return frozenset(config.bodies.fast) | frozenset(config.bodies.slow)


def _matches_ingress(ingress: Ingress, spec: SectionSpec, config: ComputationConfig) -> bool:
    if spec.include_all_events:
        return True
    if not spec.houses:
        return False
    if ingress.house_departed not in spec.houses and ingress.house_entered not in spec.houses:
        return False
    return ingress.body in _resolve_bodies(spec.house_bodies, config)


def _matches_aspect(
    aspect: TransitAspectEvent, spec: SectionSpec, config: ComputationConfig
) -> bool:
    if spec.include_all_events:
        return True
    if not spec.aspect_natal_points:
        return False
    if aspect.natal_point not in spec.aspect_natal_points:
        return False
    return aspect.transiting_body in _resolve_bodies(spec.aspect_bodies, config)


def _matches_station(station: Station, spec: SectionSpec) -> bool:
    if spec.include_all_events:
        return True
    return spec.retrogrades and station.direction == "retrograde"


def _matches_standing_retrograde(
    standing_retrograde: StandingRetrograde, spec: SectionSpec
) -> bool:
    del standing_retrograde
    if spec.include_all_events:
        return True
    return spec.retrogrades
