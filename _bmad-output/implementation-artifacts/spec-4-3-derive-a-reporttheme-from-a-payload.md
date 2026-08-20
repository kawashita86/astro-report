---
title: 'Story 4.3 — Derive a ReportTheme from a Payload'
type: 'feature'
created: '2026-08-20'
status: 'done'
review_loop_iteration: 0
baseline_commit: '0478dab0ae361adfb2ad1a73eea24f3d8ac79042'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing today summarizes a month's Report Payload into the compact, comparable form Story 4.4's continuity diffing and the Generator port (AD-3) both need — without it, "nothing significant changed since last month" cannot be computed, only guessed by the model.

**Approach:** Add a pure `derive_theme(payload, config) -> ReportTheme` (AD-14) yielding deduplicated slow-planet Aspects, this month's Lunation houses, and standing Retrogrades — and persist one immutable row per `ReportRun`, joining the Client-deletion cascade.

## Boundaries & Constraints

**Always:**
- `core/types/memory.py` — frozen `ThemeAspect`, `ThemeLunation`, `ReportTheme` (mirror `core/types/payload.py`).
- `core/memory/derive.py::derive_theme(payload, config) -> ReportTheme` — pure, model-free (AD-14): collect Aspects/Lunations/StandingRetrogrades across all six `SectionPayload`s, dedupe (frozen dataclasses compare structurally), keep only Aspects whose `transiting_body` is in `config.bodies.slow`.
- `shell/adapters/postgres/report_theme.py` — `StoredReportTheme` (mirror `ReportPayload`: uuid7 PK, `client_id`, unique `report_run_id`, `theme` JSON, `created_at`, `before_update` forbidding mutation) + `store_report_theme()` (add+flush only).
- `migrations/versions/0008_report_theme.py` — mirror `0006_report_payload.py` exactly.
- `shell/adapters/postgres/client.py` — join `_CLIENT_CASCADE_TABLES`; delete `StoredReportTheme` rows in `delete_client_and_derived` before `ReportRun`.
- `shell/runner/driver.py::_run_payload_ready` — after `store_report_payload(...)`, call `derive_theme`+`store_report_theme`, reusing `payload`/`config` already in scope. AD-10 fixes six stage names — not a new stage.

**Ask First:**
- Tightness order for `dominant_aspects`: no event carries a numeric orb-degree. Default: still-in-orb-at-month-end Aspects (`orb_exit_at is None`) first, by `perfected_at` descending (`None` last); separated ones follow, by `orb_exit_at` descending. Confirm — Story 4.4's diffing depends on this order.

**Never:**
- No new AD-10 stage. No ephemeris/Generator calls from `core/memory/`. No top-N truncation (4.4 needs the full set). No change to `ReportPayload`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No slow-planet Aspects | only fast-body Aspects this month | `dominant_aspects == ()` | N/A |
| Same slow Aspect in multiple Sections | e.g. Saturn square Sun in `amore` and `lavoro` | deduped to one `ThemeAspect` | N/A |
| No Lunations / Retrogrades | empty tuples in Payload | `lunations == ()`, `standing_retrogrades == ()` | N/A |
| Two ReportRuns, one Client | `payload_ready` runs twice | two `StoredReportTheme` rows, one per `report_run_id` | N/A |
| `payload_ready` resumed after crash | run already past `payload_ready` | `store_report_theme` not called twice | resume guard already in `drive()` |
| Client deleted | `delete_client_and_derived` runs | `StoredReportTheme` row(s) removed before `ReportRun` | N/A |

</frozen-after-approval>

## Code Map

- `core/types/payload.py`, `core/types/transits.py` -- `Payload`/`SectionPayload`/event shapes `derive_theme` reads (no orb-degree field, see Ask First).
- `core/types/computation.py:51`, `core/payload/assemble.py:104` -- `Bodies.slow` and the existing `_resolve_bodies` reuse pattern.
- `shell/adapters/postgres/report_payload.py`, `migrations/versions/0006_report_payload.py` -- shape to mirror verbatim.
- `shell/adapters/postgres/client.py:44,264` -- `_CLIENT_CASCADE_TABLES`; deletion order.
- `shell/runner/driver.py:79,281` -- `_STAGE_SEQUENCE`; `_run_payload_ready`'s scope.
- `tests/test_report_payload_store.py`, `test_client_store.py`, `test_migration_chain.py`, `test_runner_driver.py` -- shapes to mirror.

## Tasks & Acceptance

**Execution:**
- [x] `core/types/memory.py` -- `ThemeAspect`, `ThemeLunation`, `ReportTheme` frozen dataclasses.
- [x] `core/memory/derive.py` -- `derive_theme(payload, config) -> ReportTheme` per Boundaries.
- [x] `shell/adapters/postgres/report_theme.py` -- `StoredReportTheme` + `store_report_theme()`, mirror `report_payload.py`.
- [x] `migrations/versions/0008_report_theme.py` -- mirror `0006_report_payload.py`.
- [x] `shell/adapters/postgres/client.py` -- join cascade constant + deletion step.
- [x] `shell/runner/driver.py::_run_payload_ready` -- derive + store after `store_report_payload()`.
- [x] `tests/test_derive_theme.py`, `tests/test_report_theme_store.py` -- new, cover the I/O Matrix.
- [x] extend `tests/test_runner_driver.py`, `test_client_store.py`, `test_migration_chain.py` -- cascade/migration/wiring regressions.

**Acceptance Criteria:**
- Given a `ReportRun` reaches `payload_ready`, when `_run_payload_ready` completes, then exactly one `StoredReportTheme` row exists for that `report_run_id`, derived purely from the just-assembled `Payload`.
- Given a Client is deleted, when `delete_client_and_derived` runs, then no `report_theme` row referencing that Client survives.

## Spec Change Log

## Design Notes

`derive_theme` takes `config` (AD-14's shorthand is `derive_theme(payload)`) so slow/fast reads `config.bodies.slow` instead of a second, drifting hardcoded list — `config` is pure frozen data, so purity holds.

Dedup: the event dataclasses are frozen, so duplicates across `SectionPayload`s are `==` and collapse via `dict.fromkeys` before deterministic re-sorting.

## Verification

**Commands:**
- `uv run pytest tests/test_derive_theme.py tests/test_report_theme_store.py tests/test_runner_driver.py tests/test_client_store.py -q` -- expected: all pass.
- `uv run pytest tests/test_migration_chain.py tests/test_forward_only_migrations.py tests/test_migrations_precede_traffic.py -q` -- expected: all pass, `0008_report_theme` resolves in the chain.
- `uv run ruff check .` -- expected: no new violations.

## Suggested Review Order

**Pure derivation: `derive_theme`**

- Entry point -- collects, filters to `config.bodies.slow`, dedupes, and orders `dominant_aspects`/`lunations`/`standing_retrogrades`.
  [`derive.py:68`](../../core/memory/derive.py#L68)

- The Ask First default: still-open Aspects before separated ones, tie-broken by `perfected_at`/`orb_exit_at`.
  [`derive.py:49`](../../core/memory/derive.py#L49)

- `ThemeAspect`/`ThemeLunation`/`ReportTheme` -- the pure output shape, `ThemeLunation` deliberately drops `occurred_at`/`longitude`.
  [`memory.py:24`](../../core/types/memory.py#L24)

**Persistence: immutable, one row per ReportRun**

- `StoredReportTheme` -- mirrors `ReportPayload`'s shape: uuid7 PK, unique `report_run_id`, whole-value JSON column.
  [`report_theme.py:33`](../../shell/adapters/postgres/report_theme.py#L33)

- Immutability guard -- an accidental update fails loudly rather than corrupting a future month's continuity input.
  [`report_theme.py:64`](../../shell/adapters/postgres/report_theme.py#L64)

- `store_report_theme()` -- add+flush only, never decides the caller's transaction boundary.
  [`report_theme.py:102`](../../shell/adapters/postgres/report_theme.py#L102)

- `report_theme` table -- forward-only, unique index on `report_run_id` enforces "exactly one per run" at the schema layer.
  [`0008_report_theme.py:31`](../../migrations/versions/0008_report_theme.py#L31)

**Wiring and cascade**

- `_run_payload_ready` derives and stores the theme right after the payload -- no new AD-10 stage, reuses `payload`/`config` in scope.
  [`driver.py:326`](../../shell/runner/driver.py#L326)

- `report_theme` joins `_CLIENT_CASCADE_TABLES`.
  [`client.py:45`](../../shell/adapters/postgres/client.py#L45)

- Deleted before `ReportRun`, avoiding the FK violation `ReportPayload`'s own ordering already guards against.
  [`client.py:304`](../../shell/adapters/postgres/client.py#L304)

**Tests**

- Ask First tightness order, asserted stop by stop.
  [`test_derive_theme.py:228`](../../tests/test_derive_theme.py#L228)

- Cross-Section dedup for a repeated slow Aspect.
  [`test_derive_theme.py:113`](../../tests/test_derive_theme.py#L113)

- Runner wiring: exactly one `StoredReportTheme` row after `payload_ready`.
  [`test_runner_driver.py:210`](../../tests/test_runner_driver.py#L210)

- Uniqueness and cascade-deletion regressions.
  [`test_report_theme_store.py:201`](../../tests/test_report_theme_store.py#L201), [`test_report_theme_store.py:242`](../../tests/test_report_theme_store.py#L242)

- Migration chain pins the emitted DDL for `0008_report_theme`.
  [`test_migration_chain.py:161`](../../tests/test_migration_chain.py#L161)
