// An idea's screen without reloads (spec §2, §2.2). The server draws every
// part; this asks for the screen again and swaps the parts that changed.
// Without it every link and form here still works, a page at a time.
(function () {
  "use strict";
  var root = document.getElementById("idea");
  var ok = window.oknowledge;
  if (!root || !ok) return;
  var id = root.dataset.id;
  var POLL = 3000;
  var TAB_OF = { exists: "existe", improve: "mejoras", expand: "ampliacion", complete: "resumen" };

  function here() { return new URL(location.href); }

  function setParam(name, value, fallback) {
    var url = here();
    if (!value || value === fallback) url.searchParams.delete(name);
    else url.searchParams.set(name, value);
    history.replaceState(null, "", url.pathname + url.search);
  }

  function parse(html) { return new DOMParser().parseFromString(html, "text/html"); }

  // The screen again, as the URL says it now, and the named parts swapped in.
  // Two refreshes can cross on the way back: a part takes only the answer
  // to the newest refresh that asked for it, never an older one.
  var refreshes = 0;
  var newest = {};

  function refresh(ids) {
    var mine = ++refreshes;
    ids.forEach(function (name) { newest[name] = mine; });
    return fetch(location.href, { headers: { Accept: "text/html" } })
      .then(function (r) {
        if (r.status === 404) { gone(); throw new Error("gone"); }
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        var page = parse(html);
        ids.forEach(function (name) {
          if (newest[name] !== mine) return;
          var fresh = page.getElementById(name);
          var old = document.getElementById(name);
          if (fresh && old) old.replaceWith(document.adoptNode(fresh));
        });
        ok.bind(document);
      })
      .catch(function () { /* the next poll or click tries again */ });
  }

  // --- tabs and scope ---------------------------------------------------------
  function openTab(key) {
    document.querySelectorAll("a[data-tab]").forEach(function (a) {
      a.classList.toggle("on", a.dataset.tab === key);
    });
    document.querySelectorAll("[data-pane]").forEach(function (pane) {
      pane.hidden = pane.dataset.pane !== key;
    });
    setParam("pestana", key, "resumen");
  }

  document.addEventListener("click", function (event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    var tab = event.target.closest("a[data-tab]");
    if (tab) { event.preventDefault(); openTab(tab.dataset.tab); return; }
    var scope = event.target.closest("a[data-scope]");
    if (scope) {
      event.preventDefault();
      var menu = scope.closest("details");
      if (menu) menu.open = false;
      setParam("alcance", scope.dataset.scope, "vinculados");
      refresh(["idea-ai", "idea-results"]);
    }
  });

  // --- writes -------------------------------------------------------------------
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches("form[data-json]")) return;
    event.preventDefault();
    var menu = form.closest("details");
    if (menu) menu.open = false;
    ok.post(form, event.submitter)
      .then(function (body) {
        // A write that landed can still have something to say (the indexes
        // could not be rewritten); the start of a run is said by the bar.
        if (body.notice && !form.dataset.runs) ok.toast(body.notice);
        if (form.dataset.runs) started(form.dataset.runs);
        else if (form.hasAttribute("data-links")) { search(); refresh(["idea-ai"]); }
        else refresh(["idea-controls", "idea-tags"]);
      })
      .catch(function (error) {
        ok.toast(error.message);
        if (error.status === 404) whenGone(form.hasAttribute("data-links"));
      });
  });

  // A text that could not be saved because the idea is not there any more.
  document.addEventListener("savefailed", function (event) {
    if (event.detail && event.detail.status === 404) whenGone(false);
  });

  // A 404 to a write: the idea is gone, or only the link it named (a link
  // deleted from the library since the column was drawn). The poll's route
  // tells which; only the first leaves the screen.
  function whenGone(links) {
    fetch("/item/" + encodeURIComponent(id) + "/actions/state",
          { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 404) gone();
        else if (links) search();
      })
      .catch(function () { /* nothing to tell yet */ });
  }

  // --- the column of links --------------------------------------------------
  var box = document.getElementById("links-q");
  var searchAsked = 0;
  var searchTimer = null;

  function search() {
    if (!box) return;
    var mine = ++searchAsked;
    var q = box.value.trim().split(/\s+/).join(" ");
    fetch(box.dataset.results + "?q=" + encodeURIComponent(q))
      .then(function (r) {
        if (r.status === 404) { gone(); throw new Error("gone"); }
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        if (mine !== searchAsked) return;        // a newer search is on its way
        var fresh = parse(html).getElementById("idea-links-body");
        var old = document.getElementById("idea-links-body");
        if (!fresh || !old) return;
        old.replaceWith(document.adoptNode(fresh));
        var count = document.getElementById("idea-links-count");
        if (count) count.textContent = fresh.dataset.linked;
        setParam("q", q, "");
      })
      .catch(function () { /* the next key tries again */ });
  }

  if (box) {
    box.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(search, 250);
    });
    box.form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearTimeout(searchTimer);
      search();
    });
  }

  // --- while the AI works ---------------------------------------------------------
  var bar = document.getElementById("idea-ai");
  var running = (bar && bar.dataset.running || "").split(" ").filter(Boolean);
  var polling = null;
  // Each poll is numbered and only the newest answer counts: one that left
  // before an action started (or that is overtaken by a newer one) does not
  // know about it, and would say it ended.
  var ticks = 0;

  function started(action) {
    ticks += 1;                        // what is on its way predates this run
    if (running.indexOf(action) < 0) running.push(action);
    openTab(TAB_OF[action] || "resumen");
    refresh(["idea-ai", "idea-results"]);
    poll();
  }

  function poll() {
    if (polling || !running.length) return;
    polling = setInterval(tick, POLL);
  }

  function stop() {
    clearInterval(polling);
    polling = null;
  }

  function nameOf(action) {
    var now = document.getElementById("idea-ai") || bar;
    return now.dataset["name" + action.charAt(0).toUpperCase() + action.slice(1)] || action;
  }

  function settleTitle(title) {
    var field = document.getElementById("idea-title");
    if (field && title && field.oknowledgeSettle && field.oknowledgeSettle(title)) {
      field.classList.remove("waiting");
      document.title = title + " - oknowledge";
    }
  }

  function tick() {
    var mine = ++ticks;
    fetch("/item/" + encodeURIComponent(id) + "/actions/state",
          { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (r.status === 404) { stop(); gone(); return null; }
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (state) {
        if (!state) return;
        if (mine !== ticks) return;
        var ended = running.filter(function (a) { return state.running.indexOf(a) < 0; });
        var now = document.getElementById("idea-ai") || bar;
        ended.forEach(function (action) {
          var failed = state.failed.indexOf(action) >= 0;
          ok.toast((failed ? now.dataset.failedAs : now.dataset.doneAs).replace("%1", nameOf(action)));
          if (action === "complete") settleTitle(state.title);
        });
        running = state.running.slice();
        if (ended.length) {
          openTab(TAB_OF[ended[ended.length - 1]] || "resumen");
          refresh(["idea-ai", "idea-results", "idea-tags"]);
        }
        if (!running.length) stop();
      })
      .catch(function () { /* try again in three seconds */ });
  }

  // Hoisted: refresh() and search() call it too.
  function gone() { location.href = "/ideas?notice=no-such-idea"; }

  poll();
})();
