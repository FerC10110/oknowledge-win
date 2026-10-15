// What every page shares (docs/2026-10-14-rediseno-modales-teclado-design.md
// §1-§4): the one toast, the menus, the two modals and the keys. Loaded
// first of the deferred scripts, so the others find window.oknowledge here
// and add their parts to it. Without this file every page still works: the
// server's toast hides itself, menus are <details>, "Ajustes" is a link.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  var texts = document.body.dataset;
  ok.keys = ok.keys || {};

  // --- the toast (spec §2) ------------------------------------------------------
  var timer = null;

  // Kept by reference: inside a modal, a redraw of its content may take it
  // out of the page for a moment, and the next toast puts it back.
  var toastEl = document.getElementById("toast");
  function box() { return toastEl; }

  // Where it is drawn: inside the open modal, if any, so the modal's
  // backdrop does not dim it and the rest of the page being inert under the
  // modal does not take it along (its Deshacer stays clickable); else the
  // page. In the top layer, as a manual popover, shown last: above the modal.
  // Moved, a popover is hidden; shown again (hide, then show) it goes above
  // whatever went up since. Only this file makes it a popover: a [popover]
  // the server drew would stay hidden without JavaScript.
  function place(el) {
    var home = openDialog() || document.body;
    if (el.parentNode !== home) home.appendChild(el);
  }

  function onTop(el) {
    place(el);
    if (!el.showPopover) return;
    if (el.popover !== "manual") el.popover = "manual";
    if (el.matches(":popover-open")) el.hidePopover();
    el.showPopover();
  }

  // A modal opened or closed: the toast goes with it, still on top.
  function raise() {
    var el = box();
    if (!el) return;
    if (el.hidden) place(el); else onTop(el);
  }

  function hide() {
    clearTimeout(timer);
    var el = box();
    if (!el) return;
    if (el.showPopover && el.matches(":popover-open")) el.hidePopover();
    el.hidden = true;
    el.replaceChildren();
  }

  // One at a time: a new toast replaces the last one, and its button.
  function toast(text, opts) {
    var el = box();
    if (!el || !text) return;
    opts = opts || {};
    clearTimeout(timer);
    el.classList.remove("undo");
    el.classList.add("live");
    var words = document.createElement("span");
    words.className = "toast-text";
    words.textContent = text;
    el.replaceChildren(words);
    if (opts.action && opts.run) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = opts.action;
      button.addEventListener("click", function () { hide(); opts.run(); });
      el.appendChild(button);
    }
    el.hidden = false;
    onTop(el);
    timer = setTimeout(hide, opts.ms || (opts.action ? 5000 : 2200));
  }

  // A write, as JSON: the body of {"ok": true}, or an Error with the
  // server's words (or the page's "could not be saved") and the status.
  // No answer at all (offline, server down) is the page's words too, with
  // no status, never the browser's own English.
  function send(url, data) {
    return fetch(url, { method: "POST", body: data || new FormData(),
                        headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; }).then(function (body) {
          if (r.ok && body.ok) return body;
          var error = new Error(body.error || texts.saveFailed || "");
          error.status = r.status;
          throw error;
        });
      }, function () { throw new Error(texts.saveFailed || ""); });
  }

  // Deshacer (spec §6.3). `then(body)` is the screen's own follow-up;
  // without one the list reloads on the first note back, or the page does.
  // Only a failed send is toasted: an error in what follows is a bug of the
  // page and stays one (the console), not a toast.
  function undo(token, then) {
    return send("/undo/" + encodeURIComponent(token))
      .then(function (body) { toast(body.notice); return body; },
            function (error) { toast(error.message); return null; })
      .then(function (body) {
        if (!body) return;
        if (then) then(body);
        else if (ok.list) ok.list.reload(body.restored && body.restored[0]);
        else location.reload();
      });
  }

  function offerUndo(text, token, then) {
    if (!token) { toast(text); return; }
    toast(text, { action: texts.undo, run: function () { undo(token, then); } });
  }

  // --- menus (spec §1): one open at a time; a click outside or Esc closes ----
  function closeMenus() {
    var open = document.querySelectorAll("details.menu[open]");
    open.forEach(function (d) { d.open = false; });
    return open.length > 0;
  }

  document.addEventListener("toggle", function (event) {
    var opened = event.target;
    if (!opened.matches || !opened.matches("details.menu") || !opened.open) return;
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (d !== opened) d.open = false;
    });
  }, true);

  document.addEventListener("click", function (event) {
    if (!event.target.closest("details.menu")) closeMenus();
  });

  // --- the modals (spec §3) ------------------------------------------------------
  function openDialog() { return document.querySelector("dialog[open]"); }

  // "close" does not bubble: caught on its way down.
  document.addEventListener("close", function (event) {
    var el = box();
    if (el && event.target.contains && event.target.contains(el)) raise();
  }, true);

  function openModal(dialog) {
    if (!dialog || dialog.open) return;
    closeMenus();
    dialog.showModal();
    raise();
  }

  function toggleKeys() {
    var help = document.getElementById("keys-help");
    if (!help) return;
    if (help.open) help.close();
    else if (!openDialog()) openModal(help);
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-modal]");
    if (opener && event.button === 0 && !event.metaKey && !event.ctrlKey &&
        !event.shiftKey && !event.altKey) {
      if (opener.dataset.modal === "keys") { event.preventDefault(); toggleKeys(); return; }
      // On /settings itself the link stays a link: the page is the settings.
      if (opener.dataset.modal === "settings" && ok.openSettings &&
          location.pathname !== "/settings") {
        event.preventDefault();
        ok.openSettings();
        return;
      }
    }
    var closer = event.target.closest("dialog [data-close]");
    if (closer) { event.preventDefault(); closer.closest("dialog").close(); return; }
    // A click on the backdrop lands on the <dialog> itself.
    if (event.target.matches && event.target.matches("dialog.modal[open]")) event.target.close();
  });

  // --- keys (spec §4) -----------------------------------------------------------------
  // Where a key is text, not a command. A checkbox or a radio is not typing:
  // with the focus on a ticked box, j, x and ⌫ still work.
  function typing(el) {
    if (!el || el === document.body) return false;
    if (el.isContentEditable) return true;
    var tag = el.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT") return true;
    if (tag !== "INPUT") return false;
    return ["checkbox", "radio", "button", "submit", "reset", "file", "range", "color"]
      .indexOf(el.type) < 0;
  }

  var SECTIONS = { "1": "/", "2": "/ocio", "3": "/ideas" };

  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.isComposing) return;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var key = event.key;
    var dialog = openDialog();
    if (dialog) {
      // The dialog closes itself on Esc; "?" also closes the help.
      if (key === "?" && dialog.id === "keys-help") { event.preventDefault(); dialog.close(); }
      return;
    }
    var active = document.activeElement;
    if (key === "Escape") {
      if (closeMenus()) return;
      if (typing(active)) { active.blur(); return; }
      if (ok.keys.Escape) ok.keys.Escape(event);
      return;
    }
    if (typing(active)) return;
    // Enter on a link, a button or a summary already does its own thing.
    if (key === "Enter" && active && active.closest && active.closest("a, button, summary")) return;
    if (key === "?") { event.preventDefault(); toggleKeys(); return; }
    if (key === "/") {
      var slash = document.querySelector("[data-slash]");
      if (slash) { event.preventDefault(); slash.focus(); if (slash.select) slash.select(); }
      return;
    }
    if (SECTIONS[key]) { event.preventDefault(); location.href = SECTIONS[key]; return; }
    var own = ok.keys[key];
    if (own && own(event) !== false) event.preventDefault();
  });

  ok.toast = toast;
  ok.send = send;
  ok.undo = undo;
  ok.offerUndo = offerUndo;
  ok.closeMenus = closeMenus;
  ok.openModal = openModal;
  ok.raiseToast = raise;

  // The toast the server drew after a redirect: taken over and timed here,
  // and its Deshacer sent as JSON (spec §2). Without this file it is a form.
  (function () {
    var el = box();
    if (!el || el.hidden) return;
    var form = el.querySelector("form.toast-undo");
    el.classList.add("live");
    onTop(el);
    timer = setTimeout(hide, form ? 5000 : 2200);
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var token = decodeURIComponent((form.getAttribute("action") || "").split("/undo/")[1] || "");
      hide();
      undo(token);
    });
  })();
})();
