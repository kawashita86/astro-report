---
title: 'Delete a Client and everything derived from them'
type: 'feature'
created: '2026-08-17'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '0703782abbbd2f4f138a197178dffdbe5febcdd6'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Client and its charts, once created, can never be removed. An abandoned or mistaken
record, or a client's data removal request, has no path today.

**Approach:** A new authenticated confirm-then-delete route hard-deletes the `Client` row and every
`StoredNatalChart` row for it (current and superseded) in one transaction, guarded by an explicit
confirmation step that states what will be removed before anything executes. A durable invariant
test asserts every table with a foreign key to `client.id` is covered by the cascade, so a later
story that adds a new Client-referencing table fails CI until it joins the cascade.

## Boundaries & Constraints

**Always:**
- `GET /clients/{id}/delete` renders a confirmation page naming what will be removed (the Client and
  its Natal Chart, including any superseded chart). Nothing is deleted on `GET`.
- `POST /clients/{id}/delete` deletes only when the form carries `confirmed=1` -- mirrors Story 2.7's
  confirm-gate pattern in `clients.py`. Without it, re-render the same confirmation page; nothing is
  deleted.
- On confirmed delete, in one transaction: every `StoredNatalChart` row for the client (current and
  superseded) is deleted, then the `Client` row is deleted. Commit only after both steps succeed.
- Deletion is a hard delete -- no soft-delete flag, nothing left readable through the application.
- Domain Profiles are never persisted (confirmed: no `DomainProfile` table exists anywhere in
  `shell/` or `migrations/` -- Story 2.5 assembles them as a pure, unstored function of a
  `NatalChart`). Deleting the `StoredNatalChart` rows removes every input Domain Profiles could ever
  be assembled from, satisfying that part of the AC with no separate deletion step.
- A test enumerates every table in `SQLModel.metadata` carrying a foreign key to `client.id` and
  asserts that set equals an explicit, named constant the deletion function is built from -- so
  adding a new Client-referencing table without updating both fails this test, not silently.
- The deletion log line carries only the Client's UUID, never name or birth data -- mirrors
  `shell/http/auth.py`'s `log_failed_login_attempt()` (bare `_logger` call, no interpolated PII).
- Authenticated by default via the existing `AuthMiddleware` (route is not in `ALLOWLIST`).
- Unknown client id on either verb -- 404, nothing touched.

**Ask First:** none anticipated.

**Never:**
- No `ON DELETE CASCADE` at the schema/migration level -- deletion order (children, then parent) is
  explicit application code, matching how no FK in this codebase declares `ondelete` today.
- No new error hierarchy -- a 404 for a missing client is the only error path; nothing else here can
  fail once the client is found (no external resolution or computation is re-run, unlike Story 2.7).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Confirmation page | `GET /clients/{id}/delete`, id exists | 200; page states Client + chart(s) will be removed; nothing deleted | N/A |
| Unconfirmed delete | `POST /clients/{id}/delete`, no `confirmed` field | 200; same confirmation page re-rendered, nothing deleted | N/A |
| Confirmed delete, current chart only | `POST` + `confirmed=1`, one non-superseded chart | 200; Client row and its chart row are gone from the DB | N/A |
| Confirmed delete, superseded chart present | `POST` + `confirmed=1`, client has a superseded chart (Story 2.7) | 200; Client row and both chart rows (current + superseded) are gone | N/A |
| Unknown client id | `GET`/`POST /clients/{id}/delete`, id not in DB | 404 | plain 404, no row touched |
| Post-delete read | `GET /clients/{id}/chart` after deletion | 404 | existing not-found path, unchanged |

</frozen-after-approval>

## Code Map

- `shell/http/routes/clients.py:303-463` -- read-only reference: `client_edit_form`/`correct_client`'s
  confirm-gate shape (`fields.get("confirmed") != "1"` re-renders instead of persisting) and
  `_render_edit_form`'s pattern -- the new `client_delete_form`/`delete_client` routes mirror this
  shape but need no form-field parsing beyond `confirmed`, since deletion takes no new input.
- `shell/adapters/postgres/client.py:31-83` -- `Client`, `StoredNatalChart` -- add
  `delete_client_and_derived(session, *, client) -> None`: deletes every `StoredNatalChart` row for
  `client.id` (current and superseded), then `session.delete(client)`. `add()`/`delete()`/`flush()`
  only, caller commits -- exactly like `create_client_with_chart`/`correct_client_and_chart`.
  Also add module-level `_CLIENT_CASCADE_TABLES: frozenset[str] = frozenset({"natal_chart"})`, the
  single source of truth both the delete function and the invariant test read from.
- `shell/http/auth.py:116-122` -- `log_failed_login_attempt` -- pattern to mirror for a new
  `log_client_deleted(client_id: UUID) -> None` in the same module (or colocated in `clients.py`,
  matching where the call site lives): bare `_logger.info` call, client id only, no interpolated
  name/birth data.
- `shell/http/templates/client_edit.html` -- template convention (plain HTML, warning `<p
  role="alert">` + confirm form) the new `client_delete.html` follows: a confirmation page with one
  `<form method="post">` carrying a hidden `confirmed=1`.
- `shell/http/app.py:86-104` -- deferred router import + `include_router()` pattern; no new router
  needed, the delete routes join the existing `clients_router`.
- `tests/test_client_store.py:1-50` -- fixture pattern (in-memory SQLite engine, `session` fixture,
  `_create()` helper) to extend with `delete_client_and_derived()` coverage and the cascade-invariant
  test.
- `tests/test_http_client_correction.py:1-165` -- fixture pattern (`_FakeGeocoder`, `db_session`,
  `client`, `authenticated_client`) to duplicate in a new `tests/test_http_client_deletion.py`.

## Tasks & Acceptance

**Execution:**
- [x] `shell/adapters/postgres/client.py` -- add `_CLIENT_CASCADE_TABLES` constant and
  `delete_client_and_derived()` -- deletes all `StoredNatalChart` rows for a client then the client
  row, in that order, add/delete/flush only
- [x] `shell/http/auth.py` -- add `log_client_deleted(client_id)` -- bare log line, id only
- [x] `shell/http/routes/clients.py` -- add `GET`/`POST /clients/{id}/delete` -- confirm, then delete
  and commit, then log
- [x] `shell/http/templates/client_delete.html` -- create -- states what will be removed, confirm
  button
- [x] `tests/test_client_store.py` -- add: `delete_client_and_derived()` removes client + current
  chart; removes client + superseded chart when one exists; the cascade-invariant test asserting
  `SQLModel.metadata` tables with a `client.id` foreign key equal `_CLIENT_CASCADE_TABLES`
- [x] `tests/test_http_client_deletion.py` -- create -- one test per I/O matrix row

**Acceptance Criteria:**
- Given a Client, when Francesco requests deletion, then a confirmation page states what will be
  removed and nothing is deleted until confirmed.
- Given a confirmed deletion, when it executes, then the Client row and every `StoredNatalChart` row
  for it (including superseded ones) are gone, and no deleted Client's data is readable through any
  route afterward.
- Given the deletion log line, when it is written, then it carries the Client's UUID only.
- Given a future story adds a table with a foreign key to `client.id`, when the cascade-invariant test
  runs without that table being added to `_CLIENT_CASCADE_TABLES` and `delete_client_and_derived()`,
  then that test fails.

## Design Notes

The cascade-invariant test is the mechanism for epic-2-context.md's "any later Client-referencing
table joins this cascade" requirement: it does not predict what future tables will exist, it just
makes `SQLModel.metadata`'s foreign keys and `_CLIENT_CASCADE_TABLES` provably equal, so silence is
impossible -- a new table either gets added to the constant (and the delete function) or the test
red-lines.

Domain Profiles need no deletion step of their own: Story 2.5's spec is explicit that assembling them
returns a value with "no persistence -- storing DomainProfiles is a later story's concern," and no
later story introduced that storage (confirmed by grep across `shell/` and `migrations/`). The AC's
mention of removing them is satisfied by removing their only possible input, the `StoredNatalChart`
rows.

## Verification

**Commands:**
- `uv run pytest tests/test_client_store.py tests/test_http_client_deletion.py` -- new tests green
- `uv run pytest` -- full suite green, including `tests/test_http_client_correction.py` and
  `tests/test_http_chart_wheel.py` (unaffected by the new routes)
- `uv run ruff check .` -- clean

**Manual checks (if no CLI):**
- Create a Client, correct its birth data once (Story 2.7) so it has a superseded chart, then open
  `/clients/{id}/delete`, confirm, and verify `/clients/{id}/chart` now 404s.

## Suggested Review Order

**Cascade deletion: children before parent**

- Entry point: deletes every `StoredNatalChart` row for a client, then the `Client` row, in one
  flush -- no `ON DELETE CASCADE` exists at the schema level, so this is the whole cascade.
  [`client.py:216`](../../shell/adapters/postgres/client.py#L216)

- The invariant the whole feature depends on: every table with a `client.id` foreign key is named
  here, and nowhere else.
  [`client.py:41`](../../shell/adapters/postgres/client.py#L41)

**Route orchestration: confirm, then delete**

- Confirmed-POST branch: the only place deletion actually executes, gated by `confirmed=1`.
  [`clients.py:552`](../../shell/http/routes/clients.py#L552)

- Unconfirmed/malformed-body branches: re-renders the confirmation page (200) or a 422, mirroring
  `create_client`/`correct_client`'s own `_parse_form` failure handling -- nothing is deleted on
  either path.
  [`clients.py:523`](../../shell/http/routes/clients.py#L523)

- GET confirmation page: 404 for an unknown client, otherwise states what will be removed.
  [`clients.py:506`](../../shell/http/routes/clients.py#L506)

**Cross-story consistency: the cascade-invariant test**

- Compares every `client.id` foreign key in `SQLModel.metadata` against the named constant above --
  a future Client-referencing table fails this, not silently.
  [`test_client_store.py:282`](../../tests/test_client_store.py#L282)

**No-secrets-in-logs: the deletion log line**

- Bare `_logger.info` call, client id only -- mirrors `log_failed_login_attempt`'s shape.
  [`auth.py:127`](../../shell/http/auth.py#L127)

**Peripherals**

- Confirmation/error-state template, rewritten during review to avoid orphaned punctuation.
  [`client_delete.html:1`](../../shell/http/templates/client_delete.html#L1)

- Store-level deletion coverage: current chart, superseded chart, no-commit-no-persist.
  [`test_client_store.py:209`](../../tests/test_client_store.py#L209)

- Route-level coverage: one test per I/O matrix row plus cross-client isolation, double-delete, and
  the deletion log line's content.
  [`test_http_client_deletion.py:1`](../../tests/test_http_client_deletion.py#L1)
