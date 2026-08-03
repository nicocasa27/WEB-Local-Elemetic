/* Lista de piezas de Estructuras metálicas.
 *
 * Estaba escrito dentro de la plantilla, en un bloque de 735 líneas. Aquí
 * se puede leer, el navegador lo guarda en caché y —lo importante— deja de
 * copiarse a la siguiente línea de producción: este archivo y sus dos hermanos
 * de esta carpeta eran casi el mismo código tres veces.
 *
 * Lo que la plantilla sabe y este archivo no —las direcciones del servidor y
 * el modo de la página— llega en los atributos de #mesLista.
 */
const cfg = document.getElementById("mesLista").dataset;

window.addEventListener("DOMContentLoaded", () => {
const fechaInput = document.getElementById("globalFechaOperacion");
const maquinasInfoEl = document.getElementById("maquinasInfoPayload");
const maquinasEstadoEl = document.getElementById("maquinasEstadoPayload");
const maquinasInfo = maquinasInfoEl ? JSON.parse(maquinasInfoEl.textContent) : {};
const maquinasEstado = maquinasEstadoEl ? JSON.parse(maquinasEstadoEl.textContent) : {};
const machineBlockModalEl = document.getElementById("machineBlockModal");
const machineBlockModal = machineBlockModalEl ? new bootstrap.Modal(machineBlockModalEl) : null;
const machineBlockTitleEl = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-title") : null;
const machineBlockBodyEl = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-body") : null;
const machineBlockSelectWrap = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-select-wrap") : null;
const machineBlockSelect = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-select") : null;
const machineBlockGoParos = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-go-paros") : null;
const machineBlockReanudar = machineBlockModalEl ? machineBlockModalEl.querySelector(".js-reanudar") : null;
const machineActionForm = document.getElementById("machineActionForm");

if (fechaInput) {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const dd = String(now.getDate()).padStart(2, "0");
  fechaInput.value = `${yyyy}-${mm}-${dd}`;
}


document.querySelectorAll("form.js-require-fecha").forEach((form) => {
  form.addEventListener("submit", (e) => {
    const fecha = fechaInput ? (fechaInput.value || "").trim() : "";
    if (!fecha) {
      e.preventDefault();
      alert("Debes seleccionar la fecha de operación antes de cambiar el estado.");
      if (fechaInput) fechaInput.focus();
      return;
    }
    const hidden = form.querySelector('input[name="fecha_operacion"]');
    if (hidden) hidden.value = fecha;

    const estadoNuevo = (form.querySelector('input[name="estado_nuevo"]')?.value || "").trim();
    const container = form.closest(".js-viga-item");
    const estadoActual = ((container?.querySelector(".js-estado-badge")?.textContent || "").toString().trim()) || ((container?.getAttribute("data-estado") || "").toString().trim());
    if (machineBlockModal && estadoActual === "Espera de corte" && estadoNuevo === "Corte") {
      const asigBtn = container ? container.querySelector(".js-open-asignaciones") : null;
      const raw = asigBtn ? (asigBtn.getAttribute("data-corte-maquinas") || "").trim() : "";
      const mids = raw ? raw.split(",").map((x) => parseInt(x.trim(), 10)).filter((x) => Number.isFinite(x)) : [];
      const fallaIds = [];
      const paroIds = [];
      mids.forEach((id) => {
        const st = maquinasEstado[String(id)] || maquinasEstado[id];
        if (st && st.falla) fallaIds.push(id);
        else if (st && st.paro) paroIds.push(id);
      });
      if (fallaIds.length > 0) {
        if (machineBlockTitleEl) machineBlockTitleEl.textContent = "Máquina con falla activa";
        if (machineBlockBodyEl) {
          const lines = fallaIds.map((id) => {
            const info = maquinasInfo[String(id)] || maquinasInfo[id] || {};
            const st = maquinasEstado[String(id)] || maquinasEstado[id] || {};
            const name = info.nombre || `Máquina #${id}`;
            const tipo = st.tipo_falla ? ` · ${st.tipo_falla}` : "";
            const since = st.falla_inicio ? ` · desde ${st.falla_inicio}` : "";
            return `<li>${name}${tipo}${since}</li>`;
          });
          machineBlockBodyEl.innerHTML = `<div>No se puede pasar a <strong>${estadoNuevo}</strong> porque la máquina asignada tiene falla activa. Atiéndelo en Paros.</div><ul class="mb-0 mt-2">${lines.join("")}</ul>`;
        }
        if (machineBlockSelectWrap) machineBlockSelectWrap.style.display = "none";
        if (machineBlockReanudar) machineBlockReanudar.style.display = "none";
        if (machineBlockGoParos) {
          const focus = fallaIds[0] || 0;
          machineBlockGoParos.href = `${cfg.urlParos}?focus=${focus}`;
          machineBlockGoParos.style.display = "";
        }
        e.preventDefault();
        machineBlockModal.show();
        return;
      }
      if (paroIds.length > 0) {
        if (machineBlockTitleEl) machineBlockTitleEl.textContent = "Máquina en paro";
        if (machineBlockBodyEl) {
          const lines = paroIds.map((id) => {
            const info = maquinasInfo[String(id)] || maquinasInfo[id] || {};
            const st = maquinasEstado[String(id)] || maquinasEstado[id] || {};
            const name = info.nombre || `Máquina #${id}`;
            const motivo = st.motivo ? ` · ${st.motivo}` : "";
            const since = st.paro_inicio ? ` · desde ${st.paro_inicio}` : "";
            return `<li>${name}${motivo}${since}</li>`;
          });
          machineBlockBodyEl.innerHTML = `<div>Antes de pasar a <strong>${estadoNuevo}</strong>, debes reanudar la máquina (está en paro).</div><ul class="mb-0 mt-2">${lines.join("")}</ul>`;
        }
        if (machineBlockSelect) {
          machineBlockSelect.innerHTML = "";
          paroIds.forEach((id) => {
            const info = maquinasInfo[String(id)] || maquinasInfo[id] || {};
            const opt = document.createElement("option");
            opt.value = String(id);
            opt.textContent = info.nombre || `Máquina #${id}`;
            machineBlockSelect.appendChild(opt);
          });
        }
        if (machineBlockSelectWrap) machineBlockSelectWrap.style.display = "";
        if (machineBlockGoParos) machineBlockGoParos.style.display = "none";
        if (machineBlockReanudar) machineBlockReanudar.style.display = "";
        if (machineBlockReanudar && machineActionForm) {
          machineBlockReanudar.onclick = () => {
            const mid = machineBlockSelect ? (machineBlockSelect.value || "") : "";
            machineActionForm.querySelector("input[name='action']").value = "end_paro";
            machineActionForm.querySelector("input[name='maquina_id']").value = mid;
            machineActionForm.querySelector("input[name='next']").value = window.location.pathname + window.location.search;
            machineActionForm.submit();
          };
        }
        e.preventDefault();
        machineBlockModal.show();
        return;
      }
    }
    const codigo = (container?.getAttribute("data-codigo") || "").toString().trim();
    const modalEl = document.getElementById("confirmModal");
    const modal = new bootstrap.Modal(modalEl);
    modalEl.querySelector(".js-viga-codigo").textContent = codigo || "(sin código)";
    modalEl.querySelector(".js-viga-estado").textContent = estadoNuevo || "(sin estado)";
    modalEl.querySelector(".js-viga-fecha").textContent = fecha;
    const comentarioInput = modalEl.querySelector("textarea[name='comentario_modal']");
    comentarioInput.value = "";
    e.preventDefault();
    modal.show();

    const confirmBtn = modalEl.querySelector(".js-confirm");
    const cancelBtn = modalEl.querySelector(".js-cancel");
    const handler = (confirm) => {
      confirmBtn.removeEventListener("click", onConfirm);
      cancelBtn.removeEventListener("click", onCancel);
    };
    function onConfirm() {
      const comentarioHidden = form.querySelector("input[name='comentario']");
      if (comentarioHidden && comentarioInput) comentarioHidden.value = comentarioInput.value || "";
      handler(true);
      modal.hide();
      submitStatusAjax(form);
    }
    function onCancel() {
      handler(false);
      modal.hide();
    }
    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
  });
});

const liveSearchInput = document.getElementById("liveSearchViga");
const clearLiveSearchBtn = document.getElementById("clearLiveSearch");
const suggestions = document.getElementById("vigaSuggestions");
const vigaItems = Array.from(document.querySelectorAll(".js-viga-item"));
const codigoUniverse = Array.from(
  new Set(
    vigaItems
      .map((el) => (el.getAttribute("data-codigo") || "").toString().trim())
      .filter((c) => !!c)
  )
).sort();

function normalize(v) {
  return (v || "").toString().toLowerCase().trim();
}

function itemText(el) {
  const codigo = el.getAttribute("data-codigo") || "";
  const proyecto = el.getAttribute("data-proyecto") || "";
  const descripcion = el.getAttribute("data-descripcion") || "";
  return normalize(codigo + " " + proyecto + " " + descripcion);
}

function renderSuggestions(term) {
  if (!suggestions) return;
  suggestions.innerHTML = "";
  if (!term) return;
  const t = term.toLowerCase();
  const matches = [];
  for (const codigo of codigoUniverse) {
    if (codigo.toLowerCase().includes(t)) matches.push(codigo);
    if (matches.length >= 12) break;
  }
  matches.forEach((codigo) => {
    const opt = document.createElement("option");
    opt.value = codigo;
    suggestions.appendChild(opt);
  });
}

function applyLiveFilter() {
  const term = normalize(liveSearchInput ? liveSearchInput.value : "");

  vigaItems.forEach((el) => {
    const ok = !term || itemText(el).includes(term);
    el.style.display = ok ? "" : "none";
  });
  renderSuggestions(term);
}

if (liveSearchInput) {
  liveSearchInput.addEventListener("input", applyLiveFilter);
  liveSearchInput.addEventListener("change", applyLiveFilter);
  applyLiveFilter();
}

if (clearLiveSearchBtn && liveSearchInput) {
  clearLiveSearchBtn.addEventListener("click", () => {
    liveSearchInput.value = "";
    applyLiveFilter();
    liveSearchInput.focus();
    try { localStorage.removeItem("viga_list_q"); } catch (e) {}
    const u = new URL(window.location.href);
    if (u.searchParams.has("q")) {
      u.searchParams.delete("q");
      window.history.replaceState({}, "", u.toString());
    }
  });
}

document.querySelectorAll(".js-reset-vigas").forEach((el) => {
  el.addEventListener("click", () => {
    try { localStorage.removeItem("viga_list_q"); } catch (e) {}
  });
});

const urlNow = new URL(window.location.href);
const urlQ = (urlNow.searchParams.get("q") || "").trim();
if (urlQ) {
  try { localStorage.setItem("viga_list_q", urlQ); } catch (e) {}
} else {
  const savedQ = (() => { try { return (localStorage.getItem("viga_list_q") || "").trim(); } catch (e) { return ""; } })();
  if (savedQ && liveSearchInput && !normalize(liveSearchInput.value)) {
    urlNow.searchParams.set("q", savedQ);
    window.location.replace(urlNow.toString());
    return;
  }
}

if (liveSearchInput) {
  liveSearchInput.addEventListener("input", () => {
    const v = (liveSearchInput.value || "").trim();
    try {
      if (v) localStorage.setItem("viga_list_q", v);
      else localStorage.removeItem("viga_list_q");
    } catch (e) {}

    if (!v) {
      applyLiveFilter();
      const u = new URL(window.location.href);
      if (u.searchParams.has("q")) {
        u.searchParams.delete("q");
        window.history.replaceState({}, "", u.toString());
      }
    }
  });
}


async function submitStatusAjax(form) {
  const action = form.getAttribute("action") || "";
  if (!action) return;
  const fd = new FormData(form);
  const csrf = window.MES.cookie("csrftoken");
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
    updateVigaUI(String(data.id), data.estado, data.estado_clase, data.next_estado || "", data.ultimo_mov || "", data.next_label || "");
  } catch (err) {
    alert("No se pudo cambiar el estado.");
  }
}

function updateVigaUI(vid, estado, claseEstado, nextEstado, ultimoMov, nextLabel) {
  document.querySelectorAll(`.js-viga-item[data-viga='${vid}']`).forEach((container) => {
    const badges = container.querySelectorAll(".js-bg");
    badges.forEach((b) => {
      b.textContent = estado;
      // El color va en la clase, no en un estilo suelto: así la etiqueta
      // se ve igual aunque este script no llegue a correr.
      window.MES.aplicarClaseDeEstado(b, claseEstado);
    });
    container.querySelectorAll(".js-open-status-modal").forEach((btn) => {
      btn.setAttribute("data-estado", estado);
    });
    if (ultimoMov) {
      container.querySelectorAll(".js-ultimo-mov").forEach((el) => {
        el.textContent = ultimoMov;
      });
    }
    const quickForm = container.querySelector("form.js-status-ajax");
    const existingIndicator = container.querySelector(".js-next-indicator");
    if (existingIndicator) existingIndicator.remove();
    if (quickForm) {
      const estadoInput = quickForm.querySelector("input[name='estado_nuevo']");
      const btn = quickForm.querySelector("button[type='submit']");
      if (nextEstado) {
        if (estadoInput) estadoInput.value = nextEstado;
        if (btn) btn.innerHTML = `<i class=\"bi bi-arrow-right-circle me-1\"></i> Pasar a ${nextEstado}`;
        window.MES.aplicarClaseDeEstado(btn, claseEstado);
        quickForm.style.display = "";
      } else {
        quickForm.style.display = "none";
        const label = (nextLabel || "").trim();
        if (label) {
          const wrap = document.createElement("div");
          wrap.className = "d-grid gap-2 js-next-indicator";
          wrap.innerHTML = `<button type="button" class="btn btn-secondary btn-lg" disabled><i class="bi bi-info-circle me-1"></i> ${label}</button>`;
          quickForm.insertAdjacentElement("afterend", wrap);
        }
      }
    }
    container.setAttribute("data-estado", estado);
  });
}

const statusModalEl = document.getElementById("statusModal");
const statusModal = statusModalEl ? new bootstrap.Modal(statusModalEl) : null;
const statusForm = document.getElementById("statusModalForm");
const statusVidEl = document.getElementById("statusModalVigaId");
const statusCodigoEl = document.getElementById("statusModalCodigo");
const statusEstadoSel = document.getElementById("statusModalEstado");
const statusFecha = document.getElementById("statusModalFecha");
const statusComentario = document.getElementById("statusModalComentario");
const statusMotivoWrap = document.getElementById("statusMotivoWrap");
const statusMotivoSel = document.getElementById("statusModalMotivo");
const statusUrlTemplate = cfg.urlEstado;
const estadosOrder = JSON.parse(document.getElementById("estadosOrderPayload").textContent);

function idxEstado(name) {
  return estadosOrder.indexOf((name || "").toString());
}

function isRetroceso(actual, nuevo) {
  const a = idxEstado(actual);
  const n = idxEstado(nuevo);
  return a >= 0 && n >= 0 && n < a;
}

function updateMotivoVisibility() {
  if (!statusForm || !statusEstadoSel || !statusMotivoWrap || !statusMotivoSel) return;
  const actual = statusForm.getAttribute("data-estado-actual") || "";
  const nuevo = (statusEstadoSel.value || "").trim();
  const retro = isRetroceso(actual, nuevo);
  statusMotivoWrap.style.display = retro ? "" : "none";
  if (!retro) statusMotivoSel.value = "";
}

function openStatusModal(vid, codigo, estadoActual) {
  if (!statusModal || !statusForm) return;
  statusForm.action = statusUrlTemplate.replace("/0/", `/${vid}/`);
  statusForm.setAttribute("data-estado-actual", estadoActual || "");
  if (statusVidEl) statusVidEl.textContent = `#${vid}`;
  if (statusCodigoEl) statusCodigoEl.textContent = codigo || "";
  if (statusEstadoSel && estadoActual) statusEstadoSel.value = estadoActual;
  if (statusFecha && fechaInput) statusFecha.value = (fechaInput.value || "").trim();
  if (statusComentario) statusComentario.value = "";
  if (statusMotivoSel) statusMotivoSel.value = "";
  updateMotivoVisibility();
  statusModal.show();
}

document.querySelectorAll(".js-open-status-modal").forEach((btn) => {
  btn.addEventListener("click", () => {
    const vid = (btn.getAttribute("data-viga") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    const estado = (btn.getAttribute("data-estado") || "").trim();
    if (!vid) return;
    openStatusModal(vid, codigo, estado);
  });
});

if (statusForm) {
  statusForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!statusFecha || !(statusFecha.value || "").trim()) {
      alert("Debes seleccionar la fecha de operación antes de cambiar el estado.");
      return;
    }
    if (statusMotivoWrap && statusMotivoWrap.style.display !== "none") {
      const val = statusMotivoSel ? (statusMotivoSel.value || "").trim() : "";
      if (!val) {
        alert("Debes seleccionar el motivo del retroceso.");
        return;
      }
    }
    submitStatusAjax(statusForm);
    if (statusModal) statusModal.hide();
  });
}

if (statusEstadoSel) {
  statusEstadoSel.addEventListener("change", updateMotivoVisibility);
}

const metaModalEl = document.getElementById("metaModal");
const metaModal = metaModalEl ? new bootstrap.Modal(metaModalEl) : null;
const metaForm = document.getElementById("metaModalForm");
const metaVigaEl = document.getElementById("metaModalViga");
const metaFechaEl = document.getElementById("metaModalFecha");
const metaPrioridadEl = document.getElementById("metaModalPrioridad");
const metaUrlTemplate = cfg.urlMeta;

function openMetaModal(vid, codigo, fecha, prioridad) {
  if (!metaModal || !metaForm) return;
  metaForm.action = metaUrlTemplate.replace("/0/", `/${vid}/`);
  metaForm.setAttribute("data-viga", String(vid));
  if (metaVigaEl) metaVigaEl.textContent = codigo ? `#${vid} · ${codigo}` : `#${vid}`;
  if (metaFechaEl) metaFechaEl.value = (fecha || "").trim();
  if (metaPrioridadEl) metaPrioridadEl.value = String(prioridad || "3");
  metaModal.show();
}

document.querySelectorAll(".js-open-meta-modal").forEach((btn) => {
  btn.addEventListener("click", () => {
    const vid = (btn.getAttribute("data-viga") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    const fecha = (btn.getAttribute("data-fecha") || "").trim();
    const prioridad = (btn.getAttribute("data-prioridad") || "").trim();
    if (!vid) return;
    openMetaModal(vid, codigo, fecha, prioridad);
  });
});

if (metaForm) {
  metaForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const vid = (metaForm.getAttribute("data-viga") || "").trim();
    const fd = new FormData(metaForm);
    const csrf = window.MES.cookie("csrftoken");
    fetch(metaForm.action, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        ...(csrf ? { "X-CSRFToken": csrf } : {}),
      },
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data || !data.ok) {
          window.MES.aviso((data && data.error) ? data.error : "No se pudo guardar.", "danger");
          return;
        }
        const id = String(data.id || vid);
        document.querySelectorAll(`.js-viga-item[data-viga='${id}']`).forEach((container) => {
          container.querySelectorAll(".js-fecha-compromiso").forEach((el) => {
            el.textContent = data.fecha_compromiso || "";
          });
          container.querySelectorAll(".js-prioridad").forEach((el) => {
            el.textContent = `P${data.prioridad}`;
          });
        });
        document.querySelectorAll(`.js-open-meta-modal[data-viga='${id}']`).forEach((b) => {
          b.setAttribute("data-fecha", data.fecha_compromiso || "");
          b.setAttribute("data-prioridad", String(data.prioridad || ""));
        });
        window.MES.aviso("Guardado.", "success");
        if (metaModal) metaModal.hide();
      })
      .catch(() => {
        window.MES.aviso("No se pudo guardar.", "danger");
      });
  });
}

const decoteModalEl = document.getElementById("decoteModal");
const decoteModal = decoteModalEl ? new bootstrap.Modal(decoteModalEl) : null;
const decoteForm = document.getElementById("decoteForm");
const decoteInput = document.getElementById("decoteConfirmText");
const decoteBtn = document.getElementById("decoteConfirmBtn");
const decoteCodigo = document.getElementById("decoteCodigo");
const decoteDias = document.getElementById("decoteDias");
const decoteNext = document.getElementById("decoteNext");

function updateDecoteButton() {
  const ok = (decoteInput.value || "").trim().toUpperCase() === "ELIMINAR";
  decoteBtn.disabled = !ok;
}

document.querySelectorAll(".js-decote-open").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!decoteModal) return;
    const action = btn.getAttribute("data-action") || "";
    const codigo = btn.getAttribute("data-codigo") || "";
    const pieza = btn.getAttribute("data-pieza") || "";
    const dias = btn.getAttribute("data-dias") || "";
    const next = btn.getAttribute("data-next") || "";
    decoteForm.action = action;
    decoteCodigo.textContent = `${codigo} (${pieza})`;
    decoteDias.textContent = dias;
    decoteNext.value = next;
    decoteInput.value = "";
    updateDecoteButton();
    decoteModal.show();
    decoteInput.focus();
  });
});

if (decoteInput) {
  decoteInput.addEventListener("input", updateDecoteButton);
}
const decoteBulkModalEl = document.getElementById("decoteBulkModal");
const decoteBulkModal = decoteBulkModalEl ? new bootstrap.Modal(decoteBulkModalEl) : null;
const decoteBulkForm = document.getElementById("decoteBulkForm");
const decoteBulkInput = document.getElementById("decoteBulkConfirmText");
const decoteBulkBtn = document.getElementById("decoteBulkConfirmBtn");
const decoteBulkTotal = document.getElementById("decoteBulkTotal");
const decoteBulkNext = document.getElementById("decoteBulkNext");
const decoteBulkProyecto = document.getElementById("decoteBulkProyecto");
const decoteBulkQ = document.getElementById("decoteBulkQ");

function updateDecoteBulkButton() {
  const ok = (decoteBulkInput.value || "").trim().toUpperCase() === "ELIMINAR";
  decoteBulkBtn.disabled = !ok;
}

document.querySelectorAll(".js-decote-bulk-open").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!decoteBulkModal) return;
    decoteBulkForm.action = btn.getAttribute("data-action") || "";
    decoteBulkNext.value = btn.getAttribute("data-next") || "";
    decoteBulkProyecto.value = btn.getAttribute("data-proyecto") || "";
    decoteBulkQ.value = btn.getAttribute("data-q") || "";
    decoteBulkTotal.textContent = btn.getAttribute("data-total") || "0";
    decoteBulkInput.value = "";
    updateDecoteBulkButton();
    decoteBulkModal.show();
    decoteBulkInput.focus();
  });
});

if (decoteBulkInput) {
  decoteBulkInput.addEventListener("input", updateDecoteBulkButton);
}

const planoModalEl = document.getElementById("planoModal");
const planoModal = planoModalEl ? new bootstrap.Modal(planoModalEl) : null;
const planoEmbed = document.getElementById("planoModalEmbed");
const planoOpenTab = document.getElementById("planoModalOpenTab");
const planoTitle = document.getElementById("planoModalTitle");
if (planoModalEl) {
  planoModalEl.addEventListener("hidden.bs.modal", () => {
    if (planoEmbed) planoEmbed.setAttribute("src", "about:blank");
  });
}
document.querySelectorAll(".js-open-plano").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!planoModal) return;
    const url = (btn.getAttribute("data-url") || "").trim();
    if (!url) return;
    if (planoEmbed) {
      planoEmbed.setAttribute("src", "about:blank");
      window.setTimeout(() => {
        planoEmbed.setAttribute("src", url + "#view=FitH&ts=" + Date.now());
      }, 30);
    }
    if (planoOpenTab) planoOpenTab.setAttribute("href", url);
    if (planoTitle) planoTitle.textContent = "Plano PDF";
    planoModal.show();
  });
});

const participantesEl = document.getElementById("participantesPayload");
const participantes = participantesEl ? JSON.parse(participantesEl.textContent) : {};
const asignacionesModalEl = document.getElementById("asignacionesModal");
const asignacionesModal = asignacionesModalEl ? new bootstrap.Modal(asignacionesModalEl) : null;
const asignacionesForm = document.getElementById("asignacionesForm");
const asignacionesCodigoEl = document.getElementById("asignacionesVigaCodigo");
const corteOperadoresList = document.getElementById("asigCorteOperadoresList");
const soldaduraList = document.getElementById("asigSoldaduraList");
const pinturaList = document.getElementById("asigPinturaList");
const corteMaquinasList = document.getElementById("asigCorteMaquinasList");
const asignUrlTemplate = cfg.urlAsignaciones;
const pageMode = cfg.modo;

function idsToCsv(ids) {
  return (ids || []).map((x) => String(x)).join(",");
}


function parseCsvIds(raw) {
  const s = (raw || "").toString().trim();
  if (!s) return [];
  return s.split(",").map((x) => x.trim()).filter((x) => x).map((x) => parseInt(x, 10)).filter((x) => Number.isFinite(x));
}
function fillChecklist(container, items, selectedIds, inputName, withRol) {
  if (!container) return;
  container.innerHTML = "";
  const selectedSet = new Set(selectedIds || []);
  (items || []).forEach((it) => {
    const id = String(it.id);
    const checkId = `chk_${inputName}_${id}`;
    const wrap = document.createElement("div");
    wrap.className = "form-check";

    const input = document.createElement("input");
    input.className = "form-check-input";
    input.type = "checkbox";
    input.name = inputName;
    input.value = id;
    input.id = checkId;
    if (selectedSet.has(it.id)) input.checked = true;

    const label = document.createElement("label");
    label.className = "form-check-label";
    label.htmlFor = checkId;
    label.textContent = withRol ? `${it.nombre} (${it.rol})` : it.nombre;

    wrap.appendChild(input);
    wrap.appendChild(label);
    container.appendChild(wrap);
  });
}

function fillOperadores(select, items, selectedIds) {
  if (!select) return;
  select.innerHTML = "";
  const selectedSet = new Set(selectedIds || []);
  (items || []).forEach((it) => {
    const o = document.createElement("option");
    o.value = String(it.id);
    o.textContent = it.nombre;
    if (selectedSet.has(it.id)) o.selected = true;
    select.appendChild(o);
  });
}

document.querySelectorAll(".js-open-asignaciones").forEach((btn) => {
  btn.addEventListener("click", () => {
    const vid = (btn.getAttribute("data-viga") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    if (!vid || !asignacionesForm || !asignacionesModal) return;
    asignacionesForm.action = asignUrlTemplate.replace("/0/", `/${vid}/`);
    if (asignacionesCodigoEl) asignacionesCodigoEl.textContent = codigo ? `#${vid} · ${codigo}` : `#${vid}`;
    fillChecklist(corteOperadoresList, participantes.Corte?.operadores || [], parseCsvIds(btn.getAttribute("data-corte-operadores")), "corte_operador_ids", false);
    fillChecklist(corteMaquinasList, (participantes.Corte?.maquinas || []).map((m) => ({id: m.id, nombre: m.nombre, rol: "Máquina"})), parseCsvIds(btn.getAttribute("data-corte-maquinas")), "corte_maquina_ids", true);
    fillChecklist(soldaduraList, participantes.Soldadura?.items || [], parseCsvIds(btn.getAttribute("data-soldadura")), "soldadura_ids", true);
    fillChecklist(pinturaList, participantes.Pintura?.items || [], parseCsvIds(btn.getAttribute("data-pintura")), "pintura_ids", true);
    asignacionesModal.show();
  });
});

if (asignacionesForm) {
  asignacionesForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const vidMatch = (asignacionesForm.action || "").match(/\/(\d+)\/?$/);
    const vid = vidMatch ? vidMatch[1] : "";
    if (pageMode !== "soldadura") {
      const checks = asignacionesForm.querySelectorAll("input[name='corte_operador_ids']:checked");
      if (!checks || checks.length < 1) {
        window.MES.aviso("Debes seleccionar al menos 1 operador en Corte.", "danger");
        return;
      }
    }
    const fd = new FormData(asignacionesForm);
    const csrf = window.MES.cookie("csrftoken");
    fetch(asignacionesForm.action, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        ...(csrf ? { "X-CSRFToken": csrf } : {}),
      },
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data || !data.ok) {
          window.MES.aviso((data && data.error) ? data.error : "No se pudieron guardar las asignaciones.", "danger");
          return;
        }
        const id = String(data.id || vid);
        document.querySelectorAll(`.js-open-asignaciones[data-viga='${id}']`).forEach((b) => {
          b.setAttribute("data-corte-operadores", idsToCsv(data.corte_operador_ids || []));
          b.setAttribute("data-corte-maquinas", idsToCsv(data.corte_maquina_ids || []));
          b.setAttribute("data-soldadura", idsToCsv(data.soldadura_ids || []));
          b.setAttribute("data-pintura", idsToCsv(data.pintura_ids || []));
        });
        window.MES.aviso("Asignaciones guardadas.", "success");
        if (asignacionesModal) asignacionesModal.hide();
      })
      .catch(() => {
        window.MES.aviso("No se pudieron guardar las asignaciones.", "danger");
      });
  });
}

});
