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
