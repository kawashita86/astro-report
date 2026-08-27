---
title: 'Story 7.2 — Mark an entry paired or unpaired'
type: 'feature'
created: '2026-08-27'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '33c5fd810810db1af60b6a343954a53c0d852a37'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every Corpus entry added in Story 7.1 is unpaired (`client_id IS NULL`), and the form has no way to say otherwise. Until an entry can be marked paired — Francesco knows the chart behind it — and optionally linked to a Client and month, the paired subset that phase-2 exemplar selection would draw on cannot be identified, and Story 7.3's composition count has nothing to split on.

**Approach:** Add two columns to `corpus_entry` — `paired` (boolean, `NOT NULL`, backfilled `false`) and `month` (nullable `YYYY-MM` text) — via a forward-only migration. Extend the `/corpus/new` form with a paired/unpaired choice and, for a paired entry, an optional existing-Client picker and an optional month. `POST /corpus` validates and stores the marking; the list view shows it. Marking happens when the entry is recorded — there is no retroactive re-marking route.

## Boundaries & Constraints

**Always:**
- New migration `0020_corpus_entry_pairing` (`down_revision = "0019_corpus_entry"`), mirroring `0019_corpus_entry.py`'s module shape and its raising `downgrade()`. `op.add_column("corpus_entry", …)` twice: `paired` as `sa.Boolean(), nullable=False, server_default=sa.false()` (backfills every Story 7.1 row to unpaired — mirrors `0010`/`0012`'s `server_default` add-column), and `month` as `sa.String(), nullable=True` (add-column only, no `server_default` — mirrors `0016_export_record_disposition.py`).
- `CorpusEntry` (`shell/adapters/postgres/corpus_entry.py`) gains `paired: bool = Field(default=False)` and `month: str | None = Field(default=None)`, placed after `client_id`. Model side carries only `default=` — no `sa_column`, no `server_default` — mirroring `ReportRun.stage_failure_count`.
- `add_corpus_entry` gains keyword-only `paired: bool = False`, `client_id: UUID | None = None`, `month: str | None = None`, all passed straight to the `CorpusEntry(...)` constructor. It still only `add()`s + `flush()`es — the route owns the transaction boundary.
- A paired entry may have `client_id` unset, `month` unset, or both: pairing is Francesco's assertion that he knows the chart, independent of whether the application holds the Client. A Client is never created to satisfy the link — the picker only offers Clients that already exist.
- `POST /corpus` reads `paired` (radio: `paired` / `unpaired`, default `unpaired`), `client_id` (a `client.id` string or empty), `month` (a string or empty) from the same hand-parsed urlencoded body as today. When `paired` is not `paired`: store `paired=False` and force `client_id`/`month` to `NULL` regardless of what was submitted. When `paired` is `paired`: a non-empty `client_id` must parse as a UUID and name an existing `Client` (else `422`, re-render, insert nothing); a non-empty `month` must match `^\d{4}-(0[1-9]|1[0-2])$` (else `422`, re-render, insert nothing); an empty value for either is stored as `NULL`.
- `GET /corpus/new` and every `422` re-render pass the full Client list (for the picker) and echo the submitted `paired`/`client_id`/`month` back into the form alongside `content` and `error`.
- New reader `list_clients(session) -> list[Client]` in `shell/adapters/postgres/client.py` (`select(Client).order_by(Client.name, Client.id)`), added to that module's `__all__`.
- `GET /corpus` shows each entry's paired/unpaired state; for a linked entry it shows the Client name and the month.
- Existing Story 7.1 behaviour is unchanged: blank/oversized/non-UTF-8 body handling, `303` redirect to `/corpus`, authenticated-by-default (nothing added to `ALLOWLIST`), most-recent-first ordering.

**Ask First:**
- Adding a retroactive marking route (`POST /corpus/{id}` or similar) so Story 7.1's existing unpaired rows can be paired later. The epic's UX fixes marking at record time; this story honours that.
- Constraining `month` to a Client's actual `ReportRun` months instead of accepting any valid `YYYY-MM`.

**Never:**
- No composition counts or stats view — Story 7.3.
- No edit or delete of an entry's content; no per-source parsing, file upload, or format handling.
- No change to the FR-29 cascade (`delete_client_and_derived`, `_CLIENT_CASCADE_TABLES`) or to `_BACKUP_MODELS` — Story 7.1 already wired `corpus_entry` into both; the cascade matches on `client_id` and is indifferent to `paired`/`month`, and the backup serializes whole rows so the two columns export automatically.
- No `core/` changes; nothing durable on the container filesystem.
- No entry content and no client identifiers in logs or telemetry — structured identifiers only.
- No phase-2 exemplar selection or anonymization machinery — the anonymization position is an open question recorded here that gates no v1 story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unpaired entry | `POST /corpus`, `content` set, `paired=unpaired` | one row, `paired=False`, `client_id`/`month` `NULL`; `303` to `/corpus` | N/A |
| Paired + linked | `paired=paired`, `client_id` = an existing `Client`, `month=2026-05` | one row, `paired=True`, `client_id` set, `month="2026-05"`; `303` | N/A |
| Paired, Client not in app | `paired=paired`, `client_id` empty, `month` empty | one row, `paired=True`, `client_id`/`month` `NULL`; `303` | N/A |
| Paired, unknown Client | `paired=paired`, `client_id` = a well-formed UUID with no `Client` row | nothing inserted, form re-rendered with the picker and echoed fields | `422`, `role="alert"` |
| Paired, malformed client_id | `paired=paired`, `client_id` not a UUID | nothing inserted, form re-rendered | `422`, `role="alert"` |
| Paired, bad month | `paired=paired`, `month` = `2026-13` / `may` / `2026-5` | nothing inserted, form re-rendered | `422`, `role="alert"` |
| Unpaired but link fields sent | `paired=unpaired`, `client_id` and `month` both populated | one row, `paired=False`, `client_id`/`month` `NULL` (submitted link ignored) | N/A |
| List shows marking | `GET /corpus` with a paired-linked row and an unpaired row | `200`; paired row shows Client name + month, unpaired row shown as unpaired | N/A |
| Blank content, paired | `POST /corpus`, whitespace-only `content`, `paired=paired` | nothing inserted, form re-rendered | `422`, `role="alert"` |
| Unauthenticated | any `/corpus*` request without a valid session | rejected before the handler runs | `401`, empty body |

</frozen-after-approval>

## Code Map

- `migrations/versions/0019_corpus_entry.py` -- template for `0020_corpus_entry_pairing.py`: module header, `revision`/`down_revision`, raising `downgrade()`.
- `migrations/versions/0010_report_run_failure.py:36`, `migrations/versions/0012_bounded_regeneration.py:39` -- precedent for `op.add_column(..., nullable=False, server_default=...)` that backfills existing rows; use `server_default=sa.false()` for `paired`.
- `migrations/versions/0016_export_record_disposition.py:37` -- precedent for add-column nullable, no `server_default`; shape for `month`.
- `migrations/versions/0005_report_run.py:39` -- `sa.Column("month", sa.String(), nullable=False)`; the corpus `month` is the same but `nullable=True`.
- `shell/adapters/postgres/corpus_entry.py:41` -- `CorpusEntry`: add `paired`/`month` fields after `client_id` (line 57). `add_corpus_entry` at line 64 gains the three keyword-only params; extend both docstrings.
- `shell/adapters/postgres/report_run.py:121` -- `stage_failure_count: int = Field(default=0)`: the model-side pattern for a `NOT NULL` scalar whose migration carries `server_default` (no `sa_column`).
- `shell/http/routes/corpus.py:94` -- `POST /corpus`: parse and validate `paired`/`client_id`/`month`, call `add_corpus_entry(...)`. `GET /corpus/new` at line 86 and the three `422` re-renders (lines 105-126) all pass `clients=list_clients(session)` and echo `paired`/`client_id`/`month`. `_parse_form` at line 53 already returns a flat `dict[str, str]` — no change.
- `shell/http/routes/report_runs.py:69` -- `_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")`: reuse this exact shape in `corpus.py` (re-declare a module-level constant; do not import the route module).
- `shell/adapters/postgres/client.py:36` -- `__all__` (add `list_clients`); `Client` model at line 65 (`name` at line 83). Add `list_clients(session) -> list[Client]` = `select(Client).order_by(Client.name, Client.id)`.
- `shell/http/templates/corpus_new.html` -- add a `paired`/`unpaired` radio group (default `unpaired`), a `client_id` `<select>` (first option `value=""`, "not in the application"), and a `month` text input; echo submitted values; keep the `role="alert"` block.
- `shell/http/templates/corpus_list.html:14` -- per entry, render paired/unpaired; for a linked entry show `entry.client` name and `entry.month`. If the template needs the Client name, resolve it in the route (pass `entries` as `(entry, client_or_none)` pairs) rather than adding a relationship.
- `shell/http/routes/backup.py:62` -- `_BACKUP_MODELS` already contains `CorpusEntry`; `model_dump(mode="json")` picks up `paired`/`month` with no change. Read-only evidence.
- `tests/test_http_corpus.py` -- fixture shape to extend with the new matrix rows.
- `tests/test_corpus_store.py` -- `add_corpus_entry`/model tests to extend; existing FR-29 cascade tests must stay green untouched.
- `tests/test_http_backup.py:383` -- existing paired/unpaired corpus backup tests; new columns are additive, so they must still pass with no edit.
- `tests/test_migration_chain.py:47` -- `test_exactly_one_head` must still hold with `0020` on the chain.

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0020_corpus_entry_pairing.py` -- create: `add_column` `paired` (`Boolean`, `nullable=False`, `server_default=sa.false()`) and `month` (`String`, `nullable=True`) on `corpus_entry`; `down_revision = "0019_corpus_entry"`; raising `downgrade()`.
- [x] `shell/adapters/postgres/corpus_entry.py` -- add `paired: bool = Field(default=False)` and `month: str | None = Field(default=None)` after `client_id`; extend `add_corpus_entry` with keyword-only `paired`, `client_id`, `month` passed to the constructor; update module + function docstrings.
- [x] `shell/adapters/postgres/client.py` -- add `list_clients(session) -> list[Client]` (`order_by(Client.name, Client.id)`); add to `__all__`.
- [x] `shell/http/routes/corpus.py` -- add `_MONTH_PATTERN`; in `POST /corpus` parse `paired`/`client_id`/`month`, apply the Always-tier validation, call `add_corpus_entry(...)`; make `GET /corpus/new` and every `422` re-render pass `clients` and echo the three fields; in `GET /corpus` pair each entry with its resolved Client (or `None`).
- [x] `shell/http/templates/corpus_new.html` -- add the radio group, the Client `<select>`, and the `month` input; echo `paired`/`client_id`/`month`.
- [x] `shell/http/templates/corpus_list.html` -- render paired/unpaired per entry; show Client name + month for a linked entry.
- [x] `tests/test_corpus_store.py` -- add: `add_corpus_entry` persists `paired`/`client_id`/`month`; a paired entry with both link fields unset persists `paired=True`; `list_clients` ordering.
- [x] `tests/test_http_corpus.py` -- add one test per new I/O & Edge-Case Matrix row.

**Acceptance Criteria:**
- Given a valid session and `paired=paired` with an existing Client and a valid month, when posted to `/corpus`, then one row persists with `paired=True`, that `client_id`, and that `month`, and it appears in `GET /corpus` showing the Client name and month.
- Given `paired=paired` with no Client selected and no month, when posted, then one row persists with `paired=True` and `client_id`/`month` `NULL` — no Client is invented.
- Given `paired=paired` with a well-formed but unknown `client_id`, or an invalid `month`, when posted, then nothing is inserted and the form re-renders with a `role="alert"` message and `422`.
- Given the `corpus_entry` table after `0020`, when the full migration chain runs, then it has a single head and every Story 7.1 row reads back `paired = false`.
- Given `test_every_table_with_a_client_id_foreign_key_is_covered_by_the_cascade_constant` and the Story 7.1 corpus/backup tests, when the suite runs, then all still pass with no edit.

## Design Notes

`paired` is a stored boolean, not derived from `client_id`/`month`, because the "Client not in the application" acceptance criterion requires an entry that is paired with both link fields `NULL`. Pairing records Francesco's knowledge of the chart; the link records whether the application happens to hold it. Story 7.3's composition count reads this column directly (`paired` vs `NOT paired`).

The migration's `server_default=sa.false()` exists only to backfill Story 7.1's rows — all genuinely unpaired — during the `ALTER`. The model carries just `default=False`, matching `ReportRun.stage_failure_count`, whose `0010` migration uses the same `server_default` pattern while the field declares only `default=0`.

Marking is record-time only, per the epic's UX ("Paired/unpaired is chosen when the entry is recorded"). Consequently Story 7.1's existing rows stay unpaired with no path to change that; a retroactive marking route is an explicit Ask First, not silent scope.

The anonymization position is the epic's recorded open question. It gates no v1 story and nothing here consumes Corpus content — logging stays identifiers-only, consistent with 7.1.

## Verification

**Commands:**
- `uv run alembic upgrade head --sql` -- expected: emits `ALTER TABLE corpus_entry ADD COLUMN paired` and `... ADD COLUMN month`, exits 0.
- `uv run pytest tests/test_corpus_store.py tests/test_http_corpus.py tests/test_http_backup.py tests/test_migration_chain.py -q` -- expected: all pass.
- `uv run pytest -q` -- expected: full suite green (no stale count/shape assertion).
- `uv run ruff check . && uv run mypy .` -- expected: clean.

## Suggested Review Order

**Schema change**

- Two `add_column`s on `corpus_entry`: `paired` (`NOT NULL`, `server_default false` backfills Story 7.1 rows), `month` (nullable) — forward-only, raising `downgrade()`.
  [`0020_corpus_entry_pairing.py:37`](../../migrations/versions/0020_corpus_entry_pairing.py#L37)
- Model gains `paired`/`month` with `default=` only (no `sa_column`); migration owns the `server_default`.
  [`corpus_entry.py:70`](../../shell/adapters/postgres/corpus_entry.py#L70)
- `add_corpus_entry` takes the three marking values keyword-only and passes them straight to the constructor — the route owns validation.
  [`corpus_entry.py:81`](../../shell/adapters/postgres/corpus_entry.py#L81)

**Marking & link validation (entry point)**

- `POST /corpus`: unpaired forces `client_id`/`month` to `NULL`; paired validates a non-empty `client_id` against an existing `Client` and a non-empty `month` against `_MONTH_PATTERN`, else `422` re-render inserting nothing.
  [`corpus.py:229`](../../shell/http/routes/corpus.py#L229)
- `_MONTH_PATTERN` re-declared here (not imported) per the Code Map — same `YYYY-MM` shape the report-run route uses.
  [`corpus.py:55`](../../shell/http/routes/corpus.py#L55)
- `_reject` / `_render_new_form`: every `422` re-render carries the Client list and echoes the submitted `content`/`paired`/`client_id`/`month`.
  [`corpus.py:90`](../../shell/http/routes/corpus.py#L90)

**List view**

- `GET /corpus` resolves linked Clients in one `IN` query into a `{id: client}` map, hands the template `(entry, client_or_none)` pairs.
  [`corpus.py:131`](../../shell/http/routes/corpus.py#L131)
- `list_clients` — every Client ordered `name, id` for the picker; the picker only links to a Client that already exists.
  [`client.py:192`](../../shell/adapters/postgres/client.py#L192)

**UI binding**

- Form: paired/unpaired radio (default unpaired), existing-Client `<select>`, optional `month` input with a `title` format hint.
  [`corpus_new.html:23`](../../shell/http/templates/corpus_new.html#L23)
- List row shows `Paired — {client} — {month}` (parts shown only when present) or `Unpaired`.
  [`corpus_list.html:19`](../../shell/http/templates/corpus_list.html#L19)

**Tests**

- HTTP matrix rows: unpaired/paired-linked/paired-unlinked/unknown-client/bad-month/ignored-link-fields/blank-content, plus the `422` echo and per-`<li>` list assertions.
  [`test_http_corpus.py:233`](../../tests/test_http_corpus.py#L233)
- Store: `add_corpus_entry` persists the three values; a paired entry may have both link fields unset; `list_clients` ordering.
  [`test_corpus_store.py:100`](../../tests/test_corpus_store.py#L100)
