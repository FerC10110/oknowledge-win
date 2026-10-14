// The phone layout: what the CSS cannot do by itself.
//
// A <details> drawn open cannot be closed by a stylesheet, so on a narrow
// screen this closes the filters and the paste box, and keeps the search
// box from pulling the keyboard up the moment a page opens. Without this
// file everything stays open, which is how the pages were before it.
(function () {
  "use strict";
  var phone = window.matchMedia("(max-width: 42rem)");
  function fold(open) {
    document.querySelectorAll("details.filters").forEach(function (d) {
      d.open = open;
    });
  }
  function settle() {
    if (!phone.matches) return;
    fold(false);
    letGo();
  }
  // The browser focuses an autofocus box when it gets round to it, which
  // can be after this has run: let go again once the page has loaded.
  function letGo() {
    var search = document.querySelector("header input[type=search]");
    if (search) {
      search.removeAttribute("autofocus");
      if (document.activeElement === search) search.blur();
    }
  }
  window.addEventListener("load", function () { if (phone.matches) letGo(); });
  // And whenever it does it: the first focus the box gets before anybody
  // has touched the page is the browser's, not the user's.
  var touched = false;
  document.addEventListener("pointerdown", function () { touched = true; },
                            { capture: true, once: true });
  var box = document.querySelector("header input[type=search]");
  if (box) {
    box.addEventListener("focus", function () {
      if (!touched && phone.matches) box.blur();
    }, { once: true });
  }
  // Now and not on DOMContentLoaded: this file is the last thing in <body>,
  // so what it folds is already there, and waiting showed it open first.
  settle();
  // Turned sideways into a wide screen: nothing may stay hidden behind a
  // summary the desktop layout does not draw.
  phone.addEventListener("change", function (event) {
    if (!event.matches) fold(true);
  });
})();
