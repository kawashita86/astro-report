/*
 * astro-report application-shell behaviour — first-party, no dependencies.
 *
 * Seven jobs, all progressive enhancements over a shell that already works
 * without JavaScript:
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
 *   6. Report-run stage view (Story 9.5) — pause the `#run-status` HTMX poll
 *      while the tab is hidden (`document.hidden`), so a backgrounded tab
 *      never spends a request; reveal the inline `[data-poll-error]`
 *      `role="alert"` banner on `htmx:responseError` / `htmx:sendError` from
 *      that region, and hide it again once a poll succeeds. The polling
 *      cadence and stop condition are still server-driven (the `hx-*`
 *      attributes render only while `poll_active` is true,
 *      `shell/http/templates/report_run_poll.html`) — this job only pauses/
 *      resumes the already-present trigger and surfaces a transient network
 *      failure; it starts no timer of its own.
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

  // On a 422 re-render the three client-mutation templates emit a focusable
  // `role="alert"` `.banner--danger`; move focus to it so a keyboard / screen
  // reader user lands on the error. This deferred script runs post-parse, so
  // the banner (only present on the error re-render) is already in the DOM.
  var errorSummary = document.querySelector(".banner--danger[tabindex='-1']");
  if (errorSummary) {
    errorSummary.focus();
  }

  /* ---- 6. Report-run stage view (Story 9.5) ------------------------------ */

  // The poll region's own `hx-trigger="every 2s"` only renders while the run
  // is still advanceable (`poll_active`, `report_run_poll.html`); this job
  // pauses that already-present trigger while the tab is hidden, rather than
  // starting a timer of its own — `document.hidden` is re-checked on every
  // tick htmx would otherwise fire on.
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var elt = event.detail && event.detail.elt;
    if (!elt || !document.hidden) {
      return;
    }
    if (elt.id === "run-status" || (elt.closest && elt.closest("#run-status"))) {
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

  document.body.addEventListener("htmx:responseError", function (event) {
    var banner = pollErrorBanner(event.detail && event.detail.target);
    if (banner) {
      banner.hidden = false;
    }
  });

  document.body.addEventListener("htmx:sendError", function (event) {
    var banner = pollErrorBanner(event.detail && event.detail.elt);
    if (banner) {
      banner.hidden = false;
    }
  });

  document.body.addEventListener("htmx:afterOnLoad", function (event) {
    var xhr = event.detail && event.detail.xhr;
    if (!xhr || xhr.status < 200 || xhr.status >= 300) {
      return;
    }
    var banner = pollErrorBanner(event.detail && event.detail.elt);
    if (banner) {
      banner.hidden = true;
    }
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
})();
