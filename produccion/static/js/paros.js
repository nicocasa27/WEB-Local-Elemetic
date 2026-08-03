/* Paros y fallas de máquina.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v || ""; }
function setVal(id, v) { const el = document.getElementById(id); if (el) el.value = v || ""; }

document.querySelectorAll(".js-open-start-paro").forEach((btn) => {
  btn.addEventListener("click", () => {
    setVal("startParoMaquinaId", btn.getAttribute("data-maquina"));
    setText("startParoMaquinaNombre", btn.getAttribute("data-nombre"));
    new bootstrap.Modal(document.getElementById("startParoModal")).show();
  });
});
document.querySelectorAll(".js-open-end-paro").forEach((btn) => {
  btn.addEventListener("click", () => {
    setVal("endParoMaquinaId", btn.getAttribute("data-maquina"));
    setText("endParoMaquinaNombre", btn.getAttribute("data-nombre"));
    new bootstrap.Modal(document.getElementById("endParoModal")).show();
  });
});
document.querySelectorAll(".js-open-start-falla").forEach((btn) => {
  btn.addEventListener("click", () => {
    setVal("startFallaMaquinaId", btn.getAttribute("data-maquina"));
    setText("startFallaMaquinaNombre", btn.getAttribute("data-nombre"));
    new bootstrap.Modal(document.getElementById("startFallaModal")).show();
  });
});
document.querySelectorAll(".js-open-end-falla").forEach((btn) => {
  btn.addEventListener("click", () => {
    setVal("endFallaMaquinaId", btn.getAttribute("data-maquina"));
    setText("endFallaMaquinaNombre", btn.getAttribute("data-nombre"));
    new bootstrap.Modal(document.getElementById("endFallaModal")).show();
  });
});

const focusId = Number(cfg.foco) || 0;
if (focusId) {
  const el = document.getElementById(`machine-card-${focusId}`);
  if (el) el.scrollIntoView({ block: "center" });
}
