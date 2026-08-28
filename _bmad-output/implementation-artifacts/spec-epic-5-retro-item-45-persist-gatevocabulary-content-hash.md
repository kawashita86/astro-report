---
title: 'Persist GateVocabulary.content_hash on Report and StoredGateResult (epic-5-retro item 45)'
type: 'feature'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '8188edadbbd387a8a74aef37128d893a468c28c4'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `Report` and `StoredGateResult` record only the hand-bumped `vocabulary_version` int, not `GateVocabulary.content_hash`. `content_hash` exists specifically to catch a forgotten `version` bump on a vocabulary content edit; today neither persisted row can detect that failure mode after the fact — two Gate outcomes checked against materially different vocabularies are indistinguishable if the editor forgot to bump `version`.

**Approach:** Thread the already-computed `GateVocabulary.content_hash` (a sha256 hex digest) through `GateResult` and both persistence write-sites, and add one nullable `String(64)` column to each of the `report` and `gate_result` tables via a new forward migration. One added column per table, three write-sites updated, no behavior change to the Gate itself.

## Boundaries & Constraints

**Always:**
- New migration revision id keeps the `NNNN_slug` shape and is **≤ 32 characters** (`tests/test_migration_chain.py`'s `test_no_revision_id_exceeds_the_alembic_version_column_width` guard, added by epic-6-retro item 46). Use `0021_gate_vocabulary_hash` (25 chars).
- New columns are **nullable, no `server_default`** — a row written before this migration honestly has no recorded hash, mirroring `0016_export_record_disposition.py` / `0020_corpus_entry_pairing.py`'s `month` add-column. Every write after this migration always populates it.
- Column names mirror the sibling int: `report.gate_vocabulary_content_hash` and `gate_result.vocabulary_content_hash`. Model fields: `str | None = Field(default=None, max_length=64)`, mirroring `Client.computation_config_content_hash`'s `max_length=64`.
- `GateResult` gains `vocabulary_content_hash: str` (non-optional, no default), placed immediately after `vocabulary_version`; `run_gate()` populates it from `vocabulary.content_hash`, exactly as it already does for `vocabulary_version`.
- `store_report()` and `store_gate_result()` each gain one new **required** keyword-only parameter; every call site passes it in the same statement it already passes the version int.
- Both new `store_*` params are populated from `result.vocabulary_content_hash` on the pass path and from `vocabulary.content_hash` on the fail path (`shell/runner/driver.py`'s `except GateFailedError` block), matching how `vocabulary_version` is already sourced at each site.
- `downgrade()` in the new migration raises `RuntimeError` (forward-only), verbatim shape of `0020`'s.

**Ask First:**
- If investigation shows a real Postgres (Neon prod / local compose) is already past `0020` — nothing here needs a stamp, but confirm the deploy has run `0021` before relying on the column being present in prod.

**Never:**
- Do not backfill historical rows with a fabricated or empty-string hash — NULL is the correct "unknown" value.
- Do not make the new columns `NOT NULL`, and do not add a `server_default`.
- Do not touch `run_gate()`'s violation logic, the Gate's pass/fail decision, or `GateViolation`.
- Do not touch any HTML template or route — this is persistence + detectability only, not display. `report.html` / `report_draft.html` stay byte-for-byte unchanged.
- Do not widen/override `alembic_version` in `migrations/env.py` (epic-6-retro item 46's constraint).
- Do not add a uniqueness or cross-check constraint between the version int and the hash — this story only records both; reconciling them is a separate follow-up.
- Do not bump `GateVocabulary.version` or edit `core/gate/vocabulary.it.json`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Gate passes | `run_gate()` returns `passed=True` | `store_report` writes `gate_vocabulary_content_hash = vocabulary.content_hash`; passing `store_gate_result` row writes `vocabulary_content_hash` = same digest | N/A |
| Gate fails | `run_gate()` returns `passed=False`, `drive()` `except GateFailedError` | failing `gate_result` row writes `vocabulary_content_hash = vocabulary.content_hash` | existing try/except around the fail-path `store_gate_result` is unchanged |
| `GateResult` shape | `run_gate(draft, payload, vocabulary)` | `result.vocabulary_content_hash == vocabulary.content_hash` and `result.vocabulary_version == vocabulary.version` | N/A |
| Pre-migration row read back | `report` / `gate_result` row inserted before `0021` | new column reads as `NULL` / `None`; no crash in routes or backup serialization | N/A |
| Backup + restore round-trip | new column populated, `/backup` then restore into empty DB | digest string survives the round-trip on both tables; old backups lacking the key restore with `None` | restore's unknown-key handling already tolerant |
| Forgotten version bump detectable | two `gate_result` rows, equal `vocabulary_version`, different `vocabulary_content_hash` | a direct SQL query can now distinguish them | N/A |
| Over-long revision id | `0021` id > 32 chars | `test_no_revision_id_exceeds_the_alembic_version_column_width` fails | choose the 25-char id |

</frozen-after-approval>

## Code Map

- `core/types/gate.py:73` -- `GateResult` frozen dataclass. Add `vocabulary_content_hash: str` right after `vocabulary_version` (line 87); extend the docstring's "carries `GateVocabulary.version` through" sentence to name the hash too.
- `core/gate/run.py:499` -- the **only** `GateResult(...)` constructor. Add `vocabulary_content_hash=vocabulary.content_hash` next to the existing `vocabulary_version=vocabulary.version` (line 501).
- `shell/adapters/postgres/gate_result.py` -- `StoredGateResult` model (add `vocabulary_content_hash: str | None = Field(default=None, max_length=64)` after `vocabulary_version` at line 65); `store_gate_result()` (line 112) gains required kw-only `vocabulary_content_hash: str`, set on the `StoredGateResult(...)` build at line 135.
- `shell/adapters/postgres/report.py` -- `Report` model (add `gate_vocabulary_content_hash: str | None = Field(default=None, max_length=64)` after `gate_vocabulary_version` at line 54); `store_report()` (line 73) gains required kw-only `gate_vocabulary_content_hash: str`, set on the `Report(...)` build at line 91.
- `shell/runner/driver.py:613-627` -- pass path: `store_report(..., gate_vocabulary_content_hash=result.vocabulary_content_hash)` and `store_gate_result(..., vocabulary_content_hash=result.vocabulary_content_hash)`.
- `shell/runner/driver.py:827-835` -- fail path: `store_gate_result(..., vocabulary_content_hash=vocabulary.content_hash)` (here `result` is not in scope; `vocabulary` is, exactly as `vocabulary_version=vocabulary.version` already is).
- `migrations/versions/0021_gate_vocabulary_hash.py` -- NEW. `revision = "0021_gate_vocabulary_hash"`, `down_revision = "0020_corpus_entry_pairing"`. `upgrade()`: `op.add_column("report", sa.Column("gate_vocabulary_content_hash", sa.String(length=64), nullable=True))` and the same for `"gate_result"` / `"vocabulary_content_hash"`. `downgrade()` raises `RuntimeError` (copy `0020`'s wording). Model the docstring on `0020_corpus_entry_pairing.py`.
- `tests/test_gate_run.py:673` -- `test_gate_result_carries_the_vocabulary_version_through`: add a sibling assertion / test for `vocabulary_content_hash`.
- `tests/test_gate_result_store.py` -- ~20 `store_gate_result(...)` / `StoredGateResult(...)` calls (lines 115+): add the new kwarg; add one test asserting the digest persists and reads back.
- `tests/test_report_store.py` -- ~10 `store_report(...)` calls (lines 90+): add the new kwarg; add one test asserting the digest persists.
- `tests/test_runner_driver.py` -- driver pass/fail path tests: assert the persisted rows carry `vocabulary.content_hash`.
- `tests/test_http_backup.py:159,208-219` -- `_make_gate_result` / inline `Report`: nullable column flows through the generic serializer; add an assertion that the digest appears in the `gate_result` / `report` payload when set.
- `tests/test_http_report_runs.py:849,916,1102-1129,1313` / `tests/test_http_clients.py:712,906` / `tests/test_export_boundary.py:95` / `tests/test_export_record_store.py:91` -- other `store_report` / `StoredGateResult` construction sites; add the kwarg where the constructor is called directly (nullable field can be omitted, but pass it where siblings are passed for consistency).
- `tests/test_migration_chain.py` / `tests/test_forward_only_migrations.py` -- parametrized over revision files; auto-adopt `0021`. Run to confirm the id-length guard and single-head guard stay green.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/gate.py` -- add `vocabulary_content_hash: str` to `GateResult` after `vocabulary_version`; update the class docstring -- makes the digest a first-class part of the Gate verdict, mirroring the version int.
- [x] `core/gate/run.py` -- populate `vocabulary_content_hash=vocabulary.content_hash` in the sole `GateResult(...)` -- the digest is already on `vocabulary`, no new computation.
- [x] `shell/adapters/postgres/report.py` -- add nullable `gate_vocabulary_content_hash` column + required kw-only param on `store_report()` -- persists the digest alongside `gate_vocabulary_version`.
- [x] `shell/adapters/postgres/gate_result.py` -- add nullable `vocabulary_content_hash` column + required kw-only param on `store_gate_result()` -- persists the digest alongside `vocabulary_version` on every pass and fail row.
- [x] `shell/runner/driver.py` -- pass `result.vocabulary_content_hash` (pass path, 2 calls) and `vocabulary.content_hash` (fail path, 1 call) -- the three write-sites named in item 45.
- [x] `migrations/versions/0021_gate_vocabulary_hash.py` -- new forward migration adding both nullable `String(64)` columns; forward-only `downgrade()` -- reachable on real Postgres (revision id 25 chars).
- [x] `tests/*` -- update all direct `store_report` / `store_gate_result` / `StoredGateResult` / `Report` construction sites; add focused tests for the I/O & Edge-Case Matrix rows (GateResult shape, pass/fail persistence, pre-migration NULL read-back, backup round-trip).

**Acceptance Criteria:**
- Given a Gate run that passes, when `drive()` reaches `gate_passed`, then the `report` row and the passing `gate_result` row both carry `vocabulary.content_hash` in their new column.
- Given a Gate run that fails, when `drive()` handles `GateFailedError`, then the failing `gate_result` row carries `vocabulary.content_hash`.
- Given a `report` or `gate_result` row created before migration `0021`, when any route or the `/backup` serializer reads it, then the new column is `None`/`null` and nothing raises.
- Given `alembic upgrade head` against a fresh Postgres, when it runs the full chain, then it reaches `0021_gate_vocabulary_hash` without a `StringDataRightTruncation` and the two new columns exist.
- Given the full suite, when `uv run pytest` and `uv run ruff check .` run, then both pass with the single-head and revision-id-length migration guards green.

## Design Notes

Why nullable rather than `NOT NULL` + `server_default`: the sha256 digest of the vocabulary that checked a *historical* row is genuinely unknown and unrecoverable. A `server_default=""` or a fake digest would be a value that looks real in a later audit query. NULL says "written before we recorded this" — the same choice `0016`/`0020` made for `disposition` and `month`. All post-migration writes populate it unconditionally, so NULL cleanly partitions old rows from new.

Why the digest goes through `GateResult` on the pass path but straight off `vocabulary` on the fail path: this exactly mirrors the existing `vocabulary_version` wiring in `shell/runner/driver.py` — `result.vocabulary_version` at lines 618/625, `vocabulary.version` at line 833 (where `result` is out of scope). Both are the same value; `run_gate()` copies `vocabulary.content_hash` into `result` verbatim.

## Verification

**Commands:**
- `uv run pytest` -- expected: all green, including `tests/test_gate_run.py`, `tests/test_gate_result_store.py`, `tests/test_report_store.py`, `tests/test_runner_driver.py`, `tests/test_http_backup.py`, `tests/test_migration_chain.py`, `tests/test_forward_only_migrations.py`.
- `uv run ruff check .` -- expected: clean.
- `uv run alembic upgrade head --sql` -- expected: exits 0, emits `0021_gate_vocabulary_hash`, no `StringDataRightTruncation` reference.
- `MIGRATION_TEST_DATABASE_URL=<throwaway pg> uv run pytest tests/test_migration_chain.py` -- expected: the real-Postgres upgrade test reaches `0021` (skips cleanly if the env var is unset).

## Suggested Review Order

**The verdict shape (entry point)**

- Start here: the digest becomes a first-class field of the Gate verdict, next to the version int it complements.
  [`gate.py:89`](../../core/types/gate.py#L89)

- The sole `GateResult` constructor copies `vocabulary.content_hash` through verbatim -- no new computation.
  [`run.py:502`](../../core/gate/run.py#L502)

**Schema change**

- New forward migration: one nullable `String(64)` column on each table; forward-only `downgrade()`. Revision id is 25 chars (under the 32-char `alembic_version` ceiling).
  [`0021_gate_vocabulary_hash.py:41`](../../migrations/versions/0021_gate_vocabulary_hash.py#L41)

- `Report.gate_vocabulary_content_hash` -- nullable, no `server_default`; comment records why NULL is the honest pre-`0021` value.
  [`report.py:62`](../../shell/adapters/postgres/report.py#L62)

- `StoredGateResult.vocabulary_content_hash` -- same shape, written on every pass and fail row.
  [`gate_result.py:72`](../../shell/adapters/postgres/gate_result.py#L72)

**Persistence write path**

- `store_report()` gains a required kw-only `gate_vocabulary_content_hash: str`, set on the `Report(...)` build.
  [`report.py:88`](../../shell/adapters/postgres/report.py#L88)

- `store_gate_result()` gains a required kw-only `vocabulary_content_hash: str`, set on the `StoredGateResult(...)` build.
  [`gate_result.py:126`](../../shell/adapters/postgres/gate_result.py#L126)

- Driver pass path: both writes take `result.vocabulary_content_hash` -- mirroring the existing `vocabulary_version` wiring.
  [`driver.py:619`](../../shell/runner/driver.py#L619)

- Driver fail path: `store_gate_result` takes `vocabulary.content_hash` directly (here `result` is out of scope), exactly as `vocabulary_version=vocabulary.version` already does two lines up.
  [`driver.py:836`](../../shell/runner/driver.py#L836)

**Supporting tests**

- `run_gate()` threads the digest onto the result.
  [`test_gate_run.py:679`](../../tests/test_gate_run.py#L679)

- Pass + fail rows persist the digest; a pre-`0021` row reads back `None`; two equal-version rows with different hashes are distinguishable by SQL.
  [`test_gate_result_store.py:189`](../../tests/test_gate_result_store.py#L189)

- Migration `0021` emits both `ALTER TABLE ... ADD COLUMN ... VARCHAR(64)` statements -- the only check tying the hand-written add-column SQL to the model fields.
  [`test_migration_chain.py:189`](../../tests/test_migration_chain.py#L189)

- Backup payload carries the digest on both tables; backup -> restore round-trips it.
  [`test_http_backup.py:370`](../../tests/test_http_backup.py#L370)
