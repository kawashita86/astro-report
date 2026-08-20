---
title: 'Story 4.2 — Edit the Style Guide without a deploy'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '1223c3c1a20e87daddd8b467d01a8510de5ebeaf'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Style Guide exists only as `data/style-guide.seed.md`, a repository file — revising Francesco's register today means a code change and a redeploy, and no Report records which version actually produced it.

**Approach:** Persist the Style Guide as append-only versioned rows, seed version 1 from the seed file the first time migrations run, and add an authenticated editor that reads the current version and writes a new one on save — never overwriting, never deleting.

## Boundaries & Constraints

**Always:**
- New `style_guide` table (`id` uuid7 PK, `version` int unique monotonic from 1, `content` text, `created_at` timestamptz) via a forward-only Alembic migration.
- Seeding happens inside that migration: parse `data/style-guide.seed.md`'s `version: 1` marker + body, insert one row, run exactly once via Alembic's own revision tracking — never re-seeds.
- `style_guide` rows are append-only: a save inserts `version = max + 1`; nothing updates or deletes a row (mirror `ReportPayload`'s `before_update` listener).
- `current_style_guide(session)` is the one reader: highest-version row, or `StyleGuideMissingError` naming why when empty.
- Editor at `/style-guide` (history + current) and `/style-guide/edit` (form), authenticated by default (nothing added to `ALLOWLIST`). Every prior version stays readable via `/style-guide/{version}`.

**Ask First:**
- Whether `StyleGuideMissingError` needs wiring into a route today — Story 4.5's Generator, the actual "attempt generation" caller, doesn't exist yet, so this story only needs the reader to exist and behave correctly.

**Never:**
- No change to `core/` — persistence + UI only.
- No downgrade/rollback migration.
- No confirm-then-act gate on save — nothing is destroyed, so no double-submit protection beyond normal form handling.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First deploy | migrations run against a fresh DB | `style_guide` has exactly one row: version 1, content = seed file body | N/A |
| Re-deploy | migrations run again (0007 already applied) | no second row inserted, version 1 unchanged | N/A |
| Save a revision | POST `/style-guide/edit` with new content | new row `version = max + 1` inserted; prior rows untouched | N/A |
| Reader called against an empty table | `current_style_guide()` with no rows | raises `StyleGuideMissingError` naming the table is empty | caught and rendered, never a bare 500 |
| View a historical version | GET `/style-guide/{version}` | that version's content, read-only, no edit affordance | 404 if the version doesn't exist |
| Unauthenticated request | GET/POST `/style-guide*` without a valid session | rejected exactly like every other route | 401, empty body |

</frozen-after-approval>

## Code Map

- `data/style-guide.seed.md` -- version-1 content + `version: 1` marker; read once by the migration.
- `migrations/versions/0006_report_payload.py` -- mirror: forward-only, `downgrade()` raises.
- `shell/adapters/postgres/report_payload.py:28-80` -- table + `before_update` immutability listener to mirror.
- `shell/adapters/postgres/report_run.py:28-49` -- `_UTCDateTime` `TypeDecorator` to reuse.
- `shell/computation.py:318` -- version-marker parsing shape to mirror.
- `shell/http/app.py:83-117` -- router registration, alongside `clients`/`chart`/`report_runs`.
- `shell/http/auth.py:44` (`ALLOWLIST`) -- confirms no entry needed; authenticated by default.
- `shell/http/routes/clients.py:342-420` -- form-prefill/POST shape to mirror (minus the confirm gate).
- `shell/http/templates/client_edit.html` -- template shape to mirror.
- `tests/test_migration_chain.py`, `tests/test_forward_only_migrations.py` -- generic; exercise the new migration unchanged.
- `tests/test_http_clients.py` -- route-test shape to mirror.

## Tasks & Acceptance

**Execution:**
- [x] `shell/style_guide_seed.py` -- `load_style_guide_seed(path=DEFAULT_STYLE_GUIDE_SEED_PATH)`: parse the `version: N` marker + body from `data/style-guide.seed.md`, raise if marker missing/not `1` -- feeds the migration.
- [x] `migrations/versions/0007_style_guide.py` -- create `style_guide` table; in the same `upgrade()`, insert version 1 via `load_style_guide_seed()` -- forward-only, `downgrade()` raises.
- [x] `shell/adapters/postgres/style_guide.py` -- `StyleGuide` model, `StyleGuideMissingError`, `current_style_guide(session)`, `create_style_guide_version(session, content)` (`version = max + 1`), `before_update` listener forbidding mutation.
- [x] `shell/http/routes/style_guide.py` + `shell/http/app.py` -- GET `/style-guide` (current + history), GET `/style-guide/{version}` (read-only), GET/POST `/style-guide/edit` (form -> new version -> redirect); register the router.
- [x] `shell/http/templates/style_guide_list.html`, `style_guide_view.html`, `style_guide_edit.html` -- mirroring `client_edit.html`'s form shape.
- [x] `tests/test_style_guide_seed.py`, `tests/test_style_guide_store.py`, `tests/test_http_style_guide.py` -- seed-parsing edge cases; store append-only/immutability/`StyleGuideMissingError`; route round-trip, historical view, 404, unauthenticated 401.

**Acceptance Criteria:**
- Given the seed already applied, when a Style Guide revision is saved, then no code change or redeploy is required and the database, not `data/style-guide.seed.md`, is what `current_style_guide()` reads thereafter.

## Spec Change Log

## Design Notes

Seed inside the migration, not an app-startup lazy-seed: `docker-entrypoint.sh` already treats `alembic upgrade head` as the one "runs once, before traffic" mechanism every schema change here uses (0001-0006), and Alembic's revision-tracking is the "seeds once, never again" idempotency the AC needs.

## Verification

**Commands:**
- `uv run pytest tests/test_style_guide_seed.py tests/test_style_guide_store.py tests/test_http_style_guide.py -q` -- expected: all pass.
- `uv run pytest tests/test_migration_chain.py tests/test_forward_only_migrations.py tests/test_migrations_precede_traffic.py -q` -- expected: all pass, `0007_style_guide` resolves in the chain.
- `uv run ruff check .` -- expected: no new violations.

**Re-verified (2026-08-20):** all three commands above pass (64 tests across the new files plus the migration suite; full `uv run pytest -q` also green; `ruff check .` clean). Matrix Test Audit found one gap: the "First deploy" row (`style_guide` seeded to version 1 from `data/style-guide.seed.md`) had no automated coverage -- the adapter/HTTP tests build schema via `SQLModel.metadata.create_all()`, bypassing the migration's own `INSERT`, and none of the generic migration tests asserted on it either. Fixed by extending `tests/test_migration_chain.py::test_an_offline_upgrade_runs_env_py_and_emits_the_chain` (the file's existing pattern for pinning a migration's DDL/DML) with assertions on `CREATE TABLE style_guide`, the unique version index, the seed `INSERT`, and the seeded body text -- re-run and passing.

**Blind Hunter review (2026-08-20):** 11 findings, all classified `patch` or `reject` (no `intent_gap`/`bad_spec` -- the frozen intent held). 3 patches applied to `shell/http/routes/style_guide.py` (+ tests): a concurrent-save race now returns 409 with the submitter's content preserved instead of a bare 500 (`IntegrityError` around `session.commit()`, mirroring `place_cache.py`'s pattern but never silently discarding the edit); the current version no longer appears twice on `/style-guide` (`_history()` now excludes it); `StyleGuideMissingError` now renders `503`, not `200`, so monitoring can tell the pre-seed state apart from a healthy page. 8 findings rejected as noise or already-decided: no preview/confirm gate before save (re-litigates this spec's frozen "Never: no confirm-then-act gate" -- nothing is destroyed, every version stays readable); no author/editor identity on rows (the app has exactly one configured principal, so "who edited" is not a meaningful question); no pagination/diff view on history (feature requests beyond "every prior version stays readable", implausible at this app's single-author scale); seed-marker regex scanning the whole file (the seed file is a one-time, human-reviewed input never re-read after migration 0007 first runs); textarea content not `.strip()`ed like the seed body (verbatim storage of what was submitted is defensible, not a defect); no no-op-save guard (UX nicety, not a correctness issue); duplicate unique-index declaration between the SQLModel class and the migration (the same convention already used by every other table in this codebase -- `Client`, `ReportRun`, `ReportPayload` -- not a risk specific to this story). Re-ran all three Verification commands after the patches: still green (67 tests total; `ruff check .` clean).

## Suggested Review Order

**Persistence: append-only, immutable versions**

- Entry point -- one version per row, `version` unique from 1, `content`/`created_at` mirror `ReportPayload`'s shape.
  [`style_guide.py:34`](../../shell/adapters/postgres/style_guide.py#L34)

- No code path may rewrite a persisted row -- a citation into a future Report must mean the same thing years later.
  [`style_guide.py:68`](../../shell/adapters/postgres/style_guide.py#L68)

- The one reader: highest version, or a named error -- never `None`, never a bare exception.
  [`style_guide.py:82`](../../shell/adapters/postgres/style_guide.py#L82)

- Every save is an insert at `max + 1` -- flush only, caller decides the transaction boundary.
  [`style_guide.py:97`](../../shell/adapters/postgres/style_guide.py#L97)

**Seeding: version 1 lands exactly once**

- Parses the seed file's `version: 1` marker and discards everything before it -- title/note aren't content.
  [`style_guide_seed.py:43`](../../shell/style_guide_seed.py#L43)

- The migration inserts the seed as part of `upgrade()` -- Alembic's own revision tracking makes this run-once.
  [`0007_style_guide.py:38`](../../migrations/versions/0007_style_guide.py#L38)

- `bulk_insert` writes version 1 in the same transaction as the table's creation.
  [`0007_style_guide.py:58`](../../migrations/versions/0007_style_guide.py#L58)

**Editor: save, race, and error-state handling**

- A concurrent double-save is caught and returns 409 with the submitter's content preserved -- never silently discarded.
  [`style_guide.py:182`](../../shell/http/routes/style_guide.py#L182)

- History excludes the current version so "Current" and "History" stay disjoint on the page.
  [`style_guide.py:87`](../../shell/http/routes/style_guide.py#L87)

- An empty table (pre-seed) renders 503, not 200 -- distinguishable from a healthy page by monitoring.
  [`style_guide.py:116`](../../shell/http/routes/style_guide.py#L116)

- The historical view is read-only by construction -- no edit affordance, 404 on an unknown version.
  [`style_guide.py:201`](../../shell/http/routes/style_guide.py#L201)

**Wiring and templates**

- The router joins the app the same way `clients`/`chart`/`report_runs` do -- authenticated by default, no allowlist entry.
  [`app.py:118`](../../shell/http/app.py#L118)

- Plain-form editor, mirroring `client_edit.html`'s shape.
  [`style_guide_edit.html:1`](../../shell/http/templates/style_guide_edit.html#L1)

- Current + history list.
  [`style_guide_list.html:1`](../../shell/http/templates/style_guide_list.html#L1)

- One historical version, read-only.
  [`style_guide_view.html:1`](../../shell/http/templates/style_guide_view.html#L1)

**Tests**

- Concurrent-save race asserted end to end: 409, preserved content, no data loss.
  [`test_http_style_guide.py:210`](../../tests/test_http_style_guide.py#L210)

- Current-version-not-duplicated and empty-table-503 regressions from the review round.
  [`test_http_style_guide.py:113`](../../tests/test_http_style_guide.py#L113)

- Seed-marker edge cases: missing file, bad UTF-8, missing/malformed/wrong-version marker, empty body.
  [`test_style_guide_seed.py:1`](../../tests/test_style_guide_seed.py#L1)

- Append-only/immutability/uniqueness at the adapter layer, SQLite standing in for Postgres.
  [`test_style_guide_store.py:1`](../../tests/test_style_guide_store.py#L1)

- Pins the migration's actual emitted SQL (table, index, seed `INSERT`) -- closes the one Matrix Test Audit gap.
  [`test_migration_chain.py:150`](../../tests/test_migration_chain.py#L150)
