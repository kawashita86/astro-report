---
title: 'Style the sentence_text correction textarea'
type: 'chore'
created: '2026-09-15'
status: 'done'
route: 'one-shot'
---

# Style the sentence_text correction textarea

## Intent

**Problem:** In `report_draft.html`'s "Modifica e ricontrolla" hand-correction form, the `sentence_text` textarea had no styling — too narrow to comfortably read or edit a violation's full sentence — and its submit button sat beside it via the browser's default inline layout instead of below it.

**Approach:** Add a `.violation-card__textarea` class (full-width, multi-line, reusing the existing `.field input`/`.field select` box styling and focus ring) and a `.violation-card__correct-form` flex-column wrapper so the "Ricontrolla" button stacks below the textarea.

## Suggested Review Order

**Textarea sizing and styling**

- Shares the `.field input`/`.field select` box styling (width, padding, colors, border, focus ring) via a combined selector instead of duplicating it, then overrides only `min-height`/`resize` for multi-line editing.
  [`tokens.css:1005`](../../shell/http/static/tokens.css#L1005)

- Textarea-specific overrides: taller `min-height` and vertical resize handle.
  [`tokens.css:1486`](../../shell/http/static/tokens.css#L1486)

**Button placement**

- Flex-column wrapper stacks the form's children (textarea, then button) instead of the browser's default inline flow.
  [`tokens.css:1479`](../../shell/http/static/tokens.css#L1479)

- Keeps the submit button left-aligned rather than stretching full-width under the flex column.
  [`tokens.css:1491`](../../shell/http/static/tokens.css#L1491)

**Template wiring**

- Applies the new classes to the existing form/textarea markup; no structural or behavioral change.
  [`report_draft.html:48`](../../shell/http/templates/report_draft.html#L48)
