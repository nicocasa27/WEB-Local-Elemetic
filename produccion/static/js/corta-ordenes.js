/* Órdenes de Corta.mx.
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
