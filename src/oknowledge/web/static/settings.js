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
  var renamed = false;
  var pendingRename = null;   // a rename sent and not answered yet: true if it landed

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
    if (onPage) history.replaceState(null, "", "/settings?tab=" + encodeURIComponent(key));
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
      ok.send(form.getAttribute("action"), data)
        .then(function (body) {
          if (body.reload) { location.reload(); return; }
          toast(body.notice);
          syncKeep(form);
        })
        .catch(function (error) { lastSent = ""; toast(error.message); })
        .then(done);
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
        pendingRename = ok.send(form.getAttribute("action"), new FormData(form))
          .then(function (body) {
            renamed = true;
            sending = false;
            // Until the redraw lands (or if it fails) the row is the new name.
            known[known.indexOf(old)] = name;
            form.elements.old.value = old = name;
            toast(body.notice);
            redraw(root, onPage);
            return true;
          })
          .catch(function (error) { sending = false; toast(error.message); return false; });
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

  function bind(root, onPage) {
    if (!root) return;
    root.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    var on = root.querySelector("a[data-settings-tab].on");
    lastTab = on ? on.dataset.settingsTab : lastTab;
    root.addEventListener("click", function (event) {
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
  function failed() {
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
    close.focus();
  }

  ok.openSettings = function (tab) {
    if (!modal) { location.href = "/settings"; return; }
    var key = tab || lastTab || "motores";
    renamed = false;
    pendingRename = null;
    modal.replaceChildren();
    modal.classList.add("loading");
    ok.openModal(modal);
    fetch("/settings/panel?tab=" + encodeURIComponent(key), { headers: { Accept: "text/html" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) {
        if (!modal.open) return;
        modal.classList.remove("loading");
        modal.innerHTML = html;
        bind(modal.querySelector("[data-settings-root]"), false);
      })
      .catch(function () {
        if (!modal.open) return;
        modal.classList.remove("loading");
        failed();
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
    // Closing blurs the box first, so a rename may still be out: the page
    // reloads once it lands.
    modal.addEventListener("close", function () {
      if (renamed) { location.reload(); return; }
      if (pendingRename) pendingRename.then(function (landed) { if (landed) location.reload(); });
    });
  }

  // The page /settings: the same fragment, bound in place.
  var page = document.querySelector(".settings-body[data-settings-root]");
  if (page && !(modal && modal.contains(page))) bind(page, true);
})();
