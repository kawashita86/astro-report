"""``core/`` never imports ``shell/`` and touches nothing outside itself.

``shell/`` may import ``core/``; the reverse never happens, and outside the
single declared exception -- ``core/ephemeris/``, which reads its vendored
``.se1`` files from disk (AD-1) -- nothing under ``core/`` may reach the
network, the clock, the filesystem or the environment either. This is a rule
only while this test exists: without it, a future change imports ``shell/``
into ``core/`` once, or reads the clock from inside a domain module once, and
the byte-identical-Payload guarantee is broken -- possibly silently.

The check is syntactic on purpose, mirroring
``tests/test_env_access_is_centralized.py``: it parses source with ``ast``
rather than importing it, so a module the app never happens to import at
test time is still caught. Two independently parametrized passes keep the
ephemeris exception from leaking into the simpler shell-import rule, which
has none.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories that are not this project's own source: virtual environments,
#: VCS metadata, tooling and planning artifacts, caches, and plausible future
#: vendor/build trees that could otherwise produce a false positive.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".venv",
        ".git",
        "__pycache__",
        "_bmad",
        "_bmad-output",
        ".idea",
        ".ruff_cache",
        ".pytest_cache",
        ".tokensave",
        ".mypy_cache",
        "node_modules",
        ".claude",
        "vendor",
        "dist",
        "build",
        "htmlcov",
    }
)

#: Reserved names that must never label a module or package anywhere in the
#: tree -- a grab-bag module is where the purity boundary quietly rots.
FORBIDDEN_MODULE_NAMES = frozenset({"utils", "helpers", "common"})

#: Modules whose import alone reaches the network or spawns another process
#: (which can itself reach the network, filesystem, clock or environment).
_NETWORK_MODULES = frozenset(
    {
        "socket",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ssl",
        "http",
        "ftplib",
        "smtplib",
        "websockets",
        "grpc",
        "subprocess",
    }
)

#: ``os`` members that read or write the process environment (reused from
#: test_env_access_is_centralized.py rather than re-derived).
_OS_ENVIRONMENT_MEMBERS = frozenset(
    {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
)

#: Modules whose whole purpose is reading the environment from a file
#: (reused from test_env_access_is_centralized.py rather than re-derived).
#: ``environ`` is django-environ's import name, not a typo for ``environs``
#: (a different, also-real package) -- both are listed.
_ENVIRONMENT_MODULES = frozenset({"dotenv", "environ", "environs", "decouple", "pydantic_settings"})

#: ``time`` members that read the clock.
_CLOCK_TIME_MEMBERS = frozenset(
    {"time", "monotonic", "monotonic_ns", "time_ns", "perf_counter", "perf_counter_ns",
     "gmtime", "localtime"}
)

#: ``datetime.datetime``/``datetime.date`` members that read the clock.
_CLOCK_DATETIME_MEMBERS = frozenset({"now", "utcnow", "today"})

#: ``os`` members that touch the filesystem.
_OS_FILESYSTEM_MEMBERS = frozenset(
    {"open", "listdir", "scandir", "stat", "remove", "mkdir", "rmdir", "rename", "walk"}
)

#: ``pathlib.Path`` members that touch the filesystem.
_PATH_FILESYSTEM_MEMBERS = frozenset(
    {
        "open",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "exists",
        "is_file",
        "is_dir",
        "mkdir",
        "unlink",
        "iterdir",
        "glob",
        "rglob",
        "stat",
    }
)


def files_under(root: str) -> list[Path]:
    return [
        path
        for path in sorted((REPO_ROOT / root).rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def core_files() -> list[Path]:
    return files_under("core")


def is_ephemeris(relative_path: Path) -> bool:
    """True for anything under ``core/ephemeris/`` -- the single declared exception."""
    parts = relative_path.parts
    return len(parts) >= 2 and parts[0] == "core" and parts[1] == "ephemeris"


def core_files_outside_ephemeris() -> list[Path]:
    return [path for path in core_files() if not is_ephemeris(path.relative_to(REPO_ROOT))]


def forbidden_module_names(root: Path) -> list[Path]:
    """Every file or directory under ``root`` named utils, helpers or common."""
    offenders: list[Path] = []
    for path in sorted(root.rglob("*")):
        if any(part in _EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        is_forbidden_dir = path.is_dir() and path.name in FORBIDDEN_MODULE_NAMES
        is_forbidden_file = (
            path.is_file() and path.suffix == ".py" and path.stem in FORBIDDEN_MODULE_NAMES
        )
        if is_forbidden_dir or is_forbidden_file:
            offenders.append(path)
    return offenders


class ShellImportVisitor(ast.NodeVisitor):
    """Collect every syntactic import reaching into ``shell/``."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] == "shell":
                self.findings.append((node.lineno, f"imports {alias.name}"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if node.level == 0 and module.split(".")[0] == "shell":
            self.findings.append((node.lineno, f"imports from {module}"))
        self.generic_visit(node)


class ForbiddenFacilityVisitor(ast.NodeVisitor):
    """Collect every syntactic route to the network, clock, filesystem or environment.

    Using ``datetime``/``Decimal``/etc. as *types* on values passed in is not a
    violation -- only reading the clock or a file is -- so this visitor tracks
    specific members and call shapes, not whole-module imports of ``time`` or
    ``datetime``/``pathlib``. Module and class aliases (``import time as t``,
    ``from datetime import datetime as X``) are tracked explicitly, the same
    way ``os`` aliases already are -- an aliased import is an ordinary Python
    style choice, not an evasion, and the guard must see through it.
    """

    def __init__(self) -> None:
        self.findings: list[tuple[int, str, str]] = []
        self._os_aliases: set[str] = {"os"}
        self._time_module_aliases: set[str] = set()
        self._datetime_module_aliases: set[str] = set()
        self._datetime_class_aliases: set[str] = set()
        self._date_class_aliases: set[str] = set()
        self._path_aliases: set[str] = set()
        self._path_var_names: set[str] = set()
        self._bound_env_names: set[str] = set()
        self._bound_clock_names: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if alias.name == "os":
                self._os_aliases.add(alias.asname or "os")
            if root == "time":
                self._time_module_aliases.add(alias.asname or "time")
            if root == "datetime":
                self._datetime_module_aliases.add(alias.asname or "datetime")
            if root in _NETWORK_MODULES:
                self.findings.append((node.lineno, "network", f"imports {alias.name}"))
            if root in _ENVIRONMENT_MODULES:
                self.findings.append((node.lineno, "environment", f"imports {alias.name}"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".")[0]
        if root in _NETWORK_MODULES:
            self.findings.append((node.lineno, "network", f"imports from {module}"))
        elif root in _ENVIRONMENT_MODULES:
            self.findings.append((node.lineno, "environment", f"imports from {module}"))
        elif module == "os":
            for alias in node.names:
                if alias.name in _OS_ENVIRONMENT_MEMBERS:
                    self._bound_env_names.add(alias.asname or alias.name)
                    self.findings.append(
                        (node.lineno, "environment", f"imports os.{alias.name}")
                    )
        elif module == "time":
            for alias in node.names:
                if alias.name in _CLOCK_TIME_MEMBERS:
                    self._bound_clock_names.add(alias.asname or alias.name)
                    self.findings.append((node.lineno, "clock", f"imports time.{alias.name}"))
        elif module == "pathlib":
            for alias in node.names:
                if alias.name == "Path":
                    self._path_aliases.add(alias.asname or alias.name)
        elif module == "datetime":
            for alias in node.names:
                if alias.name == "datetime":
                    self._datetime_class_aliases.add(alias.asname or alias.name)
                if alias.name == "date":
                    self._date_class_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_path_expression(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._path_var_names.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id == "open":
                self.findings.append((node.lineno, "filesystem", "calls open(...)"))
            elif node.func.id in self._bound_clock_names:
                self.findings.append((node.lineno, "clock", f"calls {node.func.id}(...)"))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        value = node.value

        if (
            isinstance(value, ast.Name)
            and value.id in self._os_aliases
            and node.attr in _OS_ENVIRONMENT_MEMBERS
        ):
            self.findings.append((node.lineno, "environment", f"reads {value.id}.{node.attr}"))

        if (
            isinstance(value, ast.Name)
            and value.id in self._os_aliases
            and node.attr in _OS_FILESYSTEM_MEMBERS
        ):
            self.findings.append((node.lineno, "filesystem", f"calls {value.id}.{node.attr}"))

        if (
            isinstance(value, ast.Name)
            and value.id in self._time_module_aliases
            and node.attr in _CLOCK_TIME_MEMBERS
        ):
            self.findings.append((node.lineno, "clock", f"reads {value.id}.{node.attr}"))

        if node.attr in _CLOCK_DATETIME_MEMBERS:
            if (
                isinstance(value, ast.Attribute)
                and value.attr in ("datetime", "date")
                and isinstance(value.value, ast.Name)
                and value.value.id in self._datetime_module_aliases
            ):
                self.findings.append(
                    (node.lineno, "clock", f"reads {value.value.id}.{value.attr}.{node.attr}")
                )
            elif isinstance(value, ast.Name) and (
                value.id in self._datetime_class_aliases or value.id in self._date_class_aliases
            ):
                self.findings.append((node.lineno, "clock", f"reads {value.id}.{node.attr}"))

        if node.attr in _PATH_FILESYSTEM_MEMBERS and (
            self._is_path_expression(value)
            or (isinstance(value, ast.Name) and value.id in self._path_var_names)
        ):
            self.findings.append((node.lineno, "filesystem", f"calls Path(...).{node.attr}"))

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self._bound_env_names:
            self.findings.append((node.lineno, "environment", f"uses {node.id}"))
        self.generic_visit(node)

    def _is_path_expression(self, node: ast.AST) -> bool:
        """True for ``Path(...)`` and ``pathlib.Path(...)`` call expressions."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in self._path_aliases
        if isinstance(func, ast.Attribute):
            return func.attr == "Path"
        return False


def shell_import_findings(path: Path) -> list[tuple[int, str]]:
    visitor = ShellImportVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor.findings


def forbidden_facility_findings(path: Path) -> list[tuple[int, str, str]]:
    visitor = ForbiddenFacilityVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor.findings


# --- core/ never imports shell/, no exceptions ------------------------------


@pytest.mark.parametrize("path", core_files(), ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_core_never_imports_shell(path: Path) -> None:
    relative = path.relative_to(REPO_ROOT)
    findings = shell_import_findings(path)
    assert not findings, (
        f"{relative} imports from shell/: "
        + "; ".join(f"line {line}: {what}" for line, what in findings)
        + ". core/ may never import shell/, anywhere, no exceptions."
    )


def test_core_is_actually_covered() -> None:
    """If core/ were emptied or renamed, an empty parametrize would report green
    over a tree it no longer reads."""
    assert core_files(), "core/ contributed no files to the guard"


def test_the_guard_detects_a_shell_import(tmp_path: Path) -> None:
    offenders = {
        "plain.py": "import shell\n",
        "submodule.py": "import shell.config\n",
        "from_import.py": "from shell.config import Settings\n",
        "from_submodule.py": "from shell import http\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        assert shell_import_findings(path), f"{name} should have been flagged"

    innocent = tmp_path / "innocent.py"
    innocent.write_text("import core\nfrom core import errors\n", encoding="utf-8")
    assert not shell_import_findings(innocent)


# --- core/, outside core/ephemeris/, touches no facility --------------------


@pytest.mark.parametrize(
    "path",
    core_files_outside_ephemeris(),
    ids=lambda path: str(path.relative_to(REPO_ROOT)),
)
def test_core_touches_no_facility_outside_ephemeris(path: Path) -> None:
    relative = path.relative_to(REPO_ROOT)
    findings = forbidden_facility_findings(path)
    assert not findings, (
        f"{relative} reaches a forbidden facility outside core/ephemeris/: "
        + "; ".join(f"line {line}: [{category}] {what}" for line, category, what in findings)
        + ". Only core/ephemeris/ may touch the world."
    )


def test_ephemeris_exception_is_exercised() -> None:
    """The carve-out only matters if it actually removes files from the facility
    check -- otherwise it could silently stop applying and no test would notice."""
    all_core = {p.relative_to(REPO_ROOT) for p in core_files()}
    outside = {p.relative_to(REPO_ROOT) for p in core_files_outside_ephemeris()}
    ephemeris_only = all_core - outside
    assert ephemeris_only, (
        "core/ephemeris/ contributed no files, so the exception carve-out is "
        "not actually being tested by this guard"
    )
    assert all(is_ephemeris(path) for path in ephemeris_only)


def test_core_outside_ephemeris_is_actually_covered() -> None:
    """The mirror image of test_ephemeris_exception_is_exercised: if every file
    under core/ moved into core/ephemeris/, the facility parametrize would go
    empty and report green over a tree it no longer reads."""
    assert core_files_outside_ephemeris(), (
        "core/ outside core/ephemeris/ contributed no files, so the facility "
        "guard is not actually being tested"
    )


def test_ephemeris_is_recognised_as_the_declared_exception() -> None:
    assert is_ephemeris(Path("core/ephemeris/loader.py"))
    assert is_ephemeris(Path("core/ephemeris/__init__.py"))
    assert not is_ephemeris(Path("core/transits/foo.py"))
    assert not is_ephemeris(Path("core/ephemeris.py"))  # a file, not the package


def test_the_guard_detects_a_network_reader(tmp_path: Path) -> None:
    offenders = {
        "socket_.py": "import socket\n",
        "urllib_.py": "import urllib.request\n",
        "urllib3_.py": "import urllib3\n",
        "requests_.py": "import requests\n",
        "httpx_.py": "from httpx import Client\n",
        "aiohttp_.py": "import aiohttp\n",
        "ssl_.py": "import ssl\n",
        "http_client.py": "import http.client\n",
        "ftplib_.py": "import ftplib\n",
        "smtplib_.py": "import smtplib\n",
        "subprocess_import.py": "import subprocess\n",
        "subprocess_from.py": "from subprocess import run\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        findings = forbidden_facility_findings(path)
        assert findings and findings[0][1] == "network", f"{name} should have been flagged"


def test_the_guard_detects_a_clock_reader(tmp_path: Path) -> None:
    offenders = {
        "time_time.py": "import time\nvalue = time.time()\n",
        "time_monotonic.py": "import time\nvalue = time.monotonic()\n",
        "time_perf_counter.py": "import time\nvalue = time.perf_counter()\n",
        "time_aliased.py": "import time as t\nvalue = t.time()\n",
        "time_aliased_monotonic.py": "import time as t\nvalue = t.monotonic()\n",
        "from_time_import.py": "from time import time\nvalue = time()\n",
        "datetime_now.py": "import datetime\nvalue = datetime.datetime.now()\n",
        "datetime_utcnow.py": "from datetime import datetime\nvalue = datetime.utcnow()\n",
        "datetime_today.py": "import datetime\nvalue = datetime.datetime.today()\n",
        "datetime_aliased.py": "import datetime as dt\nvalue = dt.datetime.now()\n",
        "date_today.py": "from datetime import date\nvalue = date.today()\n",
        "datetime_date_today.py": "import datetime\nvalue = datetime.date.today()\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        findings = forbidden_facility_findings(path)
        assert findings and findings[0][1] == "clock", f"{name} should have been flagged"

    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "from datetime import datetime, timedelta\n"
        "from decimal import Decimal\n"
        "\n"
        "\n"
        "def add(base: datetime, delta: timedelta) -> datetime:\n"
        "    return base + delta\n"
        "\n"
        "\n"
        "def price(x: Decimal) -> Decimal:\n"
        "    return x\n",
        encoding="utf-8",
    )
    assert not forbidden_facility_findings(innocent)


def test_the_guard_detects_a_filesystem_reader(tmp_path: Path) -> None:
    offenders = {
        "builtin_open.py": "value = open('x')\n",
        "os_open.py": "import os\nvalue = os.open('x', 0)\n",
        "os_listdir.py": "import os\nvalue = os.listdir('x')\n",
        "os_remove.py": "import os\nos.remove('x')\n",
        "path_read_text.py": "from pathlib import Path\nvalue = Path('x').read_text()\n",
        "path_write_text.py": "from pathlib import Path\nPath('x').write_text('y')\n",
        "path_read_bytes.py": "from pathlib import Path\nvalue = Path('x').read_bytes()\n",
        "path_open.py": "from pathlib import Path\nvalue = Path('x').open()\n",
        "path_var.py": "from pathlib import Path\np = Path('x')\nvalue = p.read_text()\n",
        "path_exists.py": "from pathlib import Path\nvalue = Path('x').exists()\n",
        "path_iterdir.py": "from pathlib import Path\nvalue = list(Path('x').iterdir())\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        findings = forbidden_facility_findings(path)
        assert findings and findings[0][1] == "filesystem", f"{name} should have been flagged"


def test_the_guard_detects_an_environment_reader(tmp_path: Path) -> None:
    offenders = {
        "attribute.py": "import os\nvalue = os.environ['DATABASE_URL']\n",
        "getenv.py": "import os\nvalue = os.getenv('X')\n",
        "from_import.py": "from os import environ\nvalue = environ.get('X')\n",
        "dotenv.py": "from dotenv import load_dotenv\nload_dotenv()\n",
        "environs_.py": "import environs\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        findings = forbidden_facility_findings(path)
        assert findings and findings[0][1] == "environment", f"{name} should have been flagged"


# --- no module anywhere in the tree is a grab-bag utils/helpers/common ------


def test_no_module_is_named_utils_helpers_or_common() -> None:
    offenders = forbidden_module_names(REPO_ROOT)
    assert not offenders, "forbidden grab-bag module name(s): " + ", ".join(
        str(path.relative_to(REPO_ROOT)) for path in offenders
    )


def test_the_guard_detects_a_forbidden_module_name(tmp_path: Path) -> None:
    (tmp_path / "utils.py").write_text("", encoding="utf-8")
    (tmp_path / "helpers.py").write_text("", encoding="utf-8")
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "__init__.py").write_text('"""x"""\n', encoding="utf-8")
    (tmp_path / "innocent.py").write_text("", encoding="utf-8")

    offenders = {path.name for path in forbidden_module_names(tmp_path)}
    assert offenders == {"utils.py", "helpers.py", "common"}


def test_vendor_and_build_directories_are_excluded_from_the_name_scan(tmp_path: Path) -> None:
    for dirname in ("vendor", "dist", "build", ".mypy_cache", "htmlcov"):
        nested = tmp_path / dirname / "utils.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("", encoding="utf-8")

    assert not forbidden_module_names(tmp_path)
