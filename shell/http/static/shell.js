/*
 * astro-report application-shell behaviour — first-party, no dependencies.
 *
 * Three jobs, all progressive enhancements over a shell that already works
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
})();
