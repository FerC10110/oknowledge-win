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

  // True when the dialog was opened.
  function openModal(dialog) {
    if (!dialog || dialog.open) return false;
    // On the phone Ajustes is a layer: back closes it (delivery 4, §8). Not
    // over another layer -- the detail covers the top bar anyway. Forward
    // onto its entry opens it again on that entry, with no new one. Outgrown
    // (past 60rem) it stays open: the desktop's modal.
    if (dialog.id === "settings-modal" && phone()) {
      var ours = history.state && history.state.layer === "settings";
      if (!(ours ? adoptLayer("settings", shutSettings) : openLayer("settings", shutSettings))) return false;
    }
    closeMenus();
    dialog.showModal();
    raise();
    return true;
  }

  function shutSettings(how) {
    var dialog = document.getElementById("settings-modal");
    if (how !== "wide" && dialog && dialog.open) dialog.close();
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
    // A click on the backdrop lands on the <dialog> itself -- and so does a
    // text drag that started in a box and was let go out there: only a press
    // that began on the backdrop too closes it.
    var down = pressed;
    pressed = null;
    if (event.target.matches && event.target.matches("dialog.modal[open]") && down === event.target) {
      event.target.close();
    }
  });

  var pressed = null;        // where the last press began
  document.addEventListener("pointerdown", function (event) { pressed = event.target; }, true);

  // --- the phone (docs/2026-10-15-rediseno-celular-design.md §1, §6.3, §8) -----------
  // One breakpoint for the CSS and every script.
  var narrow = window.matchMedia ? window.matchMedia("(max-width: 60rem)") : null;
  function phone() { return !!(narrow && narrow.matches); }

  // A field whose hint is clipped at 390px has a shorter one for the phone
  // (Ocio's, §15); aria-label keeps the whole.
  function hints() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-short-placeholder]"), function (field) {
      if (field.dataset.longPlaceholder === undefined) field.dataset.longPlaceholder = field.placeholder;
      field.placeholder = phone() ? field.dataset.shortPlaceholder : field.dataset.longPlaceholder;
    });
  }
  hints();
  if (narrow && narrow.addEventListener) narrow.addEventListener("change", hints);
  else if (narrow && narrow.addListener) narrow.addListener(hints);

  // A layer is a screen drawn over the page (the detail, Ajustes) that the
  // browser's back closes. One at a time. `open` gives it a history entry;
  // `adopt` takes one the page started with, which has an entry of its own
  // only if history.state says so (a forward, a reload of our entry).
  var layer = null;          // {name, onClose, pushed}
  var leaving = null;        // a back() under way, as a Promise
  var landed = null;         // ...and its resolve

  function openLayer(name, onClose, url) {
    if (layer) return false;
    // `base`: the entry it was pushed from (a reload checks it, below).
    history.pushState({ layer: name, base: location.href }, "", url || location.href);
    layer = { name: name, onClose: onClose, pushed: true };
    return true;
  }

  function adoptLayer(name, onClose) {
    if (layer) return false;
    if (stale === name) stale = null;
    layer = { name: name, onClose: onClose,
              pushed: !!(history.state && history.state.layer === name) };
    return true;
  }

  // The layer on top goes: by back() when it has its entry (popstate below
  // does the rest), else at once, in place. Never off the site.
  function closeLayer() {
    if (leaving) return leaving;           // one back() per layer, never two
    if (!layer) return Promise.resolve();
    if (layer.pushed && history.state && history.state.layer === layer.name) {
      if (!leaving) leaving = new Promise(function (resolve) { landed = resolve; });
      history.back();
      return leaving;
    }
    var top = layer;
    layer = null;
    top.onClose("close");
    return Promise.resolve();
  }

  // A reload (pull to refresh) on a layer's entry draws the page without
  // that layer unless a script adopts it while the page loads (the detail
  // with ?sel= does). One nobody adopted is a dead step: back from it would
  // change nothing. When it was pushed from this same URL (Ajustes) it goes,
  // by a back() that changes nothing on screen or in the address bar; else
  // (another URL before it) it stays, as a plain entry of this page.
  var stale = (window.history && history.state && history.state.layer) || null;
  document.addEventListener("DOMContentLoaded", function () {
    var state = history.state;
    if (stale && !layer && state && state.layer === stale) {
      if (history.length > 1 && state.base === location.href) history.back();
      else history.replaceState(null, "", location.href);
    }
    stale = null;
  });

  // Back from the bfcache: a back() under way never landed here, and the
  // layer on top may no longer be on its own entry. Start over from what is.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    if (layer) layer.pushed = !!(history.state && history.state.layer === layer.name);
    if (landed) { var done = landed; landed = null; leaving = null; done(); }
    leaving = null;
  });

  window.addEventListener("popstate", function () {
    var top = layer;
    layer = null;
    if (top) top.onClose("back");
    if (landed) { var done = landed; landed = null; leaving = null; done(); }
    // Forward onto Ajustes' entry (after a back, even after a reload): it
    // opens again, or the entry would be a step that shows nothing.
    var state = history.state;
    if (!top && state && state.layer === "settings" && phone() && ok.openSettings) ok.openSettings();
  });

  // A tablet turned past 60rem: the desktop has no layers. The one on top
  // stays drawn (the detail is the panel there, Ajustes the modal) and its
  // entry stops being one, so Esc or ✕ there do not go back. An entry
  // pushed from this same URL (Ajustes) goes by a back() that changes
  // nothing on screen; another (the detail's, with sel) stays, as a plain
  // entry of the page.
  // Back under 60rem with Ajustes still open (the desktop's modal): it is
  // the phone's layer again, with a new entry, so back closes it and never
  // leaves the site.
  function outgrown(event) {
    var dialog = document.getElementById("settings-modal");
    if (event.matches) {
      if (!layer && dialog && dialog.open) openLayer("settings", shutSettings);
      return;
    }
    if (!layer) return;
    var top = layer;
    layer = null;
    var state = history.state;
    if (top.pushed && state && state.layer === top.name) {
      if (state.base === location.href) history.back();
      else history.replaceState(null, "", location.href);
    }
    top.onClose("wide");
  }
  if (narrow && narrow.addEventListener) narrow.addEventListener("change", outgrown);
  else if (narrow && narrow.addListener) narrow.addListener(outgrown);

  // ✕, Esc and a tap on the backdrop close the dialog; on the phone its
  // entry goes with it. Bound now, before settings.js binds its own "close"
  // (which reloads after a rename once this back() has landed, Ruling 14).
  var settingsDialog = document.getElementById("settings-modal");
  if (settingsDialog) settingsDialog.addEventListener("close", function () {
    if (layer && layer.name === "settings") closeLayer();
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
      // A layer (delivery 4, §6.3): after the modal (which closes itself),
      // before the menus -- and a sheet open over it goes with it. A field
      // being typed in is let go first, so its text saves (Ruling 13).
      if (layer && !typing(active)) { closeMenus(); closeLayer(); return; }
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
  ok.phone = phone;
  ok.layers = { open: openLayer, adopt: adoptLayer, close: closeLayer,
                top: function () { return layer ? layer.name : ""; },
                settled: function () { return leaving || Promise.resolve(); } };

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
