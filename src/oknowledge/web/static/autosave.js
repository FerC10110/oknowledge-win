// Saving as you go (docs/2026-10-14-rediseno-ocio-ideas-design.md §1).
// Every form under it works without this file: each keeps a Save button
// marked data-nojs, which this hides. A text field with data-autosave posts
// itself 1 s after the last key or when it loses focus; every post asks for
// JSON, so the routes answer {"ok": ...} instead of redirecting.
(function () {
  "use strict";
  var DELAY = 1000;
  var texts = document.body.dataset;

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

  // The answer of a write, as JSON. Anything that is not {"ok": true} is an
  // error with the server's words, or the page's "could not be saved".
  function answer(r) {
    return r.json().catch(function () { return { ok: false }; }).then(function (body) {
      if (r.ok && body.ok) return body;
      var error = new Error(body.error || texts.saveFailed || "");
      error.status = r.status;
      throw error;
    });
  }

  // `keep`: the request outlives the page, for what is sent while leaving it.
  function send(url, data, keep) {
    return fetch(url, { method: "POST", body: data, keepalive: keep === true,
                        headers: { Accept: "application/json" } }).then(answer);
  }

  function post(form, submitter) {
    return send(form.action, new FormData(form, submitter || undefined));
  }

  function watchField(field) {
    if (field.dataset.bound) return;
    field.dataset.bound = "1";
    var saved = field.value;        // what the server has, as far as we know
    var timer = null;
    var inflight = false;
    var again = false;
    var outgoing = null;            // the newest text sent, until it fails
    var indicator = field.dataset.indicator ? document.querySelector(field.dataset.indicator) : null;

    function say(state) {
      if (indicator) indicator.textContent = state ? (indicator.dataset[state] || "") : "";
    }

    // One request in flight per field. A flush asked for while one is out
    // waits for it, and then sends what the field holds by then: the newest
    // text always lands last, and a reply never writes the field.
    function flush(keep) {
      clearTimeout(timer);
      timer = null;
      if (field.value === saved) return;
      if (field.hasAttribute("data-skip-empty") && !field.value.trim()) return;
      if (inflight) { again = true; return; }
      inflight = true;
      var sending = field.value;
      outgoing = sending;
      var data = new FormData();
      data.set(field.name, sending);
      say("saving");
      send(field.dataset.autosave, data, keep)
        .then(function (body) {
          if (outgoing === sending) saved = sending;   // not when leave() sent a newer one
          else return;
          say(field.value === saved ? "saved" : "saving");
          if (body.notice) toast(body.notice);         // saved, with a warning
          field.dispatchEvent(new CustomEvent("saved", { bubbles: true }));
        })
        .catch(function (error) {
          if (outgoing === sending) outgoing = null;
          say("");
          toast(error.message || texts.saveFailed);    // the text stays in the field
          field.dispatchEvent(new CustomEvent("savefailed",
                                              { bubbles: true, detail: { status: error.status } }));
        })
        .then(function () {
          inflight = false;
          if (again) { again = false; flush(); }
        });
    }

    // Leaving the page -- closing the tab, going back, switching away -- the
    // second of waiting would be lost: what is not saved goes now, in a
    // request that outlives the page, unless that text is already on its way.
    function leave() {
      clearTimeout(timer);
      timer = null;
      var value = field.value;
      if (value === saved || value === outgoing) return;
      if (field.hasAttribute("data-skip-empty") && !value.trim()) return;
      if (!inflight) { flush(true); return; }
      // An older text is out: this cannot wait for it, the page may be gone.
      again = false;
      outgoing = value;
      var data = new FormData();
      data.set(field.name, value);
      send(field.dataset.autosave, data, true)
        .then(function () {
          if (outgoing !== value) return;
          saved = value;
          say(field.value === saved ? "saved" : "saving");
        })
        .catch(function () { if (outgoing === value) outgoing = null; });
    }

    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(flush, DELAY);
    }

    field.addEventListener("input", schedule);
    field.addEventListener("blur", function () { flush(); });
    window.addEventListener("pagehide", leave);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") leave();
    });
    if (field.form) {
      field.form.addEventListener("submit", function (event) {
        event.preventDefault();          // Enter in the title: save now, stay here
        flush();
      });
    }
    // A value from elsewhere (the model named the idea): taken only when
    // nobody is typing in the field and nothing of theirs is unsaved.
    field.oknowledgeSettle = function (value) {
      if (document.activeElement === field || field.value !== saved || inflight) return false;
      field.value = value;
      saved = value;
      return true;
    };
  }

  function bind(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    scope.querySelectorAll("[data-autosave]").forEach(watchField);
  }

  window.oknowledge = { toast: toast, post: post, bind: bind };
  bind(document);
})();
