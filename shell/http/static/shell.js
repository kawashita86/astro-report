/*
 * astro-report application-shell behaviour — first-party, no dependencies.
 *
 * Thirteen jobs, all progressive enhancements over a shell that already
 * works without JavaScript:
 *
 *   1. Theme toggle — flip `data-theme` on <html>, persist the choice to
 *      localStorage (wrapped in try/catch: a private window or blocked storage
 *      must silently fall back to `prefers-color-scheme`). The pre-paint
 *      snippet in base.html's <head> re-applies the stored choice before the
 *      stylesheet paints, so there is no flash.
 *
 *   2. Off-canvas drawer (<900px) — open from the header menu button, trap
 *      focus while open (via `trapFocus`, job 0 below), close on Esc or scrim
 *      click, and restore focus to the trigger on close.
 *
 *   3. Clienti list filter — client-side, name-only, case-insensitive. Typing
 *      in `[data-client-filter]` hides non-matching `[data-client-row]`s, keeps
 *      `[data-client-count]` at `{shown} di {total}`, and swaps the table for
 *      an inline no-match line when nothing matches. No server round-trip.
 *
 *   4. Delete-confirm modal (Story 9.4) — intercept the `[data-delete-client]`
 *      trigger on the Anagrafica screen, open the inline `[data-delete-modal]`
 *      instead of navigating, trap focus (via `trapFocus`) with initial focus
 *      on `Annulla` (`[data-delete-cancel]`), close on Esc / scrim click /
 *      cancel and restore focus to the trigger. The `danger` submit
 *      (`[data-delete-submit]`) stays disabled until the trimmed
 *      `[data-delete-confirm]` value exactly equals the modal's
 *      `data-client-name` (both sides trimmed). Opening the modal closes the
 *      drawer and makes the rest of the page `inert` / `aria-hidden`; closing
 *      it clears the typed value, re-disables the submit, undoes the inerting,
 *      and restores focus to the trigger. The route contract is untouched —
 *      the no-JS path is the restyled `GET /clients/{id}/delete` page.
 *
 *   5. Form-level error summary — on a 422 re-render, move focus to the
 *      focusable `role="alert"` `.banner--danger` so a keyboard / screen
 *      reader user lands on the error.
 *
 *   6. Report-run stage view (Story 9.5, extended by Story 9.8) — pause the
 *      `#run-status` HTMX poll while the tab is hidden (`document.hidden`),
 *      so a backgrounded tab never spends a request; reveal the inline
 *      `[data-poll-error]` `role="alert"` banner on `htmx:responseError` /
 *      `htmx:sendError` from that region, and hide it again once a poll
 *      succeeds. The polling cadence and stop condition are still
 *      server-driven (the `hx-*` attributes render only while `poll_active`
 *      is true, `shell/http/templates/report_run_poll.html`) — this job
 *      only pauses/resumes the already-present `every 2s` trigger; it
 *      starts no timer of its own.
 *
 *      Story 9.8 adds backoff on top: each consecutive poll failure gates
 *      the *next automatic* tick behind a growing delay (5s after the 1st
 *      failure, 15s after the 2nd and every one after that) by vetoing
 *      `htmx:beforeRequest` for ticks that land before that gate opens —
 *      the same `event.preventDefault()` shape the hidden-tab pause above
 *      already uses, never a change to the `every 2s` attribute itself
 *      (AD-20's server semantics, and `report_run_poll.html`'s own polling
 *      cadence, are untouched). `[data-poll-retry]` (`Riprova`) appears once
 *      the 2nd failure lands and, on click, dispatches a `poll-retry` event
 *      on `document.body` — the extended `hx-trigger`
 *      (`every 2s, poll-retry from:body`) fires an immediate request for
 *      it, which this job's gate always lets through (an operator-requested
 *      retry is never itself throttled). A success resets the failure count
 *      and the gate, and hides `Riprova` again.
 *
 *   7. Regenerate-confirm modal (Story 9.5) — intercept the Gate-failure
 *      panel's `[data-regen-trigger]` button on `/draft`, open the inline
 *      `[data-regen-modal]` instead of submitting immediately, trap focus
 *      (via `trapFocus`) with initial focus on `Annulla`
 *      (`[data-regen-cancel]`), close on Esc / scrim click / cancel and
 *      restore focus to the trigger — no typed-name gate (Rigenera is a
 *      bounded recovery action, not a destroy). The no-JS path is the same
 *      panel's plain `<form method="post">`, already a working full-page
 *      submit before this script ever runs.
 *
 *   8. Click-to-copy mono chips (Story 9.6) — one delegated `click` listener
 *      on `document.body` for `.badge-mono[data-copy-chip]`: copies the
 *      chip's own text via `navigator.clipboard.writeText`, wrapped in a
 *      try/catch so a missing/blocked Clipboard API is a silent no-op, never
 *      a thrown error. On success the chip's text swaps to `Copiato` for
 *      ~1.5s, then reverts to the original text (stashed in a closure var,
 *      not a data-attribute, so a pending restore timer is cancelled before
 *      a rapid re-click starts a new one — no stale-state races). Every
 *      `.badge-mono` in the app — report/payload entry ids, the draft's
 *      violation-card chips, the dashboard's month codes — is wired by this
 *      one listener; no per-template JS. Native `<button>` markup gives
 *      keyboard operability (Enter/Space) for free.
 *
 *   9. Report-sheet scroll-spy (Story 9.6) — guarded on the presence of
 *      `[data-report-toc]` (only `report.html` has one): an
 *      `IntersectionObserver` watches every `.report-sheet section[id]` and
 *      toggles `.is-active` on the matching `.report-toc a[href="#…"]` as
 *      each Section crosses a top-anchored viewport band. Not gated by
 *      `prefers-reduced-motion` — this is a state toggle, not an animation;
 *      only the anchor links' own scroll is smoothed, via tokens.css's
 *      global `scroll-behavior: smooth` (itself turned back to `auto` under
 *      reduced motion). Without JS the `report-toc` links still work as
 *      plain in-page anchors — no highlighting, but every jump still lands.
 *
 *   10. Corpus clamp toggle (Story 9.7) — on load, reveal
 *      `[data-corpus-expand]` only where its paired `[data-corpus-text]` is
 *      actually clamped (`scrollHeight > clientHeight`); a short entry's
 *      button stays hidden, since the full text already fits. One delegated
 *      `click` listener on `document.body` for `[data-corpus-expand]`:
 *      toggles `.is-expanded` on the sibling text (found via
 *      `closest(".corpus-entry")`), flips the button's `aria-expanded`, and
 *      swaps its label Espandi ↔ Comprimi. Without JS every entry's full
 *      text stays in the DOM -- readable, selectable, screen-reader visible,
 *      just visually clamped to 6 lines with no toggle -- per the epic's
 *      "JS only upgrades ... in-place disclosure" rule.
 *
 *   11. Toast queue (Story 9.8) — `showToast(kind, message)` appends a
 *      `.toast` into `[data-toast-region]` (`base.html`, fixed to the
 *      viewport). FIFO-capped at 3: a 4th queued toast dismisses the oldest
 *      first. A `"success"` toast auto-dismisses after ~5s, pausing that
 *      timer on `mouseenter` and resuming the remaining time on
 *      `mouseleave`; `"warning"`/`"danger"` toasts never auto-dismiss and
 *      carry their own `.toast__close` button instead.
 *
 *   12. `[data-flash]` → toast promotion (Story 9.8) — on load, if the
 *      shared flash banner (`base.html`) is present, read its kind/message
 *      and hand them to `showToast` (job 11), then hide the plain banner —
 *      the JS-enhanced experience is the toast; without JS the banner
 *      itself is what's shown (still dismissible via a delegated click
 *      listener on every `.banner__dismiss`, this job's other half, which
 *      covers the flash banner and any other `.banner` that grows one).
 *
 *   13. Submit-button lock + spinner (Story 9.8) — on submit, every
 *      `[data-submit-lock]` form disables its own `button[type="submit"]`
 *      and gives it a `.spinner`, and marks every descendant `.field` both
 *      `aria-disabled` and locked via CSS `pointer-events: none` — never
 *      the native `disabled` attribute on a field itself, which would drop
 *      that field's value from the very submission already in flight. The
 *      lock is one-way for the lifetime of the page: a 422 re-render is a
 *      fresh page load, which starts unlocked again.
 *
 * All shell transitions are disabled by tokens.css under
 * `prefers-reduced-motion`; this file adds no scripted animation.
 */
(function () {
  "use strict";

  var root = document.documentElement;

  var FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  /* ---- 0. Shared focus trap ---------------------------------------------
   *
   * `trapFocus(container, { onEscape, initialFocus })` wires a capturing
   * `keydown` listener that cycles Tab/Shift+Tab within `container`'s own
   * focusable descendants and calls `onEscape` (if given) on Escape. Focus
   * lands on `initialFocus` if given, otherwise the container's first
   * focusable element. Returns a `release()` function that removes the
   * listener — the caller still owns hiding the container and restoring
   * focus to whatever triggered it; this helper only owns the trap itself.
   * Shared by the drawer (job 2), the delete-confirm modal (job 4) and the
   * regenerate-confirm modal (job 7) — extracted once a third consumer
   * appeared, per the Story 9.4 Design Notes.
   */
  function trapFocus(container, options) {
    options = options || {};
    var onEscape = options.onEscape;
    var initialFocus = options.initialFocus;

    function focusables() {
      return Array.prototype.filter.call(
        container.querySelectorAll(FOCUSABLE),
        function (el) {
          return el.offsetParent !== null || el === document.activeElement;
        }
      );
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (onEscape) {
          onEscape();
        }
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      var items = focusables();
      if (items.length === 0) {
        return;
      }
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeydown, true);

    var toFocus = initialFocus;
    if (!toFocus) {
      var items = focusables();
      toFocus = items.length > 0 ? items[0] : null;
    }
    if (toFocus && typeof toFocus.focus === "function") {
      toFocus.focus();
    }

    return function release() {
      document.removeEventListener("keydown", onKeydown, true);
    };
  }

  /* ---- 1. Theme toggle ------------------------------------------------- */

  function currentTheme() {
    var explicit = root.getAttribute("data-theme");
    if (explicit === "light" || explicit === "dark") {
      return explicit;
    }
    var prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    return prefersDark ? "dark" : "light";
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem("theme", theme);
    } catch (e) {
      /* storage unavailable — the choice lasts for this page only */
    }
    var toggle = document.querySelector("[data-theme-toggle]");
    if (toggle) {
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
    }
  }

  var themeToggle = document.querySelector("[data-theme-toggle]");
  if (themeToggle) {
    themeToggle.setAttribute(
      "aria-pressed",
      currentTheme() === "dark" ? "true" : "false"
    );
    themeToggle.addEventListener("click", function () {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  /* ---- 2. Off-canvas drawer (<900px) -------------------------------------- */

  var shell = document.querySelector("[data-app-shell]");
  var menuButton = document.querySelector("[data-nav-toggle]");
  var sidebar = document.querySelector("[data-app-sidebar]");
  var scrim = document.querySelector("[data-app-scrim]");

  var releaseDrawerTrap = null;

  function drawerOpen() {
    return !!shell && shell.classList.contains("is-drawer-open");
  }

  function openDrawer() {
    if (!shell || drawerOpen()) {
      return;
    }
    shell.classList.add("is-drawer-open");
    if (menuButton) {
      menuButton.setAttribute("aria-expanded", "true");
    }
    if (sidebar) {
      releaseDrawerTrap = trapFocus(sidebar, { onEscape: closeDrawer });
    }
  }

  function closeDrawer() {
    if (!shell || !drawerOpen()) {
      return;
    }
    shell.classList.remove("is-drawer-open");
    if (menuButton) {
      menuButton.setAttribute("aria-expanded", "false");
      menuButton.focus();
    }
    if (releaseDrawerTrap) {
      releaseDrawerTrap();
      releaseDrawerTrap = null;
    }
  }

  if (menuButton) {
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.addEventListener("click", function () {
      if (drawerOpen()) {
        closeDrawer();
      } else {
        openDrawer();
      }
    });
  }

  if (scrim) {
    scrim.addEventListener("click", closeDrawer);
  }

  // Resizing the viewport wide again (>=900px, where the sidebar is back in
  // the flow) must release a drawer left open: clear the focus trap, drop
  // `is-drawer-open`, and reset `aria-expanded`.
  if (window.matchMedia) {
    var wideQuery = window.matchMedia("(min-width: 900px)");
    var releaseWhenWide = function (event) {
      if (event.matches) {
        closeDrawer();
      }
    };
    if (wideQuery.addEventListener) {
      wideQuery.addEventListener("change", releaseWhenWide);
    } else if (wideQuery.addListener) {
      wideQuery.addListener(releaseWhenWide);
    }
  }

  /* ---- 3. Clienti list filter (client-side, name-only) ------------------- */

  var filterInput = document.querySelector("[data-client-filter]");
  if (filterInput) {
    var countRegion = document.querySelector("[data-client-count]");
    var listTable = document.querySelector("[data-client-table]");
    var noMatchLine = document.querySelector("[data-client-empty]");
    var rows = Array.prototype.slice.call(
      document.querySelectorAll("[data-client-row]")
    );
    var total = rows.length;

    var applyFilter = function () {
      var raw = filterInput.value;
      var needle = raw.trim().toLowerCase();
      var shown = 0;

      for (var i = 0; i < rows.length; i++) {
        var name = rows[i].dataset.name || "";
        var hit = needle === "" || name.indexOf(needle) !== -1;
        rows[i].hidden = !hit;
        if (hit) {
          shown++;
        }
      }

      if (countRegion) {
        countRegion.textContent = shown + " di " + total;
      }

      var noMatch = shown === 0 && needle !== "";
      if (listTable) {
        listTable.hidden = noMatch;
      }
      if (noMatchLine) {
        noMatchLine.hidden = !noMatch;
        if (noMatch) {
          noMatchLine.textContent =
            'Nessun cliente corrisponde a "' + raw.trim() + '".';
        }
      }
    };

    filterInput.addEventListener("input", applyFilter);

    // A value restored by bfcache / back-navigation is present before any
    // keystroke — run once now so the rows, the count, and the no-match line
    // always match the field's current contents.
    applyFilter();
  }

  /* ---- 4. Delete-confirm modal (Story 9.4) ------------------------------- */

  var deleteScrim = document.querySelector("[data-delete-modal]");
  if (deleteScrim) {
    var deleteTrigger = document.querySelector("[data-delete-client]");
    var deleteCancel = deleteScrim.querySelector("[data-delete-cancel]");
    var deleteSubmit = deleteScrim.querySelector("[data-delete-submit]");
    var deleteConfirmField = deleteScrim.querySelector("[data-delete-confirm]");
    var deleteReturnFocusTo = null;
    var releaseDeleteTrap = null;
    var expectedName = (deleteScrim.dataset.clientName || "").trim();

    var deleteModalOpen = function () {
      return !deleteScrim.hidden;
    };

    // Take the rest of the page out of the a11y tree / tab order while the
    // modal is open: `inert` where supported, `aria-hidden` as the fallback.
    // Everything except the modal scrim itself.
    var backgroundInertTargets = function () {
      var targets = [];
      var appSidebar = document.querySelector("[data-app-sidebar]");
      var header = document.querySelector(".app-header");
      if (appSidebar) {
        targets.push(appSidebar);
      }
      if (header) {
        targets.push(header);
      }
      var mainContent = document.getElementById("main-content");
      if (mainContent) {
        Array.prototype.forEach.call(mainContent.children, function (child) {
          if (child !== deleteScrim) {
            targets.push(child);
          }
        });
      }
      return targets;
    };

    var setBackgroundInert = function (on) {
      backgroundInertTargets().forEach(function (el) {
        if (on) {
          el.setAttribute("inert", "");
          el.setAttribute("aria-hidden", "true");
        } else {
          el.removeAttribute("inert");
          el.removeAttribute("aria-hidden");
        }
      });
    };

    var syncDeleteSubmit = function () {
      if (!deleteSubmit || !deleteConfirmField) {
        return;
      }
      // Typed-name gate: browser-only friction, never enforced server-side.
      deleteSubmit.disabled = deleteConfirmField.value.trim() !== expectedName;
    };

    var closeDeleteModal = function () {
      if (!deleteModalOpen()) {
        return;
      }
      deleteScrim.hidden = true;
      setBackgroundInert(false);
      if (releaseDeleteTrap) {
        releaseDeleteTrap();
        releaseDeleteTrap = null;
      }
      // Reset the friction: the next open starts from a blank field and a
      // disabled submit even if the operator typed the full name last time.
      if (deleteConfirmField) {
        deleteConfirmField.value = "";
      }
      if (deleteSubmit) {
        deleteSubmit.disabled = true;
      }
      if (
        deleteReturnFocusTo &&
        typeof deleteReturnFocusTo.focus === "function"
      ) {
        deleteReturnFocusTo.focus();
      }
      deleteReturnFocusTo = null;
    };

    var openDeleteModal = function () {
      if (deleteModalOpen()) {
        return;
      }
      // The <900px drawer's own capturing keydown trap must not compete with
      // the modal's — close it first.
      closeDrawer();
      deleteReturnFocusTo =
        deleteTrigger ||
        (document.activeElement &&
        typeof document.activeElement.focus === "function"
          ? document.activeElement
          : null);
      deleteScrim.hidden = false;
      setBackgroundInert(true);
      // Initial focus lands on cancel, never on the destructive button.
      releaseDeleteTrap = trapFocus(deleteScrim, {
        onEscape: closeDeleteModal,
        initialFocus: deleteCancel,
      });
    };

    if (deleteTrigger) {
      deleteTrigger.addEventListener("click", function (event) {
        event.preventDefault();
        openDeleteModal();
      });
    }

    if (deleteCancel) {
      deleteCancel.addEventListener("click", closeDeleteModal);
    }

    // Scrim click (outside the dialog card) cancels; a click inside does not.
    deleteScrim.addEventListener("click", function (event) {
      if (event.target === deleteScrim) {
        closeDeleteModal();
      }
    });

    if (deleteConfirmField && deleteSubmit) {
      deleteConfirmField.addEventListener("input", syncDeleteSubmit);
      syncDeleteSubmit();
    }
  }

  /* ---- 5. Form-level error summary takes focus -------------------------- */

  // On a 422 (or, for `/login`, a 401) re-render, the three client-mutation
  // templates and `login.html` emit a focusable `role="alert"` `.banner--
  // danger`; move focus to it so a keyboard / screen reader user lands on
  // the error. This deferred script runs post-parse, so the banner (only
  // present on the error re-render) is already in the DOM -- and runs after
  // native `autofocus` has already applied, so this always wins when it
  // finds a banner (`login.html` itself also drops `autofocus` server-side
  // on the error branch, so a no-JS reload doesn't skip past the message).
  var errorSummary = document.querySelector(".banner--danger[tabindex='-1']");
  if (errorSummary) {
    errorSummary.focus();
  }

  /* ---- 6. Report-run stage view (Story 9.5, backoff added Story 9.8) ----- */

  //: 5s after the 1st consecutive poll failure, 15s from the 2nd onward —
  //: this story's I/O & Edge-Case Matrix ("Poll fails once, then twice").
  var POLL_BACKOFF_MS_FIRST = 5000;
  var POLL_BACKOFF_MS_SUBSEQUENT = 15000;
  //: How many consecutive failures before `[data-poll-retry]` (`Riprova`)
  //: is revealed.
  var POLL_RETRY_VISIBLE_AT_FAILURE = 2;

  var pollBackoff = { failureCount: 0, nextAllowedAt: 0 };

  function isRunStatusElt(elt) {
    if (!elt) {
      return false;
    }
    return elt.id === "run-status" || (elt.closest && !!elt.closest("#run-status"));
  }

  // The poll region's own `hx-trigger="every 2s, poll-retry from:body"` only
  // renders while the run is still advanceable (`poll_active`,
  // `report_run_poll.html`); this job pauses/gates that already-present
  // trigger, rather than starting a timer of its own or touching the
  // trigger's cadence.
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var elt = event.detail && event.detail.elt;
    if (!isRunStatusElt(elt)) {
      return;
    }

    // Paused while the tab is hidden — `document.hidden` is re-checked on
    // every tick htmx would otherwise fire on.
    if (document.hidden) {
      event.preventDefault();
      return;
    }

    // A manual `Riprova` click (job below) dispatches its own `poll-retry`
    // event on `document.body`; the request it triggers always fires
    // immediately, bypassing the backoff gate below — an operator-requested
    // retry is never itself throttled.
    var requestConfig = event.detail.requestConfig;
    var triggeringEvent = requestConfig && requestConfig.triggeringEvent;
    if (triggeringEvent && triggeringEvent.type === "poll-retry") {
      return;
    }

    // The backoff gate on the automatic `every 2s` tick: vetoed until
    // `pollBackoff.nextAllowedAt` has passed.
    if (Date.now() < pollBackoff.nextAllowedAt) {
      event.preventDefault();
    }
  });

  function pollErrorBanner(elt) {
    if (!elt || !elt.querySelector) {
      return null;
    }
    if (elt.id === "run-status") {
      return elt.querySelector("[data-poll-error]");
    }
    var region = elt.closest ? elt.closest("#run-status") : null;
    return region ? region.querySelector("[data-poll-error]") : null;
  }

  function pollRetryButton(elt) {
    if (!elt || !elt.querySelector) {
      return null;
    }
    if (elt.id === "run-status") {
      return elt.querySelector("[data-poll-retry]");
    }
    var region = elt.closest ? elt.closest("#run-status") : null;
    return region ? region.querySelector("[data-poll-retry]") : null;
  }

  function onPollFailure(elt) {
    var banner = pollErrorBanner(elt);
    if (banner) {
      banner.hidden = false;
    }

    pollBackoff.failureCount += 1;
    var delayMs =
      pollBackoff.failureCount >= POLL_RETRY_VISIBLE_AT_FAILURE
        ? POLL_BACKOFF_MS_SUBSEQUENT
        : POLL_BACKOFF_MS_FIRST;
    pollBackoff.nextAllowedAt = Date.now() + delayMs;

    if (pollBackoff.failureCount >= POLL_RETRY_VISIBLE_AT_FAILURE) {
      var retryButton = pollRetryButton(elt);
      if (retryButton) {
        retryButton.hidden = false;
      }
    }
  }

  document.body.addEventListener("htmx:responseError", function (event) {
    onPollFailure(event.detail && event.detail.target);
  });

  document.body.addEventListener("htmx:sendError", function (event) {
    onPollFailure(event.detail && event.detail.elt);
  });

  document.body.addEventListener("htmx:afterOnLoad", function (event) {
    var xhr = event.detail && event.detail.xhr;
    if (!xhr || xhr.status < 200 || xhr.status >= 300) {
      return;
    }
    var elt = event.detail && event.detail.elt;
    var banner = pollErrorBanner(elt);
    if (banner) {
      banner.hidden = true;
    }
    var retryButton = pollRetryButton(elt);
    if (retryButton) {
      retryButton.hidden = true;
    }
    pollBackoff.failureCount = 0;
    pollBackoff.nextAllowedAt = 0;
  });

  // The `Riprova` click itself: dispatched on `document.body`, matching the
  // `poll-retry from:body` trigger — listening on `body` rather than
  // `#run-status` survives that element being replaced wholesale by every
  // `hx-swap="outerHTML"` poll response.
  document.body.addEventListener("click", function (event) {
    var button =
      event.target && event.target.closest
        ? event.target.closest("[data-poll-retry]")
        : null;
    if (!button) {
      return;
    }
    document.body.dispatchEvent(new CustomEvent("poll-retry"));
  });

  /* ---- 7. Regenerate-confirm modal (Story 9.5) --------------------------- */

  var regenScrim = document.querySelector("[data-regen-modal]");
  if (regenScrim) {
    var regenTrigger = document.querySelector("[data-regen-trigger]");
    var regenCancel = regenScrim.querySelector("[data-regen-cancel]");
    var regenReturnFocusTo = null;
    var releaseRegenTrap = null;

    var regenModalOpen = function () {
      return !regenScrim.hidden;
    };

    var closeRegenModal = function () {
      if (!regenModalOpen()) {
        return;
      }
      regenScrim.hidden = true;
      if (releaseRegenTrap) {
        releaseRegenTrap();
        releaseRegenTrap = null;
      }
      if (
        regenReturnFocusTo &&
        typeof regenReturnFocusTo.focus === "function"
      ) {
        regenReturnFocusTo.focus();
      }
      regenReturnFocusTo = null;
    };

    var openRegenModal = function () {
      if (regenModalOpen()) {
        return;
      }
      closeDrawer();
      regenReturnFocusTo =
        regenTrigger ||
        (document.activeElement &&
        typeof document.activeElement.focus === "function"
          ? document.activeElement
          : null);
      regenScrim.hidden = false;
      // Initial focus lands on cancel, never on the destructive-looking
      // primary — no typed-name gate: Rigenera is a bounded recovery action.
      releaseRegenTrap = trapFocus(regenScrim, {
        onEscape: closeRegenModal,
        initialFocus: regenCancel,
      });
    };

    if (regenTrigger) {
      regenTrigger.addEventListener("click", function (event) {
        event.preventDefault();
        openRegenModal();
      });
    }

    if (regenCancel) {
      regenCancel.addEventListener("click", closeRegenModal);
    }

    regenScrim.addEventListener("click", function (event) {
      if (event.target === regenScrim) {
        closeRegenModal();
      }
    });
  }

  /* ---- 8. Click-to-copy mono chips (Story 9.6) --------------------------- */

  var copyRestoreTimer = null;
  var copyOriginalText = null;
  var copyOriginalEl = null;

  function restoreCopyChip() {
    if (copyOriginalEl) {
      copyOriginalEl.textContent = copyOriginalText;
    }
    copyRestoreTimer = null;
    copyOriginalEl = null;
    copyOriginalText = null;
  }

  document.body.addEventListener("click", function (event) {
    var chip =
      event.target && event.target.closest
        ? event.target.closest(".badge-mono[data-copy-chip]")
        : null;
    if (!chip) {
      return;
    }

    // If this chip is already mid-flash ("Copiato"), its live textContent
    // is the feedback label, not the identifier -- read the stashed
    // original instead, so a re-click during the 1.5s window copies (and
    // eventually restores) the real value rather than the word "Copiato".
    var text = chip === copyOriginalEl ? copyOriginalText : chip.textContent.trim();

    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      return;
    }

    try {
      navigator.clipboard
        .writeText(text)
        .then(function () {
          // Cancel any pending restore from a previous click -- rapid
          // re-clicks never race each other back to the wrong label.
          if (copyRestoreTimer) {
            clearTimeout(copyRestoreTimer);
          }
          copyOriginalEl = chip;
          copyOriginalText = text;
          chip.textContent = "Copiato";
          copyRestoreTimer = setTimeout(restoreCopyChip, 1500);
        })
        .catch(function () {
          /* clipboard write blocked/rejected — silent no-op */
        });
    } catch (e) {
      /* Clipboard API unavailable — silent no-op */
    }
  });

  /* ---- 9. Report-sheet scroll-spy (Story 9.6) ----------------------------- */

  var reportToc = document.querySelector("[data-report-toc]");
  if (reportToc && window.IntersectionObserver) {
    var tocLinks = Array.prototype.slice.call(reportToc.querySelectorAll("a[href^='#']"));
    var sections = Array.prototype.slice.call(
      document.querySelectorAll(".report-sheet section[id]")
    );

    var setActiveLink = function (id) {
      tocLinks.forEach(function (link) {
        var isActive = link.getAttribute("href") === "#" + id;
        link.classList.toggle("is-active", isActive);
      });
    };

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            setActiveLink(entry.target.id);
          }
        });
      },
      { rootMargin: "0px 0px -70% 0px" }
    );

    sections.forEach(function (section) {
      observer.observe(section);
    });
  }

  /* ---- 10. Corpus clamp toggle (Story 9.7) -------------------------------- */

  var corpusTexts = Array.prototype.slice.call(
    document.querySelectorAll("[data-corpus-text]")
  );
  corpusTexts.forEach(function (text) {
    var entry = text.closest(".corpus-entry");
    var expandButton = entry ? entry.querySelector("[data-corpus-expand]") : null;
    if (!expandButton) {
      return;
    }
    if (text.scrollHeight > text.clientHeight) {
      expandButton.hidden = false;
      expandButton.setAttribute("aria-expanded", "false");
    }
  });

  document.body.addEventListener("click", function (event) {
    var button =
      event.target && event.target.closest
        ? event.target.closest("[data-corpus-expand]")
        : null;
    if (!button) {
      return;
    }
    var entry = button.closest(".corpus-entry");
    var text = entry ? entry.querySelector("[data-corpus-text]") : null;
    if (!text) {
      return;
    }
    var expanded = text.classList.toggle("is-expanded");
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    button.textContent = expanded ? "Comprimi" : "Espandi";
  });

  /* ---- 11. Toast queue (Story 9.8) --------------------------------------- */

  var TOAST_MAX = 3;
  var TOAST_SUCCESS_MS = 5000;

  var toastRegion = document.querySelector("[data-toast-region]");
  var toastQueue = [];

  function dismissToast(entry) {
    if (!entry || entry.dismissed) {
      return;
    }
    entry.dismissed = true;
    if (entry.timer) {
      clearTimeout(entry.timer);
      entry.timer = null;
    }
    var index = toastQueue.indexOf(entry);
    if (index !== -1) {
      toastQueue.splice(index, 1);
    }
    if (entry.el && entry.el.parentNode) {
      entry.el.parentNode.removeChild(entry.el);
    }
  }

  function scheduleToastAutoDismiss(entry) {
    if (entry.kind !== "success") {
      return;
    }
    if (entry.remainingMs == null) {
      entry.remainingMs = TOAST_SUCCESS_MS;
    }
    entry.startedAt = Date.now();
    entry.timer = setTimeout(function () {
      dismissToast(entry);
    }, entry.remainingMs);
  }

  function showToast(kind, message) {
    if (!toastRegion || !message) {
      return null;
    }

    // FIFO cap: a 4th queued toast dismisses the oldest first.
    while (toastQueue.length >= TOAST_MAX) {
      dismissToast(toastQueue[0]);
    }

    var el = document.createElement("p");
    el.className = "toast toast--" + kind;
    el.setAttribute("role", kind === "success" ? "status" : "alert");

    var text = document.createElement("span");
    text.className = "toast__text";
    text.textContent = message;
    el.appendChild(text);

    var entry = {
      el: el,
      kind: kind,
      timer: null,
      dismissed: false,
      remainingMs: null,
      startedAt: 0,
    };

    if (kind === "success") {
      // Hover pauses the auto-dismiss countdown; leaving resumes it with
      // whatever time was left, never a fresh 5s.
      el.addEventListener("mouseenter", function () {
        if (entry.timer) {
          clearTimeout(entry.timer);
          entry.timer = null;
          entry.remainingMs = Math.max(0, entry.remainingMs - (Date.now() - entry.startedAt));
        }
      });
      el.addEventListener("mouseleave", function () {
        scheduleToastAutoDismiss(entry);
      });
      scheduleToastAutoDismiss(entry);
    } else {
      // warning/danger persist until explicitly closed.
      var close = document.createElement("button");
      close.type = "button";
      close.className = "toast__close";
      close.setAttribute("aria-label", "Chiudi");
      close.textContent = "×";
      close.addEventListener("click", function () {
        dismissToast(entry);
      });
      el.appendChild(close);
    }

    toastQueue.push(entry);
    toastRegion.appendChild(el);
    return entry;
  }

  /* ---- 12. [data-flash] -> toast promotion; generic banner dismiss ------- */

  function flashMessageText(banner) {
    // Only the banner's own direct text nodes -- not the `.banner__dismiss`
    // button's "×" label -- mirrors `base.html`'s markup, where the message
    // is a bare text node immediately followed by that button.
    var text = "";
    for (var i = 0; i < banner.childNodes.length; i++) {
      var node = banner.childNodes[i];
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent;
      }
    }
    return text.trim();
  }

  var flashBanner = document.querySelector("[data-flash]");
  if (flashBanner) {
    var flashKind = flashBanner.getAttribute("data-flash-kind") || "success";
    showToast(flashKind, flashMessageText(flashBanner));
    // The JS-enhanced experience is the toast; without JS the banner itself
    // is what's shown.
    flashBanner.hidden = true;
  }

  // Delegated so it covers the flash banner and any other `.banner` that
  // grows a `.banner__dismiss` control later.
  document.body.addEventListener("click", function (event) {
    var dismissButton =
      event.target && event.target.closest
        ? event.target.closest(".banner__dismiss")
        : null;
    if (!dismissButton) {
      return;
    }
    var banner = dismissButton.closest(".banner");
    if (banner) {
      banner.hidden = true;
    }
  });

  /* ---- 13. Submit-button lock + spinner (Story 9.8) ----------------------- */

  var lockForms = Array.prototype.slice.call(
    document.querySelectorAll("[data-submit-lock]")
  );
  lockForms.forEach(function (form) {
    form.addEventListener("submit", function () {
      var submitButton = form.querySelector('button[type="submit"]');
      if (submitButton && !submitButton.disabled) {
        submitButton.disabled = true;
        submitButton.setAttribute("aria-busy", "true");
        var spinner = document.createElement("span");
        spinner.className = "spinner";
        spinner.setAttribute("aria-hidden", "true");
        submitButton.insertBefore(spinner, submitButton.firstChild);
      }

      // Never the native `disabled` attribute on a field itself -- it would
      // silently drop that field's value from the submission already in
      // flight. `pointer-events: none` (tokens.css) plus `aria-disabled`
      // does the locking instead.
      var fields = form.querySelectorAll(".field");
      Array.prototype.forEach.call(fields, function (field) {
        field.classList.add("is-locked");
        field.setAttribute("aria-disabled", "true");
      });
    });
  });
})();
