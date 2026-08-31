---
title: 'Story 9.1 amendment — sign-in screen centring and mark'
type: 'feature'
created: '2026-08-31'
status: 'done'
review_loop_iteration: 1
route: 'one-shot'
context:
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '/home/francesco/PhpstormProjects/astro-report/_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-31.md'
---

## Intent

**Problem:** The sign-in screen's `.auth-view` rule only centred its column horizontally with top padding — no vertical centring, no branding mark — and it was the only form in the app whose password input never got the shared `.field` styling. Not a defect (`DESIGN.md` never specified a login mark); new scope from the correct-course pass.

**Approach:** Turn `.auth-view` (the `<main>` itself) into a flex container centring an `.auth-view__card` both axes; add a small decorative inline SVG mark (a ringed circle, on-theme for an astrology tool, built only from existing brand-ramp tokens); wrap the password field in `.field` and style the submit button with `.btn btn--primary`, matching every other form in the app.

## Suggested Review Order

**Layout**

- Entry point — the centring rule and its specificity fix (`.app-main > main` already sets `padding` with higher specificity than a bare `.auth-view` class would).
  [`tokens.css:291`](../../shell/http/static/tokens.css#L291)

- The card and mark styling.
  [`tokens.css:299`](../../shell/http/static/tokens.css#L299)

**Markup and the focus/no-JS fix**

- `login.html` — the card, the decorative mark, and the conditional `autofocus`/`aria-invalid`/`aria-describedby` wiring on the error branch.
  [`login.html:1`](../../shell/http/templates/login.html#L1)

- `shell.js`'s banner-focus comment, updated to name `login.html` as a fourth consumer and explain why the field drops `autofocus` there instead of relying on script timing.
  [`shell.js:512`](../../shell/http/static/shell.js#L512)

**Tests**

- Centring/mark markup, `.field` styling, the autofocus-on-fresh-visit vs. autofocus-dropped-and-linked-to-error split.
  [`test_http_app.py:343`](../../tests/test_http_app.py#L343)

## Spec Change Log

- review-loop 1 (blind-hunter): fixed a real CSS specificity bug — the original `.auth-view { padding: ...; }` rule was silently overridden by the pre-existing higher-specificity `.app-main > main { padding: var(--content-pad); }`, so the intended padding never rendered (vertical/horizontal centring itself was unaffected, since those properties aren't touched by the conflicting rule). Removed a redundant `margin-bottom` declaration that duplicated `.banner`'s own default. Marked the SVG mark decorative (`aria-hidden="true"`, dropped `role="img"`/`aria-label`) rather than named content, since the adjacent `<h1>`/`<title>` already state the page's purpose. Dropped `autofocus` from the password field on the error re-render (it previously always carried `autofocus`, which would race — and for a no-JS visitor, always beat — `shell.js`'s focus-into-banner behavior, silently skipping the error message) and linked the field to the error banner via `aria-invalid`/`aria-describedby`, matching `client_new.html`/`client_edit.html`'s existing invalid-field pattern. Deferred: `forced-colors`/Windows High-Contrast support for the new mark (an app-wide gap this story's decorative SVG inherits rather than introduces).
