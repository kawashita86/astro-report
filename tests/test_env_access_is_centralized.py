"""Exactly one module reads the environment.

``shell/config.py`` validates the environment into a frozen settings object at
startup; everything else receives that object. This is a rule only while this
test exists — without it, the second reader arrives quietly, defaults something
that should have failed loudly, and the application serves in a configuration
nobody chose.

The check is syntactic on purpose: it parses the source rather than importing it,
so it catches a new reader in a module that is never imported by a test run.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Source roots that ship. Test support code is excluded: it constructs
#: environments deliberately and never runs in production.
SOURCE_ROOTS = ("core", "shell", "migrations")

#: The one module permitted to read the environment.
THE_ONLY_READER = Path("shell/config.py")

#: ``os`` members that read or write the process environment.
_OS_ENVIRONMENT_MEMBERS = frozenset(
    {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
)

#: Modules whose whole purpose is reading the environment from a file.
_ENVIRONMENT_MODULES = frozenset(
    {"dotenv", "environ", "environs", "decouple", "pydantic_settings"}
)


def files_under(root: str) -> list[Path]:
    return [
        path
        for path in sorted((REPO_ROOT / root).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def source_files() -> list[Path]:
    return [path for root in SOURCE_ROOTS for path in files_under(root)]


class EnvironmentAccessVisitor(ast.NodeVisitor):
    """Collect every syntactic route to the process environment."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []
        self._os_aliases: set[str] = {"os"}
        self._bound_env_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if alias.name == "os":
                self._os_aliases.add(alias.asname or "os")
            if root in _ENVIRONMENT_MODULES:
                self.findings.append((node.lineno, f"imports {alias.name}"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".")[0]
        if root in _ENVIRONMENT_MODULES:
            self.findings.append((node.lineno, f"imports from {module}"))
        elif module == "os":
            for alias in node.names:
                if alias.name in _OS_ENVIRONMENT_MEMBERS:
                    self._bound_env_names.add(alias.asname or alias.name)
                    self.findings.append((node.lineno, f"imports os.{alias.name}"))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        value = node.value
        if (
            isinstance(value, ast.Name)
            and value.id in self._os_aliases
            and node.attr in _OS_ENVIRONMENT_MEMBERS
        ):
            self.findings.append((node.lineno, f"reads {value.id}.{node.attr}"))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self._bound_env_names:
            self.findings.append((node.lineno, f"uses {node.id}"))
        self.generic_visit(node)


def environment_access(path: Path) -> list[tuple[int, str]]:
    visitor = EnvironmentAccessVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor.findings


@pytest.mark.parametrize(
    "path", source_files(), ids=lambda path: str(path.relative_to(REPO_ROOT))
)
def test_only_shell_config_reads_the_environment(path: Path) -> None:
    relative = path.relative_to(REPO_ROOT)
    findings = environment_access(path)

    if relative == THE_ONLY_READER:
        assert findings, (
            f"{relative} is meant to be the one reader of the environment, "
            "but it no longer reads it at all."
        )
        return

    assert not findings, (
        f"{relative} reads the environment directly: "
        + "; ".join(f"line {line}: {what}" for line, what in findings)
        + f". Only {THE_ONLY_READER} may do this — take a Settings object instead."
    )


@pytest.mark.parametrize("root", SOURCE_ROOTS)
def test_every_source_root_is_actually_covered(root: str) -> None:
    """Per-root, not in aggregate.

    Asserting only that the flattened list is non-empty means that if ``core/``
    were emptied or renamed, the files contributed by ``shell/`` would absorb the
    loss and the guard would keep reporting green over a tree it no longer reads.
    """
    root_path = REPO_ROOT / root
    assert root_path.is_dir(), (
        f"source root {root}/ does not exist; the guard silently stopped covering it"
    )
    assert files_under(root), (
        f"source root {root}/ contributed no files to the guard; its coverage "
        "would be lost without any test failing"
    )


def test_the_only_reader_exists() -> None:
    assert (REPO_ROOT / THE_ONLY_READER).is_file()


def test_the_guard_detects_a_new_reader(tmp_path: Path) -> None:
    """The guard is worthless if it cannot fail; prove each route is caught."""
    offenders = {
        "attribute.py": "import os\nvalue = os.environ['DATABASE_URL']\n",
        "aliased.py": "import os as operating_system\nvalue = operating_system.getenv('X')\n",
        "from_import.py": "from os import environ\nvalue = environ.get('X')\n",
        "renamed.py": "from os import getenv as read\nvalue = read('X')\n",
        "dotenv.py": "from dotenv import load_dotenv\nload_dotenv()\n",
        "environs.py": "from environs import Env\nenv = Env()\n",
        "import_environs.py": "import environs\nenv = environs.Env()\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        assert environment_access(path), f"{name} should have been flagged"

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "import os\npath = os.path.join('a', 'b')\nenviron = {'not': 'the real one'}\n",
        encoding="utf-8",
    )
    assert not environment_access(innocent)
