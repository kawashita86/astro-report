"""``Payload``: one ``SectionPayload`` per Report Section (Story 3.6), the
byte-identical, persisted computation result each Section's future Generator
call reads from -- never hunts for its own facts by re-deriving them from
raw event lists.

Living in ``core/types/`` rather than ``core/payload/`` mirrors
``core/types/domains.py``/``core/types/transits.py``: these are pure data,
assembled by ``core/payload/assemble.py::assemble_payload()`` from an
already-computed ``NatalChart``, ``DomainProfiles`` and a month's Transit
Events, with no logic beyond the dataclass machinery itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.types.domains import AmoreProfile, BenessereProfile, DenaroProfile, LavoroProfile
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent

__all__ = ["Payload", "SectionPayload"]


@dataclass(frozen=True)
class SectionPayload:
    """One Section's exact slice of the month's computed facts.

    ``profile`` is the matching ``DomainProfiles`` attribute for a Section
    whose ``SectionSpec.domain_profile`` names one, or ``None`` for a
    Section with no single Domain Profile (``energia_generale``,
    ``consiglio_finale``). Every other field is the subset of that event
    kind ``SectionSpec``'s filter matched -- possibly empty, never ``None``.
    """

    profile: AmoreProfile | LavoroProfile | DenaroProfile | BenessereProfile | None
    aspects: tuple[TransitAspectEvent, ...]
    stations: tuple[Station, ...]
    standing_retrogrades: tuple[StandingRetrograde, ...]
    ingresses: tuple[Ingress, ...]
    lunations: tuple[Lunation, ...]


@dataclass(frozen=True)
class Payload:
    """The six Sections' ``SectionPayload``s assembled from one Natal Chart,
    its Domain Profiles and one month's Transit Events (Story 3.6).

    Sections 6/7's day-lists (harmonic/disharmonic classification) are a
    Story 3.7 projection, not part of this mapping.
    """

    energia_generale: SectionPayload
    amore: SectionPayload
    lavoro: SectionPayload
    denaro: SectionPayload
    benessere: SectionPayload
    consiglio_finale: SectionPayload
