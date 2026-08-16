"""``NominatimGeocoder`` -- the geolocator and timezone lookup are injected
fakes throughout, so these tests exercise resolution and caching logic
without a real network call or the real timezone dataset. Row-for-row
coverage of the story's I/O & Edge-Case Matrix.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import geopy.exc
import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from core.errors import PlaceResolutionError
from core.types.place import PlaceCandidate, ResolvedPlace
from shell.adapters.nominatim.geocoder import NominatimGeocoder
from shell.adapters.postgres.place_cache import lookup_cached_place


@dataclass
class _FakeLocation:
    address: str
    latitude: float
    longitude: float


class _FakeGeolocator:
    """Records every call so a cache hit's "geocoder never called" claim is
    provable rather than assumed."""

    def __init__(self, results: list[_FakeLocation] | None = None) -> None:
        self._results = results
        self.calls: list[str] = []

    def geocode(self, query: str, exactly_one: bool) -> list[_FakeLocation] | None:
        self.calls.append(query)
        return self._results


class _RaisingGeolocator:
    def geocode(self, query: str, exactly_one: bool) -> list[_FakeLocation] | None:
        raise geopy.exc.GeocoderUnavailable("service down")


class _FakeTimezoneFinder:
    def __init__(self, zone: str | None = "Europe/Rome") -> None:
        self._zone = zone

    def timezone_at(self, *, lat: float, lng: float) -> str | None:
        return self._zone


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_a_single_unambiguous_match_resolves(session: Session) -> None:
    geolocator = _FakeGeolocator([_FakeLocation("Rome, Italy", 41.893249, 12.482935)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    result = geocoder.resolve("Rome, Italy", datetime(2026, 1, 15, 12, 0))

    assert isinstance(result, ResolvedPlace)
    assert result.latitude == Decimal("41.893249")
    assert result.longitude == Decimal("12.482935")
    assert result.iana_zone == "Europe/Rome"
    # Coordinates carry at least four decimal places (FR-2).
    assert -result.latitude.as_tuple().exponent >= 4
    assert -result.longitude.as_tuple().exponent >= 4


def test_a_1975_italian_birth_resolves_to_cest_not_cet(session: Session) -> None:
    geolocator = _FakeGeolocator([_FakeLocation("Milan, Italy", 45.4642, 9.19)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    result = geocoder.resolve("Milan, Italy", datetime(1975, 6, 15, 10, 30))

    assert isinstance(result, ResolvedPlace)
    assert result.utc_offset.total_seconds() == 2 * 3600  # +02:00 CEST, not +01:00 CET


def test_an_ambiguous_place_returns_candidates_and_caches_nothing(session: Session) -> None:
    geolocator = _FakeGeolocator(
        [
            _FakeLocation("Springfield, Illinois, USA", 39.7817, -89.6501),
            _FakeLocation("Springfield, Massachusetts, USA", 42.1015, -72.5898),
        ]
    )
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    result = geocoder.resolve("Springfield", datetime(2026, 1, 15, 12, 0))

    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(candidate, PlaceCandidate) for candidate in result)
    assert lookup_cached_place(session, "Springfield") is None


def test_a_repeat_place_is_served_from_cache_without_a_new_geocoder_query(
    session: Session,
) -> None:
    geolocator = _FakeGeolocator([_FakeLocation("Rome, Italy", 41.8933, 12.4829)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )
    geocoder.resolve("Rome, Italy", datetime(2026, 1, 15, 12, 0))
    assert len(geolocator.calls) == 1

    geocoder.resolve("Rome, Italy", datetime(2026, 6, 15, 12, 0))

    assert len(geolocator.calls) == 1, "the second resolution must not re-query the geocoder"


def test_a_cache_hit_still_derives_the_offset_from_the_new_birth_instant(
    session: Session,
) -> None:
    """Proves PLACE_CACHE caches only place facts, never an offset -- an
    accelerator, never a source of truth for the birth-instant-specific
    result (AD-16)."""
    geolocator = _FakeGeolocator([_FakeLocation("Milan, Italy", 45.4642, 9.19)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )
    winter = geocoder.resolve("Milan, Italy", datetime(2026, 1, 15, 12, 0))
    summer = geocoder.resolve("Milan, Italy", datetime(2026, 6, 15, 12, 0))

    assert isinstance(winter, ResolvedPlace) and isinstance(summer, ResolvedPlace)
    assert winter.utc_offset.total_seconds() == 1 * 3600  # CET
    assert summer.utc_offset.total_seconds() == 2 * 3600  # CEST
    assert len(geolocator.calls) == 1, "the zone came from cache both times"


def test_an_unresolvable_place_raises_naming_the_geocoding_step(session: Session) -> None:
    geolocator = _FakeGeolocator(results=None)
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Nonexistent Place Zzzzz", datetime(2026, 1, 15, 12, 0))

    assert caught.value.step == "geocoding"


def test_an_unreachable_geocoder_raises_naming_the_geocoding_step(session: Session) -> None:
    geocoder = NominatimGeocoder(
        session, geolocator=_RaisingGeolocator(), timezone_finder=_FakeTimezoneFinder()
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Rome, Italy", datetime(2026, 1, 15, 12, 0))

    assert caught.value.step == "geocoding"


def test_no_timezone_found_raises_naming_the_timezone_resolution_step(session: Session) -> None:
    geolocator = _FakeGeolocator([_FakeLocation("Middle of the Ocean", 0.0, -160.0)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder(zone=None)
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Middle of the Ocean", datetime(2026, 1, 15, 12, 0))

    assert caught.value.step == "timezone_resolution"


def test_a_geocoder_returning_an_empty_list_raises_naming_the_geocoding_step(
    session: Session,
) -> None:
    """``exactly_one=False`` can come back as ``[]`` rather than ``None`` --
    the ``not results`` guard must treat both the same."""
    geolocator = _FakeGeolocator(results=[])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Nonexistent Place Zzzzz", datetime(2026, 1, 15, 12, 0))

    assert caught.value.step == "geocoding"


def test_a_cache_read_failure_raises_naming_the_cache_step() -> None:
    class _RaisingSession:
        def exec(self, *args: object, **kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection lost"))

    geocoder = NominatimGeocoder(
        _RaisingSession(),  # type: ignore[arg-type]
        geolocator=_FakeGeolocator(),
        timezone_finder=_FakeTimezoneFinder(),
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Rome, Italy", datetime(2026, 1, 15, 12, 0))

    assert caught.value.step == "cache"


def test_an_ambiguous_fall_back_local_time_raises_naming_the_timezone_resolution_step(
    session: Session,
) -> None:
    """2026-10-25 02:30 local in Europe/Rome occurs twice (DST fall-back) --
    refused rather than silently picking one of the two real offsets,
    mirroring this story's own rule for an ambiguous place match."""
    geolocator = _FakeGeolocator([_FakeLocation("Rome, Italy", 41.8933, 12.4829)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Rome, Italy", datetime(2026, 10, 25, 2, 30))

    assert caught.value.step == "timezone_resolution"


def test_a_nonexistent_spring_forward_local_time_raises_naming_the_timezone_resolution_step(
    session: Session,
) -> None:
    """2026-03-29 02:30 local in Europe/Rome never occurred (DST
    spring-forward gap) -- refused rather than silently assigning it one of
    the two neighboring offsets."""
    geolocator = _FakeGeolocator([_FakeLocation("Rome, Italy", 41.8933, 12.4829)])
    geocoder = NominatimGeocoder(
        session, geolocator=geolocator, timezone_finder=_FakeTimezoneFinder()
    )

    with pytest.raises(PlaceResolutionError) as caught:
        geocoder.resolve("Rome, Italy", datetime(2026, 3, 29, 2, 30))

    assert caught.value.step == "timezone_resolution"
