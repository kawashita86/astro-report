"""``shell/http/stage_view.py`` -- the pure view-model core behind the
stage-track / Gate-violation surfaces Story 9.5 renders. No I/O, no database:
these tests exercise every I/O & Edge-Case Matrix stage state directly
against ``build_stage_track()`` / ``stage_caption()`` / ``violation_kind_label()``.
"""

from __future__ import annotations

import pytest

from shell.http.stage_view import (
    STAGE_NODES,
    VIOLATION_KIND_LABELS,
    build_stage_track,
    stage_caption,
    violation_kind_label,
)
from shell.runner.driver import _STAGE_SEQUENCE

# --- STAGE_NODES <-> _STAGE_SEQUENCE binding --------------------------------------


def test_stage_nodes_is_bound_to_the_stage_sequence_by_length_and_order() -> None:
    """A seventh stage registered in the driver cannot ship without a label
    here -- this is exactly the binding the Code Map calls for."""
    assert len(STAGE_NODES) == len(_STAGE_SEQUENCE)
    assert tuple(key for key, _label in STAGE_NODES) == _STAGE_SEQUENCE


def test_every_stage_node_has_a_non_empty_italian_label() -> None:
    for _key, label in STAGE_NODES:
        assert isinstance(label, str)
        assert label != ""


# --- build_stage_track: the I/O Matrix's stage states -----------------------------


def test_run_just_started_has_the_first_node_active_and_the_rest_pending() -> None:
    track = build_stage_track(None, failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "active",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_mid_run_has_the_completed_nodes_done_and_the_next_one_active() -> None:
    track = build_stage_track("transits_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "active",
        "pending",
        "pending",
        "pending",
    ]


def test_payload_ready_has_the_bozza_node_active() -> None:
    track = build_stage_track("payload_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "active",
        "pending",
        "pending",
    ]


def test_gate_running_has_the_verifica_node_active() -> None:
    track = build_stage_track("draft_ready", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "active",
        "pending",
    ]


def test_gate_passed_has_the_esportazione_node_active() -> None:
    track = build_stage_track("gate_passed", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "done",
        "active",
    ]


def test_exported_has_every_node_done() -> None:
    track = build_stage_track("exported", failed=False, gate_failed=False)

    assert [node["state"] for node in track] == ["done"] * 6


def test_a_gate_failure_marks_the_verifica_node_failed() -> None:
    track = build_stage_track("draft_ready", failed=True, gate_failed=True)

    assert [node["state"] for node in track] == [
        "done",
        "done",
        "done",
        "done",
        "failed",
        "pending",
    ]


def test_a_non_gate_terminal_failure_marks_the_first_incomplete_node_failed() -> None:
    """E.g. a run that failed at ``natal_ready`` (``run.stage is None``) --
    ``gate_failed`` does not change which node is marked failed, only the
    caption (see the ``stage_caption`` tests below)."""
    track = build_stage_track(None, failed=True, gate_failed=False)

    assert [node["state"] for node in track] == [
        "failed",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_node_keys_and_labels_match_stage_nodes_regardless_of_state() -> None:
    track = build_stage_track("payload_ready", failed=False, gate_failed=False)

    assert [(node["key"], node["label"]) for node in track] == list(STAGE_NODES)


# --- stage_caption: the I/O Matrix's captions --------------------------------------


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        (None, "Calcolo del tema natale"),
        ("natal_ready", "Ricerca dei transiti"),
        ("transits_ready", "Assemblaggio del Payload"),
        ("payload_ready", "Generazione della bozza in corso, attendere"),
        ("draft_ready", "Verifica di fondatezza"),
        ("gate_passed", "Pronto per l'esportazione"),
    ],
)
def test_the_running_caption_names_the_active_stage(stage: str | None, expected: str) -> None:
    caption = stage_caption(stage, failed=False, gate_failed=False, failure_reason=None)

    assert caption == expected


def test_the_exported_caption_is_the_true_terminal_phrase() -> None:
    caption = stage_caption("exported", failed=False, gate_failed=False, failure_reason=None)

    assert caption == "Esportato"


def test_a_gate_failure_caption_is_verifica_non_superata_regardless_of_failure_reason() -> None:
    caption = stage_caption(
        "draft_ready",
        failed=True,
        gate_failed=True,
        failure_reason="Refusing to advance past the Groundedness Gate: 1 violation(s).",
    )

    assert caption == "Verifica non superata"


def test_a_non_gate_failure_caption_is_the_runs_own_failure_reason() -> None:
    caption = stage_caption(
        "draft_ready",
        failed=True,
        gate_failed=False,
        failure_reason="stage 'draft_ready' failed 5 consecutive times: simulated rate limit",
    )

    assert caption == "stage 'draft_ready' failed 5 consecutive times: simulated rate limit"


# --- violation_kind_label -----------------------------------------------------------


def test_every_known_violation_kind_has_a_distinct_italian_label() -> None:
    assert set(VIOLATION_KIND_LABELS) == {
        "empty_citation",
        "invented_fact",
        "contradicted_fact",
        "date_token_in_day_list",
    }
    assert len(set(VIOLATION_KIND_LABELS.values())) == len(VIOLATION_KIND_LABELS)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("empty_citation", "Citazione vuota"),
        ("invented_fact", "Fatto inventato"),
        ("contradicted_fact", "Fatto contraddetto"),
        ("date_token_in_day_list", "Data in un elenco di giorni"),
    ],
)
def test_a_known_kind_maps_to_its_italian_label(kind: str, expected: str) -> None:
    assert violation_kind_label(kind) == expected


def test_an_unknown_kind_falls_back_to_the_raw_token() -> None:
    assert violation_kind_label("some_future_kind") == "some_future_kind"
