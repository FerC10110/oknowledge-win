// The library without reloads (docs/2026-10-14-rediseno-biblioteca-design.md
// §1, §4, §6, §7). Every action here has a plain link or form under it; this
// only swaps the column that changed and keeps the URL in step.
(function () {
  "use strict";
  var list = document.getElementById("list");
  var panel = document.getElementById("panel");
  var form = document.getElementById("unified");
  var field = document.getElementById("field-q");
  if (!list || !panel || !form || !field) return;
  var texts = document.body.dataset;
  var STORE = "oknowledge.vista";
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
    return fetch("/lista" + target.search)
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
        if (moved) {
          var still = here().searchParams.get("sel");
          if (still) markCurrent(still);
        } else {
          var current = items ? items.dataset.current : "";
          var shown = panel.querySelector("[data-panel]");
          if (current && (!shown || shown.dataset.panel !== current)) loadPanel(current, true);
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

  // `gone` is for a link that may have stopped existing while it was shown
  // (an analysis that failed): its 404 empties the panel instead of
  // reloading the page, which would wipe the toast that just said so.
  var shownAsked = 0;
  function loadPanel(id, gone) {
    var mine = ++shownAsked;
    var url = here();
    url.searchParams.set("sel", id);
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
      })
      .catch(function () { if (mine === shownAsked) location.href = url.href; });
  }

  function emptyPanel() {
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
  try {
    var saved = localStorage.getItem(STORE);
    var now = here();
    if (saved === "lista" && !now.searchParams.get("vista")) {
      now.searchParams.set("vista", "lista");
      loadList(now.href);
    }
  } catch (e) { /* no storage: the URL decides */ }

  // --- the unified field ---------------------------------------------------
  var timer = null;
  field.addEventListener("input", function () {
    clearTimeout(timer);
    var text = field.value;
    var saving = saves(text);
    form.classList.toggle("saving", saving);
    if (saving) return;
    timer = setTimeout(function () {
      var url = new URL("/", location.href);
      var q = text.trim().split(/\s+/).join(" ");
      if (q) url.searchParams.set("q", q);
      var vista = here().searchParams.get("vista");
      if (vista) url.searchParams.set("vista", vista);
      loadList(url.href);
    }, 250);
  });

  form.addEventListener("submit", function (event) {
    if (event.submitter && event.submitter.id === "save-link") return;   // a real POST
    event.preventDefault();
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
    var picked = shownAsked;            // see loadList: a pick since wins
    closeMenus();
    fetch(target.action, { method: "POST", body: data })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        var page = new DOMParser().parseFromString(html, "text/html");
        var said = page.querySelector(".toast");
        toast(said ? said.textContent : "");
        var shown = panel.querySelector("[data-panel]");
        if (shown && picked === shownAsked) loadPanel(shown.dataset.panel, true);    // deleted: gone
        loadList(here().href, true);
      })
      .catch(function () { toast(texts.saveFailed); });
  });

  // --- links being read -----------------------------------------------------
  var watched = {};
  function watch() {
    list.querySelectorAll("[data-working]").forEach(function (li) {
      var id = li.dataset.working;
      if (watched[id]) return;
      watched[id] = setInterval(function () {
        fetch("/item/" + encodeURIComponent(id) + "/state")
          .then(function (r) { return r.json(); })
          .then(function (state) {
            if (state.working) return;
            clearInterval(watched[id]);
            delete watched[id];
            toast(state.status === "failed" ? texts.failed : texts.done);
            // What the user picked, not what is on screen: that is still the
            // old panel while a newer pick is on its way.
            var shown = panel.querySelector("[data-panel]");
            var items = document.getElementById("items");
            if (shown && shown.dataset.panel === id && items &&
                items.dataset.current === id) loadPanel(id, true);
            loadList(here().href, true);
          })
          .catch(function () { /* try again in three seconds */ });
      }, 3000);
    });
  }

  observe();
  watch();
})();
