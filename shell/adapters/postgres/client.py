"""``Client`` and its ``StoredNatalChart``: what Story 2.3's `/clients` route
persists (AD-16).

Both tables use UUIDv7 primary keys, matching ``PlaceCache``. Written
together, always, by :func:`create_client_with_chart` in a single flush: the
caller owns the transaction boundary (commit both or roll back both) --
mirrors ``store_resolved_place()``'s own note that a module deep in the call
stack must never decide the caller's commit for it.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, Session, SQLModel, select
from uuid6 import uuid7

from core.ephemeris.identity import EphemerisIdentity
from core.types.chart import NatalChart
from core.types.computation import ComputationConfig
from core.types.place import ResolvedPlace

__all__ = ["Client", "StoredNatalChart", "correct_client_and_chart", "create_client_with_chart"]


class Client(SQLModel, table=True):
    """A Client's identity and its immutable birthplace snapshot (AD-16):
    latitude, longitude and IANA zone, resolved once at creation and never
    re-read from ``PLACE_CACHE`` afterward.

    No uniqueness constraint on ``name`` -- two Clients may share a name and
    persist as distinct rows.
    """

    __tablename__ = "client"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    name: str
    birth_date: date
    birth_time: time
    latitude: Decimal
    longitude: Decimal
    iana_zone: str


class StoredNatalChart(SQLModel, table=True):
    """A computed :class:`core.types.chart.NatalChart`, persisted alongside
    the ``ComputationConfig`` version/content hash and the verified
    ``EphemerisIdentity`` that produced it -- so a stored chart can always be
    traced back to exactly what computed it.

    ``planets``/``houses``/``aspects`` are stored as JSON; every ``Decimal``
    field inside them is serialized to a string first, since JSON has no
    native Decimal type.
    """

    __tablename__ = "natal_chart"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    client_id: UUID = Field(foreign_key="client.id", index=True)
    ascendant: Decimal
    midheaven: Decimal
    # `sa_column=Column(...)` bypasses SQLModel's usual inference of
    # `nullable` from the type annotation, so `nullable=False` must be given
    # explicitly here -- matching the migration's own `NOT NULL` columns.
    planets: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    houses: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    aspects: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    computation_config_version: int
    computation_config_content_hash: str
    ephemeris_files: list[dict[str, str]] = Field(sa_column=Column(JSON, nullable=False))
    # `NULL` marks the current chart for a Client; a timestamp marks one a
    # correction (Story 2.7) superseded. `sa_column=Column(...)` again bypasses
    # SQLModel's `nullable` inference, matching the migration's own nullable
    # column.
    superseded_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


def _json_safe(value: Any) -> Any:
    """``Decimal`` -> ``str`` (JSON has no native Decimal type); everything
    else passes through unchanged. ``str(value)``, matching the
    precision-preserving pattern already used throughout
    ``core/ephemeris/chart.py`` and ``shell/adapters/nominatim/geocoder.py``.
    """
    return str(value) if isinstance(value, Decimal) else value


def _serialize(instance: Any) -> dict[str, Any]:
    assert is_dataclass(instance)
    return {key: _json_safe(value) for key, value in asdict(instance).items()}


def create_client_with_chart(
    session: Session,
    *,
    name: str,
    birth_date: date,
    birth_time: time,
    resolved_place: ResolvedPlace,
    natal_chart: NatalChart,
    computation_config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
) -> Client:
    """Persist a Client and its Natal Chart together, in one flush.

    Neither row is written without the other (AD-16). This function only
    ``add()``s and ``flush()``es -- it never commits or rolls back, exactly
    like ``store_resolved_place()``'s own nested write, so it never decides
    the caller's transaction boundary. The caller commits only once
    resolution, computation and this persistence step have all succeeded.
    """
    client = Client(
        name=name,
        birth_date=birth_date,
        birth_time=birth_time,
        latitude=resolved_place.latitude,
        longitude=resolved_place.longitude,
        iana_zone=resolved_place.iana_zone,
    )
    chart = StoredNatalChart(
        client_id=client.id,
        ascendant=natal_chart.ascendant,
        midheaven=natal_chart.midheaven,
        planets=[_serialize(planet) for planet in natal_chart.planets],
        houses=[_serialize(house) for house in natal_chart.houses],
        aspects=[_serialize(aspect) for aspect in natal_chart.aspects],
        computation_config_version=computation_config.version,
        computation_config_content_hash=computation_config.content_hash,
        ephemeris_files=[_serialize(file) for file in ephemeris_identity.files],
    )

    session.add(client)
    session.add(chart)
    session.flush()

    return client


def correct_client_and_chart(
    session: Session,
    *,
    client: Client,
    name: str,
    birth_date: date,
    birth_time: time,
    resolved_place: ResolvedPlace,
    natal_chart: NatalChart,
    computation_config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
) -> None:
    """Persist a correction to ``client``'s birth data and chart, in one flush
    (Story 2.7).

    The current (non-superseded) ``StoredNatalChart`` row for ``client`` is
    marked superseded rather than overwritten or deleted -- it stays
    queryable by its own id -- and a new current row is inserted alongside
    it. ``client``'s own fields are updated in place to the corrected values.
    This function only ``add()``s and ``flush()``es -- it never commits or
    rolls back, exactly like :func:`create_client_with_chart`, so it never
    decides the caller's transaction boundary. The caller commits only once
    resolution, computation and this persistence step have all succeeded.
    """
    current_chart = session.exec(
        select(StoredNatalChart).where(
            StoredNatalChart.client_id == client.id,
            StoredNatalChart.superseded_at.is_(None),
        )
    ).one()
    current_chart.superseded_at = datetime.now(UTC)
    session.add(current_chart)

    new_chart = StoredNatalChart(
        client_id=client.id,
        ascendant=natal_chart.ascendant,
        midheaven=natal_chart.midheaven,
        planets=[_serialize(planet) for planet in natal_chart.planets],
        houses=[_serialize(house) for house in natal_chart.houses],
        aspects=[_serialize(aspect) for aspect in natal_chart.aspects],
        computation_config_version=computation_config.version,
        computation_config_content_hash=computation_config.content_hash,
        ephemeris_files=[_serialize(file) for file in ephemeris_identity.files],
    )
    session.add(new_chart)

    client.name = name
    client.birth_date = birth_date
    client.birth_time = birth_time
    client.latitude = resolved_place.latitude
    client.longitude = resolved_place.longitude
    client.iana_zone = resolved_place.iana_zone
    session.add(client)

    session.flush()
