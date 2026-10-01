"""Only ``shell/runner/driver.py`` may create a thread, an executor or an async task (AD-20).

A background loop that appears in some handler or adapter is how a deployment ends up with
work nobody owns -- unbounded, unobserved, lost on restart. The ``RunDriver`` is the one
declared place; everything else stays synchronous and is called by it. This is a rule only
while this test exists.

Like ``tests/test_import_boundary.py`` the check is syntactic: it parses source with ``ast``
rather than importing it. It flags *creating* concurrency -- importing ``concurrent.futures``
or ``multiprocessing``, ``Thread``/``Timer``/executor construction, and the asyncio/anyio
task and executor entry points. Thread-local *state* (``threading.local``, which
``core/ephemeris/identity.py`` needs because the Swiss Ephemeris path is per-thread) creates
nothing and is not flagged.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The one module permitted to create concurrency.
ALLOWED = frozenset({Path("shell/runner/driver.py")})

#: Production source trees scanned (tests, migrations and tooling are not application code).
_ROOTS = ("core", "shell")

_FORBIDDEN_MODULES = frozenset({"concurrent.futures", "multiprocessing", "_thread"})
_FORBIDDEN_THREADING_NAMES = frozenset({"Thread", "Timer", "start_new_thread"})
_FORBIDDEN_CALLS = frozenset(
    {
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "create_task",
        "ensure_future",
        "to_thread",
        "run_in_executor",
        "run_in_threadpool",
        "TaskGroup",
    }
)


class _Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.split(".")[0] in {"multiprocessing", "_thread"} or (
                alias.name == "concurrent.futures" or alias.name.startswith("concurrent.futures.")
            ):
                self.findings.append((node.lineno, f"import {alias.name}"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module in _FORBIDDEN_MODULES or module.startswith("concurrent.futures"):
            self.findings.append((node.lineno, f"from {module} import ..."))
        if module == "concurrent" and any(alias.name == "futures" for alias in node.names):
            self.findings.append((node.lineno, "from concurrent import futures"))
        if module == "threading":
            for alias in node.names:
                if alias.name in _FORBIDDEN_THREADING_NAMES:
                    self.findings.append((node.lineno, f"from threading import {alias.name}"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in _FORBIDDEN_CALLS:
            self.findings.append((node.lineno, f"call to {name}()"))
        if (
            isinstance(func, ast.Attribute)
            and func.attr in _FORBIDDEN_THREADING_NAMES
            and isinstance(func.value, ast.Name)
            and func.value.id == "threading"
        ):
            self.findings.append((node.lineno, f"call to threading.{func.attr}()"))
        self.generic_visit(node)


def concurrency_findings(path: Path) -> list[tuple[int, str]]:
    visitor = _Visitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return visitor.findings


def application_files() -> list[Path]:
    return sorted(
        path
        for root in _ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if "__pycache__" not in path.parts
    )


@pytest.mark.parametrize(
    "path", application_files(), ids=lambda path: str(path.relative_to(REPO_ROOT))
)
def test_only_the_run_driver_creates_threads_executors_or_tasks(path: Path) -> None:
    relative = path.relative_to(REPO_ROOT)
    if relative in ALLOWED:
        pytest.skip("the declared exception")
    findings = concurrency_findings(path)
    assert not findings, (
        f"{relative} creates concurrency: "
        + "; ".join(f"line {line}: {what}" for line, what in findings)
        + ". Only shell/runner/driver.py may (AD-20)."
    )


def test_the_guard_is_actually_covered() -> None:
    files = {path.relative_to(REPO_ROOT) for path in application_files()}
    assert Path("shell/runner/driver.py") in files
    assert Path("shell/http/app.py") in files
    assert Path("core/ephemeris/identity.py") in files


def test_the_declared_exception_really_creates_concurrency() -> None:
    """If the driver stopped using executors the allowance would be a silent hole."""
    findings = concurrency_findings(REPO_ROOT / "shell/runner/driver.py")

    assert any("ThreadPoolExecutor" in what for _, what in findings)


def test_the_guard_detects_a_thread_executor_or_task(tmp_path: Path) -> None:
    offenders = {
        "import_futures.py": "import concurrent.futures\n",
        "from_futures.py": "from concurrent.futures import ThreadPoolExecutor\n",
        "from_concurrent.py": "from concurrent import futures\n",
        "multiprocessing.py": "import multiprocessing\n",
        "thread_attr.py": "import threading\nthreading.Thread(target=print).start()\n",
        "thread_from.py": "from threading import Thread\n",
        "timer.py": "import threading\nthreading.Timer(1, print)\n",
        "executor_call.py": "pool = ThreadPoolExecutor(max_workers=1)\n",
        "create_task.py": "import asyncio\nasyncio.create_task(main())\n",
        "ensure_future.py": "import asyncio\nasyncio.ensure_future(main())\n",
        "to_thread.py": "import asyncio\nawait asyncio.to_thread(work)\n",
        "run_in_executor.py": "loop.run_in_executor(None, work)\n",
    }
    for name, source in offenders.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        assert concurrency_findings(path), f"{name} should have been flagged"


def test_the_guard_does_not_flag_thread_local_state_or_plain_code(tmp_path: Path) -> None:
    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "import threading\nimport asyncio\n\nstate = threading.local()\n"
        "lock = threading.Lock()\n\nasync def f():\n    await asyncio.sleep(0)\n",
        encoding="utf-8",
    )

    assert not concurrency_findings(innocent)
