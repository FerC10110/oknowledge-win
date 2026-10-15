// Saving as you go (docs/2026-10-14-rediseno-ocio-ideas-design.md §1).
// Every form under it works without this file: each keeps a Save button
// marked data-nojs, which this hides. A text field with data-autosave posts
// itself 1 s after the last key or when it loses focus; every post asks for
// JSON, so the routes answer {"ok": ...} instead of redirecting.
(function () {
  "use strict";
  var DELAY = 1000;
  // A save with no answer by then has failed: it says so and lets the panel
  // change again (the text stays in its box, and the next try sends it).
  var LIMIT = 15000;
  // keepalive bodies share a 64 KB budget: past it the request fails at
  // once. A bigger text goes as a normal request (sendBeacon has the same
  // budget), which a page that is only hidden still finishes.
  var KEEP_MAX = 60000;
  var texts = document.body.dataset;

  // The one toast is app.js's (spec §2).
  function toast(text) {
    var ok = window.oknowledge;
    if (text && ok && ok.toast) ok.toast(text);
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

  function bytes(text) {
    try { return new Blob([text]).size; } catch (e) { return text.length * 3; }
  }

  // `keep`: the request outlives the page, for what is sent while leaving it
  // -- when its text fits in keepalive's budget.
  function send(url, data, keep, text) {
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        if (controller) controller.abort();
        reject(new Error(texts.saveFailed || ""));
      }, LIMIT);
      var keepalive = keep === true && (text === undefined || bytes(text) <= KEEP_MAX);
      fetch(url, { method: "POST", body: data, keepalive: keepalive,
                   signal: controller ? controller.signal : undefined,
                   headers: { Accept: "application/json" } })
        .then(answer)
        .then(function (body) { clearTimeout(timer); resolve(body); },
              function (error) { clearTimeout(timer); reject(error); });
    });
  }

  function post(form, submitter) {
    return send(form.action, new FormData(form, submitter || undefined));
  }

  // Every box bound, for the page's own listeners (added once, below) and
  // for settle(). A box whose panel was swapped away is dropped once it has
  // nothing left to send.
  var boxes = [];

  function watchField(field) {
    if (field.dataset.bound) return;
    field.dataset.bound = "1";
    var saved = field.value;        // what the server has, as far as we know
    var timer = null;
    var inflight = false;
    var again = false;
    var outgoing = null;            // the newest text sent, until it fails
    var failure = null;             // why the last save failed, until one lands
    var waiting = [];               // settle()s waiting for nothing in flight
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
      // In flight first: the text may go back to what was last saved while
      // a newer one is out, and must still follow it once that one lands.
      if (inflight) { again = true; return; }
      if (field.value === saved) return;
      if (field.hasAttribute("data-skip-empty") && !field.value.trim()) return;
      inflight = true;
      var sending = field.value;
      outgoing = sending;
      var data = new FormData();
      data.set(field.name, sending);
      say("saving");
      var failed = false;
      send(field.dataset.autosave, data, keep, sending)
        .then(function (body) {
          failure = null;
          if (outgoing === sending) saved = sending;   // not when leave() sent a newer one
          else return;
          say(field.value === saved ? "saved" : "saving");
          if (body.notice) toast(body.notice);         // saved, with a warning
          field.dispatchEvent(new CustomEvent("saved", { bubbles: true }));
        })
        .catch(function (error) {
          failed = true;
          failure = error;
          if (outgoing === sending) outgoing = null;
          say("");
          toast(error.message || texts.saveFailed);    // the text stays in the field
          field.dispatchEvent(new CustomEvent("savefailed",
                                              { bubbles: true, detail: { status: error.status } }));
        })
        .then(function () {
          inflight = false;
          // After a failure the round ends: whoever waited is told now, and
          // newer text typed meanwhile goes a second later, as after a key
          // -- not at once, into what just failed, with the wait doubled.
          if (again) {
            again = false;
            if (!failed) flush();
            else if (field.value !== sending) schedule();
          }
          if (!inflight) wake();
        });
    }

    // What settle() is told once nothing is in flight: null when the field
    // holds what the server has (or a failure was overtaken by a save that
    // landed), else why the last save failed.
    function wake() {
      var told = field.value === saved ? null : failure;
      var all = waiting;
      waiting = [];
      all.forEach(function (resolve) { resolve(told); });
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
      send(field.dataset.autosave, data, true, value)
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
    boxes.push({
      field: field,
      leave: leave,
      // Back on the page: what a leave() could not save is sent again now,
      // not only with the next key.
      retry: function () {
        if (timer || inflight || field.value === saved || field.value === outgoing) return;
        flush();
      },
      idle: function () { return !timer && !inflight && field.value === saved; },
      dirty: function () {
        if (timer || inflight) return true;
        // An empty text a field never sends is not waiting to be sent.
        if (field.hasAttribute("data-skip-empty") && !field.value.trim()) return false;
        return field.value !== saved;
      },
      // Send now what waits for the second, and say when it has landed.
      settle: function () {
        return new Promise(function (resolve) {
          flush();
          if (inflight) waiting.push(resolve);
          else resolve(field.value === saved ? null : failure);
        });
      }
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

  // Leaving the page: every box sends what it has not, the ones of a panel
  // swapped away too.
  function leaving() { boxes.forEach(function (box) { box.leave(); }); }
  window.addEventListener("pagehide", leaving);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") leaving();
    else boxes.forEach(function (box) { box.retry(); });
  });

  function under(root) {
    return boxes.filter(function (box) {
      return !root || root === document || !box.field.isConnected ||
             (root.contains ? root.contains(box.field) : true);
    });
  }

  // Before a part of the page is swapped (shell.js's panel): every box under
  // it sends what it has and this resolves when all of them have landed --
  // with null, or the error of one that failed, whose text is still in its
  // field. Boxes already swapped away count too: their text is still going.
  function settle(root) {
    return Promise.all(under(root).map(function (box) { return box.settle(); }))
      .then(function (told) { return told.filter(Boolean)[0] || null; });
  }

  // Whether a box under `root` has text the server does not have yet.
  function dirty(root) {
    return under(root).some(function (box) { return box.dirty(); });
  }

  function bind(root) {
    boxes = boxes.filter(function (box) { return box.field.isConnected || !box.idle(); });
    var scope = root || document;
    scope.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    scope.querySelectorAll("[data-autosave]").forEach(watchField);
  }

  // app.js made window.oknowledge (the toast, the menus, the keys); this
  // adds the saving. Never replaced: every script hangs its part on it.
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.post = post;
  ok.bind = bind;
  ok.settle = settle;
  ok.dirty = dirty;
  bind(document);
})();
