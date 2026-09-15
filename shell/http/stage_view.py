"""Pure view-model helpers for the ``ReportRun`` stage track and the
Groundedness Gate violation panel (Story 9.5) -- no I/O, no database session,
mirroring ``shell/http/draft_view.py`` / ``shell/http/payload_view.py``'s own
shape: a template-facing module that only reshapes already-loaded data.

``shell/http/routes/report_runs.py`` is the only caller. It derives every
input here from a persisted ``ReportRun`` row (``run.stage``, ``run.failed_at``,
``run.failure_reason``) plus a boolean the route itself computes
(``gate_failed``, via ``_current_cycle_gate_failure`` -- the "did the Gate
cause *this* run's current failure" discriminator, not merely "has this run
ever failed the Gate," see that function's own docstring). Nothing here
touches ``advance()``, ``_STAGE_FUNCTIONS`` or any other part of the stage
machine -- read-only against it, per this story's Boundaries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields as dataclass_fields
from typing import Any
from zoneinfo import ZoneInfo

from core.gate.run import body_sign_label
from core.types.transits import Ingress, Lunation, StandingRetrograde, Station, TransitAspectEvent
from shell.http.payload_view import _localize_value
from shell.runner.driver import _STAGE_SEQUENCE

__all__ = [
    "CITED_ENTRY_FIELD_LABELS",
    "STAGE_NODES",
    "VIOLATION_KIND_LABELS",
    "build_stage_track",
    "resolve_cited_entries",
    "stage_caption",
    "violation_kind_label",
]

#: One ``(stage_key, italian_label)`` pair per ``_STAGE_SEQUENCE`` entry, in
#: the same order -- the six nodes DESIGN.md's stage track renders (tema
#: natale, transiti, Payload, bozza, verifica di fondatezza, esportazione).
#: ``tests/test_stage_view.py`` binds this to ``_STAGE_SEQUENCE`` by length
#: and key order, so a seventh stage registered in the driver cannot ship
#: without a label here.
STAGE_NODES: tuple[tuple[str, str], ...] = (
    ("natal_ready", "Tema natale"),
    ("transits_ready", "Transiti"),
    ("payload_ready", "Payload"),
    ("draft_ready", "Bozza"),
    ("gate_passed", "Verifica di fondatezza"),
    ("exported", "Esportazione"),
)

#: The progress-tense Italian caption shown while the stage named by the key
#: is the *active* node -- i.e. the phrase for the stage that is active when
#: ``run.stage`` names its predecessor in ``_STAGE_SEQUENCE`` (``run.stage is
#: None`` names no predecessor and maps to ``"natal_ready"``'s own caption,
#: the first node). Verbatim from EXPERIENCE.md "Voice and Tone -> Stage
#: labels". The true terminal caption once *every* node is done
#: (``run.stage == "exported"``) is not in this dict -- see
#: ``stage_caption()``, which returns ``"Esportato"`` for that case directly
#: rather than treating it as some seventh node's own "in progress" phrase.
_STAGE_CAPTIONS: dict[str, str] = {
    "natal_ready": "Calcolo del tema natale",
    "transits_ready": "Ricerca dei transiti",
    "payload_ready": "Assemblaggio del Payload",
    "draft_ready": "Generazione della bozza in corso, attendere",
    "gate_passed": "Verifica di fondatezza",
    "exported": "Pronto per l'esportazione",
}

#: The Italian label for each Groundedness Gate ``GateViolation.kind``
#: (``core/types/gate.py``) -- an unrecognized kind falls back to the raw
#: token (``violation_kind_label()``) rather than raising, so a future
#: vocabulary/Gate change that adds a fifth kind degrades to a readable-if-
#: English label instead of a 500.
VIOLATION_KIND_LABELS: dict[str, str] = {
    "empty_citation": "Citazione vuota",
    "invented_fact": "Fatto inventato",
    "contradicted_fact": "Fatto contraddetto",
    "date_token_in_day_list": "Data in un elenco di giorni",
}


#: Every cited-entry ``"kind"`` tag ``core/payload/freeze.py::_event_kind()``
#: can produce, mapped to its own frozen dataclass (``core/types/transits.py``)
#: -- the single source these entries' field order and Italian headings are
#: both derived from, so a future sixth transit-event kind cannot ship
#: without this module noticing (``tests/test_stage_view.py``'s parity test).
_ENTRY_DATACLASS_BY_KIND: dict[str, type] = {
    "aspect": TransitAspectEvent,
    "station": Station,
    "standing_retrograde": StandingRetrograde,
    "ingress": Ingress,
    "lunation": Lunation,
}


def _entry_field_names(kind: str) -> tuple[str, ...]:
    """The frozen-JSON field names a cited entry of ``kind`` actually
    carries, in its dataclass's own declared field order -- mirrors
    ``core/payload/freeze.py::_tag_event()``'s ``"kind"``->``"lunation_kind"``
    rename for :class:`Lunation` (a genuine name collision with the outer
    ``"kind"`` tag every entry carries), so this always matches the real
    JSON keys :func:`resolve_cited_entries` reads, never :class:`Lunation`'s
    own raw field name."""
    dataclass_type = _ENTRY_DATACLASS_BY_KIND[kind]
    is_lunation = dataclass_type is Lunation
    names: list[str] = []
    for field in dataclass_fields(dataclass_type):
        name = "lunation_kind" if is_lunation and field.name == "kind" else field.name
        names.append(name)
    return tuple(names)


#: One cited-entry ``"kind"`` -> its own fields, in display order. Derived
#: from the dataclasses themselves (not hand-listed) so a future field
#: addition to any of the five is picked up here automatically instead of
#: silently missing from a rendered card.
_ENTRY_FIELD_ORDER: dict[str, tuple[str, ...]] = {
    kind: _entry_field_names(kind) for kind in _ENTRY_DATACLASS_BY_KIND
}

#: The Italian heading a cited-entry card shows for each ``"kind"`` tag --
#: never a raw dict key (Design Notes). ``.get(kind, kind)`` at every call
#: site degrades to the raw token for an unrecognized kind rather than
#: raising (mirrors ``violation_kind_label``'s own convention).
_ENTRY_KIND_HEADINGS_IT: dict[str, str] = {
    "aspect": "Aspetto",
    "station": "Stazione",
    "standing_retrograde": "Retrogradazione in corso",
    "ingress": "Ingresso",
    "lunation": "Lunazione",
}

#: Italian label for every field any of the five cited-entry dataclasses
#: declares (``tests/test_stage_view.py`` parity-tests this against
#: ``_ENTRY_FIELD_ORDER``'s own union) -- keyed by the frozen-JSON field
#: name (``"lunation_kind"``, not :class:`Lunation`'s own ``"kind"``).
#: ``"occurred_at"`` says what the date represents ("Data della lunazione"),
#: like every sibling timestamp label on the other four dataclasses,
#: rather than the generic "Data".
CITED_ENTRY_FIELD_LABELS: dict[str, str] = {
    "transiting_body": "Corpo transitante",
    "natal_point": "Punto natale",
    "aspect": "Aspetto",
    "perfected_at": "Perfezionato il",
    "never_perfected": "Mai perfezionato",
    "orb_entry_at": "Ingresso in orbita",
    "orb_exit_at": "Uscita dall'orbita",
    "body": "Corpo",
    "direction": "Direzione",
    "station_at": "Stazione il",
    "longitude": "Longitudine",
    "retrograde_start_utc": "Inizio della retrogradazione",
    "retrograde_end_utc": "Fine della retrogradazione",
    "house_departed": "Casa di partenza",
    "house_entered": "Casa di arrivo",
    "crossed_at": "Attraversamento il",
    "lunation_kind": "Tipo di lunazione",
    "occurred_at": "Data della lunazione",
    "natal_house": "Casa natale",
}

#: The five Aspect names ``core/ephemeris/chart.py``'s ``_ASPECTS`` table
#: can assign a :class:`TransitAspectEvent`'s ``aspect`` field.
_ASPECT_LABELS_IT: dict[str, str] = {
    "conjunction": "Congiunzione",
    "sextile": "Sestile",
    "square": "Quadratura",
    "trine": "Trigono",
    "opposition": "Opposizione",
}

#: The two directions a :class:`Station`'s ``direction`` field can carry.
_DIRECTION_LABELS_IT: dict[str, str] = {
    "retrograde": "Retrogrado",
    "direct": "Diretto",
}

#: The two kinds a :class:`Lunation`'s own ``"kind"`` field (frozen as
#: ``"lunation_kind"``) can carry.
_LUNATION_KIND_LABELS_IT: dict[str, str] = {
    "new_moon": "Luna Nuova",
    "full_moon": "Luna Piena",
}

#: Every field name across the five cited-entry dataclasses whose value is
#: a Payload-internal English body/sign/angle/node canonical key
#: (``core.gate.run.body_sign_label()``'s own domain), not free text.
_BODY_FIELD_NAMES: frozenset[str] = frozenset({"transiting_body", "natal_point", "body"})

#: Every field name whose value is a tz-aware ISO 8601 instant, localized
#: the same way ``shell/http/payload_view.py``'s own Payload walker does.
_TIMESTAMP_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "perfected_at",
        "orb_entry_at",
        "orb_exit_at",
        "station_at",
        "retrograde_start_utc",
        "retrograde_end_utc",
        "crossed_at",
        "occurred_at",
    }
)


def _format_entry_value(field_name: str, value: Any, zone: ZoneInfo) -> str:
    """One cited-entry field's raw Payload value -> its display-ready
    Italian string. Order matters: a ``bool`` is checked before any other
    branch (``never_perfected`` is boolean-valued, never a number to
    ``str()`` as ``"True"``/``"False"``); ``None`` (an open
    ``orb_exit_at``) renders as an em dash rather than the Python string
    ``"None"``."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Sì" if value else "No"
    if field_name in _TIMESTAMP_FIELD_NAMES:
        localized = _localize_value(value, zone)
        return str(localized) if localized is not None else "—"
    if field_name in _BODY_FIELD_NAMES:
        return body_sign_label(str(value))
    if field_name == "aspect":
        return _ASPECT_LABELS_IT.get(value, value)
    if field_name == "direction":
        return _DIRECTION_LABELS_IT.get(value, value)
    if field_name == "lunation_kind":
        return _LUNATION_KIND_LABELS_IT.get(value, value)
    if field_name == "longitude":
        return f"{value}°"
    return str(value)


def resolve_cited_entries(
    entry_ids: Sequence[str], entry_index: dict[str, dict[str, Any]], iana_zone: str
) -> list[dict[str, Any]]:
    """One small labeled card per id in ``entry_ids`` that resolves against
    ``entry_index`` (Story 9.5) -- an id absent from the index (should never
    happen for a real Gate run) is silently skipped rather than raising.

    ``entry_index`` is the caller's **already-built** id -> entry index
    (``core.gate.run._index_entries(stored_payload.payload)``, built once
    per HTTP request by ``shell/http/routes/report_runs.py``) -- this
    function never walks ``payload`` itself, so a multi-violation draft
    resolves every violation's citations against the one index instead of
    re-walking the whole Payload from scratch per violation.

    Returns ``[{"kind_label": ..., "id": ..., "fields": [(label, value), ...]}]``,
    one dict per resolved id, in ``entry_ids``'s own order. Every field
    value is already a display-ready Italian string (timestamps localized
    to ``iana_zone`` as ``dd/MM/yyyy HH:mm``, booleans as "Sì"/"No",
    body/sign/angle/node names via ``body_sign_label()``, the aspect/
    direction/lunation-kind vocabularies via their own small maps, a
    zodiacal degree with a trailing "°") -- ``report_draft.html`` renders
    it with no further logic.
    """
    zone = ZoneInfo(iana_zone)
    cards: list[dict[str, Any]] = []
    for entry_id in entry_ids:
        entry = entry_index.get(entry_id)
        if entry is None:
            continue
        kind = entry.get("kind")
        field_names = _ENTRY_FIELD_ORDER.get(kind, ())
        fields = [
            (
                CITED_ENTRY_FIELD_LABELS.get(field_name, field_name),
                _format_entry_value(field_name, entry.get(field_name), zone),
            )
            for field_name in field_names
        ]
        cards.append(
            {
                "kind_label": _ENTRY_KIND_HEADINGS_IT.get(kind, kind),
                "id": entry_id,
                "fields": fields,
            }
        )
    return cards


def _stage_index(stage: str | None) -> int:
    """``-1`` for ``None`` (nothing completed yet), otherwise ``stage``'s
    position in ``_STAGE_SEQUENCE`` -- mirrors
    ``shell/runner/driver.py``'s own private helper of the same name and
    shape, kept as a separate copy here rather than imported so this module
    depends on nothing from the driver beyond the one sequence tuple."""
    if stage is None:
        return -1
    return _STAGE_SEQUENCE.index(stage)


def build_stage_track(
    stage: str | None, *, failed: bool, gate_failed: bool
) -> list[dict[str, str]]:
    """The six stage-track nodes for ``report_run_poll.html``, one dict per
    node: ``{"key": ..., "label": ..., "state": ...}`` with
    ``state in {"pending", "active", "done", "failed"}``.

    ``done_index`` is ``stage``'s position in ``_STAGE_SEQUENCE`` (``-1`` if
    ``stage is None``). Node ``i``: ``done`` when ``i <= done_index``;
    ``failed`` when ``failed`` is true and ``i == done_index + 1`` (the node
    the run was working toward when it failed); ``active`` when
    ``i == done_index + 1`` and the run has not failed; ``pending``
    otherwise. A ``gate_passed`` run leaves ``done_index == 4``, so node 5
    (Esportazione) is ``active``; an ``exported`` run leaves
    ``done_index == 5``, so every node is ``done``.

    ``gate_failed`` does not change which node is marked ``failed`` -- a Gate
    failure and a generic terminal failure both fail the same
    ``done_index + 1`` node, only the caption differs (``stage_caption()``
    below). It is accepted here only so the route can call this function and
    ``stage_caption()`` with the same keyword set, computed once
    (``poll_report_run``).
    """
    del gate_failed
    done_index = _stage_index(stage)
    nodes: list[dict[str, str]] = []
    for index, (key, label) in enumerate(STAGE_NODES):
        if index <= done_index:
            state = "done"
        elif failed and index == done_index + 1:
            state = "failed"
        elif index == done_index + 1:
            state = "active"
        else:
            state = "pending"
        nodes.append({"key": key, "label": label, "state": state})
    return nodes


def stage_caption(
    stage: str | None, *, failed: bool, gate_failed: bool, failure_reason: str | None
) -> str:
    """The one Italian line ``report_run_poll.html`` shows under the stage
    track (``role="status"`` ``aria-live="polite"``): ``"Verifica non
    superata"`` when the Gate caused the current failure; ``failure_reason``
    verbatim for any other terminal failure; the active node's progress-tense
    phrase from :data:`_STAGE_CAPTIONS` otherwise; ``"Esportato"`` once every
    node is done (``stage == "exported"``, the one terminal state that is not
    a failure).
    """
    if gate_failed:
        return "Verifica non superata"
    if failed:
        return failure_reason or ""
    done_index = _stage_index(stage)
    active_index = done_index + 1
    if active_index >= len(_STAGE_SEQUENCE):
        return "Esportato"
    return _STAGE_CAPTIONS[_STAGE_SEQUENCE[active_index]]


def violation_kind_label(kind: str) -> str:
    """The Italian label for one ``GateViolation.kind`` token, or the raw
    token unchanged when it names no known kind (this story's Boundaries)."""
    return VIOLATION_KIND_LABELS.get(kind, kind)
