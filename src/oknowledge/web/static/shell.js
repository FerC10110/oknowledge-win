// The library without reloads (docs/2026-10-14-rediseno-biblioteca-design.md
// §1, §4, §6, §7), and every other list drawn the same way: the ideas
// (docs/2026-10-14-rediseno-ocio-ideas-design.md §2) and Ocio. Every action
// here has a plain link or form under it; this only swaps the column that
// changed and keeps the URL in step.
(function () {
  "use strict";
  var list = document.getElementById("list");
  var panel = document.getElementById("panel");          // not on /ideas
  var form = document.getElementById("unified");
  var field = document.getElementById("field-q");
  if (!list || !form || !field) return;
  var texts = document.body.dataset;
  var mode = form.dataset.mode || "library";
  var source = list.dataset.source || "/lista";
  var STORE = "oknowledge.vista" + (mode === "library" ? "" : "." + mode);
  // What a new search keeps from the URL: the shape and the sidebar's filter.
  var KEEP = ["vista", "estado", "tipo", "orden"];
  var prefixes = (form.dataset.savePrefixes || "").split(/\s+/).filter(Boolean);

  function toast(text) {
    if (!text) return;
    document.querySelectorAll(".toast").forEach(function (old) { old.remove(); });
    var p = document.createElement("p");
    p.className = "notice toast";
    p.setAttribute("role", "status");
    p.textContent = text;
    document.body.appendChild(p);
    setTimeout(function () { p.remove(); }, 2700);
  }

  function here() { return new URL(location.href); }

  function fold(text) {
    return text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  // What the field sends to /add instead of searching: the server's
  // library_view.saves -- a link, or "película: Terminator" (cards.wanted:
  // the word before the first colon, folded and trimmed, and a title after it).
  function saves(text) {
    // The library and Ocio save on Enter. On /ideas Enter searches and only
    // the "New idea" button saves (spec §2).
    if (mode === "ideas") return false;
    var start = text.trim().toLowerCase();
    if (start.indexOf("http://") === 0 || start.indexOf("https://") === 0 ||
        start.indexOf("www.") === 0) return true;
    var colon = text.indexOf(":");
    if (colon < 0) return false;
    return prefixes.indexOf(fold(text.slice(0, colon)).trim()) >= 0 &&
           text.slice(colon + 1).trim() !== "";
  }

  // --- the list column ---------------------------------------------------
  var asked = 0;
  function loadList(url, keepScroll) {
    var mine = ++asked;
    // The pick this list was asked under. If the user picks another link
    // before it lands, its sel (and the server's data-current) is the old
    // one, and following it would undo their click.
    var picked = shownAsked;
    var target = new URL(url, location.href);
    var body = document.getElementById("list-body");
    var top = body ? body.scrollTop : 0;
    return fetch(source + target.search)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (mine !== asked) return;
        list.innerHTML = html;
        var moved = picked !== shownAsked;
        if (moved) {
          var sel = here().searchParams.get("sel");
          if (sel) target.searchParams.set("sel", sel); else target.searchParams.delete("sel");
        }
        history.replaceState(null, "", target.pathname + target.search);
        if (keepScroll) document.getElementById("list-body").scrollTop = top;
        var items = document.getElementById("items");
        if (panel && moved) {
          var still = here().searchParams.get("sel");
          if (still) markCurrent(still);
        } else if (panel) {
          var current = items ? items.dataset.current : "";
          var shown = panel.querySelector("[data-panel]");
          // Not over a catalog search the URL still names (Ocio): the list
          // was reloaded under it, the search was not left.
          if (current && !target.searchParams.get("buscar") &&
              (!shown || shown.dataset.panel !== current)) loadPanel(current, true);
        }
        observe();
        watch();
      })
      .catch(function () { location.href = target.href; });
  }

  function markCurrent(id) {
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var li = document.getElementById("card-" + id);
    if (li) li.classList.add("on");
    var items = document.getElementById("items");
    if (items) items.dataset.current = id;
  }

  // Whether `id` is still what the user picked. markCurrent sets the pick at
  // once, while the panel on screen is the old one until the new one lands.
  // With no list on screen (a search with no matches) the panel is the pick.
  function stillPicked(id) {
    if (!panel) return true;
    var items = document.getElementById("items");
    return !items || items.dataset.current === id;
  }

  // `gone` is for a link that may have stopped existing while it was shown
  // (an analysis that failed): its 404 empties the panel instead of
  // reloading the page, which would wipe the toast that just said so.
  var shownAsked = 0;
  function loadPanel(id, gone) {
    if (!panel) return;
    var mine = ++shownAsked;
    var url = here();
    url.searchParams.set("sel", id);
    // Ocio: a card picked ends a catalog search, on reload too.
    ["buscar", "catalogo", "year"].forEach(function (name) { url.searchParams.delete(name); });
    history.replaceState(null, "", url.pathname + url.search);
    markCurrent(id);
    return fetch("/panel/" + encodeURIComponent(id) + url.search)
      .then(function (r) {
        if (gone && r.status === 404) return null;
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        if (mine !== shownAsked) return;      // a newer panel was asked for since
        if (html === null) { emptyPanel(); return; }
        panel.innerHTML = html;
        if (window.oknowledge) window.oknowledge.bind(panel);   // the note saves itself
        watch();
      })
      .catch(function () { if (mine === shownAsked) location.href = url.href; });
  }

  // Ocio: the catalogs' answers in the panel (spec §3). The URL says what
  // was searched, so a reload shows the same. The page's `tipo` is the
  // poster grid's filter and stays; `catalogo` is the kind searched. The
  // fragment takes that kind as `tipo` and the grid as `grid`, which its
  // kind links carry on.
  function loadCatalog(q, kind) {
    if (!panel) return;
    var mine = ++shownAsked;
    var url = here();
    var grid = url.searchParams.get("tipo") || "";
    // A kind picked in the panel, the one searched last, or the grid's
    // (Todo: films), as the page without JavaScript does.
    var searched = kind || url.searchParams.get("catalogo") || grid || "movie";
    if (!kind) url.searchParams.delete("year");    // a new search, not a new kind
    url.searchParams.set("buscar", q);
    url.searchParams.set("catalogo", searched);
    url.searchParams.delete("sel");
    history.replaceState(null, "", url.pathname + url.search);
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var ask = new URLSearchParams({ q: q, tipo: searched });
    var year = url.searchParams.get("year");
    if (year) ask.set("year", year);
    if (grid) ask.set("grid", grid);
    fetch("/ocio/candidatos?" + ask.toString())
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) { if (mine === shownAsked) panel.innerHTML = html; })
      .catch(function () { if (mine === shownAsked) location.href = url.href; });
  }

  function emptyPanel() {
    if (!panel) return;
    var url = here();
    url.searchParams.delete("sel");
    history.replaceState(null, "", url.pathname + url.search);
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var items = document.getElementById("items");
    if (items) items.dataset.current = "";
    var p = document.createElement("p");
    p.className = "detail-empty";
    p.textContent = panel.dataset.empty || "";
    panel.replaceChildren(p);
  }

  function setActive(link) {
    document.querySelectorAll(".sidebar .filter.on").forEach(function (a) { a.classList.remove("on"); });
    if (link.closest(".sidebar")) link.classList.add("on");
  }

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey) return;
    // Only anchors: the panel's ⋯ is a <details class="menu up more"> and
    // must keep opening as a menu, never load more of the list.
    var kind = event.target.closest("a[data-kind]");
    if (kind && panel && panel.contains(kind)) {
      event.preventDefault();
      var search = panel.querySelector("[data-search]");
      loadCatalog(search ? search.dataset.search : "", kind.dataset.kind);
      return;
    }
    var link = event.target.closest("a[data-sel], a[data-nav], a[data-view], a.more[data-more]");
    if (!link) return;
    event.preventDefault();
    if (link.dataset.sel) {
      loadPanel(link.dataset.sel);
    } else if (link.hasAttribute("data-view")) {
      try { localStorage.setItem(STORE, link.dataset.view); } catch (e) { /* private window */ }
      // From the URL as it is now, not the link's href: that carries the
      // selection from when the list head was drawn.
      var shape = here();
      shape.searchParams.set("vista", link.dataset.view);
      loadList(shape.href, true);
    } else if (link.hasAttribute("data-more")) {
      more(link);
    } else {
      setActive(link);
      field.value = "";
      form.classList.remove("saving");
      var target = new URL(link.href, location.href);
      var vista = here().searchParams.get("vista");
      if (vista) target.searchParams.set("vista", vista);
      target.searchParams.delete("hasta");       // a new list starts at its first chunk
      loadList(target.href);
    }
  });

  // --- remembered layout --------------------------------------------------
  // Per list (STORE), and only where the list offers the choice.
  if (document.querySelector("a[data-view]")) {
    try {
      var saved = localStorage.getItem(STORE);
      var now = here();
      if (saved === "lista" && !now.searchParams.get("vista")) {
        now.searchParams.set("vista", "lista");
        loadList(now.href);
      }
    } catch (e) { /* no storage: the URL decides */ }
  }

  // --- the unified field ---------------------------------------------------
  var timer = null;
  field.addEventListener("input", function () {
    clearTimeout(timer);
    var text = field.value;
    var saving = saves(text);
    // On /ideas "New idea" shows as soon as there is text, and the text
    // still searches: the button saves it, Enter does not.
    form.classList.toggle("saving", mode === "ideas" ? text.trim() !== "" : saving);
    // Ocio: text that does not save searches the catalogs with its button.
    form.classList.toggle("finding", mode === "ocio" && !saving && text.trim() !== "");
    if (saving) return;
    timer = setTimeout(function () {
      var url = new URL(form.getAttribute("action") || "/", location.href);
      var q = text.trim().split(/\s+/).join(" ");
      if (q) url.searchParams.set("q", q);
      KEEP.forEach(function (name) {
        var value = here().searchParams.get(name);
        if (value) url.searchParams.set(name, value);
      });
      loadList(url.href);
    }, 250);
  });

  form.addEventListener("submit", function (event) {
    if (event.submitter && event.submitter.id === "save-link") return;   // a real POST
    event.preventDefault();
    var catalog = event.submitter && event.submitter.id === "catalog-search";
    if (mode === "ocio" && !saves(field.value) && (catalog || field.value.trim())) {
      if (field.value.trim()) loadCatalog(field.value.trim().split(/\s+/).join(" "));
      return;
    }
    if (saves(field.value)) {
      // Not from inside this handler: a submission started while the form is
      // still firing its submit event is ignored (HTML spec, "firing
      // submission events"), so Enter would do nothing.
      setTimeout(function () { form.requestSubmit(document.getElementById("save-link")); }, 0);
      return;
    }
    clearTimeout(timer);
    field.dispatchEvent(new Event("input"));
  });

  // --- more at the end of the list ----------------------------------------
  var observer = "IntersectionObserver" in window ? new IntersectionObserver(function (seen) {
    seen.forEach(function (one) { if (one.isIntersecting) more(one.target); });
  }, { rootMargin: "400px" }) : null;

  function observe() {
    var link = list.querySelector("a.more[data-more]");
    if (observer && link) observer.observe(link);
  }

  function more(link) {
    if (link.dataset.loading) return;
    link.dataset.loading = "1";
    if (observer) observer.unobserve(link);
    fetch(link.dataset.more)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var box = document.createElement("div");
        box.innerHTML = html;
        var items = document.getElementById("items");
        var added = box.querySelectorAll("li.item");
        added.forEach(function (li) { items.appendChild(li); });
        var next = box.querySelector("a.more[data-more]");
        if (next) link.replaceWith(next); else link.remove();
        // Remember how far the list goes, so a reload of the column (after an
        // edit or a finished analysis) brings back as many and keeps the scroll.
        var from = new URL(link.dataset.more, location.href).searchParams.get("desde");
        var url = here();
        url.searchParams.set("hasta", String((parseInt(from, 10) || 0) +
                                             added.length));
        history.replaceState(null, "", url.pathname + url.search);
        observe();
        watch();
      })
      .catch(function () { delete link.dataset.loading; });
  }

  // --- menus --------------------------------------------------------------
  document.addEventListener("toggle", function (event) {
    var opened = event.target;
    if (!opened.matches || !opened.matches("details.menu") || !opened.open) return;
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (d !== opened) d.open = false;
    });
  }, true);

  function closeMenus() {
    document.querySelectorAll("details.menu[open]").forEach(function (d) { d.open = false; });
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("details.menu")) closeMenus();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenus();
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    }
  });

  // --- edits in place -------------------------------------------------------
  document.addEventListener("submit", function (event) {
    var target = event.target;
    if (!target.matches("form[data-inline]")) return;
    event.preventDefault();
    var data = new FormData(target, event.submitter || undefined);
    closeMenus();
    fetch(target.action, { method: "POST", body: data,
                           headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; });
      })
      .then(function (answer) {
        if (!answer.ok) { toast(answer.error || texts.saveFailed); return; }
        // A write that starts a run (a rewrite) is told by its watcher when
        // it ends; its own notice says "reload in a moment", which is wrong here.
        if (!target.dataset.runs) toast(answer.notice || "");
        var shown = panel && panel.querySelector("[data-panel]");
        if (shown && shown.dataset.panel && stillPicked(shown.dataset.panel)) {
          loadPanel(shown.dataset.panel, true);    // deleted: gone
        }
        loadList(here().href, true);
      })
      .catch(function () { toast(texts.saveFailed); });
  });

  // --- links being read -----------------------------------------------------
  // A link being analysed in the list, or a card being rewritten in the
  // list or the panel: each says its own words when it ends, from the
  // nearest data-done-as / data-failed-as (the library's are the page's).
  var watched = {};
  function watch() {
    var busy = Array.prototype.slice.call(list.querySelectorAll("[data-working]"));
    if (panel) busy = busy.concat(Array.prototype.slice.call(panel.querySelectorAll("[data-working]")));
    busy.forEach(function (el) {
      var id = el.dataset.working;
      if (watched[id]) return;
      var words = el.closest("[data-done-as]");
      var doneAs = words ? words.dataset.doneAs : texts.done;
      var failedAs = words ? words.dataset.failedAs : texts.failed;
      watched[id] = setInterval(function () {
        fetch("/item/" + encodeURIComponent(id) + "/state")
          .then(function (r) { return r.json(); })
          .then(function (state) {
            if (state.working) return;
            clearInterval(watched[id]);
            delete watched[id];
            toast(state.status === "failed" ? failedAs : doneAs);
            // What the user picked, not what is on screen: that is still the
            // old panel while a newer pick is on its way.
            var shown = panel && panel.querySelector("[data-panel]");
            if (shown && shown.dataset.panel === id && stillPicked(id)) loadPanel(id, true);
            loadList(here().href, true);
          })
          .catch(function () { /* try again in three seconds */ });
      }, 3000);
    });
  }

  observe();
  watch();
})();
