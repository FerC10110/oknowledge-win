// Settings (docs/2026-10-14-rediseno-modales-teclado-design.md §3.1): the
// same fragment on the page /settings and in the modal, bound here. Every
// change saves itself; without this script each pane has its Save button
// and the tabs are links.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  var texts = document.body.dataset;
  var modal = document.getElementById("settings-modal");
  var lastTab = "";
  var renamesOut = [];        // every rename sent since the modal opened: each true if it moved notes
  var opening = 0;            // the modal's last load: an older one landing late is dropped
  var SAVE_MS = 15000;        // a save with no answer by then has failed
  // A rename moves every note of the category and may take long: the ✕ and
  // the count links wait for it up to this long, then go on, saying its
  // result is unknown (final review M-2).
  var RENAME_MS = 60000;
  var renamesHeld = [];       // the same renames, as the links wait for them: bounded
  // This page's id and its revs, sent with every pane's save: the server
  // writes a pane only if no newer save of that pane from this page landed
  // first, so a save that timed out and runs late cannot put older values
  // back (final review M-1). Another page's saves are never compared.
  var PAGE = (function () {
    try { if (window.crypto && crypto.randomUUID) return crypto.randomUUID(); } catch (e) { /* below */ }
    return Date.now().toString(36) + Math.random().toString(36).slice(2) +
           Math.random().toString(36).slice(2);
  })();
  var lastRev = 0;

  // Forms whose last save failed, with what was said (the page's ✕ says it
  // again instead of leaving, once).
  var unsaved = [];
  function failed(form, message) {
    unsaved = unsaved.filter(function (u) { return u.form !== form; });
    unsaved.push({ form: form, message: message });
  }
  function landed(form) {
    unsaved = unsaved.filter(function (u) { return u.form !== form; });
  }

  // Saves still out. A redraw waits for them: drawn before one lands, the
  // box would show the old value and the next change would send it back.
  var inflight = 0;
  var idle = [];
  function hold() { inflight += 1; }
  function release() {
    inflight -= 1;
    if (!inflight) idle.splice(0).forEach(function (resume) { resume(); });
  }
  function whenIdle() {
    return inflight ? new Promise(function (resume) { idle.push(resume); }) : Promise.resolve();
  }

  function toast(text) { if (text && ok.toast) ok.toast(text); }

  // A save that never answers fails, so the redraws waiting for it go on.
  // The error says it timed out: the answer may still come (see autosave).
  function within(promise, ms) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        var error = new Error(texts.saveFailed || "");
        error.late = true;
        reject(error);
      }, ms || SAVE_MS);
      promise.then(function (body) { clearTimeout(timer); resolve(body); },
                   function (error) { clearTimeout(timer); reject(error); });
    });
  }

  // The toast lives inside the open modal (app.js): drawing the modal's
  // content takes it out, and this puts it back.
  function raiseToast() { if (ok.raiseToast) ok.raiseToast(); }

  // --- tabs -----------------------------------------------------------------------
  function showTab(root, key, onPage) {
    root.querySelectorAll("a[data-settings-tab]").forEach(function (a) {
      var on = a.dataset.settingsTab === key;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    root.querySelectorAll("section[data-settings-pane]").forEach(function (pane) {
      pane.hidden = pane.dataset.settingsPane !== key;
    });
    lastTab = key;
    if (onPage) history.replaceState(history.state, "", "/settings?tab=" + encodeURIComponent(key));
  }

  // --- the model pickers ----------------------------------------------------------
  // A model picked is added at the end of its box (the order they are
  // tried) and the pane saves. The picker's own change stops here: the
  // pane's change listener would save a second time.
  function pickers(root) {
    root.querySelectorAll("select.add-model").forEach(function (picker) {
      var box = picker.form && picker.form.elements[picker.dataset.for];
      if (!box) return;
      picker.hidden = false;
      picker.addEventListener("change", function (event) {
        event.stopPropagation();
        var model = picker.value;
        if (!model) return;
        var models = box.value.split(",").map(function (m) { return m.trim(); })
                              .filter(function (m) { return m; });
        if (!models.includes(model)) models.push(model);
        box.value = models.join(", ");
        picker.value = "";
        picker.form.requestSubmit();
      });
    });
  }

  // --- a pane saves itself -----------------------------------------------------------
  // The whole pane, on every change. One request at a time: a change while
  // one is out is sent when it lands, with what the pane holds by then. The
  // same pane twice in a row (Enter fires change and submit) is sent once.
  function autosave(form) {
    var busy = false;
    var again = false;
    var lastSent = "";
    var newest = 0;             // the rev of this pane's newest save
    function save() {
      if (busy) { again = true; return; }
      busy = true;
      hold();
      send();
    }
    function send() {
      var data = new FormData(form);
      var payload = new URLSearchParams(data).toString();
      if (payload === lastSent) { done(); return; }
      lastSent = payload;
      lastRev = Math.max(Date.now(), lastRev + 1);
      var rev = newest = lastRev;
      data.set("rev", String(rev));
      data.set("page", PAGE);
      var sent = ok.send(form.getAttribute("action"), data);
      within(sent)
        .then(function (body) {
          // Stale for the pane's newest save: nothing newer of ours landed,
          // and this was not written either.
          if (body.stale) { var error = new Error(texts.saveFailed || ""); throw error; }
          saved(body);
        })
        .catch(function (error) {
          lastSent = "";
          failed(form, error.message);
          toast(error.message);
          // Timed out, it may still land: then it saved after all (the
          // error goes, and a new interface language still reloads) --
          // unless a newer save of the pane went since: what that one
          // said stands, and a stale answer wrote nothing.
          if (error.late) {
            sent.then(function (body) { if (!body.stale && rev === newest) saved(body); },
                      function () {});
          }
        })
        .then(done);
    }
    function saved(body) {
      landed(form);
      if (body.reload) { location.reload(); return; }
      toast(body.notice);
      syncKeep(form);
    }
    function done() {
      if (again) { again = false; send(); return; }
      busy = false;
      release();
    }
    form.addEventListener("change", save);
    form.addEventListener("submit", function (event) { event.preventDefault(); save(); });
  }

  // "Keep by default" saved: the unified field's Full | Summary says the same.
  function syncKeep(form) {
    var picked = form.querySelector('input[name="default_content"]:checked');
    if (!picked) return;
    var same = document.querySelector('#unified input[name="content"][value="' + picked.value + '"]');
    if (same) same.checked = true;
  }

  // --- forms that do something (find models, create .env, analyse) ---------------
  function actions(root, onPage) {
    root.querySelectorAll("form[data-settings-action]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        // The button (it may sit outside the form, form="…") waits for the
        // answer: a double click on "Analizar" is one batch, not two.
        var button = event.submitter || form.querySelector('[type="submit"]');
        if (button && button.disabled) return;
        if (button) button.disabled = true;
        ok.send(form.getAttribute("action"), new FormData(form, event.submitter || undefined))
          .then(function (body) { toast(body.notice); return redraw(root, onPage); })
          .catch(function (error) { toast(error.message); })
          .then(function () { if (button) button.disabled = false; });
      });
    });
  }

  // --- categories ---------------------------------------------------------------------
  // On Enter or on leaving the field, if the name changed. Merging two
  // categories has no Deshacer: it is asked first.
  function renames(root, onPage) {
    var pane = root.querySelector('[data-settings-pane="categorias"]');
    if (!pane) return;
    var known = Array.prototype.map.call(
      pane.querySelectorAll('form[data-settings-rename] input[name="old"]'),
      function (input) { return input.value; });
    pane.querySelectorAll("form[data-settings-rename]").forEach(function (form) {
      var box = form.elements["new"];
      var old = form.elements.old.value;
      var sending = false;
      function rename() {
        var name = box.value.trim();
        if (sending || !name || name === old) return;
        if (known.indexOf(name) >= 0 &&
            !confirm(pane.dataset.merge.replace("%1", old).replace("%2", name))) {
          box.value = old;
          return;
        }
        sending = true;
        var sent = ok.send(form.getAttribute("action"), new FormData(form))
          .then(function (body) {
            landed(form);
            sending = false;
            // Until the redraw lands (or if it fails) the row is the new name.
            known[known.indexOf(old)] = name;
            form.elements.old.value = old = name;
            toast(body.notice);
            redraw(root, onPage);
            // Only notes moved change the list and the sidebar under the modal.
            return body.moved > 0;
          })
          .catch(function (error) {
            sending = false;
            failed(form, error.message);
            toast(error.message);
            return false;
          });
        renamesOut.push(sent);
        renamesHeld.push(within(sent, RENAME_MS).catch(function () {
          var unknown = (pane.dataset.renameUnknown || "").replace("%1", old);
          failed(form, unknown);
          toast(unknown);
          return false;
        }));
      }
      box.addEventListener("change", rename);
      form.addEventListener("submit", function (event) { event.preventDefault(); rename(); });
    });
  }

  // --- the WhatsApp export ----------------------------------------------------------
  // Dropped or chosen, it goes at once to /import, whose page shows the
  // preview and asks before saving anything.
  function drops(root) {
    root.querySelectorAll("form[data-settings-drop]").forEach(function (form) {
      var file = form.querySelector('input[type="file"]');
      if (!file) return;
      file.addEventListener("change", function () { if (file.files.length) form.submit(); });
      form.addEventListener("dragover", function (event) {
        event.preventDefault();
        form.classList.add("over");
      });
      form.addEventListener("dragleave", function () { form.classList.remove("over"); });
      form.addEventListener("drop", function (event) {
        event.preventDefault();
        form.classList.remove("over");
        if (!event.dataTransfer || !event.dataTransfer.files.length) return;
        file.files = event.dataTransfer.files;
        form.submit();
      });
    });
  }

  // The body again, as the server draws it now (models found, a .env
  // created, a category renamed), on the tab that was open.
  function redraw(root, onPage) {
    return whenIdle()
      .then(function () {
        return fetch("/settings/panel?tab=" + encodeURIComponent(lastTab),
                     { headers: { Accept: "text/html" } });
      })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        var box = document.createElement("template");
        box.innerHTML = html.trim();
        var fresh = box.content.querySelector("[data-settings-root]");
        if (!fresh || !root.isConnected) return;
        root.replaceWith(fresh);
        bind(fresh, onPage);
      })
      .catch(function () { /* what is on screen stays; the next change tries again */ });
  }

  // The page's ✕ is a link home; a category's count, a link to its list. The click's blur has just sent the field
  // typed in: leaving at once could cut that save off, so it goes once the
  // saves (and the renames) have landed. If the last save of a form failed,
  // it stays and says so again: leaving would lose the notice and the value.
  // A second ✕ leaves.
  function leave(link) {
    var active = document.activeElement;
    if (active && active.blur) active.blur();
    Promise.all([whenIdle()].concat(renamesHeld))
      .then(function () {
        if (unsaved.length) {
          toast(unsaved[unsaved.length - 1].message);
          unsaved = [];
          return;
        }
        location.href = link.getAttribute("href");
      });
  }

  function bind(root, onPage) {
    if (!root) return;
    root.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    var on = root.querySelector("a[data-settings-tab].on");
    lastTab = on ? on.dataset.settingsTab : lastTab;
    root.addEventListener("click", function (event) {
      var plain = event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey &&
                  !event.altKey;
      var close = onPage && plain && event.target.closest("a[data-close]");
      if (close) { event.preventDefault(); leave(close); return; }
      // Its click blurred a box whose rename is now out (review M2).
      var away = plain && event.target.closest("a[data-leave]");
      if (away) { event.preventDefault(); leave(away); return; }
      var tab = event.target.closest("a[data-settings-tab]");
      if (!tab || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      showTab(root, tab.dataset.settingsTab, onPage);
    });
    pickers(root);
    root.querySelectorAll("form[data-settings]").forEach(autosave);
    actions(root, onPage);
    renames(root, onPage);
    drops(root);
  }

  // --- the modal ---------------------------------------------------------------------
  function unreachable() {
    var p = document.createElement("p");
    p.className = "modal-failed";
    p.textContent = modal.dataset.failed || "";
    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn";
    close.setAttribute("data-close", "");
    close.textContent = texts.close || "";
    var foot = document.createElement("p");
    foot.className = "modal-failed-foot";
    foot.appendChild(close);
    modal.replaceChildren(p, foot);
    raiseToast();
    close.focus();
  }

  ok.openSettings = function (tab) {
    if (!modal) { location.href = "/settings"; return; }
    var key = tab || lastTab || "motores";
    // Refused on the phone over another layer (the detail): nothing to load.
    // Emptied before it opens: showModal() then focuses the dialog itself
    // (drawn with no ring, app.css), not a control of the last content,
    // which goes next and would drop the focus onto the page behind.
    if (!modal.open) {
      modal.replaceChildren();
      if (!ok.openModal(modal)) return;
    }
    renamesOut = [];
    renamesHeld = [];
    var mine = ++opening;
    modal.replaceChildren();
    modal.classList.add("loading");
    raiseToast();                          // the toast sat in what was just emptied
    fetch("/settings/panel?tab=" + encodeURIComponent(key), { headers: { Accept: "text/html" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (!modal.open || mine !== opening) return;
        modal.classList.remove("loading");
        modal.innerHTML = html;
        raiseToast();
        bind(modal.querySelector("[data-settings-root]"), false);
      })
      .catch(function () {
        if (!modal.open || mine !== opening) return;
        modal.classList.remove("loading");
        unreachable();
      });
  };
  ok.bindSettings = bind;

  if (modal) {
    // Esc closes the modal (it is a <dialog>). A text box being typed in
    // loses the focus first, so its change fires and saves.
    modal.addEventListener("cancel", function () {
      var active = document.activeElement;
      if (active && modal.contains(active) && active.blur) active.blur();
    });
    // A category renamed changes the list and the sidebar under the modal.
    // Closing blurs the box first, so renames may still be out: the page
    // reloads once they have all landed, if any moved notes -- and, on the
    // phone, once the modal's history entry has gone (app.js goes back
    // first, delivery 4 Ruling 14).
    modal.addEventListener("close", function () {
      var after = ok.layers ? ok.layers.settled() : Promise.resolve();
      Promise.all(renamesOut).then(function (results) {
        if (results.indexOf(true) >= 0) after.then(function () { location.reload(); });
      });
    });
  }

  // The page /settings: the same fragment, bound in place.
  var page = document.querySelector(".settings-body[data-settings-root]");
  if (page && !(modal && modal.contains(page))) bind(page, true);
})();
