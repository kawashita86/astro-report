---
title: 'Make the Alembic chain reach a real Postgres (the alembic_version ceiling)'
type: 'bugfix'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '896f4955518666610d1ba1fc15cc4df09c6f5577'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Revision id `0014_bound_client_and_chart_string_columns` is 42 characters, but Alembic's `alembic_version.version_num` column is `VARCHAR(32)`. `alembic upgrade head` against a real Postgres fails with `StringDataRightTruncation` when it tries to stamp `0014`, so every migration from `0014` through the current head `0020_corpus_entry_pairing` (Epics 6–8) has never run against Postgres. SQLite ignores `VARCHAR(n)` length, so the test suite and adapter tests never catch it; `tests/test_migration_chain.py` only runs offline `--sql` emission, which executes nothing. This blocks the Story 8.5 restore rehearsal and leaves the deployed Neon DB's migration state unverified.

**Approach:** Shorten `0014`'s revision id (and file, via `git mv`) to `0014_bound_string_columns` (25 chars) and re-point `0015`'s `down_revision`. Add a real-Postgres `alembic upgrade head` test that runs online against a throwaway database given by an env var (skipped when unset) and is wired to run for real in CI via a Postgres service container. Add a cheap in-suite guard that fails if any revision id exceeds 32 characters.

## Boundaries & Constraints

**Always:**
- `git mv` the revision file so `git log --follow` keeps its history.
- The new revision id keeps the `NNNN_slug` shape (`alembic.ini` `file_template`) and is ≤ 32 characters.
- The chain stays linear with a single head (`0020_corpus_entry_pairing`) and single base (`0001_baseline`) — the existing `tests/test_migration_chain.py` guards must stay green.
- The real-Postgres test drives the same path `docker-entrypoint.sh` uses: online `alembic upgrade head` through `migrations/env.py` `run_migrations_online`, not `--sql` offline.
- Match the existing style in `tests/test_migration_chain.py` — module-scoped `ScriptDirectory` fixture, the subprocess env dict shape from `run_offline_upgrade`.

**Ask First:**
- If investigation shows a real database (Neon prod, or the local `compose.yaml` Postgres) is already past `0013_gate_result` with the old 42-char `0014` id somehow applied — renaming would orphan it. HALT and decide stamp-vs-override instead.
- If the team wants the real-Postgres test to become a required check blocking `render.yaml`'s auto-deploy — that is a separate branch-protection decision; do not wire it here.

**Never:**
- Do not widen or override `alembic_version` in `migrations/env.py`, and do not subclass Alembic's `DefaultImpl.version_table_impl`.
- Do not add `testcontainers` or any new dependency.
- Do not rename any revision other than `0014` (all others are already ≤ 32 chars).
- Do not touch any `upgrade()` body or the schema it produces — this change is revision-id and pointer text only.
- Do not make the real-Postgres test a hard failure when no Postgres URL is configured — it skips.
- Do not point the test at, or auto-detect, a non-throwaway/production database — rely on the documented env var.
- Out of scope: the concurrent-upgrade advisory lock, the migration connect-timeout, `/healthz` readiness (separate `deferred-work.md` items), and the actual inspection of the live Neon DB (needs credentials — Francesco's manual follow-up).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh Postgres, full upgrade | Postgres with schema `public` empty, `MIGRATION_TEST_DATABASE_URL` set | `alembic upgrade head` exits 0; `alembic_version.version_num` = `0020_corpus_entry_pairing`; tables `export_record`, `backup_record`, `corpus_entry` exist | N/A |
| Idempotent re-run | Same DB, already at head | Second `alembic upgrade head` exits 0; head unchanged | N/A |
| No Postgres configured | `MIGRATION_TEST_DATABASE_URL` unset | `test_migration_chain_on_postgres` is skipped; rest of suite unaffected | `pytest.skip` with a message naming the env var |
| Over-long revision id added later | A revision whose id is 33+ chars | `test_no_revision_id_exceeds_the_alembic_version_column_width` fails, message explains the `VARCHAR(32)` `alembic_version` ceiling | N/A |
| Existing offline chain test after rename | `alembic upgrade head --sql` | Still exits 0, emits the chain; no reference to `0014_bound_client_and_chart_string_columns` anywhere | N/A |
| Forward-only guard after rename | `downgrade()` of renamed `0014` | Existing parametrized `tests/test_forward_only_migrations.py` picks up the new stem id and still asserts it raises | N/A |

</frozen-after-approval>

## Code Map

- `migrations/versions/0014_bound_client_and_chart_string_columns.py` -- the 42-char id: `revision: str = "..."` at line 34, plus the `Revision ID:` docstring line 21. `upgrade()` (lines 40–52) must not change. Rename file + id to `0014_bound_string_columns`.
- `migrations/versions/0015_export_record.py` -- `Revises:` docstring line 15 and `down_revision: str | None = "0014_bound_client_and_chart_string_columns"` line 29 both point at the old id.
- `tests/test_client_store.py:138` -- docstring references the old migration *filename*; update the path string.
- `tests/test_migration_chain.py` -- already has the module-scoped `script_directory` fixture and `run_offline_upgrade` helper. Home for the new id-length guard; its existing `test_an_offline_upgrade_...` asserts only `0001_baseline` / table names, so the rename does not break it.
- `tests/test_forward_only_migrations.py` -- parametrized over `revision_files()` by stem; auto-adopts the rename, no edit needed. Verify only.
- `tests/test_migrations_precede_traffic.py` -- entrypoint-ordering guard; verify still green.
- `migrations/env.py` -- `run_migrations_online()` builds the engine from `settings.sqlalchemy_url`. The new test exercises this path unchanged.
- `.github/workflows/ci.yml` -- `test` job; comment block currently states "No Postgres service container". Add a `services.postgres` container + `MIGRATION_TEST_DATABASE_URL` on the Test step.
- `compose.yaml` -- `postgres:18-alpine` service (`astro:astro@…:5432/astro_report`); the local URL for running the new test by hand. Pin the CI image to the same tag.
- `shell/config.py:144` `sqlalchemy_url` -- only accepts `postgresql` / `postgresql+psycopg` schemes; the test URL must be a real Postgres DSN.
- Alembic 1.19.1 `alembic/ddl/impl.py` `version_table_impl` -- hardcodes `Column("version_num", String(32))`; `context.configure()` exposes no width override. This is why the fix is a rename, not an `env.py` change.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0014_bound_client_and_chart_string_columns.py` -- `git mv` to `migrations/versions/0014_bound_string_columns.py`; set `revision` to `"0014_bound_string_columns"`; update the `Revision ID:` docstring line. Leave `upgrade()` and the docstring's prose untouched.
- [x] `migrations/versions/0015_export_record.py` -- set `down_revision` and the `Revises:` docstring line to `0014_bound_string_columns`.
- [x] `tests/test_client_store.py` -- update the docstring path at line 138 to the new filename.
- [x] `tests/test_migration_chain.py` -- add `test_no_revision_id_exceeds_the_alembic_version_column_width`: for every `revision` from `script_directory.walk_revisions()`, assert `len(revision.revision) <= 32`; failure message explains that `alembic_version.version_num` is `VARCHAR(32)` and a longer id throws `StringDataRightTruncation` when Postgres stamps it.
- [x] `tests/test_migration_chain_on_postgres.py` -- new module. Read `MIGRATION_TEST_DATABASE_URL`; `pytest.skip` (naming the var) when unset. When set: reset the target with `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` via `psycopg` (docstring: destructive — throwaway DB only), then run `alembic upgrade head` online in a subprocess (`cwd` = repo root, env mirroring `run_offline_upgrade` but `DATABASE_URL` = the test URL, no `--sql`); assert returncode 0. Reconnect and assert `SELECT version_num FROM alembic_version` == `0020_corpus_entry_pairing` and that `export_record`, `backup_record`, `corpus_entry` are in `information_schema.tables`. Run `alembic upgrade head` a second time and assert returncode 0 with head unchanged.
- [x] `.github/workflows/ci.yml` -- add a health-checked `postgres:18-alpine` service to the `test` job; set `MIGRATION_TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/migrationtest` on the Test step; replace the "No Postgres service container" comment with why there is one now.

**Acceptance Criteria:**
- Given a Postgres whose `public` schema is empty, when `alembic upgrade head` runs, then it exits 0 and `alembic_version.version_num` is `0020_corpus_entry_pairing` — no truncation error at `0014`.
- Given the suite on CI, when it runs, then `test_migration_chain_on_postgres` executes against the service container (not skipped) and passes.
- Given `MIGRATION_TEST_DATABASE_URL` is unset, when `uv run pytest` runs locally, then that one test skips and every other test behaves exactly as before.
- Given a hypothetical revision id of 33+ characters, when the suite runs, then `test_no_revision_id_exceeds_the_alembic_version_column_width` fails with the ceiling explanation.
- Given the rename, when `uv run pytest tests/test_migration_chain.py tests/test_forward_only_migrations.py tests/test_migrations_precede_traffic.py` runs, then all pass and `grep -rn 0014_bound_client_and_chart_string_columns --include='*.py' .` returns nothing.

## Design Notes

Rename, not an `env.py` override: Alembic 1.19's `context.configure()` has no `version_num` width knob; widening needs subclassing `version_table_impl` or pre-`ALTER`ing `alembic_version` in `env.py` — magic in the one place this project keeps stock. Nothing is orphaned: the bug guarantees no real Postgres is past `0013_gate_result`, and adapter tests build schema via `SQLModel.metadata.create_all()`, not Alembic.

Env-var-gated test + CI service, not `testcontainers`: zero new dependencies, `uv run pytest` stays hermetic and Docker-free by default, and the test still runs for real on every CI run.

Deployed-DB check is Francesco's manual follow-up. After merge the next auto-deploy rolls the fixed chain forward from wherever the Neon DB sits; no manual `alembic stamp` is needed because the new `0014` id was never applied anywhere. Confirm post-deploy with `SELECT version_num FROM alembic_version;`.

- 2026-08-28: the Render deploy ran `alembic upgrade head` against Neon and it completed cleanly — no `StringDataRightTruncation` at `0014`, migrations applied past `0014` with no truncation. This is the first real evidence that b6649cc's `alembic_version VARCHAR(32)` fix carries the chain into production Postgres. The deploy then crashed *after* migrations, on WeasyPrint's native libraries at app import (`OSError: cannot load library 'libgobject-2.0-0'`), fixed in the sibling spec `spec-epic-6-retro-item-46-render-weasyprint-native-deps.md`. The only residue of this item is a one-line `SELECT version_num FROM alembic_version;` spot-check on Neon once that deploy goes green.

## Verification

**Commands:**
- `uv run pytest tests/test_migration_chain.py tests/test_forward_only_migrations.py tests/test_migrations_precede_traffic.py` -- expected: all pass; the real-Postgres test skips (no URL) or passes (URL set).
- `docker compose up -d postgres && MIGRATION_TEST_DATABASE_URL=postgresql://astro:astro@127.0.0.1:5432/astro_report uv run pytest tests/test_migration_chain_on_postgres.py` -- expected: passes, reaches head `0020_corpus_entry_pairing`. Destructive to the local dev DB schema; restore it with `docker compose down -v postgres` or a fresh `alembic upgrade head`.
- `git log --follow --oneline migrations/versions/0014_bound_string_columns.py` -- expected: history from before the rename is present.
- `grep -rn "0014_bound_client_and_chart_string_columns" --include='*.py' .` -- expected: no matches.
- `uv run ruff check .` -- expected: clean.

**Manual checks (if no CLI):**
- `.github/workflows/ci.yml`: the `test` job declares a `postgres:18-alpine` service with a health check, the Test step sees `MIGRATION_TEST_DATABASE_URL`, and the stale "No Postgres service container" comment is gone.

## Suggested Review Order

**The fix — revision id under the 32-char ceiling**

- The 42-char id became 25 chars; this is the value Postgres writes to `alembic_version.version_num VARCHAR(32)`.
  [`0014_bound_string_columns.py:34`](../../migrations/versions/0014_bound_string_columns.py#L34)

- The only child edge that pointed at the old id; re-pointed so the chain still resolves.
  [`0015_export_record.py:29`](../../migrations/versions/0015_export_record.py#L29)

**Proof it now applies on real Postgres**

- Resets `public`, runs the real online `alembic upgrade head`, asserts head reached and blocked tables exist.
  [`test_migration_chain_on_postgres.py:99`](../../tests/test_migration_chain_on_postgres.py#L99)

- Drives the same entrypoint path as `docker-entrypoint.sh` (online env.py), not `--sql` offline.
  [`test_migration_chain_on_postgres.py:71`](../../tests/test_migration_chain_on_postgres.py#L71)

**Regression guard — runs without Postgres**

- Fails if any future revision id exceeds 32 chars, with the ceiling explained in the message.
  [`test_migration_chain.py:101`](../../tests/test_migration_chain.py#L101)

**Config / peripherals**

- Postgres service container for the `test` job; throwaway DB the new test resets each run.
  [`ci.yml:40`](../../.github/workflows/ci.yml#L40)

- `MIGRATION_TEST_DATABASE_URL` is set only here, so the test runs for real in CI and skips everywhere else.
  [`ci.yml:72`](../../.github/workflows/ci.yml#L72)

- Docstring reference to the renamed migration file.
  [`test_client_store.py:138`](../../tests/test_client_store.py#L138)
