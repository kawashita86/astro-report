"""``PLACE_CACHE``: a lookup accelerator for birthplace resolution (FR-2).

Consulted before every geocode call and written through after a fresh
unambiguous resolution. Per AD-16 it is an accelerator only, never a source
of truth once a Client has persisted its own immutable lat/lon/zone/name
snapshot -- nothing here is ever read back into an already-created Client.
Keyed on the *normalized* query text so trivial variation (case, surrounding
whitespace) still hits the cache; the geocoder, not this module, is the
source of truth for what a query resolves to.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

__all__ = [
    "CachedPlace",
    "PlaceCache",
    "lookup_cached_place",
    "normalize_place_text",
    "store_resolved_place",
]


class PlaceCache(SQLModel, table=True):
    """The ``PLACE_CACHE`` table. UUIDv7 primary key, matching every other
    table in this codebase."""

    __tablename__ = "place_cache"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    normalized_query: str = Field(unique=True, index=True)
    latitude: Decimal
    longitude: Decimal
    iana_zone: str
    #: The geocoder's own name for the match, cached alongside the
    #: coordinates so a cache hit can still supply one without re-querying
    #: Nominatim (AD-16, amended 2026-09-01). Nullable: a row cached before
    #: this column existed honestly has no recorded name, mirroring
    #: ``Client.birthplace_name``'s own nullability. ``lookup_cached_place()``
    #: passes a legacy ``NULL`` straight through as ``None`` rather than
    #: fabricating a value.
    display_name: str | None = Field(default=None, max_length=500)


@dataclass(frozen=True)
class CachedPlace:
    """The location facts a cache hit supplies. Deliberately excludes a UTC
    offset -- an offset is specific to a birth instant, not to a place, so
    the caller re-derives it from ``iana_zone`` locally rather than this
    module caching one offset per place and silently misapplying it to a
    different birth date."""

    latitude: Decimal
    longitude: Decimal
    iana_zone: str
    display_name: str | None


def normalize_place_text(place_text: str) -> str:
    """Fold case and surrounding whitespace so trivial variation of the same
    query still hits the cache."""
    return " ".join(place_text.split()).casefold()


def lookup_cached_place(session: Session, place_text: str) -> CachedPlace | None:
    normalized = normalize_place_text(place_text)
    row = session.exec(
        select(PlaceCache).where(PlaceCache.normalized_query == normalized)
    ).first()
    if row is None:
        return None
    return CachedPlace(
        latitude=row.latitude,
        longitude=row.longitude,
        iana_zone=row.iana_zone,
        display_name=row.display_name,
    )


def store_resolved_place(
    session: Session,
    place_text: str,
    *,
    latitude: Decimal,
    longitude: Decimal,
    iana_zone: str,
    display_name: str,
) -> None:
    """Write-through after a fresh unambiguous resolution.

    Scoped to a nested transaction (``SAVEPOINT``) and flushed rather than
    committed: this is an accelerator write, not the caller's transaction
    boundary. A caller building other pending work on the same session --
    Story 2.3 persists a Client on this same session -- must never have that
    work silently committed, or discarded, as a side effect of caching a
    place. Silently no-ops on a duplicate insert: two concurrent resolutions
    of the same never-before-cached place are a benign race for an
    accelerator, not a conflict either caller needs to know about, and the
    nested transaction confines that rollback to this row alone.
    """
    normalized = normalize_place_text(place_text)
    try:
        with session.begin_nested():
            session.add(
                PlaceCache(
                    normalized_query=normalized,
                    latitude=latitude,
                    longitude=longitude,
                    iana_zone=iana_zone,
                    display_name=display_name,
                )
            )
            session.flush()
    except IntegrityError:
        pass
