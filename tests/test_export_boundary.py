"""``shell/export.py::export_report()`` -- Story 5.3's I/O & Edge-Case Matrix
rows 3-6: exporting a passed ``Report``, refusing an unknown or never-passed
id, refusing once the owning Client is deleted, and the static invariant
that exactly one export-shaped function exists anywhere in ``shell/``/
``core/``.

The behavioral tests (rows 3-5) use an in-memory SQLite engine standing in
for Postgres, mirroring ``tests/test_report_store.py``. The static-scan
tests (row 6) parse source with ``ast`` rather than importing it, mirroring
``tests/test_import_boundary.py``'s own ``ast.parse`` + visitor shape.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.errors import ReportNotFoundError
from core.types.generation import GeneratedDraft
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_draft import store_report_draft
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from shell.export import export_report

REPO_ROOT = Path(__file__).resolve().parent.parent

_EPHEMERIS_IDENTITY = verify_ephemeris_identity()
_COMPUTATION_CONFIG = load_computation_config()

_LATITUDE = Decimal("32.7358")
_LONGITUDE = Decimal("-97.3453")
_RESOLVED_PLACE = ResolvedPlace(
    latitude=_LATITUDE,
    longitude=_LONGITUDE,
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)
_BIRTH_INSTANT_UTC = datetime(2026, 1, 1, 6, 0, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_client(session: Session) -> Client:
    natal_chart = compute_natal_chart(
        _BIRTH_INSTANT_UTC, _LATITUDE, _LONGITUDE, _COMPUTATION_CONFIG
    )
    return create_client_with_chart(
        session,
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_RESOLVED_PLACE,
        natal_chart=natal_chart,
        computation_config=_COMPUTATION_CONFIG,
        ephemeris_identity=_EPHEMERIS_IDENTITY,
    )


def _create_run(session: Session, client: Client) -> ReportRun:
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()
    return run


def _create_passed_report(session: Session) -> tuple[Client, ReportRun, Report]:
    client = _create_client(session)
    run = _create_run(session, client)
    report = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
    )
    session.commit()
    return client, run, report


# --- I/O matrix row 3: export a passed Report ---------------------------------


def test_export_report_returns_the_report_row_for_a_passed_report_id(session: Session) -> None:
    _, run, report = _create_passed_report(session)

    result = export_report(session, report.id)

    assert result.id == report.id
    assert result.report_run_id == run.id


# --- I/O matrix row 4: export with no Report row -------------------------------


def test_export_report_refuses_for_an_unknown_report_id(session: Session) -> None:
    with pytest.raises(ReportNotFoundError):
        export_report(session, uuid4())


def test_export_report_refuses_for_a_run_that_never_passed_the_gate(session: Session) -> None:
    """Passing a ``ReportRun.id`` where a ``Report.id`` is expected also
    refuses -- there is no ``Report`` row for that id, which is also how a
    run that never reached ``gate_passed`` refuses export (this story's
    Boundaries: "a Report row exists only on a pass")."""
    client = _create_client(session)
    run = _create_run(session, client)

    with pytest.raises(ReportNotFoundError):
        export_report(session, run.id)


def _an_empty_generated_draft() -> GeneratedDraft:
    return GeneratedDraft(
        energia_generale=(),
        amore=(),
        lavoro=(),
        denaro=(),
        benessere=(),
        giorni_favorevoli=(),
        giorni_di_attenzione=(),
        consiglio_finale=(),
    )


def test_export_report_refuses_story_5_4s_exact_bound_exhausted_run_shape(
    session: Session,
) -> None:
    """Story 5.5, I/O & Edge-Case Matrix row 3: export refuses a
    ``ReportRun`` shaped exactly like Story 5.4's regeneration-bound-
    exhausted terminal state -- ``stage`` stays ``"draft_ready"`` (never
    rewound back), ``failed_at``/``failure_reason`` are set, and the last
    ``ReportDraft`` stays reachable (``shell/runner/driver.py``'s ``except
    GateFailedError`` branch) -- yet critically no ``Report`` row exists,
    since a ``Report`` is written only on a Gate pass (Story 5.3). This
    closes AC3 against the real bound-exhaustion shape, not just the
    generic "never reached gate_passed" case
    ``test_export_report_refuses_for_a_run_that_never_passed_the_gate``
    already covers."""
    client = _create_client(session)
    run = ReportRun(
        client_id=client.id,
        month="2026-01",
        stage="draft_ready",
        regeneration_count=4,
        failed_at=datetime(2026, 1, 20, 12, 0, 0, tzinfo=UTC),
        failure_reason="regeneration bound exhausted after 4 attempts: "
        "Refusing to advance past the Groundedness Gate: 1 violation(s) against the Payload.",
    )
    session.add(run)
    session.commit()
    store_report_draft(
        session,
        run=run,
        style_guide_version=1,
        sections_config_version=1,
        draft=_an_empty_generated_draft(),
        attempt=3,
    )
    session.commit()

    with pytest.raises(ReportNotFoundError):
        export_report(session, run.id)


# --- I/O matrix row 5: Client deletion -----------------------------------------


def test_export_report_refuses_once_its_client_has_been_deleted(session: Session) -> None:
    client, _run, report = _create_passed_report(session)

    delete_client_and_derived(session, client=client)
    session.commit()

    with pytest.raises(ReportNotFoundError):
        export_report(session, report.id)


# --- I/O matrix row 6: codebase scan --------------------------------------------


def _source_files() -> list[Path]:
    """Every ``.py`` file under ``core/``/``shell/`` -- ``tests/`` is a
    separate top-level tree, so excluding it needs no special-casing here."""
    files: list[Path] = []
    for base in ("core", "shell"):
        files.extend(
            path
            for path in sorted((REPO_ROOT / base).rglob("*.py"))
            if "__pycache__" not in path.parts
        )
    return files


def _annotation_names(node: ast.AST | None) -> set[str]:
    """Every ``Name``/``Attribute`` identifier appearing in a parameter
    annotation -- covers a bare ``GeneratedDraft``, a qualified
    ``core.types.generation.GeneratedDraft``, and one wrapped in a generic
    or union."""
    if node is None:
        return set()
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


class _ExportShapeVisitor(ast.NodeVisitor):
    """Finds every function named with an ``export`` prefix, and every
    function with a parameter annotated ``GeneratedDraft`` -- the two facts
    this story's own invariant is checked against (Design Notes)."""

    def __init__(self) -> None:
        self.export_functions: list[tuple[int, str]] = []
        self.draft_accepting_functions: list[tuple[int, str]] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("export"):
            self.export_functions.append((node.lineno, node.name))

        all_args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if any("GeneratedDraft" in _annotation_names(arg.annotation) for arg in all_args):
            self.draft_accepting_functions.append((node.lineno, node.name))

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def _scan(path: Path) -> _ExportShapeVisitor:
    visitor = _ExportShapeVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor


def test_exactly_one_export_shaped_function_exists_in_shell_and_core() -> None:
    found: list[tuple[Path, int, str]] = []
    for path in _source_files():
        visitor = _scan(path)
        found.extend((path, lineno, name) for lineno, name in visitor.export_functions)

    assert len(found) == 1, (
        "exactly one export-prefixed function must exist in shell/+core/, found: "
        + ", ".join(f"{p.relative_to(REPO_ROOT)}:{ln} {n}" for p, ln, n in found)
    )
    path, _lineno, name = found[0]
    assert name == "export_report"
    assert path == REPO_ROOT / "shell" / "export.py"


def test_no_function_accepting_a_generateddraft_also_has_export_in_its_name() -> None:
    offenders: list[str] = []
    for path in _source_files():
        visitor = _scan(path)
        offenders.extend(
            f"{path.relative_to(REPO_ROOT)}:{lineno} {name}"
            for lineno, name in visitor.draft_accepting_functions
            if "export" in name.lower()
        )

    assert not offenders, (
        "a function accepting a GeneratedDraft must never also be named like an "
        "export function: " + ", ".join(offenders)
    )


def test_the_guard_detects_a_second_export_function(tmp_path: Path) -> None:
    """Proves the scan actually catches a regression, mirroring
    ``tests/test_import_boundary.py``'s own guard-detects-an-offender shape."""
    offender = tmp_path / "rogue_export.py"
    offender.write_text("def export_something_else(draft):\n    return draft\n", encoding="utf-8")

    visitor = _scan(offender)

    assert visitor.export_functions == [(1, "export_something_else")]


def test_the_guard_detects_a_draft_accepting_function_named_like_export(tmp_path: Path) -> None:
    offender = tmp_path / "rogue_draft.py"
    offender.write_text(
        "from core.types.generation import GeneratedDraft\n\n"
        "def sneaky_export(draft: GeneratedDraft) -> None:\n    ...\n",
        encoding="utf-8",
    )

    visitor = _scan(offender)

    assert visitor.draft_accepting_functions == [(3, "sneaky_export")]


def test_the_guard_does_not_flag_an_innocent_function() -> None:
    innocent = REPO_ROOT / "shell" / "export.py"
    visitor = _scan(innocent)

    assert [name for _lineno, name in visitor.export_functions] == ["export_report"]
    assert visitor.draft_accepting_functions == []
