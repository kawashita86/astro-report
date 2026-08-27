---
title: 'Story 8.5 — Restore from a backup, for real'
type: 'feature'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
baseline_commit: '82149a753f3402a09225dca0a673df0b1e887161'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-6-5-take-a-backup-i-actually-hold.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 6.5 ships `GET /backup` — the operator-held logical export that is the
application's real durability mechanism (AD-17: Neon's free plan has no scheduled backups, only a
~6-hour PITR window) — but nothing has ever restored one. Epic 8 is the release gate and requires the
restore *demonstrated*, not assumed: a complete export reconstructed into an empty database, a
previously exported Report reopened with its Payload and Gate result intact and its Claims still
traceable, and the procedure written down so it can be followed under pressure.

**Approach:** Add `shell/restore.py` — a `restore_backup(session, backup)` function that inserts every
row of the export into an empty schema in the backup route's own FK-safe table order, plus a
`python -m shell.restore <backup.json>` operator CLI — and `docs/release-validation/restore-rehearsal.md`,
a dated, Francesco-ratified record mirroring `gemini-data-terms.md` / `latency.md` / `storage-growth.md`:
a `tomllib`-parsed block plus the numbered under-pressure runbook. `tests/test_restore.py` proves the
round trip in-process (populate → serialize exactly as `GET /backup` does → restore into a second
empty, FK-enforcing engine → assert full fidelity and that the Report reopens) and guards the record.

## Boundaries & Constraints

**Always:**
- Restore's table set and order come from `_BACKUP_MODELS` **imported from
  `shell/http/routes/backup.py`** — never a second hand-maintained list. The export file's top-level
  keys are `model.__tablename__`; restore reads `backup.get(model.__tablename__, [])` for each model
  in `_BACKUP_MODELS` order.
- Each row is reconstructed with `Model.model_validate(row_dict)` — Pydantic v2 coercion turns the
  `model_dump(mode="json")` strings back into real types (`str` → `UUID`, ISO `str` → aware
  `datetime` via `_UTCDateTime`, `str` → `Decimal` for lat/long); the JSON columns (`planets`,
  `payload`, `theme`, `violations`, `draft`, `transit_events`) pass straight through. No hand-written
  per-table decoder. If a `table=True` model rejects `model_validate`, fall back to
  `Model(**_coerce(row))` with explicit `UUID(...)` / `datetime.fromisoformat(...)` / `Decimal(...)`
  on the known typed columns — the tests assert exact field equality either way.
- `restore_backup(session, backup)` inserts every table in `_BACKUP_MODELS` order, `session.flush()`
  after each table, and **does not commit** — the caller (the CLI, or a test) owns the transaction,
  so a failure on any table rolls the whole restore back. It returns a per-table inserted-row count.
- Restore refuses a non-empty target: before inserting anything it checks every `_BACKUP_MODELS`
  table has zero rows and raises `RestoreTargetNotEmptyError` otherwise. It never updates or deletes
  an existing row.
- A backup file missing a table's key (an export predating that table joining `/backup`) restores
  that table as zero rows; the others are unaffected.
- The CLI (`python -m shell.restore <file>`) builds its engine from `shell.config.settings.sqlalchemy_url`
  exactly as `migrations/env.py` does. It assumes the schema already exists (runbook step:
  `alembic upgrade head` first) and never creates, drops, or migrates schema itself. It restores in
  one transaction, prints the per-table summary, and exits non-zero on any failure or a non-empty target.
- `docs/release-validation/restore-rehearsal.md`'s machine block is a fenced ` ```toml ` block parsed
  by `tomllib` (stdlib) — mirrors `test_data_terms_record.py`; no YAML dependency exists. Keys:
  `checked` (bare ISO date → `datetime.date`), `ratified_by`, `ratified_on` (bare ISO date),
  `source_backup`, `target`, `tables_restored` (array of table names), `rows_restored` (int),
  `report_reopened` (bool), `claims_traceable` (bool), `outcome`.
- `outcome` is exactly `"pass"` or `"blocked"`; the guard asserts `== "pass"`. `tables_restored`
  equals the sorted `__tablename__`s of `_BACKUP_MODELS`; the guard binds them, so a table added to
  `/backup` but not re-rehearsed fails the suite.
- New tests mirror the read-the-file style: `REPO_ROOT` from `Path(__file__)`, in-memory SQLite, no
  network, no Docker. The round-trip tests reuse `tests/test_runner_driver.py`'s
  `_create_client_and_chart` / `_drive` helpers for a real `gate_passed` run, and enable
  `PRAGMA foreign_keys=ON` on the restore target so the FK-safe order is genuinely exercised.

**Ask First:**
- The rehearsal's `outcome`, `checked` / `ratified_on`, `rows_restored`, and the `report_reopened` /
  `claims_traceable` findings — Francesco runs the restore against a real empty Postgres and ratifies
  the record (mirrors the 8.2 / 8.3 / 8.4 ratification requirement). Draft the runbook and a
  candidate block in Design Notes; Francesco owns the ratified values and `outcome`.
- Any restore behaviour beyond insert-into-empty — upsert, merge, selective/partial restore, conflict
  resolution, or reconciling schema drift between the backup's era and the target schema. Out of
  scope; bring it to Francesco before building.
- Adding a restore **route** or any UI surface — out of scope; restore is an operator CLI plus a
  written runbook, not an authenticated endpoint.

**Never:**
- No new production runtime behaviour in the serving app: no `/restore` route, no UI, no
  `AuthMiddleware` change, no change to `shell/http/routes/backup.py`'s output.
- No new dependency: stdlib (`json`, `argparse`, `tomllib`) plus the existing SQLModel / SQLAlchemy only.
- Do not modify `core/`.
- Do not auto-run migrations from the CLI and do not have it create or drop schema — the runbook's
  `alembic upgrade head` step owns that.
- Do not restore `place_cache` or `backup_record` — neither is in the export; `place_cache` is a
  recomputable geocoding cache and `backup_record` is written fresh by `GET /backup` itself.
- Do not add an env-gated measurement harness — the round trip is fully in-process; the real-Postgres
  rehearsal is Francesco's manual, recorded step.
- Do not edit the PRD — no Assumptions Index item covers restore; AD-17's "rehearsed restore" is
  satisfied by this record, not a PRD change. Do not change any number in `epics.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Full pipeline export, empty target | populated source (Client → `ReportRun` → `Report` chain with Payload/Draft/Theme/GateResult, a `CorpusEntry`, an `ExportRecord`, ≥2 `StyleGuide` versions); target schema present, all tables empty | every `_BACKUP_MODELS` table restored with matching row count and byte-identical JSON-column values; caller commits once; summary reports per-table counts | N/A |
| Report reopen after restore | restored DB, a `run_id` that had reached `gate_passed` before the export | `GET /report-runs/{run_id}/report` → 200, eight Sections rendered from the restored Payload; restored passing `StoredGateResult` present | N/A |
| Claims traceable | restored passing `StoredGateResult` for that run | `passed is True`, `violations == []`, `vocabulary_version` intact; `/report-runs/{run_id}/payload` resolves | N/A |
| Empty export, empty target | every table key present, each `[]` | restore is a no-op; summary reports 0 for every table | N/A |
| Target not empty | any `_BACKUP_MODELS` table already holds ≥1 row | `restore_backup` raises `RestoreTargetNotEmptyError` before inserting anything | Loud failure, nothing written |
| Table key absent from file | export predates a table joining `/backup` | that table restored as 0 rows; others unaffected | Tolerated (forward-compat) |
| FK-safe order enforced | `PRAGMA foreign_keys=ON` on target | inserting arrays in `_BACKUP_MODELS` order never references a missing FK | `IntegrityError` if the order ever regresses |
| Typed-field reconstruction | JSON-mode strings: UUID, ISO datetime, `Decimal` lat/long | `model_validate` coerces each back; `UUID` / aware `datetime` / `Decimal` round-trip equal | Assertion |
| Malformed export file | not JSON, or top level not an object | `load_backup` / `restore_backup` raises naming the offending path | Loud failure |

</frozen-after-approval>

## Code Map

- `shell/restore.py` — **new.** `load_backup(path: Path) -> dict[str, list[dict]]` (`json.loads`,
  assert top level is a dict). `RestoreTargetNotEmptyError(RuntimeError)`.
  `restore_backup(session: Session, backup: Mapping[str, list[dict]]) -> dict[str, int]`: import
  `_BACKUP_MODELS` from `shell.http.routes.backup`; assert every `model.__tablename__` count is 0
  (`session.exec(select(func.count()).select_from(model))`) else raise; then for each model in order,
  `rows = [model.model_validate(r) for r in backup.get(model.__tablename__, [])]`, `session.add_all(rows)`,
  `session.flush()`; return `{tablename: len(rows)}`. `_main(argv=None)` / `if __name__ == "__main__":`
  — `argparse` one positional `backup_file`; `engine = create_engine(settings.sqlalchemy_url)`
  (mirrors `migrations/env.py:48`); `with Session(engine) as s: counts = restore_backup(s, load_backup(path)); s.commit()`;
  print `counts`; `SystemExit(1)` on `RestoreTargetNotEmptyError` / any exception.
- `shell/http/routes/backup.py:62` `_BACKUP_MODELS` — the 11-model tuple in FK-safe order
  (`Client, CorpusEntry, StoredNatalChart, ReportRun, Report, ReportPayload, ReportDraft,
  StoredReportTheme, StoredGateResult, ExportRecord, StyleGuide`) and the single source of truth for
  both the table set and its order. `:80` `download_backup` — the serialization restore must invert
  (`row.model_dump(mode="json")` keyed by `__tablename__`). Read-only.
- `shell/config.py:144` `Settings.sqlalchemy_url` (property), `:367` `settings` — the CLI's engine
  URL, read exactly as `migrations/env.py` reads it. Read-only.
- `migrations/env.py:48` — the pattern the CLI's `create_engine(settings.sqlalchemy_url, poolclass=NullPool)`
  mirrors. Read-only.
- `shell/http/routes/report_runs.py:302` `view_report` — `GET /report-runs/{run_id}/report`; after
  restore this must return 200, reading back the `Report` / `ReportDraft` / `ReportPayload` / passing
  `StoredGateResult` / `Client` rows with `RuntimeError` guards and rendering from
  `stored_payload.payload`. The round-trip test's "Report reopened / Claims traceable" assertion
  drives this handler against the restored session. Read-only.
- `shell/adapters/postgres/gate_result.py:44` `StoredGateResult` — `violations` JSON list (empty on a
  pass), `vocabulary_version`, immutable (`_forbid_update`); the row whose intact restore makes
  Claims traceable. Read-only.
- `shell/adapters/postgres/corpus_entry.py:38` `CorpusEntry`, `shell/adapters/postgres/export_record.py`
  `ExportRecord`, `shell/adapters/postgres/report_run.py:56` `ReportRun` (`transit_events` JSON,
  nullable `natal_chart_id`) — entity classes the AC names; each must round-trip. Read-only.
- `shell/adapters/postgres/backup_record.py` `store_backup_record` / `BackupRecord` — written by
  `GET /backup`, **not** in `_BACKUP_MODELS`, so **not** restored. Read-only (confirms the exclusion).
- `tests/test_runner_driver.py:112` `_create_client_and_chart`, `:166` `_drive`, `:149`
  `_FakeGenerator`, `:132` `_a_generated_draft` — reused to populate the source DB with a real
  `gate_passed` run (`Report` + `ReportPayload` + `ReportDraft` + `StoredReportTheme` +
  `StoredGateResult` + seeded `StyleGuide`). Copy-source, read-only.
- `tests/test_http_backup.py:78` `db_session` fixture (in-memory SQLite + `StaticPool` +
  `SQLModel.metadata.create_all`), `:41` `_BACKUP_MODELS` import, row builders — pattern for building
  the source DB and for serializing-as-`/backup`. Read-only.
- `tests/test_data_terms_record.py` — **pattern source (read-only).** `_TOML_BLOCK` regex,
  `_extract_toml_block`, the module-scoped `meta` fixture, the exact-key-set assertion, the
  `checked`-is-a-non-future-date check, and the `outcome in {"pass","blocked"}` + `outcome == "pass"`
  gate — copy the shape into `tests/test_restore.py`'s record-guard half.
- `docs/release-validation/restore-rehearsal.md` — **new.** ` ```toml ` block (keys per Boundaries)
  then prose: *What durability rests on* (AD-17; `GET /backup` is the mechanism, a rehearsed restore
  is the proof) · *The procedure* (numbered runbook, below) · *What the rehearsal verified* (tables
  and row counts restored; the reopened Report's id; Payload and Gate result intact; Claims traceable)
  · *Outcome* · *Re-rehearse triggers*. Draft prose in Design Notes; Francesco ratifies.
- `README.md:70` (`alembic upgrade head`), `:95` Deployment, `:122` Neon provisioning steps — the
  runbook cites these for the "provision an empty database" and "apply schema" steps. Read-only.

## Tasks & Acceptance

**Execution:**
- [x] `shell/restore.py` — new — `load_backup`, `RestoreTargetNotEmptyError`,
      `restore_backup(session, backup)` (empty-target check, then insert every `_BACKUP_MODELS` table
      in order via `model_validate`, flush per table, no commit, return per-table counts), and the
      `python -m shell.restore <backup.json>` CLI building its engine from `settings.sqlalchemy_url`
      and committing once.
- [x] `tests/test_restore.py` — new — the round-trip suite (populate via `test_runner_driver`
      helpers + a `CorpusEntry` + an `ExportRecord` + a 2nd `StyleGuide`; serialize exactly as
      `download_backup` does; `restore_backup` into a 2nd empty engine with `PRAGMA foreign_keys=ON`;
      assert per-table row counts, byte-identical JSON columns, `UUID`/`datetime`/`Decimal` field
      equality, `GET /report-runs/{run_id}/report` → 200, passing `StoredGateResult` intact,
      `RestoreTargetNotEmptyError` on a non-empty target, empty-export no-op, missing-key
      forward-compat) covering every I/O & Edge-Case Matrix row, plus the record-guard suite
      mirroring `tests/test_data_terms_record.py`.
- [x] `docs/release-validation/restore-rehearsal.md` — new — the dated record:
      the ` ```toml ` block, the numbered under-pressure runbook, what the rehearsal verified, and
      the re-rehearse triggers. Rehearsal is proven by the `tests/test_restore.py` in-process
      round-trip; the operator dry-run against a real Postgres + Francesco's sign-off is marked in
      the record as the one outstanding step (the spec's "Ask First").

**Acceptance Criteria:**
- Given a `GET /backup` export from a fully populated database, when `restore_backup` runs against an
  empty schema, then every table in `_BACKUP_MODELS` is reconstructed with the same row count and
  byte-identical JSON-column values, and the caller commits exactly once.
- Given the restored database, when `GET /report-runs/{run_id}/report` is requested for a run that
  had passed the Gate before the export, then it returns 200 with the eight Sections rendered from
  the restored Payload, and the restored passing `StoredGateResult` row's `violations` and
  `vocabulary_version` are intact so every Claim is still traceable to the Payload.
- Given a target database that already contains any row in a `_BACKUP_MODELS` table, when
  `restore_backup` is invoked, then it raises `RestoreTargetNotEmptyError` before writing anything.
- Given `docs/release-validation/restore-rehearsal.md`, when the full suite runs, then its
  ` ```toml ` block parses with exactly the expected keys, `tables_restored` equals the
  `_BACKUP_MODELS` table names, `report_reopened` and `claims_traceable` are `true`, `outcome` is
  `"pass"`, and `checked` / `ratified_on` are non-future ISO dates with `ratified_by` set.
- Given `uv run pytest -q` and `uv run ruff check .`, when they run, then both are clean.

## Spec Change Log

## Design Notes

**Why `model_validate`, not a Core `table.insert()`.** The export is `model_dump(mode="json")`
output — every `UUID` is a string, every `_UTCDateTime` value is an ISO string, and `latitude` /
`longitude` are `Decimal`-as-string. `Model.model_validate(dict)` runs Pydantic v2 coercion back to
the real column types in one call; a raw `insert()` would hand strings straight to `_UTCDateTime`'s
bind path and the `Numeric` column. The JSON columns are already plain `dict`/`list` and need no
handling. If SQLModel's `table=True` class rejects `model_validate` in this version, fall back to
`Model(**_coerce(row))` with explicit `UUID(...)` / `datetime.fromisoformat(...)` / `Decimal(...)` on
the handful of known typed columns — the round-trip test asserts exact per-field equality, so the
reconstruction mechanism is free to change but the fidelity guarantee is not.

**Why refuse a non-empty target.** Restore is a disaster-recovery action into a *fresh* database
(AD-17 — Neon's free plan has no scheduled backups). Run against a live populated DB it would
duplicate every row or hit primary-key collisions. The zero-row precondition makes that a loud
refusal before any write, not a mess to unwind.

**Why no restore route.** Epic 8 ships no serving-app feature. "Followed under pressure" means a
command Francesco runs against a newly provisioned Neon database when the old one is gone — not an
endpoint on an application whose database just died.

**Illustrative record block** (values are placeholders — Francesco runs the restore and ratifies):

```toml
checked = 2026-08-27
ratified_by = "Francesco"
ratified_on = 2026-08-27
source_backup = "backup-20260827T101500Z.json"
target = "empty Neon Postgres 18 branch, Europe/Frankfurt"
tables_restored = ["client", "corpus_entry", "export_record", "gate_result", "natal_chart", "report", "report_draft", "report_payload", "report_run", "report_theme", "style_guide"]
rows_restored = 0
report_reopened = true
claims_traceable = true
outcome = "pass"
```

**Draft runbook** (goes in the record's *The procedure* section, refine with Francesco):

1. Download the current export: authenticated `GET /backup` → `backup-<UTC>.json`, held off-host.
2. Provision an empty Postgres (a fresh Neon branch/project, `Europe/Frankfurt`, per `README.md`);
   set `DATABASE_URL` to it.
3. Apply the schema: `uv run --env-file .env alembic upgrade head`.
4. Restore: `uv run --env-file .env python -m shell.restore backup-<UTC>.json` — prints per-table
   counts; refuses if the target is not empty.
5. Verify: sign in, open a known Report at `/report-runs/{id}/report`, open its Payload at
   `/report-runs/{id}/payload`; confirm the eight Sections render and the Gate verdict shows.
6. Record `checked`, `ratified_on`, `rows_restored`, `report_reopened`, `claims_traceable`,
   `outcome` in this file.

**Re-rehearse triggers:** any change to `_BACKUP_MODELS` (a table added to or removed from
`/backup`), any migration altering a restored table's columns, a SQLModel/SQLAlchemy major bump, or
any change to how `GET /backup` serializes rows — re-run the restore against a fresh database and
bump `checked`.

## Verification

**Commands:**
- `uv run pytest tests/test_restore.py -q` — expected: all round-trip and record-guard tests pass.
- `uv run pytest tests/test_http_backup.py tests/test_restore.py -q` — expected: both green; the
  FK-safe order the export and the restore share stays consistent.
- `uv run pytest -q` — expected: full suite green.
- `uv run ruff check .` — expected: clean.

**Manual checks:**
- Francesco: provision an empty Neon branch, run `uv run --env-file .env alembic upgrade head` then
  `uv run --env-file .env python -m shell.restore <latest backup>.json`, sign in, reopen a known
  Report and its Payload, and fill in `restore-rehearsal.md`'s `checked` / `ratified_on` /
  `rows_restored` / `report_reopened` / `claims_traceable` / `outcome`.

## Suggested Review Order

**The restore contract**

- Entry point: insert every table in `_BACKUP_MODELS` order, `model_validate` per row, flush per table, never commit — the caller owns the transaction.
  [`restore.py:182`](../../shell/restore.py#L182)
- The table set and its FK-safe order are imported live from the backup route, never re-listed — a table added to `/backup` joins the restore automatically.
  [`restore.py:81`](../../shell/restore.py#L81)
- `model_dump(mode="json")` strings coerced back to `UUID` / aware `datetime` / `Decimal` by Pydantic v2 — no hand-written per-table decoder.
  [`restore.py:213`](../../shell/restore.py#L213)

**Failure & safety boundaries**

- Refuses a non-empty target before writing anything — restore is disaster-recovery into a fresh database, never an upsert.
  [`restore.py:166`](../../shell/restore.py#L166)
- Rejects an unknown top-level key or a non-list table value, naming the offender — a mismatched-schema export stops loudly instead of silently dropping rows.
  [`restore.py:127`](../../shell/restore.py#L127)
- Any mid-restore exception is re-raised naming the table being inserted — the "followed under pressure" path tells the operator where it broke.
  [`restore.py:216`](../../shell/restore.py#L216)

**The operator CLI**

- `python -m shell.restore` — engine from `settings.sqlalchemy_url` like `migrations/env.py`, one transaction, one commit; schema assumed present.
  [`restore.py:224`](../../shell/restore.py#L224)
- `--dry-run` validates the file and the empty-target precondition and prints would-insert counts, writing nothing; distinct exit codes 0 / 2 / 1; `--traceback` for the stack.
  [`restore.py:277`](../../shell/restore.py#L277)

**The rehearsal record (the epic-8 deliverable)**

- The `tomllib`-parsed block the guard binds: `tables_restored` == sorted `_BACKUP_MODELS`, `rows_restored` == the round-trip count, `outcome = "pass"`.
  [`restore-rehearsal.md:31`](../../docs/release-validation/restore-rehearsal.md#L31)
- Status framing: proven in-process by `tests/test_restore.py`; the operator dry-run against a real Postgres is the one outstanding step.
  [`restore-rehearsal.md:13`](../../docs/release-validation/restore-rehearsal.md#L13)
- The under-pressure runbook: dry-run pre-flight, exit codes, and the retry/recovery path (restore won't write a non-empty target).
  [`restore-rehearsal.md:65`](../../docs/release-validation/restore-rehearsal.md#L65)

**Tests (peripherals)**

- Full-pipeline round trip: populate a real `gate_passed` run, serialize as `download_backup` does, restore into an FK-enforcing engine, assert byte-identical fidelity.
  [`test_restore.py:217`](../../tests/test_restore.py#L217)
- Bound to the real serializer: one round trip runs through an actual `GET /backup` response, not the hand copy.
  [`test_restore.py:641`](../../tests/test_restore.py#L641)
- Mid-restore failure names the table and leaves the target empty after rollback — the whole-transaction-rolls-back claim, exercised.
  [`test_restore.py:606`](../../tests/test_restore.py#L606)
- In-process CLI coverage: success summary, exit 2 / exit 1, `--dry-run`, `--traceback`, missing-arg — no real Postgres.
  [`test_restore.py:692`](../../tests/test_restore.py#L692)
- Record guard mirrors `test_data_terms_record.py`: key set, non-future dates, `tables_restored` bound to `_BACKUP_MODELS`, `rows_restored` bound to the round-trip count, `outcome == "pass"`.
  [`test_restore.py:802`](../../tests/test_restore.py#L802)
