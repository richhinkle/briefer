// Drag-to-reorder sections; write the resulting order into the hidden `order`
// field on every submit so the server rebuilds the list in the new order.
(function () {
  var list = document.getElementById("sections");
  var orderField = document.getElementById("order");
  var form = document.getElementById("brief-form");
  if (!list || !orderField || !form) return;

  if (window.Sortable) {
    Sortable.create(list, { handle: ".handle", animation: 150 });
  }

  function syncOrder() {
    var idx = [].map.call(list.querySelectorAll(".section"), function (el) {
      return el.getAttribute("data-index");
    });
    orderField.value = idx.join(",");
  }

  form.addEventListener("submit", syncOrder);
  syncOrder();
})();

// On-demand preview: previews aren't rendered on page load. Clicking "Preview"
// evicts the server caches (?fresh=1) and busts the browser cache with a
// timestamp so the <img> refetches a freshly rendered brief.
(function () {
  var btn = document.getElementById("refresh-preview");
  var img = document.getElementById("preview-img");
  var empty = document.getElementById("preview-empty");
  if (!btn || !img) return;

  btn.addEventListener("click", function () {
    var base = btn.getAttribute("data-base");
    var label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Rendering…";

    function done() {
      btn.disabled = false;
      btn.textContent = label;
      img.onload = img.onerror = null;
    }
    img.onload = function () {
      if (empty) empty.hidden = true;
      img.hidden = false;
      done();
    };
    img.onerror = done;
    img.src = base + "?fresh=1&t=" + Date.now();
  });
})();
