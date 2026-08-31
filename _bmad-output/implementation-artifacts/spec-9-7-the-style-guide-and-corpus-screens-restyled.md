---
title: 'The Style Guide and Corpus screens, restyled'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'db9aa6f50340ffeeb8b66d712b959af67578af42'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `style_guide_list.html`, `style_guide_view.html`, `style_guide_edit.html` and `corpus_list.html` still ship pre-rebuild plain markup — Style Guide and Corpus prose both dumped into a bare monospace `<pre>`, no editor warning that saving forks a version, no length limit or styled badge on Corpus entries, no Italian copy.

**Approach:** Restyle all three Style Guide screens and the Corpus list, routes unchanged — `body-read` prose replaces `<pre>`, a `.form-view`/`.field` editor gets a new `.banner--info` note, a `.list-panel` history table, and a new `.corpus-list` where each entry clamps to ~6 lines with a JS-delegated Expand toggle, a paired/unpaired badge, and the existing composition counts.

## Boundaries & Constraints

**Always:** Every route in `shell/http/routes/style_guide.py`/`corpus.py` keeps its exact contract (status codes, redirects, context keys) — presentation-only, per Story 9.6's boundary. Style Guide versioning and Corpus pairing (Epic 7) are unchanged. All new copy is Italian (label map: Guida di stile, Corpus). Reuse `tokens.css` components verbatim where they fit (`.page-header`, `.form-view`/`.field`, `.btn*`, `.list-panel`, `.banner`, `.status-badge`); add only `.banner--info`, `.prose`, `.corpus-list`/`.corpus-entry*`. The clamp/Expand toggle is a JS-delegated `shell.js` enhancement (mirrors jobs 8/9) — sanctioned by the epic's "JS only upgrades ... in-place disclosure" rule; without JS, full entry text stays in the DOM (readable, selectable, screen-reader visible), only the visual affordance is inert.

**Ask First:** None — scope and mechanics are decided below; raise deviations at review, not mid-build.

**Never:** No date-format filter — Story 9.9 owns that sweep; `created_at` rendering is unchanged. No markdown-to-HTML parsing or new dependency — "readable" means `body-read` prose, not literal Markdown rendering. `corpus_new.html` is out of scope (AC names only the Corpus *list*). No `core/` change, no new route, no data-model change, no touch to `report_export.html`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Style Guide missing | `StyleGuideMissingError` | `/style-guide`, `/style-guide/edit` still render the existing 503, styled, Italian | N/A |
| Style Guide history | current + priors | Current its own block; History a `.list-panel` table (Versione, Creata) excluding current | N/A |
| Corpus empty | no entries | `.list-empty`: "Nessun report passato è stato ancora aggiunto." + link to `/corpus/new` | N/A |
| Corpus entry ≤ 6 lines | short `content` | Full text shown, Expand hidden (JS measures overflow on load) | N/A |
| Corpus entry > 6 lines | long `content` | Clamped to 6 lines; Espandi/Comprimi toggles; full text always in DOM | N/A |
| Expand toggle, no JS | JS disabled | Entry stays visually clamped; text still selectable/screen-reader visible | N/A |
| Composition counts | mixed entries | "{total} totali · {paired} accoppiati · {unpaired} non accoppiati"; each entry badged | N/A |

</frozen-after-approval>

## Code Map

- `shell/http/templates/style_guide_list.html` — `.page-header` (`h1` "Guida di stile" + `.page-header__action` "Modifica" → `/style-guide/edit`); keep `.banner--danger` on `error`. Current version as a small block ("Versione {{ current.version }}" + "Visualizza" link). History as `.list-panel` (Versione/Creata columns, one row per `_history()` entry).
- `shell/http/templates/style_guide_view.html` — breadcrumb "Guida di stile / Versione {{ n }}"; `<pre>{{ content }}</pre>` → `<div class="prose">{{ content }}</div>`; Italian copy.
- `shell/http/templates/style_guide_edit.html` — `.form-view` + `.field` around the unchanged `name="content"` textarea; new `.banner--info` `role="status"` above the form ("Il salvataggio crea una nuova versione — la corrente resta invariata."); error stays `.banner--danger`; submit `.btn.btn--primary` "Salva nuova versione".
- `shell/http/templates/corpus_list.html` — `.page-header` (`h1` "Corpus" + action "Aggiungi report" → `/corpus/new`); counts line `<p class="list-panel__meta">{{ total }} totali · {{ paired_count }} accoppiati · {{ unpaired_count }} non accoppiati</p>`; entries in a new `.corpus-list` `<ul>` (1120px, hairline dividers) — **keep the `<li>` wrapper** (existing test splits on it) — each `<li class="corpus-entry">` holds `.corpus-entry__meta` (`created_at`, `.status-badge--success`/`--neutral` "Accoppiato"/"Non accoppiato", client + month when present) then `<p class="corpus-entry__text" data-corpus-text>{{ entry.content }}</p>` + `<button type="button" class="corpus-entry__expand" data-corpus-expand hidden>Espandi</button>`; empty state `.list-empty`.
- `shell/http/static/tokens.css` — append `PROVISIONAL — Story 9.7`: `.banner--info` (mirrors `.banner--warning`, `--info`/`--info-surface`); `.prose` (720px, `body-read` tokens, `white-space: pre-wrap`); `.corpus-list`/`.corpus-entry` (1120px, hairline divider, `--space-base` padding, no shadow); `.corpus-entry__meta` (`small` tokens, flex row); `.corpus-entry__text` (`body-read`, `-webkit-line-clamp: 6` + `overflow: hidden`, `.is-expanded` clears both); `.corpus-entry__expand` (chromeless, `link` color, underline).
- `shell/http/static/shell.js` — **section 10: Corpus clamp toggle.** On load, un-hide `[data-corpus-expand]` only where its sibling `[data-corpus-text]` has `scrollHeight > clientHeight`. One delegated `click` on `document.body` for `[data-corpus-expand]`: toggle `.is-expanded` on the paired text via `closest(".corpus-entry")`, flip `aria-expanded`, swap label Espandi ↔ Comprimi. Docstring "Nine jobs" → "Ten jobs".
- `tests/test_http_style_guide.py`, `tests/test_http_corpus.py` — amend to new markup/copy: `"Paired"`/`"Unpaired"` → `"Accoppiato"`/`"Non accoppiato"`; `"No past reports"` → the Italian empty-state line; `"{n} total · {p} paired · {u} unpaired"` → the Italian counts line; keep the `<li>`-split assertions structurally unchanged. Add: a short entry renders with no Expand button; a Style Guide view has no `<pre>`.

## Tasks & Acceptance

**Execution:**
- [x] `style_guide_list.html` — page-header, current block, `.list-panel` history table, Italian copy.
- [x] `style_guide_view.html` — `.prose` block, breadcrumb, Italian copy.
- [x] `style_guide_edit.html` — `.form-view`/`.field`, `.banner--info`, Italian copy.
- [x] `corpus_list.html` — page-header, `.corpus-list`/`.corpus-entry*`, `.list-empty`, Italian copy and counts.
- [x] `tokens.css` — `PROVISIONAL — Story 9.7` block.
- [x] `shell.js` — section 10 (overflow-aware Expand toggle); docstring update.
- [x] test files — amend copy/markup assertions; add the two new cases.

**Acceptance Criteria:**
- Given `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, when done, then all pass.
- Given the Style Guide list/view/editor, when rendered, then no `<pre>` remains, the editor shows the info banner, and save/history/no-version behavior is unchanged.
- Given the Corpus list, when rendered, then each entry clamps with a working Expand control and composition counts show, Epic 7 behavior unchanged.
- Given every existing `/style-guide/*` and `/corpus*` status-code/404/redirect test, when done, then they still pass unchanged.

## Spec Change Log

## Design Notes

**Why the clamp lives in `shell.js`, not `<details>`.** Payload sections and Style Guide history (Story 9.6) use `<details>`/`<summary>` because "collapsed" there means fully hidden. A Corpus entry's collapsed state is a 6-line preview, not zero — `<details>` has no native partial reveal, and duplicating the text in `<summary>` and body would double-announce it on expand. One `<p>` toggled by a class avoids that and keeps full text in the DOM even with JS off.

## Verification

**Commands:**
- `uv run pytest tests/test_http_style_guide.py tests/test_http_corpus.py` — expected: green.
- `uv run pytest` — expected: full suite green.
- `uv run ruff check .` && `uv run ruff format --check .` — expected: clean.

**Manual checks:**
- Load `/style-guide` and `/style-guide/edit`: confirm current block, styled history table, no `<pre>`, and the info banner.
- Load `/corpus` with long/short and paired/unpaired entries: short entries show no Expand; long ones clamp and toggle; badges/counts correct.
- With JS off: Corpus entries stay clamped but text is present in view-source.

## Suggested Review Order

**The Corpus clamp/expand interaction (the only genuinely new behavior)**

- Entry point — the clamped text and its Expand control, wired to each other via `aria-controls`.
  [`corpus_list.html:29`](../../shell/http/templates/corpus_list.html#L29)

- The 6-line clamp itself and its `.is-expanded` override — CSS-only truncation, no content lost.
  [`tokens.css:1507`](../../shell/http/static/tokens.css#L1507)

- The overflow-aware reveal and toggle logic — why this isn't `<details>` (see Design Notes).
  [`shell.js:691`](../../shell/http/static/shell.js#L691)

- Composition line and paired/unpaired badges, restyled and re-labelled.
  [`corpus_list.html:11`](../../shell/http/templates/corpus_list.html#L11)

**The Style Guide readable-prose swap**

- `<pre>` → `.prose`, the core "readable, not `<pre>`" fix for the historical view.
  [`style_guide_view.html:11`](../../shell/http/templates/style_guide_view.html#L11)

- The new info banner warning that saving forks a version, plus the restyled form.
  [`style_guide_edit.html:16`](../../shell/http/templates/style_guide_edit.html#L16)

- Current-version block and the `.list-panel` history table replacing the plain list.
  [`style_guide_list.html:17`](../../shell/http/templates/style_guide_list.html#L17)

**Tests**

- New: a short entry's Expand control stays hidden; a long entry's content survives verbatim server-side.
  [`test_http_corpus.py:608`](../../tests/test_http_corpus.py#L608)

- New: the historical Style Guide view carries no `<pre>` anywhere.
  [`test_http_style_guide.py:179`](../../tests/test_http_style_guide.py#L179)
