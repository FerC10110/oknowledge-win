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

  function send(url, data) {
    return fetch(url, { method: "POST", body: data,
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
    var indicator = field.dataset.indicator ? document.querySelector(field.dataset.indicator) : null;

    function say(state) {
      if (indicator) indicator.textContent = state ? (indicator.dataset[state] || "") : "";
    }

    // One request in flight per field. A flush asked for while one is out
    // waits for it, and then sends what the field holds by then: the newest
    // text always lands last, and a reply never writes the field.
    function flush() {
      clearTimeout(timer);
      timer = null;
      if (field.value === saved) return;
      if (field.hasAttribute("data-skip-empty") && !field.value.trim()) return;
      if (inflight) { again = true; return; }
      inflight = true;
      var sending = field.value;
      var data = new FormData();
      data.set(field.name, sending);
      say("saving");
      send(field.dataset.autosave, data)
        .then(function (body) {
          saved = sending;
          say(field.value === saved ? "saved" : "saving");
          if (body.notice) toast(body.notice);         // saved, with a warning
          field.dispatchEvent(new CustomEvent("saved", { bubbles: true }));
        })
        .catch(function (error) {
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

    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(flush, DELAY);
    }

    field.addEventListener("input", schedule);
    field.addEventListener("blur", flush);
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
