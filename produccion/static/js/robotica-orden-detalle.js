/* Detalle de orden de Robótica.
 *
 * Estaba escrito dentro de la plantilla.
 */

(function () {
  const el = document.getElementById("avanceBarRobot");
  if (!el) return;
  const v = parseFloat(el.getAttribute("data-pct") || "0");
  const pct = Math.max(0, Math.min(100, Number.isFinite(v) ? v : 0));
  el.style.width = `${pct}%`;
})();
