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
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.keys = ok.keys || {};
  var mode = form.dataset.mode || "library";
  var source = list.dataset.source || "/lista";
  var STORE = "oknowledge.vista" + (mode === "library" ? "" : "." + mode);
  // What a new search keeps from the URL: the shape and the sidebar's filter.
  var KEEP = ["vista", "estado", "tipo", "orden"];
  var prefixes = (form.dataset.savePrefixes || "").split(/\s+/).filter(Boolean);

  // The one toast is app.js's (spec §2).
  function toast(text) {
    var ok = window.oknowledge;
    if (text && ok && ok.toast) ok.toast(text);
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

  // --- the list on screen (spec §4, §5) --------------------------------------
  function shown() {
    return Array.prototype.slice.call(list.querySelectorAll("#items > li.item"));
  }

  function idOf(li) { return li.id.replace(/^(card|idea)-/, ""); }

  function itemOf(id) {
    return id ? document.getElementById("card-" + id) || document.getElementById("idea-" + id)
              : null;
  }

  function current() {
    var items = document.getElementById("items");
    return items ? items.dataset.current || "" : "";
  }

  // The one after `id` on screen, else the one before, else "" (Ruling 25).
  function neighbour(id) {
    var items = shown();
    for (var at = 0; at < items.length; at++) {
      if (idOf(items[at]) !== id) continue;
      var near = items[at + 1] || items[at - 1];
      return near ? idOf(near) : "";
    }
    return "";
  }

  // The list changed under the selection (select.js listens).
  function told(reason) {
    list.dispatchEvent(new CustomEvent("oknowledge:list", { bubbles: true,
                                                           detail: { reason: reason } }));
  }

  // Picked by a key: the panel opens it, or on /ideas the cursor moves.
  function pick(id) {
    if (!id) return;
    if (panel) loadPanel(id); else markCurrent(id);
    var li = itemOf(id);
    if (li) li.scrollIntoView({ block: "nearest" });
  }

  // --- the list column ---------------------------------------------------
  var asked = 0;
  function loadList(url, keepScroll, reason) {
    var mine = ++asked;
    // The pick this list was asked under. If the user picks another link
    // before it lands, its sel (and the server's data-current) is the old
    // one, and following it would undo their click.
    var picked = shownAsked;
    var target = new URL(url, location.href);
    var body = document.getElementById("list-body");
    var top = body ? body.scrollTop : 0;
    var cursor = panel ? "" : current();   // the ideas list's
    return fetch(source + target.search)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (mine !== asked) return;
        list.innerHTML = html;
        sideFilters();
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
          var serverPick = items ? items.dataset.current : "";
          var onScreen = panel.querySelector("[data-panel]");
          // Not over a catalog search the URL still names (Ocio): the list
          // was reloaded under it, the search was not left.
          if (serverPick && !target.searchParams.get("buscar") &&
              (!onScreen || onScreen.dataset.panel !== serverPick)) loadPanel(serverPick, true);
        }
        observe();
        watch();
        // The ideas list has no panel to follow: its cursor is put back.
        if (!panel && cursor && itemOf(cursor)) markCurrent(cursor);
        told(reason || "filter");
      })
      .catch(function () { if (mine === asked) location.href = target.href; });
  }

  // Ocio's column answer brings TIPO and ESTADO for its filter (final
  // review I-1): their words (a book is read), counts, links (each keeps
  // the other's choice) and lit rows, as a full page load draws them.
  // Swapped under loadList's own guard, so only the newest list's land.
  function sideFilters() {
    // The phone's row comes with it, drawn for the same filter (delivery 4, §3).
    var chips = list.querySelector("template#chip-filters");
    if (chips) {
      chips.remove();
      var row = document.querySelector(".chip-row");
      if (row) row.replaceWith(chips.content);
      litChipInView();
    }
    var fresh = list.querySelector("template#side-filters");
    if (!fresh) return;
    fresh.remove();
    var sidebar = document.querySelector(".sidebar");
    if (!sidebar) return;
    sidebar.querySelectorAll("nav.group").forEach(function (old) { old.remove(); });
    sidebar.insertBefore(fresh.content, sidebar.querySelector(".foot"));
  }

  function markCurrent(id) {
    list.querySelectorAll("li.item.on").forEach(function (li) { li.classList.remove("on"); });
    var li = itemOf(id);
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

  // The panel's text boxes (Ocio's note) save themselves. Before the panel
  // is swapped they send what they have and it waits for them to land: a
  // panel fetched before would show older text, and the next keys would
  // save that over what was typed in between. Resolves with null, or the
  // error of a save that failed.
  function settled() {
    var ok = window.oknowledge;
    return ok && ok.settle ? ok.settle(panel) : Promise.resolve(null);
  }

  function dirty() {
    var ok = window.oknowledge;
    return !!(ok && ok.dirty && ok.dirty(panel));
  }

  // A save failed: the panel stays, with the text in its box (spec §1), and
  // the URL and the list say it is still the one shown.
  function keepShown(failed) {
    toast(failed.message || texts.saveFailed);
    var onScreen = panel.querySelector("[data-panel]");
    var id = onScreen ? onScreen.dataset.panel : "";
    if (!id) return;
    var url = here();
    ["buscar", "catalogo", "year"].forEach(function (name) { url.searchParams.delete(name); });
    url.searchParams.set("sel", id);
    history.replaceState(null, "", url.pathname + url.search);
    markCurrent(id);
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
    var STOP = {};
    return settled()
      .then(function (failed) {
        if (mine !== shownAsked) return STOP;   // a newer panel was asked for since
        if (failed) { keepShown(failed); return STOP; }
        return fetch("/panel/" + encodeURIComponent(id) + url.search)
          .then(function (r) {
            if (gone && r.status === 404) return null;
            if (!r.ok) throw new Error(r.status);
            return r.text();
          });
      })
      .then(function (html) {
        if (html === STOP || mine !== shownAsked) return;      // a newer panel was asked for since
        // Typed in while this was on its way: that text is not in `html`.
        if (dirty(panel)) { loadPanel(id, gone); return; }
        if (html === null) { emptyPanel(); return; }
        var active = document.activeElement;
        var refocus = active && active.id && panel.contains(active) ? active.id : "";
        panel.innerHTML = html;
        if (window.oknowledge && window.oknowledge.bind) window.oknowledge.bind(panel);   // the note saves itself
        // The same card again (a rewrite ended): the box being typed in keeps the caret.
        var again = refocus && document.getElementById(refocus);
        if (again && panel.contains(again) && again.focus) {
          again.focus();
          if (again.setSelectionRange) again.setSelectionRange(again.value.length, again.value.length);
        }
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
    // The card's note leaves with the panel: it lands first (loadPanel).
    settled().then(function (failed) {
      if (mine !== shownAsked) return;
      if (failed) { keepShown(failed); return; }
      showCatalog(q, kind, mine);
    });
  }

  function showCatalog(q, kind, mine) {
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
      .then(function (html) {
        if (mine !== shownAsked) return;
        if (dirty()) { loadCatalog(q, kind); return; }
        panel.innerHTML = html;
      })
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

  // The library's groups are one choice: a click clears them all. Ocio's
  // TIPO and ESTADO are apart: a click lights its row in its own group.
  // The sidebar and the phone's chip row draw the same filters: the link
  // clicked and its twin (the same href) light together (delivery 4, §3).
  function setActive(link) {
    // A sort link in the list head is not a filter: the filters keep their row.
    if (!link.closest(".sidebar, .chip-row")) return;
    var href = link.getAttribute("href");
    document.querySelectorAll(".sidebar, .chip-row").forEach(function (root) {
      var twin = root.contains(link) ? link : Array.prototype.find.call(
        root.querySelectorAll("a[data-nav]"),
        function (a) { return a.getAttribute("href") === href; });
      // No twin (★ Favoritos has no chip): a library filter still unlights
      // the other drawing, or its last choice would stay lit there.
      if (!twin && link.closest("[data-apart]")) return;
      (twin ? twin.closest("[data-apart]") || root : root).querySelectorAll("a.filter.on, a.fchip.on")
        .forEach(function (a) { a.classList.remove("on"); });
      if (twin) twin.classList.add("on");
    });
    litTab(href);
    litChipInView();
  }

  // The phone's tab bar follows a filter clicked: ★ Favoritos lights its
  // tab, any other library filter lights Biblioteca (a tab of the same
  // page with no query). A page with no such tab keeps its own.
  function litTab(href) {
    var tabs = Array.prototype.slice.call(document.querySelectorAll(".tabbar a"));
    var path = new URL(href, location.href).pathname;
    var tab = tabs.find(function (a) { return a.getAttribute("href") === href; }) ||
      tabs.find(function (a) { var u = new URL(a.href); return u.pathname === path && !u.search; });
    if (!tab) return;
    tabs.forEach(function (a) { a.classList.toggle("on", a === tab); });
  }

  // The chip row scrolls sideways: the lit chip is brought into view, and
  // "nearest" on both axes never moves the page. On a desktop the row is
  // not drawn and this does nothing.
  function litChipInView() {
    var lit = document.querySelector(".chip-row .fchip.on");
    if (lit && lit.scrollIntoView) lit.scrollIntoView({ inline: "nearest", block: "nearest" });
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
      loadList(shape.href, true, "refresh");
    } else if (link.hasAttribute("data-more")) {
      more(link);
    } else {
      clearTimeout(timer);         // a search typed just before must not land after this
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
        loadList(now.href, false, "refresh");
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
      // The pick goes along: kept if it matches, the first one if not, and
      // with no matches it stays in the panel and the URL, so clearing the
      // search comes back to it.
      var pick = panel && here().searchParams.get("sel");
      if (pick) url.searchParams.set("sel", pick);
      loadList(url.href);
    }, 250);
  });

  form.addEventListener("submit", function (event) {
    if (event.submitter && event.submitter.id === "save-link") return;   // a real POST
    event.preventDefault();
    var catalog = event.submitter && event.submitter.id === "catalog-search";
    if (mode === "ocio" && !saves(field.value) && (catalog || field.value.trim())) {
      // Not the live filter after it: its list would take buscar off the URL.
      clearTimeout(timer);
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
    var mine = asked;
    if (observer) observer.unobserve(link);
    fetch(link.dataset.more)
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        // The list was drawn again meanwhile: this chunk belongs to the old one.
        if (mine !== asked) return;
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
        told("more");
      })
      .catch(function () { delete link.dataset.loading; });
  }

  // --- menus ------------------------------------------------------------------
  // Their rule is app.js's now, on every page (one open at a time, a click
  // outside or Esc closes them); an inline write only closes them.
  function closeMenus() {
    var ok = window.oknowledge;
    if (ok && ok.closeMenus) ok.closeMenus();
  }

  // --- edits in place -------------------------------------------------------
  document.addEventListener("submit", function (event) {
    var target = event.target;
    if (!target.matches("form[data-inline]")) return;
    event.preventDefault();
    var data = new FormData(target, event.submitter || undefined);
    closeMenus();
    // The panel's Delete (not a mention's): the one after it is picked
    // before the list changes (Ruling 25), and the toast offers Deshacer.
    var deleting = /^\/item\/[^/]+\/delete$/.test(new URL(target.action, location.href).pathname);
    var shownNow = panel && panel.querySelector("[data-panel]");
    var gone = shownNow ? shownNow.dataset.panel : "";
    var next = deleting ? neighbour(gone) : "";
    fetch(target.action, { method: "POST", body: data,
                           headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; });
      })
      .then(function (answer) {
        if (!answer.ok) { toast(answer.error || texts.saveFailed); return; }
        if (deleting) {
          ok.offerUndo(answer.notice, answer.undo);
          if (next) {
            loadList(here().href, true, "refresh");
            loadPanel(next);
          } else {
            emptyPanel();
            loadList(here().href, true, "refresh");
          }
          return;
        }
        // A write that starts a run (a rewrite) is told by its watcher when
        // it ends; its own notice says "reload in a moment", which is wrong
        // here. The server marks those (`runs`); every other notice is said.
        if (!answer.runs) toast(answer.notice || "");
        var onScreen = panel && panel.querySelector("[data-panel]");
        if (onScreen && onScreen.dataset.panel && stillPicked(onScreen.dataset.panel)) {
          loadPanel(onScreen.dataset.panel, true);    // deleted: gone
        }
        loadList(here().href, true, "refresh");
      })
      .catch(function () { toast(texts.saveFailed); });
  });

  // --- links being read -----------------------------------------------------
  // A link being analysed in the list, or a card being rewritten in the
  // list or the panel: each says its own words when it ends, from the
  // nearest data-done-as / data-failed-as (the library's are the page's).
  var watched = {};

  // Still in the list or the panel: an id that left both (filtered out,
  // deleted) is not asked about any more.
  function onScreen(id) {
    var mark = '[data-working="' + CSS.escape(id) + '"]';
    return !!(list.querySelector(mark) || (panel && panel.querySelector(mark)));
  }

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
        if (!onScreen(id)) { clearInterval(watched[id]); delete watched[id]; return; }
        fetch("/item/" + encodeURIComponent(id) + "/state")
          .then(function (r) { return r.json(); })
          .then(function (state) {
            if (state.working) return;
            clearInterval(watched[id]);
            delete watched[id];
            toast(state.status === "failed" ? failedAs : doneAs);
            // What the user picked, not what is on screen: that is still the
            // old panel while a newer pick is on its way.
            var inPanel = panel && panel.querySelector("[data-panel]");
            if (inPanel && inPanel.dataset.panel === id && stillPicked(id)) loadPanel(id, true);
            loadList(here().href, true, "refresh");
          })
          .catch(function () { /* try again in three seconds */ });
      }, 3000);
    });
  }

  // --- keys (spec §4) -----------------------------------------------------------------
  // A row is the items level with the first one: one in a list, the
  // columns that fit in a grid.
  function rowWidth() {
    var items = shown();
    if (!items.length) return 1;
    var top = items[0].offsetTop;
    var n = 0;
    while (n < items.length && items[n].offsetTop === top) n++;
    return n || 1;
  }

  // With nothing picked, any move picks the first one. An empty list is
  // nothing to move: the key is left alone (false).
  function step(by) {
    var items = shown();
    if (!items.length) return false;
    var at = -1;
    var id = current();
    for (var i = 0; i < items.length; i++) if (idOf(items[i]) === id) at = i;
    if (at < 0) { pick(idOf(items[0])); return; }
    var to = Math.max(0, Math.min(items.length - 1, at + by));
    if (to !== at) pick(idOf(items[to]));
  }

  ok.keys.j = ok.keys.ArrowRight = function () { return step(1); };
  ok.keys.k = ok.keys.ArrowLeft = function () { return step(-1); };
  ok.keys.ArrowDown = function () { return step(rowWidth()); };
  ok.keys.ArrowUp = function () { return step(-rowWidth()); };

  // The panel, only once it shows the pick. Right after a j the old one is
  // still on screen until the new one lands: f, e and Enter wait for it
  // rather than act on the item just left.
  function pickedPanel() {
    var onScreen = panel && panel.querySelector("[data-panel]");
    var id = current();
    return onScreen && id && onScreen.dataset.panel === id ? panel : null;
  }

  // Enter: the original in another tab (library, Ocio), or the idea's screen.
  // On an item's own checkbox (select.js) it is that item's Enter: one not
  // picked yet is picked first, as a click on it would.
  ok.keys.Enter = function () {
    var active = document.activeElement;
    var box = active && active.type === "checkbox" && active.closest("#items > li.item");
    if (box && idOf(box) !== current()) { pick(idOf(box)); return; }
    if (!panel) {
      var li = itemOf(current());
      var hit = li && li.querySelector("a.hit");
      if (!hit) return false;
      location.href = hit.href;
      return;
    }
    var open = pickedPanel() && panel.querySelector("a[data-open]");
    if (!open) return false;
    window.open(open.href, "_blank", "noopener");
    toast((texts.opening || "").replace("%1", new URL(open.href).hostname.replace(/^www\./, "")));
  };

  // f: the panel's ★, as a click (the library only: Ocio has no favourites).
  ok.keys.f = function () {
    var star = mode === "library" && pickedPanel() && panel.querySelector("form.push button.star");
    if (!star) return false;
    star.click();
  };

  // e: the panel's "+ tag" (the keydown's default is prevented, so no "e").
  ok.keys.e = function () {
    var box = pickedPanel() && document.getElementById("tag-add");
    if (!box || !panel.contains(box)) return false;
    box.focus();
  };

  // v: the layout that is not on. Ocio has none: nothing happens.
  ok.keys.v = function () {
    var other = list.querySelector("a[data-view]:not(.on)");
    if (!other) return false;
    other.click();
  };

  ok.list = {
    current: current,
    pick: pick,
    next: neighbour,
    shown: shown,
    // No pick left (a bulk action took every one away): the empty panel.
    empty: emptyPanel,
    // After an undo or a bulk action: the same list again, and `id` opened
    // (the first one restored, or the one after those deleted).
    reload: function (id) {
      var done = loadList(here().href, true, "refresh");
      if (id && panel) loadPanel(id, true);
      else if (id && done) done.then(function () { if (itemOf(id)) markCurrent(id); });
      return done;
    },
  };

  // --- the pick in the URL -------------------------------------------------
  // With no sel, a reload of the list would open whatever is first by then
  // (a batch adds links on top): the pick shown is written down.
  (function () {
    var items = document.getElementById("items");
    var url = here();
    // Not beside the catalog's panel (/ocio?buscar=X): #items still holds the
    // first card, but the panel shows the search, and buscar wins on reload.
    var catalog = panel && panel.querySelector('[data-panel=""]');
    if (panel && items && items.dataset.current && !url.searchParams.get("sel") &&
        !url.searchParams.get("buscar") && !catalog) {
      url.searchParams.set("sel", items.dataset.current);
      history.replaceState(null, "", url.pathname + url.search);
    }
  })();

  litChipInView();
  observe();
  watch();
})();
