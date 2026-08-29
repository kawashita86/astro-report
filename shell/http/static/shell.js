/*
 * astro-report application-shell behaviour — first-party, no dependencies.
 *
 * Five jobs, all progressive enhancements over a shell that already works
 * without JavaScript:
 *
 *   1. Theme toggle — flip `data-theme` on <html>, persist the choice to
 *      localStorage (wrapped in try/catch: a private window or blocked storage
 *      must silently fall back to `prefers-color-scheme`). The pre-paint
 *      snippet in base.html's <head> re-applies the stored choice before the
 *      stylesheet paints, so there is no flash.
 *
 *   2. Off-canvas drawer (<900px) — open from the header menu button, trap
 *      focus while open, close on Esc or scrim click, and restore focus to the
 *      trigger on close.
 *
 *   3. Clienti list filter — client-side, name-only, case-insensitive. Typing
 *      in `[data-client-filter]` hides non-matching `[data-client-row]`s, keeps
 *      `[data-client-count]` at `{shown} di {total}`, and swaps the table for
 *      an inline no-match line when nothing matches. No server round-trip.
 *
 *   4. Delete-confirm modal (Story 9.4) — intercept the `[data-delete-client]`
 *      trigger on the Anagrafica screen, open the inline `[data-delete-modal]`
 *      instead of navigating, trap focus with initial focus on `Annulla`
 *      (`[data-delete-cancel]`), close on Esc / scrim click / cancel and
 *      restore focus to the trigger. The `danger` submit
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
 * All shell transitions are disabled by tokens.css under
 * `prefers-reduced-motion`; this file adds no scripted animation.
 */
(function () {
  "use strict";

  var root = document.documentElement;

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

  var FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function drawerOpen() {
    return !!shell && shell.classList.contains("is-drawer-open");
  }

  function focusables() {
    if (!sidebar) {
      return [];
    }
    return Array.prototype.filter.call(
      sidebar.querySelectorAll(FOCUSABLE),
      function (el) {
        return el.offsetParent !== null || el === document.activeElement;
      }
    );
  }

  function onKeydown(event) {
    if (!drawerOpen()) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeDrawer();
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

  function openDrawer() {
    if (!shell || drawerOpen()) {
      return;
    }
    shell.classList.add("is-drawer-open");
    if (menuButton) {
      menuButton.setAttribute("aria-expanded", "true");
    }
    document.addEventListener("keydown", onKeydown, true);
    var items = focusables();
    if (items.length > 0) {
      items[0].focus();
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
    document.removeEventListener("keydown", onKeydown, true);
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
    var expectedName = (deleteScrim.dataset.clientName || "").trim();

    var deleteModalOpen = function () {
      return !deleteScrim.hidden;
    };

    var deleteFocusables = function () {
      return Array.prototype.filter.call(
        deleteScrim.querySelectorAll(FOCUSABLE),
        function (el) {
          return el.offsetParent !== null || el === document.activeElement;
        }
      );
    };

    // Take the rest of the page out of the a11y tree / tab order while the
    // modal is open: `inert` where supported, `aria-hidden` as the fallback.
    // Everything except the modal scrim itself.
    var backgroundInertTargets = function () {
      var targets = [];
      var sidebar = document.querySelector("[data-app-sidebar]");
      var header = document.querySelector(".app-header");
      if (sidebar) {
        targets.push(sidebar);
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
      document.removeEventListener("keydown", onDeleteKeydown, true);
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
      document.addEventListener("keydown", onDeleteKeydown, true);
      // Initial focus lands on cancel, never on the destructive button.
      if (deleteCancel) {
        deleteCancel.focus();
      }
    };

    function onDeleteKeydown(event) {
      if (!deleteModalOpen()) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        closeDeleteModal();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      var items = deleteFocusables();
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
})();
