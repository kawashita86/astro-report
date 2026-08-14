"""Every migration is forward-only, mechanically.

A mistake in a migration is corrected by a new forward migration, never by
reverting one that has already run. That is a rule only while it is enforced:
a ``downgrade()`` body left empty by a future generator is silently reversible,
and the first person to reach for ``alembic downgrade`` gets a schema change
instead of the refusal this project promises.

Two things are checked — the revisions that exist now, and the template every
future revision is generated from.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS_DIR = REPO_ROOT / "migrations" / "versions"
SCRIPT_TEMPLATE = REPO_ROOT / "migrations" / "script.py.mako"


def revision_files() -> list[Path]:
    """Every revision on disk. ``rglob`` so a nested version directory is not missed."""
    files = [
        path
        for path in sorted(VERSIONS_DIR.rglob("*.py"))
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    ]
    assert files, "no revisions found; the guard would pass vacuously"
    return files


def load_revision(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", revision_files(), ids=lambda p: p.stem)
def test_downgrade_raises(path: Path) -> None:
    """`alembic downgrade` must raise rather than revert — matrix row 7."""
    module = load_revision(path)

    with pytest.raises(RuntimeError) as caught:
        module.downgrade()

    message = str(caught.value)
    assert "forward-only" in message, (
        f"{path.name}: downgrade raised, but the message does not explain why: {message!r}"
    )


@pytest.mark.parametrize("path", revision_files(), ids=lambda p: p.stem)
def test_downgrade_makes_no_schema_change_before_raising(path: Path) -> None:
    """The refusal is the whole body: nothing runs, so nothing is half-applied."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    downgrades = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade"
    ]
    assert len(downgrades) == 1, f"{path.name}: expected exactly one downgrade()"

    body = [
        statement
        for statement in downgrades[0].body
        if not (
            isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
        )
    ]
    assert body, f"{path.name}: downgrade() has an empty body and silently succeeds"
    assert all(isinstance(statement, ast.Raise) for statement in body), (
        f"{path.name}: downgrade() does work before raising; "
        "a partial downgrade is worse than a refused one"
    )


def test_the_generator_template_raises_too() -> None:
    """Future revisions inherit the refusal instead of relying on memory."""
    template = SCRIPT_TEMPLATE.read_text(encoding="utf-8")

    assert "def downgrade()" in template, "the template no longer defines downgrade()"
    downgrade_body = template.split("def downgrade()", 1)[1]
    # `raise` alone is satisfied by a docstring that merely mentions raising;
    # require the statement itself.
    assert "raise RuntimeError(" in downgrade_body, (
        "the revision template generates a downgrade() that does not raise; "
        "the next generated migration would be silently reversible"
    )
    assert "forward-only" in downgrade_body
