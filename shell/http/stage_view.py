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

from shell.runner.driver import _STAGE_SEQUENCE

__all__ = [
    "STAGE_NODES",
    "VIOLATION_KIND_LABELS",
    "build_stage_track",
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
    "draft_ready": "Generazione della bozza",
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
