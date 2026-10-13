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
    document.querySelectorAll("details.filters, details.paste").forEach(function (d) {
      d.open = open;
    });
  }
  function settle() {
    if (!phone.matches) return;
    fold(false);
    var search = document.querySelector("header input[type=search]");
    if (search) { search.removeAttribute("autofocus"); search.blur(); }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", settle);
  } else {
    settle();
  }
  // Turned sideways into a wide screen: nothing may stay hidden behind a
  // summary the desktop layout does not draw.
  phone.addEventListener("change", function (event) {
    if (!event.matches) fold(true);
  });
})();
