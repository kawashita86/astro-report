"""The built image ships WeasyPrint's native runtime libraries and a serif font.

WeasyPrint 69 loads the Pango / GLib / HarfBuzz stack at *import* time, and
``shell/http/routes/report_runs.py`` imports ``html_to_pdf`` at module top
level, so a missing native library takes down ``create_app()`` -- uvicorn never
serves, the whole HTTP app is down, not just the PDF route. ``uv run pytest``
against a checkout can't catch that: no test here builds or runs the image, and
the developer's own machine already has these libraries. Without a structural
check on the Dockerfile, dropping a package from the ``apt-get install`` line
stays green here and only surfaces at an actual deploy.

Every check reads *code* (Dockerfile instruction lines with comments stripped),
never raw text, so a comment naming the right package can't satisfy an
assertion about it. The ``strip_comments`` helper is copied from
``test_dockerfile_ephemeris_build.py`` on purpose -- test modules do not import
each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"

# package -> why WeasyPrint needs it (surfaced in the failure message).
REQUIRED_PACKAGES = {
    "libpango-1.0-0": (
        "WeasyPrint 69 dlopen's Pango at import time; it also pulls libglib2.0-0, "
        "which provides libgobject-2.0-0 -- the exact symbol in the deploy crash"
    ),
    "libpangoft2-1.0-0": (
        "Pango's FreeType backend plus the fontconfig / FreeType bindings "
        "WeasyPrint dlopen's at import -- a separate package that libpango-1.0-0 "
        "does not pull in transitively"
    ),
    "libharfbuzz-subset0": (
        "a separate Debian package for PDF font subsetting that libpango does not "
        "pull in transitively -- easy to forget, fatal to omit"
    ),
    "fonts-liberation": (
        "report_export.html requests `Georgia, \"Times New Roman\", serif` and "
        "python:3.13-slim ships no fonts; Liberation Serif is metric-compatible "
        "with Times New Roman"
    ),
}


def strip_comments(dockerfile: str) -> list[str]:
    lines: list[str] = []
    for raw in dockerfile.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        lines.append(line)
    return lines


@pytest.fixture(scope="module")
def code() -> list[str]:
    assert DOCKERFILE.exists(), "the Dockerfile the image is built from is gone"
    return strip_comments(DOCKERFILE.read_text(encoding="utf-8"))


def _apt_install_line(lines: list[str]) -> str | None:
    for line in lines:
        if "apt-get install" in line:
            return line
    return None


def test_weasyprint_native_libs_are_on_the_apt_install_line(code: list[str]) -> None:
    install_line = _apt_install_line(code)

    assert install_line is not None, (
        "no `apt-get install` instruction in the Dockerfile; WeasyPrint's Pango / "
        "HarfBuzz native libraries would be missing and create_app() would crash "
        "on import inside the image"
    )

    missing = {
        pkg: reason
        for pkg, reason in REQUIRED_PACKAGES.items()
        if pkg not in install_line
    }

    assert not missing, "the Dockerfile's `apt-get install` line is missing:\n" + "\n".join(
        f"  - {pkg}: {reason}" for pkg, reason in missing.items()
    )


def test_a_comment_cannot_satisfy_the_weasyprint_libs_check() -> None:
    """Proof that stripping comments is doing real work."""
    only_a_comment = (
        "FROM python:3.13-slim\n"
        "# RUN apt-get install -y libpango-1.0-0 libharfbuzz-subset0 fonts-liberation\n"
        "RUN apt-get install --no-install-recommends -y build-essential\n"
    )
    code = strip_comments(only_a_comment)
    install_line = _apt_install_line(code)

    assert install_line is not None
    assert all(pkg not in install_line for pkg in REQUIRED_PACKAGES)
