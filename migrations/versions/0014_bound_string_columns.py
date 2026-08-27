"""bound_client_and_chart_string_columns: an explicit length bound on three
previously-unbounded string columns (deferred-work item 41).

`client.name` (free-text, user-typed) -> `VARCHAR(200)`; `client.iana_zone`
(a real IANA zone id, Geocoder-resolved, never user-typed directly -- the
longest real id is ~33 characters) -> `VARCHAR(64)`;
`natal_chart.computation_config_content_hash` (a sha256 hex digest, always
exactly 64 characters) -> `VARCHAR(64)`. Mirrors each column's new
``Field(max_length=...)`` on ``Client``/``StoredNatalChart``
(``shell/adapters/postgres/client.py``). `client.name` is also rejected over
200 characters at the `/clients` and `/clients/{id}/edit` HTTP boundary
(``shell/http/routes/clients.py``) -- the only one of the three a caller
submits as raw text; `iana_zone`/`computation_config_content_hash` are
schema-only bounds, named out of scope for a form check by the deferred item
itself.

Out of scope (named out of scope by the deferred item itself):
``place_cache.iana_zone`` and ``report_payload.computation_config_content_hash``/
``.sections_config_content_hash`` -- a separate follow-up if ever needed.

Revision ID: 0014_bound_string_columns
Revises: 0013_gate_result
Create Date: 2026-08-26

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_bound_string_columns"
down_revision: str | None = "0013_gate_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "client", "name", existing_type=sa.String(), type_=sa.String(length=200)
    )
    op.alter_column(
        "client", "iana_zone", existing_type=sa.String(), type_=sa.String(length=64)
    )
    op.alter_column(
        "natal_chart",
        "computation_config_content_hash",
        existing_type=sa.String(),
        type_=sa.String(length=64),
    )


def downgrade() -> None:
    """Migrations are forward-only; a mistake is corrected by a new migration."""
    raise RuntimeError(
        f"Migration {revision} is forward-only and cannot be downgraded. "
        "Correct a mistake with a new forward migration."
    )
