# Epic 10 Context: Fast reports — parallel Section generation and instant PDF

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Francesco gets a report on screen in under a minute, sees each Section appear as it is written, waits only for the Sections the Gate rejected, and downloads the PDF in seconds. The epic ports md-report's per-Section generation, background driver with leases, and progressive drafting UI into astro-report, and adds a stored-PDF cache plus a block-layout export template. Every existing correctness contract (Payload, id aliases, Gate, export gate, review paths) is kept.

## Stories

- Story 10.1: A PDF in seconds, and instantly the second time
- Story 10.2: Paid flash, configured, and the data terms re-recorded
- Story 10.3: Generate one Section at a time
- Story 10.4: Section rows and the RunDriver
- Story 10.5: Regenerate only what the Gate rejected
- Story 10.6: Watch the Sections being written
- Story 10.7: Measure it

## Requirements & Constraints

- Production PDF export took 20–25 s; locally 3.5 s with flex/grid-heavy `report_export.html`, 1.0 s with block layout. WeasyPrint's flex layout re-measures every word of long prose several times; production is a slower vCPU with one uvicorn worker.
- Repeat downloads must not re-render: stored PDF bytes are served when a fingerprint of everything the PDF depends on matches.
- Generation today is one ~118 s p90 8-Section call; Epic 10 moves to per-Section parallel calls (later stories). Story 10.1 is independent of that and goes first.
- No partial Report is ever exportable (FR-19 holds); the export gate is unchanged.

## Technical Decisions

- Migrations are forward-only; new table `exported_pdf` (`report_id`, `fingerprint`, `pdf_bytes`, `created_at`) mirrors md-report's table of the same name.
- `ExportRecord` and `run.stage` writes on download are unchanged by the cache.
- The fingerprint covers the rendered draft, Client name and birth data, chart id, and the template file hash; a hand-correction of a Section changes it.
- md-report is the reference implementation (`../md-report`).
- Real-Postgres checks (`MIGRATION_TEST_DATABASE_URL`) are required for the migration.

## UX & Interaction Patterns

- Export layout must visually match `mockups/key-pdf-export.html`; prose cards use block layout (floats or `display: table` for side-by-side), flex/grid only on small fixed-size rows.

## Cross-Story Dependencies

- Build order: 10.1 (independent) → 10.2 → 10.3 → 10.4 → 10.5 → 10.6 → 10.7. Story 10.7 measures and updates `latency.md`.
