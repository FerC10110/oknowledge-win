// An idea's column of links: search as you type, and the general box.
//
// Progressive enhancement. Without this file the search box is a GET form
// that reloads the idea with ?q=, and the boxes are read by the server
// either way: it ignores the cards' boxes when the general one is off.
(function () {
  "use strict";

  var input = document.getElementById("field-find");
  var out = document.getElementById("idea-found");
  if (input && out) {
    var timer = null;
    var asked = 0;
    // Only the newest answer is shown: a slow reply to an older query must
    // not land over the results of the one typed after it.
    var run = function () {
      var mine = ++asked;
      fetch(input.dataset.results + "?q=" + encodeURIComponent(input.value),
            { headers: { "X-Requested-With": "search" } })
        .then(function (answer) {
          if (!answer.ok) throw new Error(answer.status);
          return answer.text();
        })
        .then(function (html) {
          if (mine === asked) out.innerHTML = html;
        })
        .catch(function () {});
    };
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(run, 250);
    });
    input.form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearTimeout(timer);
      run();
    });
  }

  var all = document.querySelector('input[name="with_links"]');
  if (all) {
    var sync = function () {
      document.querySelectorAll('input[name="use"]').forEach(function (box) {
        box.disabled = !all.checked;
        var card = box.closest(".card");
        if (card) card.classList.toggle("unused", !all.checked);
      });
    };
    all.addEventListener("change", sync);
    sync();
  }
})();
