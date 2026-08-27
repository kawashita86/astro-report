"""Restore a ``GET /backup`` export into an empty database (Story 8.5).

Story 6.5 ships ``GET /backup`` -- the operator-held logical export that is
this application's real durability mechanism (AD-17: Neon's free plan has no
scheduled backups, only a ~6-hour PITR window). This module is the other
half: :func:`restore_backup` inserts every row of such an export back into an
empty schema, and ``python -m shell.restore <backup.json>`` is the operator
CLI that does it against the database named by ``DATABASE_URL``.

The restore is the exact inverse of ``shell/http/routes/backup.py``'s
serialization:

* The table set and its FK-safe order come from ``_BACKUP_MODELS`` **imported
  from that module** -- never a second hand-maintained list. A table added to
  ``/backup`` is automatically part of the restore.
* The export's top-level keys are ``model.__tablename__``; restore reads
  ``backup.get(model.__tablename__, [])`` for each model in ``_BACKUP_MODELS``
  order. A file missing a table's key (an export predating that table joining
  ``/backup``) restores that table as zero rows; the others are unaffected. A
  file carrying a top-level key this build does **not** know is a hard error --
  its rows have nowhere to go.
* Each row is reconstructed with ``Model.model_validate(row_dict)`` -- Pydantic
  v2 coercion turns ``model_dump(mode="json")``'s strings back into real types
  (``str`` -> ``UUID``, ISO ``str`` -> aware ``datetime`` via ``_UTCDateTime``,
  ``str`` -> ``Decimal`` for lat/long); the JSON columns (``planets``,
  ``payload``, ``theme``, ``violations``, ``draft``, ``transit_events``) pass
  straight through. No hand-written per-table decoder.

Restore is insert-into-empty only. It refuses a non-empty target
(:class:`RestoreTargetNotEmptyError`) before writing anything, and it never
updates or deletes an existing row -- run against a live populated database it
would only ever collide on a primary key or duplicate rows, so the zero-row
precondition makes that a loud refusal rather than a mess to unwind. Upsert,
merge, selective restore and schema-drift reconciliation are all out of scope
(this story's Boundaries).

``restore_backup`` does **not** commit -- the caller (the CLI below, or a
test) owns the transaction, so a failure on any table rolls the whole restore
back. ``place_cache`` (a recomputable geocoding cache) and ``backup_record``
(written fresh by ``GET /backup`` itself) are not in the export and are not
restored.

The CLI assumes the schema already exists: the runbook in
``docs/release-validation/restore-rehearsal.md`` runs ``alembic upgrade head``
first. This module never creates, drops, or migrates schema.

Import hygiene: ``load_backup`` and ``restore_backup`` are importable in a
minimal environment -- ``import shell.restore`` does not boot the FastAPI app
or force env validation. The ``_BACKUP_MODELS`` import (which pulls
``shell.http.app``) and the ``shell.config`` settings import are both deferred
to first use (see :func:`_backup_models` / :func:`_main`).
"""

from __future__ import annotations

import argparse
import json
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine, select

__all__ = ["RestoreTargetNotEmptyError", "load_backup", "restore_backup"]


class RestoreTargetNotEmptyError(RuntimeError):
    """The restore target already holds rows in a ``_BACKUP_MODELS`` table.

    Raised by :func:`restore_backup` before it writes anything. Restore is a
    disaster-recovery action into a *fresh* database (AD-17); a non-empty
    target means either a mistaken run against a live database or an
    already-restored one, both of which restore must refuse loudly rather
    than duplicate rows or collide on a primary key.
    """


def _backup_models() -> tuple[type, ...]:
    """The ``_BACKUP_MODELS`` tuple, imported lazily from
    ``shell/http/routes/backup.py`` -- restore's single source of truth for
    the table set and its FK-safe order.

    ``shell.http.routes.backup`` and ``shell.http.app`` are mutually recursive
    (the app imports the router lazily inside ``create_app``; the router
    imports ``get_session`` from the app), a cycle that only resolves when the
    app module is entered first -- hence the ``import shell.http.app`` here
    before the router import. Doing this on first use rather than at module
    import keeps ``import shell.restore`` free of the FastAPI app boot and the
    full env validation those imports trigger, so ``load_backup`` /
    ``restore_backup`` stay importable in a minimal environment.
    """
    import shell.http.app  # noqa: F401 -- imported to order the import cycle; see docstring
    from shell.http.routes.backup import _BACKUP_MODELS

    return _BACKUP_MODELS


def load_backup(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read and parse a ``GET /backup`` export file.

    Returns the parsed object: a mapping of ``__tablename__`` to a list of
    ``model_dump(mode="json")`` row dicts. Raises ``RuntimeError`` naming
    ``path`` if the file cannot be read, is not valid JSON, or does not have
    a JSON object at the top level. Per-table shape (unknown keys, non-list
    values) is validated later, by :func:`restore_backup`.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"restore: cannot read backup file {path}: {exc}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"restore: backup file {path} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"restore: backup file {path} has a {type(parsed).__name__} at the top level, "
            "expected a JSON object keyed by table name"
        )
    return parsed


def _validate_backup(
    backup: Mapping[str, list[dict[str, Any]]], models: tuple[type, ...]
) -> dict[str, int]:
    """Check ``backup``'s shape against the known table set and return the
    per-table row counts a restore *would* insert (no DB access, no writes).

    Raises ``RuntimeError`` if ``backup`` is not a mapping, carries a
    top-level key this build does not recognise (its rows have nowhere to
    go), or gives a non-list value for a known table.
    """
    if not isinstance(backup, Mapping):
        raise RuntimeError(
            f"restore: backup must be a mapping of table name to row list, "
            f"got {type(backup).__name__}"
        )

    known = {model.__tablename__ for model in models}
    unknown = sorted(set(backup) - known)
    if unknown:
        raise RuntimeError(
            f"restore: backup contains table(s) this build does not know: {unknown}; "
            "cannot place their rows. Restore only understands the current "
            "_BACKUP_MODELS set -- this file is likely from a newer schema."
        )

    for name in sorted(known & set(backup)):
        if not isinstance(backup[name], list):
            raise RuntimeError(
                f"restore: backup table {name!r} must be a JSON array of rows, "
                f"got {type(backup[name]).__name__}"
            )

    return {model.__tablename__: len(backup.get(model.__tablename__, [])) for model in models}


def _row_count(session: Session, model: type) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def _assert_target_empty(session: Session, models: tuple[type, ...]) -> None:
    """Raise :class:`RestoreTargetNotEmptyError` if any ``models`` table
    already holds a row -- restore only ever inserts into an empty schema."""
    non_empty = sorted(
        model.__tablename__ for model in models if _row_count(session, model) > 0
    )
    if non_empty:
        raise RestoreTargetNotEmptyError(
            "restore target is not empty -- these tables already hold rows: "
            + ", ".join(non_empty)
            + ". Restore only ever inserts into an empty schema; it never updates or "
            "deletes an existing row. Re-provision an empty database (or drop and "
            "recreate the schema) and retry."
        )


def restore_backup(
    session: Session, backup: Mapping[str, list[dict[str, Any]]]
) -> dict[str, int]:
    """Insert every row of ``backup`` into an empty schema, in FK-safe order.

    For each model in ``_BACKUP_MODELS`` order: reconstruct
    ``backup.get(model.__tablename__, [])`` with ``model.model_validate``,
    ``session.add_all`` them, and ``session.flush()`` -- so a table is only
    inserted after every table it foreign-keys into, and a failure on any
    table leaves the whole restore rolled back for the caller to handle. A
    per-table failure is re-raised as ``RuntimeError`` naming the table it
    died on.

    Validates ``backup``'s shape first (unknown top-level key -> error;
    non-list table value -> error; missing key -> that table restored as 0
    rows). Then refuses a non-empty target: if any ``_BACKUP_MODELS`` table
    already holds a row, raises :class:`RestoreTargetNotEmptyError` before
    inserting anything. Never updates or deletes an existing row.

    Does **not** commit -- the caller owns the transaction boundary.

    Returns a ``{tablename: inserted_row_count}`` dict.
    """
    models = _backup_models()
    _validate_backup(backup, models)
    _assert_target_empty(session, models)

    counts: dict[str, int] = {}
    for model in models:
        name = model.__tablename__
        try:
            rows = [model.model_validate(row) for row in backup.get(name, [])]
            session.add_all(rows)
            session.flush()
        except Exception as exc:
            raise RuntimeError(
                f"restore: failed while inserting table {name!r}: {exc}"
            ) from exc
        counts[name] = len(rows)
    return counts


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shell.restore",
        description=(
            "Restore a GET /backup export into the database named by DATABASE_URL. "
            "The schema must already exist (run `alembic upgrade head` first); the "
            "target must be empty. Restores in one transaction and prints a per-table "
            "row-count summary."
        ),
        epilog=(
            "Exit codes: 0 = restored; 2 = target not empty (re-provision an empty "
            "database, or drop and recreate the schema, then retry); 1 = any other "
            "failure (bad file, DB error, ...)."
        ),
    )
    parser.add_argument(
        "backup_file", type=Path, help="path to the backup-<UTC>.json file produced by GET /backup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "validate the file and the empty-target precondition, print the per-table "
            "row counts that would be inserted, and exit 0 without writing anything"
        ),
    )
    parser.add_argument(
        "--traceback",
        "-v",
        "--verbose",
        action="store_true",
        dest="traceback",
        help="on failure, also print the full Python traceback",
    )
    args = parser.parse_args(argv)

    # Deferred to here so `import shell.restore` needs no env; the CLI does.
    from shell.config import settings

    try:
        models = _backup_models()
        backup = load_backup(args.backup_file)
        would_insert = _validate_backup(backup, models)
        if sum(would_insert.values()) == 0:
            print(
                "restore: backup contains no rows for any known table -- is this the "
                "right file?"
            )

        engine = create_engine(settings.sqlalchemy_url, poolclass=NullPool)
        try:
            with Session(engine) as session:
                _assert_target_empty(session, models)
                if args.dry_run:
                    print(
                        f"dry run -- would restore {sum(would_insert.values())} row(s) "
                        f"from {args.backup_file} into {settings.redacted_database_url}:"
                    )
                    for name, count in would_insert.items():
                        print(f"  {name}: {count}")
                    return 0
                counts = restore_backup(session, backup)
                session.commit()
        finally:
            engine.dispose()
    except RestoreTargetNotEmptyError as exc:
        print(f"restore aborted: {exc}")
        if args.traceback:
            traceback.print_exc()
        return 2
    except Exception as exc:
        # An operator CLI: report and exit non-zero, never crash on a raw
        # traceback (unless --traceback asked for one).
        print(f"restore failed: {exc}")
        if args.traceback:
            traceback.print_exc()
        return 1

    total = sum(counts.values())
    print(
        f"restored {total} row(s) from {args.backup_file} into "
        f"{settings.redacted_database_url}"
    )
    for name, count in counts.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
