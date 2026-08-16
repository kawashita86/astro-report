"""Nominatim ``Geocoder`` adapter: geocode via ``geopy``, then derive the
historical UTC offset via ``timezonefinder`` + ``zoneinfo`` (FR-2).

``PLACE_CACHE`` (``shell/adapters/postgres/place_cache.py``) is consulted
first so a repeat place never re-queries Nominatim. A cache hit still
re-derives the offset locally from the cached zone and the *current* birth
instant -- the zone is a property of the place, the offset is not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from geopy.geocoders import Nominatim
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session
from timezonefinder import TimezoneFinder

from core.errors import PlaceResolutionError
from core.types.place import PlaceCandidate, ResolvedPlace
from shell.adapters.postgres.place_cache import (
    CachedPlace,
    lookup_cached_place,
    store_resolved_place,
)

__all__ = ["NominatimGeocoder"]

#: Nominatim's usage policy requires a descriptive User-Agent identifying the
#: application, not a browser default.
_USER_AGENT = "astro-report-geocoder (single-operator natal chart tool)"


class _GeocoderClient(Protocol):
    def geocode(self, query: str, exactly_one: bool) -> list[Any] | None: ...


class _TimezoneLookup(Protocol):
    def timezone_at(self, *, lat: float, lng: float) -> str | None: ...


class NominatimGeocoder:
    """The ``Geocoder`` port implementation this application runs against.

    ``geolocator`` and ``timezone_finder`` are injectable so tests exercise
    the resolution and caching logic against fakes, without a real network
    call or the multi-hundred-megabyte timezone dataset.
    """

    def __init__(
        self,
        session: Session,
        *,
        geolocator: _GeocoderClient | None = None,
        timezone_finder: _TimezoneLookup | None = None,
    ) -> None:
        self._session = session
        self._geolocator = geolocator or Nominatim(user_agent=_USER_AGENT)
        self._timezone_finder = timezone_finder or TimezoneFinder()

    def resolve(
        self, place_text: str, birth_local_time: datetime
    ) -> ResolvedPlace | list[PlaceCandidate]:
        if birth_local_time.tzinfo is not None:
            raise ValueError(
                "birth_local_time must be naive: it is the wall-clock time as "
                "entered, and the zone it belongs to is what resolution determines."
            )

        cached = self._lookup_cache(place_text)
        if cached is not None:
            return ResolvedPlace(
                latitude=cached.latitude,
                longitude=cached.longitude,
                iana_zone=cached.iana_zone,
                utc_offset=self._historical_offset(cached.iana_zone, birth_local_time),
            )

        candidates = self._geocode(place_text)
        if len(candidates) > 1:
            return [
                PlaceCandidate(
                    display_name=candidate.address,
                    latitude=_to_decimal(candidate.latitude),
                    longitude=_to_decimal(candidate.longitude),
                )
                for candidate in candidates
            ]

        match = candidates[0]
        latitude = _to_decimal(match.latitude)
        longitude = _to_decimal(match.longitude)
        iana_zone = self._zone_for(latitude, longitude)
        # Computed before the cache write so an ambiguous/nonexistent birth
        # instant is rejected before a place is ever persisted to the cache.
        utc_offset = self._historical_offset(iana_zone, birth_local_time)
        store_resolved_place(
            self._session,
            place_text,
            latitude=latitude,
            longitude=longitude,
            iana_zone=iana_zone,
        )
        return ResolvedPlace(
            latitude=latitude,
            longitude=longitude,
            iana_zone=iana_zone,
            utc_offset=utc_offset,
        )

    def resolve_candidate(
        self, candidate: PlaceCandidate, birth_local_time: datetime
    ) -> ResolvedPlace:
        if birth_local_time.tzinfo is not None:
            raise ValueError(
                "birth_local_time must be naive: it is the wall-clock time as "
                "entered, and the zone it belongs to is what resolution determines."
            )

        iana_zone = self._zone_for(candidate.latitude, candidate.longitude)
        utc_offset = self._historical_offset(iana_zone, birth_local_time)
        return ResolvedPlace(
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            iana_zone=iana_zone,
            utc_offset=utc_offset,
        )

    def _lookup_cache(self, place_text: str) -> CachedPlace | None:
        try:
            return lookup_cached_place(self._session, place_text)
        except SQLAlchemyError as error:
            raise PlaceResolutionError("cache", f"reading {place_text!r}: {error}") from error

    def _geocode(self, place_text: str) -> list[Any]:
        try:
            results = self._geolocator.geocode(place_text, exactly_one=False)
        except Exception as error:
            raise PlaceResolutionError("geocoding", f"{place_text!r}: {error}") from error
        if not results:
            raise PlaceResolutionError("geocoding", f"no match for {place_text!r}")
        return list(results)

    def _zone_for(self, latitude: Decimal, longitude: Decimal) -> str:
        try:
            zone = self._timezone_finder.timezone_at(lat=float(latitude), lng=float(longitude))
        except Exception as error:
            raise PlaceResolutionError(
                "timezone_resolution", f"looking up ({latitude}, {longitude}): {error}"
            ) from error
        if zone is None:
            raise PlaceResolutionError(
                "timezone_resolution",
                f"no IANA zone found for ({latitude}, {longitude})",
            )
        return zone

    def _historical_offset(self, iana_zone: str, birth_local_time: datetime) -> timedelta:
        try:
            zone = ZoneInfo(iana_zone)
        except ZoneInfoNotFoundError as error:
            raise PlaceResolutionError(
                "timezone_resolution", f"{iana_zone!r} is not a known IANA zone: {error}"
            ) from error

        # Per PEP 495: `fold` disambiguates the two local instants a DST
        # fall-back repeats, and reveals a spring-forward instant that never
        # occurred at all. Neither is silently auto-resolved here, mirroring
        # this story's own rule for an ambiguous *place* match (FR-2): an
        # ambiguous or nonexistent birth time is refused, not guessed.
        before = birth_local_time.replace(tzinfo=zone, fold=0)
        after = birth_local_time.replace(tzinfo=zone, fold=1)
        offset_before, offset_after = before.utcoffset(), after.utcoffset()
        assert offset_before is not None and offset_after is not None

        if offset_before == offset_after:
            return offset_before

        round_trip = before.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
        if round_trip == birth_local_time:
            raise PlaceResolutionError(
                "timezone_resolution",
                f"{birth_local_time} is ambiguous in {iana_zone} (occurs twice across a "
                "DST fall-back); cannot resolve a single offset without disambiguation",
            )
        raise PlaceResolutionError(
            "timezone_resolution",
            f"{birth_local_time} does not exist in {iana_zone} (skipped by a DST "
            "spring-forward gap)",
        )


def _to_decimal(value: float) -> Decimal:
    """``str(value)`` first -- ``Decimal(value)`` on a raw float would compound
    the imprecision geopy's own float parsing of Nominatim's response already
    introduces, rather than merely preserving it."""
    return Decimal(str(value))
