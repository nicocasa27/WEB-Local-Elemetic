/* Alta y edición de piezas de Herrería.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

(function () {
  const piezasWeightEl = document.getElementById("piezasCatalogoWeight");
  const piezasNameEl = document.getElementById("piezasCatalogoName");
  const piezasWeight = piezasWeightEl ? JSON.parse(piezasWeightEl.textContent) : {};
  const piezasName = piezasNameEl ? JSON.parse(piezasNameEl.textContent) : {};
  const piezaSel = document.getElementById(cfg.campoPieza);
  const kgInput = document.getElementById(cfg.campoPeso);
  const descInput = document.getElementById(cfg.campoDescripcion);
  function syncKgFromCatalog() {
    if (!piezaSel || !kgInput) return;
    const pid = (piezaSel.value || "").trim();
    if (pid) {
      const w = piezasWeight[pid] ?? piezasWeight[String(pid)] ?? "";
      if (w !== "") kgInput.value = String(w);
      kgInput.readOnly = true;
      kgInput.classList.add("bg-light");
      if (descInput && !(descInput.value || "").trim()) {
        const n = piezasName[pid] ?? piezasName[String(pid)] ?? "";
        if (n) descInput.value = String(n);
      }
    } else {
      kgInput.readOnly = false;
      kgInput.classList.remove("bg-light");
    }
  }
  if (piezaSel) piezaSel.addEventListener("change", syncKgFromCatalog);
  syncKgFromCatalog();

  const input = document.getElementById("pdfPlanoInput");
  const frame = document.getElementById("pdfPlanoFrame");
  const openTab = document.getElementById("pdfPlanoOpenTab");
  if (!input || !frame) return;
  input.addEventListener("change", function () {
    const f = input.files && input.files[0];
    if (!f) return;
    const prev = frame.dataset.objectUrl;
    if (prev) URL.revokeObjectURL(prev);
    const url = URL.createObjectURL(f);
    frame.dataset.objectUrl = url;
    frame.src = url + "#view=FitH";
    if (openTab) {
      openTab.href = url;
      openTab.style.display = "";
    }
  });
})();
