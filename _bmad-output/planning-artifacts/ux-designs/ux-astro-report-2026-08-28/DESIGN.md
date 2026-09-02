---
name: astro-report
description: Visual identity for astro-report — a single-operator internal console (Italian UI) for natal charts, monthly transits, and grounded eight-section Italian reports. Deep-indigo on white, Inter, airy for reading and forms, compact for lists. Light and dark authored.
status: final
updated: 2026-09-02
sources:
  - ../../architecture/architecture-astro-report-2026-08-14/ARCHITECTURE-SPINE.md
colors:
  # Light theme. Dark values carry a `-dark` suffix; the token model is CSS
  # custom properties, swapped under [data-theme="dark"] and
  # @media (prefers-color-scheme: dark).
  surface-base: '#FFFFFF'
  surface-sunken: '#F6F5FA'
  surface-raised: '#FFFFFF'
  surface-nav: '#F7F6FB'
  ink-primary: '#141221'
  ink-secondary: '#585472'
  ink-tertiary: '#8A85A0'
  ink-disabled: '#B7B2C6'
  ink-on-primary: '#FFFFFF'
  border-hairline: '#E6E3F0'
  border-strong: '#CFC9E0'
  primary-50: '#F5F3FA'
  primary-100: '#EBE7F5'
  primary-200: '#D5CCEC'
  primary-300: '#B3A4DB'
  primary-400: '#8F79C6'
  primary-500: '#6F52B0'
  primary-600: '#573A97'
  primary-700: '#42297A'
  primary-800: '#341F60'
  primary-900: '#241542'
  primary-950: '#170D2C'
  link: '#5B3FA0'
  focus-ring: '#8F79C6'
  success: '#1F7A4D'
  success-surface: '#E7F4EC'
  warning: '#B45309'
  warning-surface: '#FBF0E1'
  danger: '#B42318'
  danger-surface: '#FBEBE9'
  info: '#42297A'
  info-surface: '#EBE7F5'
  # Dark theme
  surface-base-dark: '#161320'
  surface-sunken-dark: '#100E18'
  surface-raised-dark: '#211C2E'
  surface-nav-dark: '#1B1726'
  ink-primary-dark: '#ECE9F4'
  ink-secondary-dark: '#A9A2BC'
  ink-tertiary-dark: '#7B7590'
  ink-disabled-dark: '#5A5570'
  ink-on-primary-dark: '#F5F3FA'
  border-hairline-dark: '#322B44'
  border-strong-dark: '#463D5E'
  primary-300-dark: '#B3A4DB'
  primary-400-dark: '#8F79C6'
  primary-500-dark: '#6F52B0'
  primary-600-dark: '#7A5FC0'
  primary-700-dark: '#8F79C6'
  link-dark: '#B3A4DB'
  focus-ring-dark: '#B3A4DB'
  success-dark: '#34D399'
  success-surface-dark: '#10331F'
  warning-dark: '#FBBF24'
  warning-surface-dark: '#3A2A0A'
  danger-dark: '#F87171'
  danger-surface-dark: '#3A1512'
  info-dark: '#8F79C6'
  info-surface-dark: '#241542'
typography:
  # Inter for everything; system monospace for identifiers, hashes, month
  # codes and ephemeris identity. Scale is fixed-step, not fluid.
  display:
    fontFamily: 'Inter'
    fontSize: 28px
    fontWeight: '700'
    lineHeight: '34px'
    letterSpacing: -0.01em
  title:
    fontFamily: 'Inter'
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '28px'
    letterSpacing: -0.005em
  heading:
    fontFamily: 'Inter'
    fontSize: 16px
    fontWeight: '600'
    lineHeight: '22px'
  body:
    fontFamily: 'Inter'
    fontSize: 15px
    fontWeight: '400'
    lineHeight: '23px'
  body-read:
    fontFamily: 'Inter'
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '28px'
  label:
    fontFamily: 'Inter'
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '20px'
  small:
    fontFamily: 'Inter'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '18px'
  mono:
    fontFamily: 'ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '18px'
rounded:
  sm: 6px      # inputs, chips, table-row hover target
  md: 10px     # buttons, cards, banners
  lg: 14px     # panels, modals, the report reading sheet
  xl: 20px     # large empty-state containers
  full: 9999px # pills, status dots, the theme toggle
spacing:
  # 4px base. Named steps; components reference these, never raw px.
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  base: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  xxxl: 64px
components:
  app-shell:
    sidebar-width: 240px
    content-pad: '{spacing.xl}'
    content-pad-narrow: '{spacing.base}'
    background: '{colors.surface-base}'
  sidebar:
    background: '{colors.surface-nav}'
    border-right: '1px solid {colors.border-hairline}'
    item-radius: '{rounded.sm}'
  sidebar-item-active:
    background: '{colors.primary-100}'
    foreground: '{colors.primary-700}'
    marker: '3px solid {colors.primary-700}'  # left edge
  sidebar-item-hover:
    background: '{colors.primary-50}'
    foreground: '{colors.ink-primary}'
  page-header:
    border-bottom: '1px solid {colors.border-hairline}'
    padding: '{spacing.lg} {spacing.xl}'
    sticky: true
  button-primary:
    background: '{colors.primary-700}'
    foreground: '{colors.ink-on-primary}'
    radius: '{rounded.md}'
    padding: '10px 16px'
    hover-background: '{colors.primary-600}'
    active-background: '{colors.primary-800}'
  button-secondary:
    background: '{colors.surface-base}'
    foreground: '{colors.primary-700}'
    border: '1px solid {colors.border-strong}'
    radius: '{rounded.md}'
    hover-background: '{colors.primary-50}'
  button-ghost:
    background: 'transparent'
    foreground: '{colors.ink-secondary}'
    hover-background: '{colors.surface-sunken}'
    radius: '{rounded.md}'
  button-danger:
    background: '{colors.danger}'
    foreground: '#FFFFFF'
    radius: '{rounded.md}'
  input:
    background: '{colors.surface-base}'
    border: '1px solid {colors.border-strong}'
    radius: '{rounded.sm}'
    padding: '9px 12px'
    focus-border: '{colors.primary-500}'
    focus-ring: '0 0 0 3px {colors.primary-100}'
    invalid-border: '{colors.danger}'
  card:
    background: '{colors.surface-raised}'
    border: '1px solid {colors.border-hairline}'
    radius: '{rounded.md}'
    padding: '{spacing.lg}'
    shadow: 'none'
  panel:
    background: '{colors.surface-raised}'
    border: '1px solid {colors.border-hairline}'
    radius: '{rounded.lg}'
    padding: '{spacing.xl}'
  table-row:
    height: 40px
    padding-x: '{spacing.md}'
    border-bottom: '1px solid {colors.border-hairline}'
    hover-background: '{colors.surface-sunken}'
  badge:
    radius: '{rounded.full}'
    padding: '2px 10px'
    font: '{typography.small}'
  badge-mono:              # entry IDs, hashes, month codes
    radius: '{rounded.sm}'
    padding: '1px 6px'
    background: '{colors.surface-sunken}'
    foreground: '{colors.ink-secondary}'
    font: '{typography.mono}'
  banner:
    radius: '{rounded.md}'
    padding: '{spacing.md} {spacing.base}'
    border-left: '3px solid'   # color per severity token
  toast:
    background: '{colors.surface-raised}'
    border: '1px solid {colors.border-hairline}'
    radius: '{rounded.md}'
    shadow: '0 8px 24px rgba(20, 18, 33, 0.12), 0 2px 6px rgba(20, 18, 33, 0.08)'
    width: 360px
  modal:
    background: '{colors.surface-raised}'
    radius: '{rounded.lg}'
    shadow: '0 8px 24px rgba(20, 18, 33, 0.12), 0 2px 6px rgba(20, 18, 33, 0.08)'
    width: 480px
    scrim: 'rgba(20, 18, 33, 0.45)'
  stage-track:              # ReportRun progress: natal → transits → payload → draft → gate → export
    dot-pending: '{colors.border-strong}'
    dot-active: '{colors.primary-700}'
    dot-done: '{colors.success}'
    dot-failed: '{colors.danger}'
    connector: '{colors.border-hairline}'
  skeleton:
    base: '{colors.surface-sunken}'
    sheen: '{colors.primary-50}'
  report-sheet:            # the eight-section reading view
    background: '{colors.surface-raised}'
    max-width: 720px
    border: '1px solid {colors.border-hairline}'
    radius: '{rounded.lg}'
    padding: '{spacing.xxl}'
    body: '{typography.body-read}'
  focus-visible:
    outline: '2px solid {colors.focus-ring}'
    outline-offset: '2px'
    radius: 'inherit'
---

## Brand & Style

astro-report is a private instrument, not a product with an audience. Exactly one
person signs in (ARCHITECTURE-SPINE.md AD-15), and everything they do — recording a
client, verifying a chart wheel, driving a report run, reading eight sections of
Italian prose, exporting a PDF, running a backup — is careful, low-frequency,
consequence-bearing work done at a desk. The visual identity serves that: **calm,
literate, and exact**. It should feel closer to a well-set reference document or a
scientific console than to a SaaS dashboard.

Three commitments:

- **Deep indigo on white.** One brand hue — `#42297A` — anchors the whole system:
  headings, primary actions, the active nav item, the progress track. It is grave
  rather than bright. No second brand color; semantic colors (success / warning /
  danger) are the only other chroma, and they earn their place by meaning.
- **Inter, set with air.** A single typeface across the console. Reading surfaces
  (the report, the Style Guide, corpus text) get generous line-height and a narrow
  measure; list surfaces get tight rows. The contrast between those two rhythms is
  deliberate and is the main compositional device.
- **Restraint as the default.** Hairline borders instead of shadows for structure;
  elevation only for things that float (toasts, modals, popovers). No gradients, no
  decorative iconography, no filled illustration. White space does the work.

Anti-references: the current interface (sixteen unstyled island pages, raw JSON
dumps, no feedback on save) and the generic violet-gradient astrology aesthetic.
The rhythm reference is `matricedeldestino.it` — its Inter-on-white, its 4px
spacing discipline, its airy centred reading column — but cooler and more sober in
hue, and denser wherever the operator is scanning rather than reading.

**Language.** Every visible string is **Italian** — there is no English in the UI
and no language switch. The document is `<html lang="it">` so the native `date`
and `time` controls render in Italian format (`gg/mm/aaaa`, 24-hour `hh:mm`); all
other displayed dates are `dd/MM/yyyy`, times `HH:mm`, timestamps
`dd/MM/yyyy HH:mm`. Identifiers (`YYYY-MM` month codes, hashes, UUIDs) are the
only Latin-alphanumeric strings on screen and always carry the `badge-mono`
treatment. The Italian label for every surface and every microcopy string is
specified in `EXPERIENCE.md` → Voice and Tone.

## Colors

Visual reference: [`mockups/color-themes-1.html`](mockups/color-themes-1.html) —
the full ramp, semantics, and a realistic snippet in light and dark. On any
conflict between a mock and this spine, the spine wins.

**One brand ramp.** `primary-50 … primary-950` is a single indigo-violet hue
(~254°) stepped in lightness. `primary-700` (`#42297A`) is the anchor: primary
button fill, `h1`/`h2` color, active sidebar item text and its 3px left marker, the
active dot on the stage track. `primary-600` is the primary-button hover;
`primary-800` the pressed state. `primary-50`/`primary-100` are the only tints used
as fills (nav hover, active-item background, info banner, input focus ring).

- **`link` (`#5B3FA0`)** — inline text links only. Distinct from `primary-700` so a
  link inside a heading is still legible. Underlined by default, not on color alone.
- **`ink-primary` (`#141221`)** on `surface-base` — 15.8:1. Body copy, table cells,
  form values.
- **`ink-secondary` (`#585472`)** — 7.4:1. Labels, metadata, helper text, the
  timestamp column. Never below 13px.
- **`ink-tertiary` (`#8A85A0`)** — 4.6:1. Placeholder text, disabled-adjacent hints,
  the connector labels on the stage track. Never load-bearing.
- **`border-hairline` (`#E6E3F0`)** — the default separator: table rows, card
  edges, the sidebar's right edge, the page-header underline.
- **`border-strong` (`#CFC9E0`)** — input borders and secondary-button outlines,
  where the edge must read as interactive.

**Semantic colors** each pair a foreground with a `-surface` tint for banners and
badges, and appear in exactly these roles:

| Token | Meaning in this app | Where it shows |
|---|---|---|
| `success` | a run reached `exported`; a backup completed; a form saved | toast, stage-track done dot, disposition confirmation |
| `warning` | something is stale but not broken | **backup-stale** banner (global), **config-stale** chart banner, **superseded-chart** marker |
| `danger`  | a run failed the Gate or errored; a destructive confirm | Gate-failure panel, delete/supersede modals, field errors |
| `info`    | neutral procedural note | "saving creates a new version" on the Style Guide editor |

Dark theme keeps the same roles. Surfaces go to near-black with a violet cast
(`surface-base-dark #161320`, `surface-raised-dark #211C2E`); the brand hue lifts
to `primary-400`/`primary-300` for interactive text and dots so it stays legible on
dark; semantic foregrounds brighten (`success #34D399`, `danger #F87171`, etc.).
Shadows are near-invisible on dark — separation comes from the raised surface being
lighter than the base, plus `border-hairline-dark`.

Avoid: any hue outside the indigo ramp and the four semantics; color as the only
signal for state (always pair with text or an icon-shape); tinted surfaces larger
than a banner or a card; pure `#000` or pure white text on dark.

## Typography

**Inter** for all UI and reading text. **System monospace** for anything that is an
identifier and must not be misread: Report Payload entry IDs, the ephemeris SHA
identity, `computation.toml` / sections / vocabulary version hashes, `YYYY-MM` month
codes, UUIDs. Monospace runs get the `badge-mono` chip treatment when inline.

Fixed nine-role scale (no fluid sizing):

| Role | Size / line-height / weight | Used for |
|---|---|---|
| `display` | 28 / 34 / 700 | page title (`h1`), one per screen |
| `title` | 20 / 28 / 600 | section headers (`h2`), card group titles, modal titles |
| `heading` | 16 / 22 / 600 | `h3`, table-group headers, the eight Section titles in the report sheet |
| `body` | 15 / 23 / 400 | default UI text, table cells, form values |
| `body-read` | 16 / 28 / 400 | report prose, Style Guide content, corpus entry text |
| `label` | 14 / 20 / 600 | form labels, column headers, badge text |
| `small` | 13 / 18 / 400 | timestamps, helper text, stage connector captions, empty-state sublines |
| `mono` | 13 / 18 / 400 | identifiers and hashes |

The report reading sheet uses `body-read` at a 720px measure with `heading` for the
eight Section titles and a 32px gap between Sections — this is the one place the
type is set for sustained reading. Everywhere else, `body` at 15px.

## Layout & Spacing

**4px base**, named steps `xxs 2 · xs 4 · sm 8 · md 12 · base 16 · lg 24 · xl 32 ·
xxl 48 · xxxl 64`. Components reference the names.

**App shell:** a fixed **240px sidebar** (`surface-nav`, hairline right border) and a
content column. The sidebar carries the app name, the five top-level areas, a
theme toggle, and **Sign out pinned to the bottom**. Below **900px** the sidebar
leaves the flow and becomes an off-canvas drawer opened from a header menu button;
below **768px** is best-effort (single operator, desktop-primary).

**Content column:** padded `xl` (32px), dropping to `base` (16px) under 1200px. A
sticky **page header** inside it holds the breadcrumb, the `h1`, and the screen's
one primary action, over a hairline underline.

**Measure by context — the density split:**

| Context | Max width | Rhythm |
|---|---|---|
| Lists / tables (Clients, report history, corpus index, Style Guide history) | 1120px, full-bleed rows | compact: 40px rows, `md` cell padding, hairline dividers, no card per row |
| Forms (new/correct Client, start run, Style Guide editor, corpus intake) | 560px | airy: `lg` (24px) between fields, label above input, helper text below |
| Report reading sheet | 720px | airy: `body-read`, 32px between Sections |
| Payload / draft / Gate views | 960px | structured: disclosure sections, `base` padding, mono chips for IDs |
| Dashboard (Home) | 1120px | cards in a 2–3 column grid, `lg` gutters |

## Elevation & Depth

Structure is drawn with **hairline borders and surface tints**, not shadow.
Elevation is reserved for genuinely floating layers:

| Level | Shadow | Applies to |
|---|---|---|
| flat | none — `border-hairline` instead | cards, panels, table, sidebar, page header |
| overlay | `0 8px 24px rgba(20,18,33,.12), 0 2px 6px rgba(20,18,33,.08)` | toasts, modal, dropdown/select menu, popover |

No hover-elevation on cards. No z-layered stacking beyond one overlay level plus
the modal scrim (`rgba(20,18,33,.45)`). On dark, overlay shadows are kept but do
almost nothing visually — the raised surface color carries the separation.

## Shapes

| Token | Radius | Applies to |
|---|---|---|
| `sm` | 6px | inputs, select, textarea, mono chips, row hover target |
| `md` | 10px | buttons, cards, banners, badges-as-buttons |
| `lg` | 14px | panels, modal, the report sheet |
| `xl` | 20px | large empty-state containers |
| `full` | 9999px | status pills, the stage-track dots, the theme toggle knob |

Consistent, not tight and not soft. Pills are only for status badges and small
binary toggles — never for buttons that perform an action.

## Components

Visual specs for the token set are in the frontmatter `components` map. Notes on
the ones specific to this app (behavior lives in EXPERIENCE.md):

- **Sidebar nav item** — `sm` radius, `label`-weight text. Hover: `primary-50`
  fill. Active: `primary-100` fill, `primary-700` text, a 3px `primary-700` marker
  on the left edge. Exactly one active at a time.
- **Button** — four variants: `primary` (indigo fill, the one per-screen main
  action), `secondary` (outline, indigo text), `ghost` (chromeless, for tertiary
  actions and table-row actions), `danger` (solid `danger`, only inside a confirm
  modal). Height 38px, `md` radius, `label` text. Disabled = `ink-disabled` text on
  `surface-sunken`, no border.
- **Input / Select / Textarea** — `border-strong` 1px, `sm` radius, label always
  above (never placeholder-as-label). Focus: `primary-500` border + 3px
  `primary-100` ring. Invalid: `danger` border, error text below in `small`/`danger`
  with `aria-describedby`. The `date` and `time` inputs keep **native pickers**,
  which inherit `lang="it"` and so present `gg/mm/aaaa` / 24-hour `hh:mm` with
  Italian month names — do not replace them with a custom date widget.
- **Candidate picker** — the birthplace-disambiguation radio group. `fieldset` with
  a `legend`, each option a full-width row with generous hit area; selected row gets
  a `primary-50` fill and `primary-700` left marker.
- **Table / list row** — 40px, `body` text, hairline bottom border, `surface-sunken`
  hover. No per-row card. Row-level actions are `ghost` buttons revealed on hover
  and always present to keyboard focus. A "timestamp" column is `ink-secondary`
  `small`.
- **Card** — `md` radius, hairline border, no shadow, `lg` padding. Used on the
  dashboard and to group a form section.
- **Panel** — `lg` radius, `xl` padding. The Gate-failure container, the payload
  disclosure container, the chart-wheel frame.
- **Badge** — pill, `small` text. Status badges: `success-surface`/`success` for
  *exported*, `warning-surface`/`warning` for *superseded* / *stale* / **"Superato
  con N eccezioni"** (a Report completed via Story 5.7's accepted-violation
  closure, `accepted_violation_count > 0` — correct-course 2026-09-02), `danger-
  surface`/`danger` for *failed*, `primary-100`/`primary-700` for *in progress*,
  `surface-sunken`/`ink-secondary` for *draft* / neutral. Badges **stack**, they
  don't replace each other, when more than one independent concern applies to
  the same row — e.g. *esportato* (status) beside *superato* (chart-supersession
  warning) or beside *"Superato con N eccezioni"* (Gate-exception warning); see
  `key-home.html`'s "Esposito Sara" row and *Report Run Lifecycle* /
  *Per-violation review actions* in EXPERIENCE.md.
- **Mono chip (`badge-mono`)** — `sm` radius, `surface-sunken` fill, monospace. Every
  entry ID, hash, version and `YYYY-MM` code renders as one; click-to-copy.
- **Banner (inline alert)** — `md` radius, 3px left border in the severity color,
  `-surface` tint fill, icon-shape + text + optional single action link. The
  **backup-stale** banner is `warning` and sits at the top of the content column on
  every screen while stale. The **config-stale** and **superseded-chart** banners
  are `warning` and scoped to the chart / client they concern.
- **Toast** — 360px, overlay shadow, top-right, stacks downward (newest on top, max
  3 visible). `success` auto-dismisses at ~5s; `danger`/`warning` persist until
  dismissed. Renders into an `aria-live` region.
- **Modal / confirm dialog** — 480px, `lg` radius, scrim, focus-trapped. Title in
  `title`, body in `body`, actions right-aligned (`secondary` cancel +
  `primary`/`danger` confirm). Destructive confirms (delete Client, supersede
  chart) state the consequence in full and put the irreversible action on `danger`.
- **Stage track** — the ReportRun lifecycle as a horizontal six-node track: `natal
  → transits → payload → draft → gate → export`
  ([`mockups/key-run-stage.html`](mockups/key-run-stage.html), both states).
  Nodes are `full` dots connected by
  1px `border-hairline`; pending = `border-strong`, active = `primary-700` (with a
  gentle pulse, suppressed under `prefers-reduced-motion`), done = `success`,
  failed = `danger`. A caption under each node in `small`.
- **Skeleton** — `surface-sunken` blocks with a slow `primary-50` sheen for page and
  section loads. Used when structure is known; a centered **spinner** is used when
  it is not (a single indeterminate action).
- **Report sheet** — `lg` radius, `surface-raised`, 720px, `xxl` (48px) padding,
  `body-read`. `heading`-weight Section titles with a 32px gap. A left-rail or
  top in-page nav lists the eight Sections and scroll-spies the active one.
  ([`mockups/key-report-sheet.html`](mockups/key-report-sheet.html)).
- **Empty state** — `xl`-radius container, `surface-sunken`, a one-line `body`
  statement of what is absent and a single primary action ("Add the first one").
- **Breadcrumb** — `small`, `ink-secondary`, `/` separators, last crumb
  non-interactive `ink-primary`.
- **Contextual tabs** — the Record / Chart / Reports row under a Client. Underline
  style: active tab has a 2px `primary-700` bottom border, `primary-700` text.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `primary-700` for one hue across headings, primary actions, active nav, stage track | Introduce a second brand color, or use gradients |
| Draw structure with hairline borders and `surface-sunken` tints | Use drop shadows on cards or as a hierarchy device |
| Keep lists compact (40px rows) and reading surfaces airy (`body-read`, 720px) | Apply one uniform density everywhere |
| Render every ID / hash / month code as a monospace chip | Set identifiers in the body font where they can be misread |
| Pair every state color with text or an icon-shape | Signal *superseded* / *failed* / *stale* with color alone |
| Put destructive actions on `danger` inside a focus-trapped modal that names the consequence | Rely on a bare confirm page with a single unlabeled button |
| Give the backup-stale warning a persistent global banner | Hide staleness on one deep screen (as the current UI does) |
| Reserve elevation for toasts, modals, menus, popovers | Stack more than one overlay level |
| Respect `prefers-color-scheme` and offer a manual toggle in the sidebar | Ship a dark theme that only swaps background and text |
| Keep every visible string Italian; set `dd/MM/yyyy` / `HH:mm` and `lang="it"` | Leave English chrome, or build a custom date widget over the native pickers |
