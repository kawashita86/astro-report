---
title: "Ship WeasyPrint's native libraries in the Render image (and record the Neon migration state)"
type: 'bugfix'
created: '2026-08-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'fa5253004a0feb0e44069ebef24a4e91843509f1'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Render image is `python:3.13-slim` + `build-essential` only. WeasyPrint 69 loads the Pango / GLib / HarfBuzz native libraries at *import* time, and `shell/http/routes/report_runs.py:44` imports `html_to_pdf` at module top level, so `create_app()` (`shell/http/app.py:118`) dies with `OSError: cannot load library 'libgobject-2.0-0'` and uvicorn never serves — the whole HTTP app is down, not just the PDF route. The 2026-08-28 deploy reached this crash *after* `alembic upgrade head` ran cleanly against Neon: the first real evidence that epic-6-retro item 46's `alembic_version` `VARCHAR(32)` fix (b6649cc) actually carries the chain into production Postgres.

**Approach:** Add WeasyPrint's documented Debian runtime packages (`libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`) plus `fonts-liberation` (the export template asks for `Georgia, "Times New Roman", serif`; slim ships no fonts) to the Dockerfile's single `apt-get install`. Add a structural Dockerfile guard test. Fold the now-observable Neon migration state into the item-46 tracking so that half of the retro item closes on evidence.

## Boundaries & Constraints

**Always:**
- Install exactly WeasyPrint's official Debian ≥11 list — `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0` — plus `fonts-liberation`. GLib/`libgobject-2.0-0`, HarfBuzz, Fontconfig and FreeType arrive transitively via `libpango-1.0-0` / `libpangoft2-1.0-0`.
- Keep the install in the one existing `apt-get update && apt-get install --no-install-recommends -y … && rm -rf /var/lib/apt/lists/*` RUN, `--no-install-recommends` preserved, list purged in the same layer.
- Rewrite that RUN's comment to carry both rationales: compiler for `pyswisseph`, and the Pango/HarfBuzz stack + font for WeasyPrint. The file's style is deliberate, heavily-commented `apt` choices.
- `build-essential` stays, and stays before `uv sync` (`tests/test_dockerfile_ephemeris_build.py::test_a_compiler_is_installed_before_uv_sync`).
- The new guard reads comment-stripped Dockerfile instruction lines only — a comment must not be able to satisfy it.

**Ask First:**
- If `libharfbuzz-subset0` is not in the `python:3.13-slim` (Debian 13 / trixie) apt index — the build fails loudly on it — stop and confirm the substitute (`libharfbuzz0b`) rather than guessing.
- Flipping sprint-status items 46 / 55 / 60 to `done` vs. leaving them `open` with a progress note — proposed as `done` below; confirm at approval.

**Never:**
- No multi-stage build, no removing `build-essential` from the final image, no image-size refactor.
- No cairo or gdk-pixbuf packages — WeasyPrint ≥53 dropped the cairo backend; raster images go through Pillow's bundled libs.
- No new Python dependency; no edit to `shell/adapters/weasyprint/render.py` or any route.
- No new local-dev docs — `compose.yaml` builds the same Dockerfile, so it is covered.
- Do not assert the Neon DB is at a named head without a `SELECT version_num` result — record only what the deploy log shows (migrations ran past `0014` with no truncation).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Image build | `docker build .` on the amended Dockerfile | Build succeeds; apt resolves all four packages | `libharfbuzz-subset0` unknown to apt → build fails at that step → Ask First |
| App import in the image | `python -c "import shell.http.app"` inside the built image | Exits 0; no `OSError` from `weasyprint` | N/A |
| PDF render in the image | `html_to_pdf("<html><body>x</body></html>")` inside the image | Returns non-empty `bytes` starting `%PDF-` | N/A |
| Dockerfile guard | comment-stripped Dockerfile lines | new test finds `libpango-1.0-0` + `libharfbuzz-subset0` + `fonts-liberation` in one `apt-get install` line | fails naming the missing package and why WeasyPrint needs it |
| Guard vs. comment | Dockerfile with only a *commented* `apt install libpango-1.0-0` | new test still fails | N/A |

</frozen-after-approval>

## Code Map

- `Dockerfile:27-29` — the single `RUN apt-get update && apt-get install --no-install-recommends -y build-essential && rm -rf /var/lib/apt/lists/*`. Add the three WeasyPrint libs + `fonts-liberation` after `build-essential`; rewrite the comment block at `Dockerfile:21-26`.
- `Dockerfile:7` — `FROM python:3.13-slim` (Debian 13 / trixie). `Dockerfile:53-55` ENTRYPOINT/CMD unchanged.
- `shell/adapters/weasyprint/render.py:14` — top-level `from weasyprint import HTML`; the failing import. Not modified.
- `shell/http/routes/report_runs.py:44` — top-level `from shell.adapters.weasyprint.render import html_to_pdf`, so the failure is fatal to `create_app`, not just the PDF route; sole call site is `report_runs.py:496`.
- `shell/http/app.py:118` — `from shell.http.routes.report_runs import router`; the traceback's dying frame.
- `shell/http/templates/report_export.html:11` — `font-family: Georgia, "Times New Roman", serif;` → why `fonts-liberation`.
- `tests/test_dockerfile_ephemeris_build.py:26-33` — `strip_comments()` helper and the structural-assertion / comment-cannot-satisfy pattern to mirror. Not modified.
- `tests/test_dockerfile_weasyprint_runtime.py` — NEW. Local copy of the comment-stripping helper; asserts an `apt-get install` line carries `libpango-1.0-0`, `libharfbuzz-subset0`, `fonts-liberation`; plus a comment-cannot-satisfy proof.
- `pyproject.toml:21` — `weasyprint==69.0` (pinned; informs the list — no cairo).
- `compose.yaml:28-29` — `build: context: .`; same Dockerfile, so local dev is fixed too. Verify only.
- `_bmad-output/implementation-artifacts/spec-epic-6-retro-item-46-alembic-version-ceiling.md` — `status: done`. Frozen block untouched; append one dated bullet to `## Design Notes`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `epic-6-retro-item-46-make-the-alembic-migration-chain-reachab` (~L505-514), `epic-7-retro-item-55-re-prioritise-epic-6-retro-item-46-as-ga` (~L608-616), `epic-8-retro-item-60-fix-epic-6-retro-item-46-alembic_version` (~L658-668); `epic-8-retro-item-59-run-the-story-8-5-operator-restore-rehea` (~L650-658, "Blocked by epic-6-retro-item-46").

## Tasks & Acceptance

**Execution:**
- [x] `Dockerfile` — in the existing `apt-get install` RUN (~line 28) append `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation` after `build-essential`; rewrite the comment block above it to explain the compiler rationale *and* the WeasyPrint Pango/HarfBuzz/font rationale. Keep `--no-install-recommends` and the single-layer `rm -rf /var/lib/apt/lists/*`.
- [x] `tests/test_dockerfile_weasyprint_runtime.py` — new guard module: strip comments from the Dockerfile, assert one `apt-get install` line contains `libpango-1.0-0`, `libharfbuzz-subset0`, and `fonts-liberation` (failure message names whichever is missing and why WeasyPrint needs it), plus a `test_a_comment_cannot_satisfy_*` proof mirroring `tests/test_dockerfile_ephemeris_build.py`. Copy the ~7-line `strip_comments` helper locally rather than cross-importing test modules.
- [x] `_bmad-output/implementation-artifacts/spec-epic-6-retro-item-46-alembic-version-ceiling.md` — append a dated bullet to `## Design Notes`: the 2026-08-28 Render deploy ran `alembic upgrade head` against Neon with no `StringDataRightTruncation` at `0014`; the chain reaches production Postgres; the app then crashed on WeasyPrint native libs (fixed in the sibling spec); the only residue is a `SELECT version_num FROM alembic_version;` spot-check. Do not touch the frozen block.
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` — add a `done_note` to items `…item-46-make-the-alembic-migration-chain-reachab`, `…item-55-re-prioritise-…`, `…item-60-fix-epic-6-retro-item-46-alembic_version` citing b6649cc (id shortened to `0014_bound_string_columns`, real-Postgres + CI test added) and this deploy evidence; set each `status: done` and `decided_on: 2026-08-28`. On `…item-59-run-the-story-8-5-operator-restore-rehea`, note the item-46 blocker is cleared but keep `status: open`. Keep the file valid YAML.

**Acceptance Criteria:**
- Given the amended Dockerfile, when the image is built and `python -c "import shell.http.app"` runs inside it, then it exits 0 with no `weasyprint` `OSError`.
- Given the built image started with the required env vars, when Render probes `/healthz`, then it returns 200 (no import crash) and the deploy goes green.
- Given the built image, when `html_to_pdf("<html><body>hi</body></html>")` is called, then it returns bytes beginning `%PDF-`.
- Given `uv run pytest` and `uv run ruff check .`, when they run (no Docker), then the suite is green — including the new `tests/test_dockerfile_weasyprint_runtime.py` — and lint is clean.
- Given the sprint-status edits, when `_bmad-output/implementation-artifacts/sprint-status.yaml` is parsed, then it still loads and any existing sprint-status guard test stays green.

## Spec Change Log

## Design Notes

The package list is WeasyPrint's own Debian ≥11 "First steps" list for wheel installs: `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`. `libgobject-2.0-0` (the symbol in the traceback) lives in `libglib2.0-0`, pulled in by `libpango-1.0-0`; fontconfig/FreeType via `libpangoft2-1.0-0`. WeasyPrint 53+ replaced its cairo/pango-cairo backend with an internal PDF writer and raster images go through Pillow's bundled libs — so cairo and gdk-pixbuf are deliberately not installed. `libharfbuzz-subset0` is a *separate* Debian package (PDF font subsetting) that is easy to forget.

`fonts-liberation` because `report_export.html:11` requests `Georgia, "Times New Roman", serif` and slim ships no fonts — without it the serif fallback is empty and text renders as notdef boxes or blank pages. Liberation Serif is metric-compatible with Times New Roman. Non-Latin / astrological-glyph coverage is a separate concern, not addressed here.

One RUN, not a second `apt-get` layer: one apt transaction, one list purge, and the file already keeps every system package in a single deliberate instruction.

Item-46 fold-in: b6649cc fixed the `alembic_version VARCHAR(32)` ceiling and added the real-Postgres test, but left "check the deployed Render DB migration state" as a manual follow-up. The 2026-08-28 deploy *is* that check running for real — migrations applied to Neon with no truncation. The residue is a one-line `SELECT version_num FROM alembic_version;` confirmation, which this Docker fix unblocks by letting the deploy complete.

## Verification

**Commands:**
- `uv run pytest tests/test_dockerfile_weasyprint_runtime.py tests/test_dockerfile_ephemeris_build.py` — expected: all pass.
- `uv run pytest` — expected: full suite green (no Docker involved).
- `uv run ruff check .` — expected: clean.
- `python -c "import yaml; yaml.safe_load(open('_bmad-output/implementation-artifacts/sprint-status.yaml'))"` — expected: parses.
- `docker build -t astro-report:weasy-fix .` — expected: build succeeds; apt resolves `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation`.
- `docker run --rm --entrypoint python astro-report:weasy-fix -c "import shell.http.app; from shell.adapters.weasyprint.render import html_to_pdf; print(html_to_pdf('<html><body>ok</body></html>')[:5])"` — expected: prints `b'%PDF-'`, no `OSError`.

**Manual checks (if no CLI):**
- `Dockerfile`: the single `apt-get install` line lists `build-essential` **and** `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-liberation`; `--no-install-recommends` intact; `rm -rf /var/lib/apt/lists/*` in the same RUN; the comment above explains both rationales.
- Post-deploy (Francesco): Render deploy green; `/healthz` 200; a PDF export downloads and opens; `SELECT version_num FROM alembic_version;` on Neon returns `0021_gate_vocabulary_hash`.

## Suggested Review Order

**The fix — WeasyPrint's native libraries in the image**

- The one substantive change: four runtime packages appended to the existing single `apt-get install`, so `import weasyprint` (hence `create_app()`) survives inside the image.
  [`Dockerfile:43`](../../Dockerfile#L43)

- The rewritten rationale block above it — why each package, why no cairo/gdk-pixbuf, why `fonts-liberation`.
  [`Dockerfile:20`](../../Dockerfile#L20)

**The regression guard**

- Structural check mirroring `test_dockerfile_ephemeris_build.py`: all four packages must sit on one comment-stripped `apt-get install` line.
  [`test_dockerfile_weasyprint_runtime.py:74`](../../tests/test_dockerfile_weasyprint_runtime.py#L74)

- Package → reason map, surfaced in the failure message; `libpangoft2-1.0-0` added in review because `libpango-1.0-0` does not pull it transitively.
  [`test_dockerfile_weasyprint_runtime.py:29`](../../tests/test_dockerfile_weasyprint_runtime.py#L29)

- Proof the comment-stripping does real work — a commented-out `apt install` line does not satisfy the check.
  [`test_dockerfile_weasyprint_runtime.py:94`](../../tests/test_dockerfile_weasyprint_runtime.py#L94)

**Item-46 migration-state fold-in (tracking only, no code)**

- Dated evidence bullet: the 2026-08-28 deploy ran `alembic upgrade head` on Neon with no truncation at `0014` — the chain reaches production Postgres.
  [`spec-epic-6-retro-item-46-alembic-version-ceiling.md:93`](spec-epic-6-retro-item-46-alembic-version-ceiling.md#L93)

- Items 46 / 55 / 60 → `done` with `done_note`s citing b6649cc + the deploy; the residual `SELECT version_num` spot-check is parked on still-open item 59.
  [`sprint-status.yaml:505`](sprint-status.yaml#L505)

- Item 59 (restore rehearsal) keeps `status: open` with a dated note that its item-46 blocker is cleared.
  [`sprint-status.yaml:669`](sprint-status.yaml#L669)
