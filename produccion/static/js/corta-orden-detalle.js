/* Detalle de orden de Corta.mx.
 *
 * Estaba escrito dentro de la plantilla.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

(function () {
  const cp = document.getElementById(cfg.campoCliente);
  if (cp) cp.setAttribute("list", "cortaClienteProyectoList");
})();

        (function () {
          const el = document.getElementById("avanceBarLaser");
          if (!el) return;
          const v = parseFloat(el.getAttribute("data-pct") || "0");
          const pct = Math.max(0, Math.min(100, Number.isFinite(v) ? v : 0));
          el.style.width = `${pct}%`;
        })();
