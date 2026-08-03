/* Control de producción de Herrería.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

function getCookie(name) {
  const v = `; ${document.cookie}`;
  const parts = v.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "";
}

async function submitStatusAjax(form) {
  const action = form.getAttribute("action") || "";
  if (!action) return;
  const fd = new FormData(form);
  const csrf = getCookie("csrftoken");
  try {
    const res = await fetch(action, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: csrf ? { "X-CSRFToken": csrf } : {},
    });
    const data = await res.json();
    if (!data || !data.ok) {
      alert((data && data.error) ? data.error : "No se pudo cambiar el estado.");
      return;
    }
    const id = String(data.id || "");
    document.querySelectorAll(`.js-herr-item[data-orden='${id}']`).forEach((row) => {
      row.setAttribute("data-estado", data.estado || "");
      const badge = row.querySelector(".js-estado-badge");
      if (badge) {
        badge.textContent = data.estado || "";
        // El color va en la clase, no en un estilo suelto: así la
        // etiqueta se ve igual aunque este script no llegue a correr.
        window.MES.aplicarClaseDeEstado(badge, data.estado_clase);
      }
      const btn = row.querySelector(".js-open-status-modal");
      if (btn) btn.setAttribute("data-estado", data.estado || "");
    });
  } catch (err) {
    alert("No se pudo cambiar el estado.");
  }
}

const statusModalEl = document.getElementById("statusModal");
const statusModal = statusModalEl ? new bootstrap.Modal(statusModalEl) : null;
const statusForm = document.getElementById("statusModalForm");
const statusVidEl = document.getElementById("statusModalVigaId");
const statusCodigoEl = document.getElementById("statusModalCodigo");
const statusEstadoSel = document.getElementById("statusModalEstado");
const statusFecha = document.getElementById("statusModalFecha");
const statusComentario = document.getElementById("statusModalComentario");
const statusUrlTemplate = cfg.urlEstado;

function openStatusModal(oid, codigo, estadoActual) {
  if (!statusModal || !statusForm) return;
  statusForm.action = statusUrlTemplate.replace("/0/", `/${oid}/`);
  if (statusVidEl) statusVidEl.textContent = `#${oid}`;
  if (statusCodigoEl) statusCodigoEl.textContent = codigo || "";
  if (statusEstadoSel && estadoActual) statusEstadoSel.value = estadoActual;
  if (statusFecha) statusFecha.valueAsDate = new Date();
  if (statusComentario) statusComentario.value = "";
  statusModal.show();
}

document.querySelectorAll(".js-open-status-modal").forEach((btn) => {
  btn.addEventListener("click", () => {
    const oid = (btn.getAttribute("data-orden") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    const estado = (btn.getAttribute("data-estado") || "").trim();
    if (!oid) return;
    openStatusModal(oid, codigo, estado);
  });
});

if (statusForm) {
  statusForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!statusFecha || !(statusFecha.value || "").trim()) {
      alert("Debes seleccionar la fecha de operación antes de cambiar el estado.");
      return;
    }
    submitStatusAjax(statusForm);
    if (statusModal) statusModal.hide();
  });
}
