/* Proyectos.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 */

document.querySelectorAll(".js-proyecto-row").forEach((row) => {
  row.addEventListener("dblclick", () => {
    const href = row.getAttribute("data-href");
    if (href) window.location.href = href;
  });
});

const toggleModalEl = document.getElementById("toggleProyectoModal");
const toggleModal = toggleModalEl ? new bootstrap.Modal(toggleModalEl) : null;
let pendingToggleForm = null;

document.querySelectorAll("form.js-toggle-proyecto").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!toggleModal) return;
    e.preventDefault();
    pendingToggleForm = form;
    const nombre = form.getAttribute("data-proyecto") || "";
    const activo = form.getAttribute("data-activo") === "1";
    toggleModalEl.querySelector(".js-proyecto-nombre").textContent = nombre;
    toggleModalEl.querySelector(".js-proyecto-accion").textContent = activo ? "activar" : "desactivar";
    toggleModal.show();
  });
});

if (toggleModalEl) {
  toggleModalEl.querySelector(".js-confirm").addEventListener("click", () => {
    if (pendingToggleForm) pendingToggleForm.submit();
  });
}
