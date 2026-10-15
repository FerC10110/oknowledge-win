// What has to run before the first paint, on every page.
//
// The class `js` shows what only works with JavaScript (checkboxes, key
// hints, "Seleccionar"), which is drawn hidden. The phone is CSS now
// (docs/2026-10-15-rediseno-celular-design.md §13); the one breakpoint the
// scripts share is app.js's oknowledge.phone().
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  // A notice is said once, and its Deshacer is offered once. Left in the URL,
  // a reload would say it again. The entry keeps its state: it may be a
  // layer's (docs/2026-10-15-rediseno-celular-design.md §6.3).
  var said = new URL(location.href);
  if (said.searchParams.has("notice") || said.searchParams.has("undo")) {
    ["notice", "n", "m", "undo"].forEach(function (name) { said.searchParams.delete(name); });
    history.replaceState(history.state, "", said.pathname + said.search + said.hash);
  }
})();
