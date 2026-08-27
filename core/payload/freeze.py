"""Freeze a ``Payload``+``DayLists`` pair into canonical JSON with a stable,
content-hashed id per event (Story 3.8, AD-4, PRD FR-14).

Pure (AD-1): reads only the passed arguments, no I/O, clock, network or
randomness -- identical inputs produce byte-identical
``canonical_json_bytes(freeze_payload(...))`` output every call. This is what
makes a persisted ``ReportPayload`` (``shell/adapters/postgres/report_payload.py``)
reproducible: no citation into it depends on insertion order, wall-clock time
or a database-assigned sequence.

Every event in each ``SectionPayload`` tuple (Story 3.6) and both
``DayLists`` tuples (Story 3.7) gets an ``"id"``: the SHA-256 hex digest of
its own JSON-safe, kind-tagged field dict -- never sequential, time-based or
random. Kind-tagging mirrors ``shell/runner/driver.py::_serialize_event``
(``aspect``/``station``/``standing_retrograde``/``ingress``/``lunation``,
with a ``Lunation``'s own ``"kind"`` field renamed to ``"lunation_kind"`` to
survive the name collision) rather than importing it -- that function lives
in ``shell/``, which ``core/`` may never import (AD-1). Each tuple is then
re-emitted sorted by its own ``canonical_json_bytes(fields)``: the total
order AD-4 requires, and the reason two calls on identical inputs are
byte-identical regardless of the order ``core/transits/*`` happened to
produce events in.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from core.ephemeris.identity import EphemerisIdentity
from core.types.computation import ComputationConfig
from core.types.day_lists import DayLists
from core.types.payload import Payload, SectionPayload
from core.types.sections import SectionsConfig
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent

__all__ = ["PAYLOAD_SCHEMA_VERSION", "canonical_json_bytes", "freeze_payload"]

#: Bumped whenever ``freeze_payload()``'s output shape changes in a way a
#: reader must branch on. A stored ``ReportPayload`` keys its own reader on
#: ``stored.schema_version`` -- only ``1`` exists today, but the switch point
#: is real, not a stub.
PAYLOAD_SCHEMA_VERSION: int = 1


def canonical_json_bytes(value: Any) -> bytes:
    """Sorted keys, no insignificant whitespace -- the one serialization every
    entry ``id`` is hashed from and the Generator prompt is built from, so two
    byte-identical inputs always produce byte-identical output.

    A ``ReportPayload`` row's ``payload`` column is *not* written this way:
    with no custom ``json_serializer`` on the engine, SQLAlchemy's ``JSON``
    type stores it through ``json.dumps``'s defaults -- unsorted keys and the
    default ``", "``/``": "`` separators, unlike this function's sorted,
    whitespace-free form. That on-disk text is still deterministic for a
    stably-built dict; nothing downstream depends on its exact byte shape,
    because the content-hashed entry ids are computed here, before persistence."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _json_safe(value: Any) -> Any:
    """``Decimal`` -> ``str``, ``datetime`` -> ISO 8601, a frozen dataclass ->
    its fields recursively converted the same way, a tuple/list -> a list of
    converted items, a dict -> a dict of converted values -- everything else
    passes through unchanged.

    Recursive (unlike ``shell/adapters/postgres/client.py``'s/
    ``shell/runner/driver.py``'s own shallow ``_json_safe``s) because a
    ``SectionPayload.profile`` (``AmoreProfile``/etc.) nests further
    dataclasses (``DomainPlanet``/``DomainHouse``/``HouseRuler``/``Aspect``/
    ``PlanetPosition``) carrying their own ``Decimal`` fields -- the five
    transit-event dataclasses happen to be flat, but this same function
    freezes both.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_safe(getattr(value, field.name))
            for field in dataclass_fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _event_kind(event: Any) -> str:
    """The same kind tag ``shell/runner/driver.py::_serialize_event`` already
    assigns each of the five transit-event dataclasses, reimplemented here
    (not imported -- ``core/`` may never import ``shell/``, AD-1)."""
    if isinstance(event, TransitAspectEvent):
        return "aspect"
    if isinstance(event, Station):
        return "station"
    if isinstance(event, StandingRetrograde):
        return "standing_retrograde"
    if isinstance(event, Ingress):
        return "ingress"
    if isinstance(event, Lunation):
        return "lunation"
    raise TypeError(f"freeze_payload() does not recognize event type {type(event)!r}.")


def _tag_event(event: Any) -> dict[str, Any]:
    """One transit-event dataclass -> its JSON-safe field dict, tagged
    ``"kind"``. ``Lunation`` carries its own ``"kind"`` field
    (``"new_moon"``/``"full_moon"``) -- a genuine name collision with this
    wrapper's own outer ``"kind"`` tag -- renamed to ``"lunation_kind"``
    before the outer tag is applied, exactly like ``_serialize_event``."""
    kind = _event_kind(event)
    fields = _json_safe(event)
    assert isinstance(fields, dict)
    if "kind" in fields:
        fields[f"{kind}_kind"] = fields.pop("kind")
    return {"kind": kind, **fields}


def _freeze_events(events: tuple[Any, ...]) -> list[dict[str, Any]]:
    """``events`` re-emitted as a list of ``{"id": ..., **fields}`` dicts,
    sorted by ``canonical_json_bytes(fields)`` (the ``fields`` dict *before*
    ``"id"`` is added) -- the total order AD-4 requires."""
    tagged = sorted((_tag_event(event) for event in events), key=canonical_json_bytes)
    return [
        {"id": hashlib.sha256(canonical_json_bytes(fields)).hexdigest(), **fields}
        for fields in tagged
    ]


def _freeze_section(section: SectionPayload) -> dict[str, Any]:
    """``section``'s own fields, introspected via ``dataclasses.fields``
    (mirroring how ``freeze_payload()`` introspects ``Payload``'s six
    fields below) rather than named by hand -- a future ``SectionPayload``
    field is frozen automatically instead of silently dropped. ``profile``
    is the one field that is not an event tuple, special-cased to
    ``_json_safe`` (or ``None``); every other field is treated as a tuple of
    events for ``_freeze_events``."""
    frozen: dict[str, Any] = {}
    for field in dataclass_fields(section):
        value = getattr(section, field.name)
        if field.name == "profile":
            frozen[field.name] = _json_safe(value) if value is not None else None
        else:
            frozen[field.name] = _freeze_events(value)
    return frozen


def freeze_payload(
    payload: Payload,
    day_lists: DayLists,
    *,
    config: ComputationConfig,
    sections_config: SectionsConfig,
    ephemeris_identity: EphemerisIdentity,
    schema_version: int = PAYLOAD_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Freeze ``payload``/``day_lists`` into the canonical, JSON-safe dict a
    ``ReportPayload`` row persists verbatim (``shell/adapters/postgres/report_payload.py``).

    Every event in each of ``payload``'s six ``SectionPayload``s and both of
    ``day_lists``'s tuples gets a stable, content-hashed ``"id"`` and is
    re-emitted in a total order over its own canonical fields (see this
    module's docstring). The returned dict also carries the exact identity
    that produced it -- ``schema_version``, ``computation.toml``'s
    version/content hash, ``sections.toml``'s version/content hash, and the
    verified ephemeris file identity -- so a stored row is traceable back to
    what computed it without a second lookup.

    Deterministic and side-effect free: no clock, I/O, network or database is
    consulted, so calling this twice with the same arguments returns two
    values whose ``canonical_json_bytes()`` are byte-identical.
    """
    return {
        "schema_version": schema_version,
        "computation_config_version": config.version,
        "computation_config_content_hash": config.content_hash,
        "sections_config_version": sections_config.version,
        "sections_config_content_hash": sections_config.content_hash,
        "ephemeris_files": [
            {"filename": file.filename, "sha256": file.sha256}
            for file in ephemeris_identity.files
        ],
        "sections": {
            section_field.name: _freeze_section(getattr(payload, section_field.name))
            for section_field in dataclass_fields(payload)
        },
        "day_lists": {
            "giorni_favorevoli": _freeze_events(day_lists.giorni_favorevoli),
            "giorni_di_attenzione": _freeze_events(day_lists.giorni_di_attenzione),
        },
    }
