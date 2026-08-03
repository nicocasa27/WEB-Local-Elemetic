/* Equipos de trabajo.
 *
 * Estaba escrito dentro de la plantilla.
 */

window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form.js-confirm-delete").forEach((f) => {
    f.addEventListener("submit", (e) => {
      const ok = confirm("¿Seguro que deseas eliminar? Esta acción no se puede deshacer.");
      if (!ok) e.preventDefault();
    });
  });
});
