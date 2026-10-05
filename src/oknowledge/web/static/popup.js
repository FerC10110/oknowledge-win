// The card's dialog: read a note without leaving the grid.
//
// Progressive enhancement, not a single-page app. Every trigger is an
// ordinary link to /item/<id>, so with this file blocked or broken the card
// still navigates there. The dialog is only ever an improvement on top.
(function () {
  "use strict";

  var dialog = document.createElement("dialog");
  dialog.className = "popup";
  dialog.innerHTML =
    '<button class="close" type="button" aria-label="' +
    (document.body.dataset.close || "Close") +
    '">×</button><div class="popup-body" aria-live="polite"></div>';
  document.body.appendChild(dialog);

  var body = dialog.querySelector(".popup-body");

  dialog.querySelector(".close").addEventListener("click", function () {
    dialog.close();
  });

  // Clicking the backdrop closes it: the dialog element itself is the only
  // target a click outside the content can land on.
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });

  function open(href, fallback) {
    body.textContent = "…";
    dialog.showModal();
    // credentials: "same-origin" is the default; this is a local server with
    // no login, and the fragment is on the same origin either way.
    fetch(href, { headers: { "X-Requested-With": "popup" } })
      .then(function (answer) {
        if (!answer.ok) throw new Error(answer.status);
        return answer.text();
      })
      .then(function (html) {
        body.innerHTML = html;
      })
      .catch(function () {
        // Anything at all -- offline, a 404, a 503 from an unreadable vault
        // -- and the link does what it would have done without this file.
        dialog.close();
        window.location.href = fallback;
      });
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest("[data-popup]");
    if (!trigger) return;
    // Leave every click a browser gives a meaning of its own: a new tab, a
    // new window, a download, the context menu.
    if (event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    open(trigger.dataset.popup, trigger.getAttribute("href"));
  });
})();
