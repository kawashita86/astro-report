"""Parse ``data/style-guide.seed.md``'s ``version: N`` marker and body
(Story 4.2).

The sole consumer is ``migrations/versions/0007_style_guide.py``'s
``upgrade()``, which inserts the returned body as the ``style_guide`` table's
version-1 row -- exactly once, ever, since Alembic's own revision tracking
never re-runs an applied migration. This module never touches the database
itself; it only reads and validates the seed file, mirroring
``shell/computation.py``'s ``_read_version()``/``load_computation_config()``
shape (naming every offense rather than letting a raw ``OSError``,
``UnicodeDecodeError`` or malformed-marker case escape untyped).
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["DEFAULT_STYLE_GUIDE_SEED_PATH", "StyleGuideSeedError", "load_style_guide_seed"]

DEFAULT_STYLE_GUIDE_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "style-guide.seed.md"
)

#: The marker line's shape: "version: " plus a bare (non-negative) integer,
#: possibly surrounded by whitespace once the line itself is stripped --
#: matches ``data/style-guide.seed.md``'s ``version: 1`` line.
_MARKER_PATTERN = re.compile(r"^version:\s*(\d+)\s*$")


class StyleGuideSeedError(RuntimeError):
    """The seed file cannot be trusted to seed ``style_guide`` version 1.

    Raised when the file is missing or unreadable, is not valid UTF-8, has no
    ``version: N`` marker line, or names a version other than ``1`` -- the
    only version this seed file is ever entitled to produce (every revision
    after that lives in the database, not this file). There is no partial or
    best-guess body to seed with: the migration that calls this must fail
    loudly rather than seed a database with content nobody asked for.
    """


def load_style_guide_seed(path: Path = DEFAULT_STYLE_GUIDE_SEED_PATH) -> str:
    """Read ``path``, verify its ``version: 1`` marker line, and return the
    body that follows it -- the marker line itself, and everything before it
    (the seed file's own title and administrative note), are discarded: they
    describe the seeding mechanism, not content a future database row should
    carry forward.
    """
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise StyleGuideSeedError(
            f"Refusing to seed: style guide seed not found at {path}: {error}."
        ) from error

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StyleGuideSeedError(
            f"Refusing to seed: style guide seed {path} could not be decoded as UTF-8: {error}."
        ) from error

    lines = text.splitlines()
    marker_index: int | None = None
    version: int | None = None
    for index, line in enumerate(lines):
        match = _MARKER_PATTERN.match(line.strip())
        if match is not None:
            marker_index = index
            version = int(match.group(1))
            break

    if marker_index is None or version is None:
        raise StyleGuideSeedError(
            f"Refusing to seed: style guide seed {path} has no 'version: N' marker line."
        )
    if version != 1:
        raise StyleGuideSeedError(
            f"Refusing to seed: style guide seed {path} names version {version}, expected 1."
        )

    body = "\n".join(lines[marker_index + 1 :]).strip()
    if not body:
        raise StyleGuideSeedError(
            f"Refusing to seed: style guide seed {path} has no body after its version marker."
        )
    return body
