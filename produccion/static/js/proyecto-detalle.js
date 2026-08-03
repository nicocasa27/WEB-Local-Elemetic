/* Detalle de proyecto.
 *
 * Estaba escrito dentro de la plantilla.
 */

window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".js-avance").forEach((el) => {
    const pct = (el.getAttribute("data-pct") || "0").replace(",", ".");
    requestAnimationFrame(() => {
      el.style.width = pct + "%";
    });
  });
});
