// Re-analyse a link without leaving the page you are on.
//
// Progressive enhancement: with this file blocked or broken the
// button is an ordinary form post that works exactly as it did -- it just
// reloads the library and takes you back to the top of it, which is the thing
// this file exists to avoid.
//
// While the work runs the button spins. The spin is not a guess: the server is
// asked, every few seconds, whether anything is still holding that link.
(function () {
  "use strict";

  var POLL = 3000;          // a link takes tens of seconds; this is not a race
  var GRACE = 20000;        // before the background task reaches the lock
  var LIMIT = 15 * 60000;   // a server killed mid-run would spin for ever

  function state(link) {
    return fetch("/item/" + encodeURIComponent(link) + "/state")
      .then(function (answer) {
        if (!answer.ok) throw new Error(answer.status);
        return answer.json();
      });
  }

  function stop(form, status) {
    form.classList.remove("working");
    form.querySelector("button").disabled = false;
    if (status === "ok") {
      // Analysed: the one button that would overwrite an analysis belongs on
      // the note's own page, behind its confirmation.
      form.remove();
      return;
    }
    var failed = document.body.dataset.redoFailed;
    if (failed && status && status !== "pending") {
      form.querySelector("button").title = failed;
    }
  }

  function watch(form, link) {
    var began = Date.now();
    var sawWork = false;

    (function again() {
      window.setTimeout(function () {
        if (Date.now() - began > LIMIT) return stop(form, null);
        state(link).then(function (answer) {
          if (answer.working) {
            sawWork = true;
            return again();
          }
          // Not working *yet* is not the same as finished: the task may not
          // have reached the lock. Only a run we have seen, or a grace long
          // past, ends the spin.
          if (!sawWork && Date.now() - began < GRACE) return again();
          stop(form, answer.status);
        }).catch(function () {
          // The server went away, or answered nonsense. Leave the button
          // usable rather than spinning over nothing.
          stop(form, null);
        });
      }, POLL);
    })();
  }

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("form.redo");
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    if (form.classList.contains("working")) return;
    form.classList.add("working");
    form.querySelector("button").disabled = true;

    // The header is what tells the server this click is staying on the page:
    // it answers 204 instead of the redirect the plain form gets.
    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "redo" },
    }).then(function (answer) {
      if (!answer.ok) throw new Error(answer.status);
      watch(form, form.dataset.link);
    }).catch(function () {
      // It never reached the server. Do what the page would have done without
      // this file, so the click is not silently lost.
      form.classList.remove("working");
      form.querySelector("button").disabled = false;
      form.submit();
    });
  });
})();
