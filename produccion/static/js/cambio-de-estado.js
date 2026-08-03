/* Cambio de estado de una pieza.
 *
 * Estaba escrito dentro de la plantilla.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

window.addEventListener("DOMContentLoaded", () => {
  const estadosOrder = JSON.parse(document.getElementById("mesEstados").textContent);
  const estadoActual = cfg.estadoActual;
  const sel = document.getElementById("id_estado_nuevo");
  const wrap = document.getElementById("motivoRetrocesoWrap");
  const motivo = document.getElementById("motivoRetrocesoSelect");
  const retroModalEl = document.getElementById("retrocesoMotivoModal");
  const retroModal = retroModalEl ? new bootstrap.Modal(retroModalEl) : null;
  let pendingQuickForm = null;

  function idxEstado(name) {
    return estadosOrder.indexOf((name || "").toString());
  }
  function isRetroceso(nuevo) {
    const a = idxEstado(estadoActual);
    const n = idxEstado(nuevo);
    return a >= 0 && n >= 0 && n < a;
  }
  function update() {
    if (!sel || !wrap || !motivo) return;
    const retro = isRetroceso(sel.value || "");
    wrap.style.display = retro ? "" : "none";
    if (!retro) motivo.value = "";
  }
  if (sel) {
    sel.addEventListener("change", update);
    update();
  }

  document.querySelectorAll("form.js-quick-change").forEach((f) => {
    f.addEventListener("submit", (e) => {
      const estado = (f.getAttribute("data-estado") || "").trim();
      if (!isRetroceso(estado)) return;
      if (!retroModal) return;
      e.preventDefault();
      pendingQuickForm = f;
      retroModal.show();
    });
  });

  if (retroModalEl) {
    retroModalEl.querySelector(".js-motivo-error")?.addEventListener("click", () => {
      if (!pendingQuickForm) return;
      const inp = pendingQuickForm.querySelector('input[name="motivo_retroceso"]');
      if (inp) inp.value = "error_dedo";
      retroModal.hide();
      pendingQuickForm.submit();
      pendingQuickForm = null;
    });
    retroModalEl.querySelector(".js-motivo-retrabajo")?.addEventListener("click", () => {
      if (!pendingQuickForm) return;
      const inp = pendingQuickForm.querySelector('input[name="motivo_retroceso"]');
      if (inp) inp.value = "retrabajo";
      retroModal.hide();
      pendingQuickForm.submit();
      pendingQuickForm = null;
    });
  }
});
