---
title: 'Reduce the poll-failure retry backoff to 1-2 seconds'
type: 'chore'
created: '2026-09-14'
status: 'done'
review_loop_iteration: 0
route: 'one-shot'
---

## Reduce the poll-failure retry backoff to 1-2 seconds

## Intent

**Problem:** Story 9.8's poll-failure backoff (`shell/http/static/shell.js`) waited 5s after the
first consecutive poll failure and 15s from the second onward before the stage-track view's
automatic `every 2s` HTMX tick was allowed through again. Francesco found this too slow relative to
the already-long wait for report generation itself.

**Approach:** Reduce `POLL_BACKOFF_MS_FIRST` from 5000 to 1000 and `POLL_BACKOFF_MS_SUBSEQUENT` from
15000 to 2000, so the automatic retry gate never withholds a tick for more than 1-2 seconds. Update
the two prose comments (module header docstring and the inline constant comment) that documented the
old 5s/15s numbers so they stay accurate. Purely a constants-and-comments change — no behavior other
than the timing values, no test exists on these values to update (confirmed: no JS test harness in
this repo), and no architecture, epic, or PRD document references these specific numbers.

## Suggested Review Order

- Backoff delay shortened from 5s/1st-failure, 15s/subsequent to 1s/1st-failure, 2s/subsequent.
  [`shell.js:529`](../../shell/http/static/shell.js#L529)

- Matching prose comment above the constants updated to the new numbers.
  [`shell.js:527`](../../shell/http/static/shell.js#L527)

- Module header docstring (job 6's description) updated to match.
  [`shell.js:51`](../../shell/http/static/shell.js#L51)
