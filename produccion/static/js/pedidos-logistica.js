/* Logística de pedidos.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 */

document.addEventListener(
  "click",
  function (e) {
    const a = e.target && e.target.closest ? e.target.closest("a.js-pdf-preview") : null;
    if (!a) return;
    e.preventDefault();
    const url = a.getAttribute("data-pdf-url") || a.getAttribute("href") || "";
    const frame = document.getElementById("pdfPreviewFrame");
    if (frame) frame.src = url;
    const modalEl = document.getElementById("pdfPreviewModal");
    if (modalEl && window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  },
  true
);

const pdfModal = document.getElementById("pdfPreviewModal");
if (pdfModal) {
  pdfModal.addEventListener("hidden.bs.modal", function () {
    const frame = document.getElementById("pdfPreviewFrame");
    if (frame) frame.src = "about:blank";
  });
}

document.addEventListener(
  "submit",
  function (e) {
    const form = e.target;
    if (!form || !form.matches) return;
    if (form.matches(".js-confirm-revert")) {
      if (!confirm("¿Confirmas revertir este envío?")) e.preventDefault();
    }
    if (form.matches(".js-confirm-decote-delete")) {
      if (!confirm("¿Confirmas eliminar este pedido de Decote? Esta acción borra historial y archivos.")) e.preventDefault();
    }
  },
  true
);
