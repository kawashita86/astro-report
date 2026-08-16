"""``PLACE_CACHE`` -- an in-memory SQLite engine stands in for Postgres.
``PlaceCache`` uses no Postgres-specific type, so this exercises the real
schema and query behavior without a live database.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres.place_cache import (
    lookup_cached_place,
    normalize_place_text,
    store_resolved_place,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_normalize_folds_case_and_collapses_whitespace() -> None:
    assert normalize_place_text("  Rome,   Italy  ") == "rome, italy"
    assert normalize_place_text("ROME, ITALY") == "rome, italy"


def test_a_place_never_resolved_before_misses(session: Session) -> None:
    assert lookup_cached_place(session, "Rome, Italy") is None


def test_a_stored_place_is_served_from_cache(session: Session) -> None:
    store_resolved_place(
        session,
        "Rome, Italy",
        latitude=Decimal("41.8933"),
        longitude=Decimal("12.4829"),
        iana_zone="Europe/Rome",
    )

    cached = lookup_cached_place(session, "rome,   ITALY")

    assert cached is not None
    assert cached.latitude == Decimal("41.8933")
    assert cached.longitude == Decimal("12.4829")
    assert cached.iana_zone == "Europe/Rome"


def test_storing_the_same_normalized_place_twice_does_not_raise(session: Session) -> None:
    store_resolved_place(
        session,
        "Milan, Italy",
        latitude=Decimal("45.4642"),
        longitude=Decimal("9.1900"),
        iana_zone="Europe/Rome",
    )
    store_resolved_place(
        session,
        "milan, italy",
        latitude=Decimal("45.4642"),
        longitude=Decimal("9.1900"),
        iana_zone="Europe/Rome",
    )

    assert lookup_cached_place(session, "Milan, Italy") is not None
