// Multi-selection (docs/2026-10-14-rediseno-modales-teclado-design.md §5):
// the ticked ids, the bar, and its actions sent as JSON. Lives across the
// list's reloads (the oknowledge:list event of shell.js): a refresh keeps what is
// still on screen, a new filter clears. Without JavaScript nothing of this
// is drawn.
(function () {
  "use strict";
  var ok = window.oknowledge || (window.oknowledge = {});
  ok.keys = ok.keys || {};
  var bar = document.getElementById("bulk");
  var list = document.getElementById("list");
  if (!bar || !list) return;
  var picked = [];          // ids, in the order they were ticked
  var sending = false;      // a bulk action is out: the next waits for its answer

  function boxes() {
    return Array.prototype.slice.call(list.querySelectorAll('input[type="checkbox"][name="ids"]'));
  }

  function draw() {
    var n = picked.length;
    boxes().forEach(function (box) {
      box.checked = picked.indexOf(box.value) >= 0;
      var li = box.closest("li.item");
      if (li) li.classList.toggle("picked", box.checked);
    });
    list.classList.toggle("picking", n > 0);
    bar.querySelector("[data-count]").textContent =
      n === 1 ? bar.dataset.one : (bar.dataset.many || "").replace("%1", n);
    if (!n) ok.closeMenus();
    bar.hidden = n === 0;
  }

  function toggle(id, on) {
    var at = picked.indexOf(id);
    if (on && at < 0) picked.push(id);
    if (!on && at >= 0) picked.splice(at, 1);
    draw();
  }

  // Every way out of a selection (✕, Esc, a new filter, a bulk action that
  // went through, Cancelar) is this one: the phone's mode goes with it.
  function clear() {
    picked = [];
    mode(false);
    draw();
  }

  // --- the phone's mode (docs/2026-10-15-rediseno-celular-design.md §9) ------------
  // No hover, so no checkbox to find: "Seleccionar" turns each tap on an
  // item into a tick until one of clear()'s ways out.
  function selecting() { return list.classList.contains("selecting"); }

  // The button lives in the list head, which every list reload draws again.
  function drawMode() {
    var button = list.querySelector("[data-select-mode]");
    if (!button) return;
    var on = selecting();
    if (!button.dataset.off) button.dataset.off = button.textContent;
    button.textContent = on ? button.dataset.on : button.dataset.off;
    button.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function mode(on) {
    list.classList.toggle("selecting", on);
    drawMode();
  }

  // On #list, in the capture phase: before shell.js's click on the document,
  // so a tap in the mode ticks and never opens the item.
  list.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("[data-select-mode]")) {
      event.preventDefault();
      if (selecting()) clear(); else mode(true);
      return;
    }
    if (!selecting()) return;
    var hit = target.closest("a.hit");
    if (!hit) return;
    event.preventDefault();
    event.stopPropagation();
    var li = hit.closest("li.item");
    var box = li && li.querySelector('input[type="checkbox"][name="ids"]');
    if (box) toggle(box.value, !box.checked);      // one being analysed has none
  }, true);

  list.addEventListener("change", function (event) {
    var box = event.target;
    if (box.matches && box.matches('input[type="checkbox"][name="ids"]')) toggle(box.value, box.checked);
  });

  bar.addEventListener("click", function (event) {
    if (event.target.closest("[data-clear]")) { event.preventDefault(); clear(); }
  });

  // The list was drawn again: a new filter clears, the same list keeps
  // the ids still on screen and forgets the rest.
  list.addEventListener("oknowledge:list", function (event) {
    if (event.detail && event.detail.reason === "filter") { clear(); return; }
    var there = boxes().map(function (box) { return box.value; });
    picked = picked.filter(function (id) { return there.indexOf(id) >= 0; });
    draw();
    drawMode();
  });

  // --- sending -------------------------------------------------------------------
  bar.addEventListener("submit", function (event) {
    event.preventDefault();
    submit(event.submitter);
  });

  // While one is out the bar is off: a second ⌫ or click on Borrar would
  // split the lot, and part of it would have no Deshacer.
  function busy(on) {
    sending = on;
    bar.classList.toggle("sending", on);
    Array.prototype.forEach.call(bar.querySelectorAll("button"), function (b) { b.disabled = on; });
  }

  function submit(submitter) {
    if (!picked.length || sending) return;
    var url = (submitter && submitter.getAttribute("formaction")) || bar.getAttribute("action");
    bar.elements.back.value = location.pathname + location.search;
    var data = new FormData(bar, submitter || undefined);
    data.delete("ids");
    picked.forEach(function (id) { data.append("ids", id); });
    ok.closeMenus();
    var deleting = /\/bulk\/delete$/.test(url);
    // A delete picks the one after those deleted. A change to the pick
    // itself (its ★, its category...) redraws its panel once the list is
    // back, or, if the change took it out of this list, picks the one after.
    var cur = ok.list.current();
    var mine = picked.indexOf(cur) >= 0;
    var after = deleting || mine ? pickAfter() : "";
    busy(true);
    ok.send(url, data)
      .then(function (body) {
        busy(false);
        clear();
        if (deleting) {
          ok.offerUndo(body.notice, body.undo, function (back) {
            ok.list.reload(back.restored && back.restored[0]);
          });
        } else {
          ok.toast(body.notice);
        }
        if (bar.elements.new_category) bar.elements.new_category.value = "";
        if (deleting || !mine) {
          var settled = ok.list.reload(after);
          // Every listed one deleted: nothing to pick, the panel empties.
          if (settled) settled.then(function () { if (mine && !after) ok.list.empty(); });
          return;
        }
        var back = ok.list.reload();
        if (back) back.then(function () {
          var next = listed(cur) ? cur : after;
          if (next) ok.list.pick(next); else ok.list.empty();
        });
      })
      .catch(function (error) {
        busy(false);
        ok.toast(error.message);
        // All of them gone meanwhile: the list says so.
        if (error.status === 404) { clear(); ok.list.reload(); }
      });
  }

  function listed(id) {
    return ok.list.shown().some(function (li) { return li.id.replace(/^(card|idea)-/, "") === id; });
  }

  // After a delete: the pick stays if it was not ticked; else the first
  // item after it that was not, else the one before.
  function pickAfter() {
    var id = ok.list.current();
    if (!id || picked.indexOf(id) < 0) return id;
    var items = ok.list.shown().map(function (li) { return li.id.replace(/^(card|idea)-/, ""); });
    var at = items.indexOf(id);
    for (var i = at + 1; i < items.length; i++) if (picked.indexOf(items[i]) < 0) return items[i];
    for (var j = at - 1; j >= 0; j--) if (picked.indexOf(items[j]) < 0) return items[j];
    return "";
  }

  // --- keys (spec §4) --------------------------------------------------------------
  // x: the picked item, when it has a box (an "Analysing…" one has not).
  ok.keys.x = function () {
    var id = ok.list && ok.list.current();
    var has = id && boxes().some(function (box) { return box.value === id; });
    if (!has) return false;
    toggle(id, picked.indexOf(id) < 0);
  };

  // A held key repeats: only the first press deletes.
  ok.keys.Backspace = ok.keys.Delete = function (event) {
    if (!picked.length) return false;
    if (sending || (event && event.repeat)) return;
    submit(bar.querySelector('button[formaction="/bulk/delete"]'));
  };

  // Last in Esc's chain (app.js): no modal, no menu, no field.
  ok.keys.Escape = function () {
    if (!picked.length && !selecting()) return false;
    clear();
  };

  draw();
  drawMode();
})();
