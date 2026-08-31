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
from core.types.chart import Aspect, HouseCusp, NatalChart, PlanetPosition
from core.types.computation import ComputationConfig
from core.types.place import ResolvedPlace
from shell.adapters.postgres.corpus_entry import CorpusEntry
from shell.adapters.postgres.export_record import ExportRecord
from shell.adapters.postgres.gate_result import StoredGateResult
from shell.adapters.postgres.report import Report
from shell.adapters.postgres.report_draft import ReportDraft
from shell.adapters.postgres.report_payload import ReportPayload
from shell.adapters.postgres.report_run import ReportRun
from shell.adapters.postgres.report_theme import StoredReportTheme

__all__ = [
    "Client",
    "StoredNatalChart",
    "correct_client_and_chart",
    "create_client_with_chart",
    "current_chart_for_client",
    "delete_client_and_derived",
    "deserialize_natal_chart",
    "list_clients",
]

#: The single source of truth for every table carrying a foreign key to
#: ``client.id`` (Story 2.8). Both :func:`delete_client_and_derived` and
#: ``tests/test_client_store.py``'s cascade-invariant test read from this
#: constant -- a table added here without joining the delete function below,
#: or vice versa, is exactly the drift that invariant test exists to catch.
_CLIENT_CASCADE_TABLES: frozenset[str] = frozenset(
    {
        "natal_chart",
        "report_run",
        "report_payload",
        "report_theme",
        "report_draft",
        "report",
        "gate_result",
        "export_record",
        "corpus_entry",
    }
)


class Client(SQLModel, table=True):
    """A Client's identity and its immutable birthplace snapshot (AD-16):
    latitude, longitude and IANA zone, resolved once at creation and never
    re-read from ``PLACE_CACHE`` afterward.

    No uniqueness constraint on ``name`` -- two Clients may share a name and
    persist as distinct rows.
    """

    __tablename__ = "client"

    id: UUID = Field(default_factory=uuid7, primary_key=True)
    #: Free-text, user-typed (deferred-work item 41): generous enough for any
    #: real name, bounded so a single oversized field cannot pass the
    #: `/clients` form's whole-body byte cap while remaining pathologically
    #: large. Enforced again at the HTTP boundary
    #: (`shell/http/routes/clients.py`'s `_MAX_NAME_LENGTH`) since this is the
    #: only one of the three bounded columns a caller submits as raw text.
    name: str = Field(max_length=200)
    birth_date: date
    birth_time: time
    latitude: Decimal
    longitude: Decimal
    #: A real IANA zone id, Geocoder-resolved -- never user-typed directly
    #: (deferred-work item 41). The longest real id is ~33 characters; 64 is
    #: a generous bound with no HTTP-boundary check needed (not a raw form
    #: field).
    iana_zone: str = Field(max_length=64)


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
    #: A sha256 hex digest, always exactly 64 characters (deferred-work item
    #: 41). Derived from `computation_config.content_hash`, never a raw form
    #: field, so no HTTP-boundary check applies -- only this schema-level
    #: bound.
    computation_config_content_hash: str = Field(max_length=64)
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


def _build_stored_chart(
    *,
    client_id: UUID,
    natal_chart: NatalChart,
    computation_config: ComputationConfig,
    ephemeris_identity: EphemerisIdentity,
) -> StoredNatalChart:
    """The ``StoredNatalChart`` row both :func:`create_client_with_chart` and
    :func:`correct_client_and_chart` insert (epic-2-retro-item-13) -- the
    construction block was byte-identical in both.

    ``planets``/``houses``/``aspects`` are JSON-serialized here via
    :func:`_serialize` (every ``Decimal`` inside them to a string first). The
    caller owns ``session.add()`` and the transaction boundary; this only
    builds the row.
    """
    return StoredNatalChart(
        client_id=client_id,
        ascendant=natal_chart.ascendant,
        midheaven=natal_chart.midheaven,
        planets=[_serialize(planet) for planet in natal_chart.planets],
        houses=[_serialize(house) for house in natal_chart.houses],
        aspects=[_serialize(aspect) for aspect in natal_chart.aspects],
        computation_config_version=computation_config.version,
        computation_config_content_hash=computation_config.content_hash,
        ephemeris_files=[_serialize(file) for file in ephemeris_identity.files],
    )


def deserialize_natal_chart(stored: StoredNatalChart) -> NatalChart:
    """Reverse :func:`_serialize`'s ``Decimal``-to-``str`` JSON encoding back
    into the frozen :mod:`core.types.chart` dataclasses (Story 3.5).

    ``shell/runner/driver.py``'s ``advance()`` needs an already-computed chart
    as a real :class:`NatalChart` -- the shape ``core/transits/*``'s four
    scan functions take -- not the JSON rows ``StoredNatalChart`` persists it
    as. ``stored.ascendant``/``stored.midheaven`` are already ``Decimal``
    (they are their own typed columns, never JSON-encoded), so only the
    ``planets``/``houses``/``aspects`` JSON lists need their ``Decimal``
    fields converted back from ``str``.
    """
    return NatalChart(
        ascendant=stored.ascendant,
        midheaven=stored.midheaven,
        planets=tuple(
            PlanetPosition(
                name=planet["name"],
                longitude=Decimal(planet["longitude"]),
                sign=planet["sign"],
                degree=Decimal(planet["degree"]),
                house=planet["house"],
                retrograde=planet["retrograde"],
            )
            for planet in stored.planets
        ),
        houses=tuple(
            HouseCusp(number=house["number"], longitude=Decimal(house["longitude"]))
            for house in stored.houses
        ),
        aspects=tuple(
            Aspect(
                body1=aspect["body1"],
                body2=aspect["body2"],
                aspect=aspect["aspect"],
                orb=Decimal(aspect["orb"]),
                applying=aspect["applying"],
            )
            for aspect in stored.aspects
        ),
    )


def current_chart_for_client(session: Session, client_id: UUID) -> StoredNatalChart | None:
    """The current (non-superseded) ``StoredNatalChart`` for ``client_id``, or
    ``None`` if it has none -- the one "can a run start against this Client"
    predicate every caller that gates on a chart needs (Story 9.3's Report-tab
    ``Nuovo report`` control and ``report_runs.py``'s ``start_report_run``/
    ``drive_report_run`` both used their own copy of this query before this
    function existed to share).
    """
    return session.exec(
        select(StoredNatalChart).where(
            StoredNatalChart.client_id == client_id,
            StoredNatalChart.superseded_at.is_(None),
        )
    ).first()


def list_clients(session: Session) -> list[Client]:
    """Every Client, ordered by ``name`` then ``id`` (Story 7.2).

    What ``/corpus/new``'s Client picker offers: the picker only links an
    entry to a Client that already exists -- it never creates one. ``id`` is
    the tie-breaker so two Clients sharing a name (allowed -- ``Client`` has
    no uniqueness constraint on ``name``) still order deterministically.
    """
    return list(session.exec(select(Client).order_by(Client.name, Client.id)))


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
    chart = _build_stored_chart(
        client_id=client.id,
        natal_chart=natal_chart,
        computation_config=computation_config,
        ephemeris_identity=ephemeris_identity,
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

    new_chart = _build_stored_chart(
        client_id=client.id,
        natal_chart=natal_chart,
        computation_config=computation_config,
        ephemeris_identity=ephemeris_identity,
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


def delete_client_and_derived(session: Session, *, client: Client) -> None:
    """Delete ``client`` and every row derived from it, in one flush (Story 2.8;
    ``ReportRun`` joined the cascade in Story 3.5; ``StoredReportTheme`` in
    Story 4.3; ``ReportDraft`` in Story 4.6; ``Report`` in Story 5.3;
    ``StoredGateResult`` in Story 5.6; ``ExportRecord`` in Story 6.2;
    ``CorpusEntry`` in Story 7.1).

    Every ``CorpusEntry`` row *paired* to ``client`` (``client_id == client.id``)
    is deleted in the first batch, before the ``client`` row. A ``CorpusEntry``
    with ``client_id IS NULL`` -- every entry added in Story 7.1, which has no
    linking UI yet -- is never matched by this cascade and is intentionally
    left untouched.

    Every ``CorpusEntry`` row paired to ``client``, every ``ReportPayload``
    row, every ``StoredReportTheme`` row, every ``ReportDraft`` row, every
    ``ExportRecord`` row, every ``Report`` row, every ``StoredGateResult``
    row and every ``ReportRun`` row for ``client``
    are deleted first, then every ``StoredNatalChart`` row for ``client`` --
    current and superseded -- and only then the ``Client`` row itself:
    children before parent, matching how no foreign key in this codebase
    declares ``ondelete`` at the schema level, so the cascade is explicit
    application code, not the database's job. ``ExportRecord`` rows are
    deleted before ``Report`` rows specifically -- ``ExportRecord.report_id``
    (Story 6.2) is itself a foreign key to ``report.id``, so a ``Report`` row
    still referenced by one would violate that constraint if deleted first.
    ``ReportPayload``, ``StoredReportTheme``, ``ReportDraft``, ``Report`` and
    ``StoredGateResult`` rows are all deleted before ``ReportRun`` rows
    specifically -- ``ReportPayload.report_run_id`` (Story 3.8),
    ``StoredReportTheme.report_run_id`` (Story 4.3), ``ReportDraft.report_run_id``
    (Story 4.6), ``Report.report_run_id`` (Story 5.3) and
    ``StoredGateResult.report_run_id`` (Story 5.6) are themselves foreign
    keys to ``report_run.id``, so a ``ReportRun`` row still referenced by any
    of them would violate that constraint if deleted first. ``StoredNatalChart``
    rows are deleted *after* ``ReportRun`` rows specifically, the one entry in
    this cascade running in the opposite direction from every other table
    here -- ``ReportRun.natal_chart_id`` (Story 6.4) is a foreign key *from*
    ``report_run`` *to* ``natal_chart.id``, so a ``StoredNatalChart`` row
    still referenced by a ``ReportRun`` would violate that constraint if
    deleted first, exactly the same hazard as every table above, just
    pointing the other way.
    :data:`_CLIENT_CASCADE_TABLES` is the single source of truth for which
    tables that first step must cover; the cascade-invariant test in
    ``tests/test_client_store.py`` asserts it stays equal to every table in
    ``SQLModel.metadata`` carrying a foreign key to ``client.id``.

    This function only ``delete()``s and ``flush()``es -- it never commits or
    rolls back, exactly like :func:`create_client_with_chart` and
    :func:`correct_client_and_chart`, so it never decides the caller's
    transaction boundary. The caller commits only once every deletion here has
    succeeded.
    """
    corpus_entries = session.exec(
        select(CorpusEntry).where(CorpusEntry.client_id == client.id)
    ).all()
    for corpus_entry in corpus_entries:
        session.delete(corpus_entry)

    payloads = session.exec(
        select(ReportPayload).where(ReportPayload.client_id == client.id)
    ).all()
    for stored_payload in payloads:
        session.delete(stored_payload)

    themes = session.exec(
        select(StoredReportTheme).where(StoredReportTheme.client_id == client.id)
    ).all()
    for stored_theme in themes:
        session.delete(stored_theme)

    drafts = session.exec(
        select(ReportDraft).where(ReportDraft.client_id == client.id)
    ).all()
    for stored_draft in drafts:
        session.delete(stored_draft)

    export_records = session.exec(
        select(ExportRecord).where(ExportRecord.client_id == client.id)
    ).all()
    for stored_export_record in export_records:
        session.delete(stored_export_record)

    reports = session.exec(select(Report).where(Report.client_id == client.id)).all()
    for stored_report in reports:
        session.delete(stored_report)

    gate_results = session.exec(
        select(StoredGateResult).where(StoredGateResult.client_id == client.id)
    ).all()
    for stored_gate_result in gate_results:
        session.delete(stored_gate_result)

    runs = session.exec(select(ReportRun).where(ReportRun.client_id == client.id)).all()
    for run in runs:
        session.delete(run)

    # Deleted last, after every ReportRun: ReportRun.natal_chart_id (Story
    # 6.4) is a foreign key from report_run to natal_chart.id, the opposite
    # direction from every other table in this cascade -- see this
    # function's own docstring.
    charts = session.exec(
        select(StoredNatalChart).where(StoredNatalChart.client_id == client.id)
    ).all()
    for chart in charts:
        session.delete(chart)

    # Every table above relies on the SQLAlchemy `Session`'s own autoflush
    # -- triggered by the next `select()` in the loop above -- to actually
    # emit each batch of `DELETE` statements before the next one is queued,
    # since none of these tables declare an ORM `relationship()` for the
    # unit of work to infer cross-table delete ordering from on its own.
    # ``client`` has no following `select()` after it to trigger that same
    # autoflush, so this explicit `flush()` plays that same role here:
    # without it, the chart deletes above and the client delete below would
    # land in one unordered flush and could violate
    # ``report_run.natal_chart_id``'s new foreign key (Story 6.4) or
    # ``natal_chart.client_id``'s existing one.
    session.flush()

    session.delete(client)

    session.flush()
