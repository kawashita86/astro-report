---
title: 'Story 7.1 — Add a past report to the Corpus'
type: 'feature'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'b289d33ac72560006f8e82d22093a830a33143eb'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Francesco's hundreds of past hand-written reports are scattered across email, messaging and folders. The application has no place to put them, so the raw material for phase-2 voice conditioning cannot be gathered or, later, counted.

**Approach:** Add a `corpus_entry` table via a forward-only Alembic migration, an authenticated paste-in route that stores one report as plain text regardless of its origin, and a plain most-recent-first list of what has been added. The table carries a nullable `client_id` from creation so it joins the FR-29 Client-deletion cascade now; the UI to set that link, and the paired/unpaired marking, are Story 7.2.

## Boundaries & Constraints

**Always:**
- New `corpus_entry` table via forward-only migration `0019_corpus_entry` (`down_revision = "0018_backup_record"`), mirroring `0018_backup_record.py`'s module shape and its raising `downgrade()`: `id` uuid7 PK, `content` Text `NOT NULL`, `client_id` `postgresql.UUID` `NULL` with a foreign key to `client.id` plus `ix_corpus_entry_client_id`, `created_at` `DateTime(timezone=True)` `NOT NULL`.
- `CorpusEntry` SQLModel in a new `shell/adapters/postgres/corpus_entry.py`, mirroring `BackupRecord`/`StyleGuide`: `content` via `sa_column=Column(Text, nullable=False)`; `created_at` via `sa_column=Column(_UTCDateTime, nullable=False)` (import from `shell.adapters.postgres.report_run`) defaulting to `datetime.now(UTC)`; `client_id: UUID | None` as a nullable, indexed FK to `client.id`.
- `corpus_entry` joins the FR-29 cascade: add `"corpus_entry"` to `_CLIENT_CASCADE_TABLES` and a `CorpusEntry` deletion loop (`WHERE client_id == client.id`) to `delete_client_and_derived`, in the first batch before the `client` row, and extend that function's docstring. An entry with `client_id IS NULL` is never touched by a Client deletion.
- `CorpusEntry` joins `_BACKUP_MODELS` in `shell/http/routes/backup.py`, placed immediately after `Client` (its only FK target) so `test_backup_model_order_is_fk_safe` and `test_backup_models_cover_exactly_the_client_cascade_tables_plus_client_and_style_guide` both hold; update `_TABLE_ORDER` and the "ten keys" test in `tests/test_http_backup.py` and the "ten tables" wording in `backup.py`'s docstring to match.
- Adapter writers only `add()` + `flush()`, never commit or roll back (mirror `create_style_guide_version`); the route owns the transaction boundary.
- `GET /corpus` lists stored entries most-recent-first (`created_at` desc); `GET /corpus/new` renders the paste-in form; `POST /corpus` stores one entry then redirects `303` to `/corpus`. Authenticated by default — nothing added to `shell.http.auth.ALLOWLIST` — mirroring `style_guide.py`. Register `corpus_router` in `create_app()`.
- `POST /corpus` hand-parses the urlencoded body exactly like `style_guide.py::_parse_form` (no `python-multipart`) with a 1 MiB whole-body cap; oversized or non-UTF-8 body → `422`; empty or whitespace-only `content` → `422` re-rendering the form with a `role="alert"` message.

**Ask First:**
- Adding any `corpus_entry` column beyond the four named above (a source label, a title, a checksum). Story 7.1 stores prose only, source-agnostic.

**Never:**
- No `paired`/`unpaired` marking, no `month` column, no UI or route input that sets `client_id` — Story 7.2.
- No composition counts or stats view — Story 7.3.
- No per-source parsing, no file upload, no format handling, no edit or delete of an entry.
- No `core/` changes; nothing durable written to the container filesystem.
- No entry content and no client identifiers in logs or telemetry — structured identifiers only.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Add an entry | `POST /corpus`, non-empty `content`, valid session | one `corpus_entry` row inserted with `client_id` NULL, committed; `303` redirect to `/corpus` | N/A |
| List with rows | `GET /corpus`, entries exist | `200`, entries rendered most-recent-first by `created_at` | N/A |
| Empty corpus | `GET /corpus`, no rows | `200`, empty-state text and a link to `/corpus/new` | N/A |
| Blank content | `POST /corpus`, missing or whitespace-only `content` | form re-rendered, nothing inserted | `422`, `role="alert"` message |
| Oversized body | `POST /corpus`, `Content-Length` absent or > 1 MiB | body not read, nothing inserted | `422` |
| Non-UTF-8 body | `POST /corpus`, body not UTF-8 decodable | nothing inserted | `422` |
| Unauthenticated | any `/corpus*` request without a valid session | rejected before the handler runs | `401`, empty body |
| Paired entry, Client deleted | `corpus_entry` with `client_id = C`; `delete_client_and_derived(C)` | that entry is deleted together with the Client | N/A |
| Unpaired entry, Client deleted | `corpus_entry` with `client_id = NULL`; any Client deleted | entry survives untouched | N/A |

</frozen-after-approval>

## Code Map

- `migrations/versions/0018_backup_record.py` -- template for the new `0019_corpus_entry.py`: module header, `revision`/`down_revision`, `op.create_table`, raising `downgrade()`.
- `migrations/versions/0017_report_run_natal_chart.py` -- pattern for `op.create_foreign_key` + `op.create_index` on a nullable UUID FK column.
- `shell/adapters/postgres/backup_record.py` -- closest model template: uuid7 PK, `Column(_UTCDateTime, nullable=False)` `created_at`, thin `add()`+`flush()` writer, `latest_*` reader shape.
- `shell/adapters/postgres/style_guide.py:51` -- `content: str = Field(sa_column=Column(Text, nullable=False))` exact pattern; `create_style_guide_version` transaction-boundary contract to mirror.
- `shell/adapters/postgres/report_run.py` -- source of `_UTCDateTime`.
- `shell/adapters/postgres/client.py:49` -- `_CLIENT_CASCADE_TABLES` frozenset (add `"corpus_entry"`).
- `shell/adapters/postgres/client.py:292` -- `delete_client_and_derived`: add the `CorpusEntry` deletion loop in the first batch (lines ~335-371) and extend the docstring.
- `shell/http/routes/style_guide.py` -- full template for `corpus.py`: `APIRouter()`, `_TEMPLATES_DIR`/`Jinja2Templates`, `_MAX_*_FORM_BODY_BYTES`, `_FormTooLarge`/`_FormNotUtf8`, `_parse_form`, GET-form + POST-insert + redirect, literal path registered before any parameterized one.
- `shell/http/app.py:114-141` -- deferred router imports and `application.include_router(...)` block; add `corpus_router`.
- `shell/http/routes/backup.py:62` -- `_BACKUP_MODELS` tuple (insert `CorpusEntry` after `Client`); docstring "ten tables" wording at lines 85, 90.
- `shell/http/templates/style_guide_edit.html`, `shell/http/templates/client_new.html` -- template shape (`<!doctype>`, `role="alert"` error block, `<form method="post">`, `<textarea name="content" required>`).
- `tests/test_http_style_guide.py` -- fixture shape (`db_session` SQLite `StaticPool`, `app_instance`, `client`, `authenticated_client`); one test per matrix row plus an auth test.
- `tests/test_client_store.py:328-355` -- `test_delete_client_and_derived_leaves_backup_record_untouched` and the explicit `export_record in _CLIENT_CASCADE_TABLES` regression; templates for the new corpus cascade tests. `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant` (line ~347) auto-covers the invariant.
- `tests/test_http_backup.py:62` -- `_TABLE_ORDER` list (add `"corpus_entry"` after `"client"`); `test_empty_database_downloads_all_ten_keys_as_empty_lists` (line ~273) name + wording.
- `tests/test_gate_result_store.py` -- template for a dedicated `tests/test_corpus_store.py` covering cascade deletion behaviour end to end.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0019_corpus_entry.py` -- create: `create_table("corpus_entry", ...)` with the four columns, `create_foreign_key` + `ix_corpus_entry_client_id`, raising `downgrade()`; `down_revision = "0018_backup_record"`.
- [x] `shell/adapters/postgres/corpus_entry.py` -- create: `CorpusEntry` SQLModel (`__tablename__ = "corpus_entry"`), `add_corpus_entry(session, *, content) -> CorpusEntry` (add+flush only), `list_corpus_entries(session) -> list[CorpusEntry]` (`created_at` desc). `__all__` exports all three.
- [x] `shell/adapters/postgres/client.py` -- add `"corpus_entry"` to `_CLIENT_CASCADE_TABLES`; import `CorpusEntry`; add its deletion loop to `delete_client_and_derived` before the `client` delete; extend the docstring noting `corpus_entry` (Story 7.1) and that a NULL `client_id` is intentionally left untouched.
- [x] `shell/http/routes/corpus.py` -- create: `router`, `_parse_form` + `_MAX_CORPUS_FORM_BODY_BYTES = 1_048_576` + `_FormTooLarge`/`_FormNotUtf8` (mirror `style_guide.py`), `GET /corpus`, `GET /corpus/new`, `POST /corpus`.
- [x] `shell/http/app.py` -- deferred-import `corpus_router` and `application.include_router(corpus_router)`.
- [x] `shell/http/routes/backup.py` -- import `CorpusEntry`; insert it into `_BACKUP_MODELS` right after `Client`; update the "ten tables" wording to "eleven".
- [x] `shell/http/templates/corpus_list.html` -- create: entries list (or empty-state + `/corpus/new` link).
- [x] `shell/http/templates/corpus_new.html` -- create: `role="alert"` error block, `<form method="post" action="/corpus">` with a required `content` textarea.
- [x] `tests/test_corpus_store.py` -- create: model insert, `add_corpus_entry`/`list_corpus_entries` ordering, paired-entry deleted with its Client, unpaired-entry survives.
- [x] `tests/test_http_corpus.py` -- create: one test per I/O & Edge-Case Matrix row plus the unauthenticated `401` case.
- [x] `tests/test_client_store.py` -- add an explicit `"corpus_entry" in _CLIENT_CASCADE_TABLES` regression, mirroring the `export_record` one.
- [x] `tests/test_http_backup.py` -- add `"corpus_entry"` to `_TABLE_ORDER` after `"client"`; rename/adjust `test_empty_database_downloads_all_ten_keys_as_empty_lists` to eleven; a populated paired `CorpusEntry` appears once in the export under `corpus_entry`.

**Acceptance Criteria:**
- Given a valid session and pasted prose, when it is posted to `/corpus`, then exactly one `corpus_entry` row is persisted in Postgres and the entry appears in `GET /corpus`.
- Given the `corpus_entry` table, when the full migration chain runs, then it has a single head and `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant` passes with `corpus_entry` included.
- Given a Client with a paired Corpus entry and an unrelated unpaired entry, when the Client is deleted, then the paired entry is gone and the unpaired entry remains.
- Given any request to a `/corpus` path without a valid session, when it is made, then it is rejected with `401` before the handler runs.

## Design Notes

`client_id` ships in Story 7.1, not 7.2, because 7.1's own acceptance criterion — "it joins the FR-29 Client deletion cascade for any entry that references a Client" — is only testable if the column exists, and the durable invariant `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant` would otherwise not exercise `corpus_entry` at all. The column is nullable and no 7.1 code path sets it: entries added in 7.1 are always unpaired (`client_id IS NULL`). 7.2 adds the marking and the linking UI on top of a table and cascade that are already correct.

The FR-29 cascade and the `_BACKUP_MODELS` export set are kept in lockstep by two structural invariant tests (`backup_tables == _CLIENT_CASCADE_TABLES | {"client", "style_guide"}` and the FK-safe order check), so adding `corpus_entry` to the cascade forces the matching `_BACKUP_MODELS` change in the same story — it is not optional scope.

## Verification

**Commands:**
- `uv run alembic upgrade head --sql` -- expected: emits `CREATE TABLE corpus_entry`, exits 0.
- `uv run pytest tests/test_corpus_store.py tests/test_http_corpus.py tests/test_client_store.py tests/test_http_backup.py tests/test_migration_chain.py -q` -- expected: all pass.
- `uv run pytest -q` -- expected: full suite green (no pre-existing count/order assertion left stale).
- `uv run ruff check . && uv run mypy .` -- expected: clean.

## Suggested Review Order

**Design intent & schema**

- Entry point: the `client_id`-in-7.1 decision, its rationale, and the append/flush writer contract
  [`corpus_entry.py:41`](../../shell/adapters/postgres/corpus_entry.py#L41)
- Nullable, indexed FK to `client.id` — present now so the cascade AC binds, never set by 7.1 code
  [`corpus_entry.py:57`](../../shell/adapters/postgres/corpus_entry.py#L57)
- Forward-only migration; FK inlined in the column to match the other create-table migrations
  [`0019_corpus_entry.py:37`](../../migrations/versions/0019_corpus_entry.py#L37)
- `list_corpus_entries` — `created_at desc, id desc` so equal timestamps stay deterministic
  [`corpus_entry.py:80`](../../shell/adapters/postgres/corpus_entry.py#L80)

**FR-29 cascade & backup coupling**

- `"corpus_entry"` joins the single source of truth for client-referencing tables
  [`client.py:50`](../../shell/adapters/postgres/client.py#L50)
- Deletion loop, first batch before the `client` row; `client_id IS NULL` entries left untouched
  [`client.py:345`](../../shell/adapters/postgres/client.py#L345)
- `CorpusEntry` placed right after `Client` in `_BACKUP_MODELS` to stay FK-safe (both invariant tests)
  [`backup.py:66`](../../shell/http/routes/backup.py#L66)

**HTTP surface**

- The three routes: list, paste-in form, and the store-then-303 POST — authenticated by default
  [`corpus.py:95`](../../shell/http/routes/corpus.py#L95)
- Hand-parsed urlencoded body with a 1 MiB cap; oversized / non-UTF-8 / blank → 422 (mirrors style_guide)
  [`corpus.py:53`](../../shell/http/routes/corpus.py#L53)
- Router registered in the app factory
  [`app.py:143`](../../shell/http/app.py#L143)
- List view: most-recent-first, empty-state with a link to the form
  [`corpus_list.html:14`](../../shell/http/templates/corpus_list.html#L14)

**Tests**

- Matrix rows 8 & 9 together: paired entry deleted with its Client, unpaired one survives
  [`test_corpus_store.py:132`](../../tests/test_corpus_store.py#L132)
- Route matrix: add / list / empty / blank / oversized / non-UTF-8 / auth
  [`test_http_corpus.py:103`](../../tests/test_http_corpus.py#L103)
- Explicit cascade-constant regression, mirroring the `export_record` one
  [`test_client_store.py:328`](../../tests/test_client_store.py#L328)
- Backup: `_TABLE_ORDER` gains `corpus_entry`; an unpaired entry serializes with `client_id: null`
  [`test_http_backup.py:406`](../../tests/test_http_backup.py#L406)
