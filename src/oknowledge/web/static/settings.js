// Settings: a model picked from an engine's list is added at the end of its
// box -- the box holds the models in the order they are tried -- and the
// page is saved at once, so nobody has to scroll down to Save for it.
// Without this script the pickers stay hidden and the boxes are typed by hand.
(function () {
  document.querySelectorAll("select.add-model").forEach(function (picker) {
    var box = picker.form && picker.form.elements[picker.dataset.for];
    if (!box) return;
    picker.hidden = false;
    picker.addEventListener("change", function () {
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
})();
