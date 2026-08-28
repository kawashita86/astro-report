# Restore rehearsal (Story 8.5)

`GET /backup` (Story 6.5) is this application's real durability mechanism —
AD-17 is explicit that Neon's free plan has **no scheduled backups**, only a
~6-hour point-in-time-restore window, so the operator-held logical export plus a
*rehearsed* restore is what stands between a dropped database and permanent data
loss. Story 6.5 shipped the export; nothing had ever restored one. This file is
the durable, dated record that the restore works: a complete export
reconstructed into an empty schema, a previously exported Report reopened with
its Payload and Gate result intact and its Claims still traceable, and the
procedure written down so it can be followed under pressure.

**Status: proven by the automated round-trip; operator dry-run against a real
Postgres still to be run.** The restore has been rehearsed end to end *in
process* — a fully-populated database serialized exactly as `GET /backup` does,
restored into an empty foreign-key-enforcing schema, and the restored Report
reopened — by `tests/test_restore.py`, which runs on every change. What has
**not** yet happened is the operator running `python -m shell.restore` against a
freshly provisioned empty Neon branch and signing off on the result. That step
(the runbook below) is recommended before release; this record is updated with
its real `source_backup`, `rows_restored`, `checked` / `ratified_on` and
`ratified_by` when it is done.

The machine-readable block below is parsed by `tests/test_restore.py`'s
record-guard half (mirroring `tests/test_data_terms_record.py`). The guard stays
red while `tables_restored` drifts from `_BACKUP_MODELS`
(`shell/http/routes/backup.py`), while `report_reopened` or `claims_traceable`
is anything but `true`, while `checked` / `ratified_on` are in the future or
`ratified_by` is blank, or while `outcome` is anything other than `"pass"`. Per
epic-8-retro-item-65 the guard also refuses `outcome = "pass"` unless
`rehearsed_against = "real-postgres"` — the in-process SQLite round-trip alone
is not enough for a release sign-off; the operator dry-run of `python -m
shell.restore` against a real Postgres must have been run.

```toml
checked = 2026-08-27
ratified_by = "automated round-trip (tests/test_restore.py); operator dry-run against a real Postgres pending"
ratified_on = 2026-08-27
source_backup = "in-process GET /backup serialization of a fully-populated test database (tests/test_restore.py::_populate_source / _serialize_as_backup)"
target = "empty in-process SQLite schema, foreign keys enforced (tests/test_restore.py::_fk_enforcing_engine); dry-run against an empty Neon Europe/Frankfurt branch still to be run"
tables_restored = ["client", "corpus_entry", "export_record", "gate_result", "natal_chart", "report", "report_draft", "report_payload", "report_run", "report_theme", "style_guide"]
rows_restored = 12
report_reopened = true
claims_traceable = true
rehearsed_against = "in-process-sqlite"
outcome = "blocked"
```

`tables_restored` is the **sorted** list of `model.__tablename__` for every
model in `_BACKUP_MODELS` — the single source of truth the export and the
restore share. `restore_backup` inserts them in `_BACKUP_MODELS` *FK-safe* order
(`client` first, `style_guide` last); this record lists them sorted so the guard
can bind them regardless of that order.

## What durability rests on

- **AD-17 — durability is an operator action.** One authenticated route
  (`GET /backup`) produces the complete logical export, downloaded to
  Francesco's machine; the Report History banner (Story 6.6) warns whenever the
  newest Report postdates the last export. Neon's free plan gives only a
  ~6-hour PITR window and no scheduled backups, so this export **is** the
  backup.
- **A backup nobody has restored is a hope, not a mechanism.** Epic 8 is the
  release gate; it requires the restore *demonstrated*. `restore_backup`
  (`shell/restore.py`) and its `python -m shell.restore <backup.json>` operator
  CLI are that demonstration, and this record is its dated proof.
- **No PRD change.** AD-17's "rehearsed restore" is satisfied by this record —
  no Assumptions Index item covers restore, and no number in `epics.md` moves.

## The procedure

The runbook Francesco follows when the live database is gone. Every step is a
command that can be run against a **newly provisioned** database — restore is
insert-into-empty only; it refuses a non-empty target
(`RestoreTargetNotEmptyError`) before writing anything, and never updates or
deletes an existing row.

1. **Get the export off-host.** The most recent `backup-<UTC>.json` from an
   authenticated `GET /backup`, held somewhere that is not the dead database's
   host. (If the app is still up, download a fresh one now — the banner tells
   you how stale the last one is.)
2. **Provision an empty Postgres.** A fresh Neon branch or project,
   `Europe/Frankfurt` (PRD §6.2 / `README.md` — storage stays in the EEA).
   Point `DATABASE_URL` at it.
3. **Apply the schema.** `uv run --env-file .env alembic upgrade head`. This
   step — and only this step — creates the schema; the restore CLI never
   creates, drops, or migrates anything.
4. **Restore.** Optionally dry-run first —
   `uv run --env-file .env python -m shell.restore --dry-run backup-<UTC>.json`
   validates the file and the empty-target precondition and prints the
   per-table counts it *would* insert, writing nothing. Then:
   `uv run --env-file .env python -m shell.restore backup-<UTC>.json`. It
   restores every table in one transaction, prints a per-table row-count
   summary, and exits **0** on success, **2** if the target is not empty, and
   **1** on any other failure (add `--traceback` to see the full stack).

   *If the restore fails partway, or you want to retry:* restore will not
   write into a non-empty target by design, so provision a fresh empty branch
   — or drop and recreate the schema (`alembic upgrade head` on a clean
   database) — before re-running. A failed run rolls its whole transaction
   back, so a half-restored database never happens; a *retry* still needs a
   genuinely empty target.
5. **Verify by hand.** Sign in. Open a known Report at `/report-runs/{id}/report`
   — confirm the eight Sections render and the Gate verdict shows — and its
   Payload at `/report-runs/{id}/payload`. Spot-check a Client's birth data and
   a Corpus entry.
6. **Record the outcome.** Fill in `checked`, `ratified_on`, `ratified_by`,
   `source_backup`, `rows_restored`, `report_reopened`, `claims_traceable` and
   `outcome` in the block above with the real dry-run values, and commit this
   file.

## What the rehearsal verified

`tests/test_restore.py` builds a full-depth source database — a real
`gate_passed` run (Client → Natal Chart → ReportRun → Report / Payload / Draft /
Theme / GateResult, reusing `tests/test_runner_driver.py`'s `_drive`) plus a
paired `CorpusEntry`, an `ExportRecord` and a second `StyleGuide` version —
serializes it byte-for-byte the way `download_backup` does, and restores it into
a second, empty, `PRAGMA foreign_keys=ON` schema. It asserts:

- **Every entity class round-tripped.** All eleven `_BACKUP_MODELS` tables
  restored with matching row counts (12 rows: one each across Clients, Natal
  Charts, Report Runs, Reports, Report Payloads, Report Drafts, Report Themes,
  Gate results, Export records and a Corpus entry, plus two Style Guide
  versions) and byte-identical JSON-column values (`planets` / `houses` /
  `aspects`, `payload`, `draft`, `theme`, `violations`, `transit_events`,
  `ephemeris_files`). `UUID` primary and foreign keys, aware UTC `datetime`s,
  and the `Decimal` latitude/longitude all reconstructed to their real types.
- **A previously exported Report reopened.** `GET /report-runs/{run_id}/report`
  for the run that had reached `gate_passed` before the export returned 200
  against the restored database, with all eight Sections rendered from the
  restored `ReportPayload`; its `/report-runs/{run_id}/payload` view resolved.
- **Claims stayed traceable.** The restored passing `StoredGateResult` for that
  run has `passed = true`, `violations = []` and its `vocabulary_version`
  intact, and the `ReportPayload` its Claims resolve against survived unchanged
  — so every citation in the reopened Report still points at real Payload data.
- **FK-safe order held.** With foreign keys enforced on the target, inserting
  the export's arrays in `_BACKUP_MODELS` order never referenced a missing row.
- **Restore refuses a non-empty target** and rolls back cleanly on any failure
  (the caller owns the single commit).

`place_cache` (a recomputable geocoding cache) and `backup_record` (written
fresh by `GET /backup` itself) are deliberately absent from the export and are
not restored; a freshly restored database simply shows "stale" until the next
backup.

### Still outstanding

The one thing the in-process round-trip cannot exercise is the real operator
path: a `backup-<UTC>.json` file from a live `GET /backup`, `alembic upgrade
head` against an empty **Neon** branch, and `python -m shell.restore` driven
from the shell with `DATABASE_URL` pointed at Postgres (not SQLite). The runbook
above is that path; running it once and pasting the real numbers into the block
is the remaining step before this record is a full operator sign-off.

## Outcome

**`blocked`** — the restore is proven to work *in process*: a complete
`GET /backup` export was restored into an empty, foreign-key-enforcing database
with full fidelity, a previously exported Report reopened with its Payload and
Gate result intact and its Claims still traceable, and the under-pressure
runbook above is written down. This is established by `tests/test_restore.py`,
which runs on every change.

What holds `outcome` at `blocked` is `rehearsed_against = "in-process-sqlite"`:
the operator dry-run of `python -m shell.restore` against a freshly provisioned
empty **Neon** Postgres branch (see *Still outstanding*) has not been run. Per
epic-8-retro-item-65 the guard now refuses `outcome = "pass"` while
`rehearsed_against` is not `"real-postgres"`, so `test_outcome_permits_release`
is a strict `xfail` until that dry-run is done — at which point set
`rehearsed_against = "real-postgres"`, fill in the real `source_backup` /
`rows_restored` / `checked` / `ratified_*` values, set `outcome = "pass"`, and
remove the `xfail` marker. The in-process round-trip is not expected to be
contradicted by that run.

## Re-rehearse triggers

Re-run `python -m shell.restore` against a fresh database and bump `checked`
(and `rows_restored` / `outcome` as needed) whenever any of these changes:

- **`_BACKUP_MODELS`** — a table added to or removed from `GET /backup`
  (`tests/test_restore.py`'s guard fails until `tables_restored` is updated to
  match and the rehearsal is re-run).
- **A migration altering a restored table's columns** — a new NOT NULL column,
  a type change, a renamed column: the old export's rows may no longer
  `model_validate` against the new schema.
- **A SQLModel / SQLAlchemy / Pydantic major bump** — the `model_dump(mode="json")`
  ↔ `model_validate` round trip the restore relies on could change.
- **Any change to how `GET /backup` serializes rows** — `restore_backup` inverts
  exactly that serialization.
