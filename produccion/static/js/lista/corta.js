/* Lista de órdenes de Corta.mx.
 *
 * Estaba escrito dentro de la plantilla, en un bloque de 912 líneas. Aquí
 * se puede leer, el navegador lo guarda en caché y —lo importante— deja de
 * copiarse a la siguiente línea de producción: este archivo y sus dos hermanos
 * de esta carpeta eran casi el mismo código tres veces.
 *
 * Lo que la plantilla sabe y este archivo no —las direcciones del servidor y
 * el modo de la página— llega en los atributos de #mesLista.
 */
const cfg = document.getElementById("mesLista").dataset;

window.addEventListener("DOMContentLoaded", () => {
const scrollKey = `scrollY:${window.location.pathname}${window.location.search}`;
function saveScroll() {
  try { sessionStorage.setItem(scrollKey, String(window.scrollY || 0)); } catch (e) {}
}
try {
  const saved = sessionStorage.getItem(scrollKey);
  if (saved !== null) {
    sessionStorage.removeItem(scrollKey);
    const y = parseInt(saved || "0", 10);
    if (y > 0) window.scrollTo(0, y);
  }
} catch (e) {}
document.querySelectorAll("form.js-preserve-scroll").forEach((f) => {
  f.addEventListener("submit", () => saveScroll());
});
const fechaInput = document.getElementById("globalFechaOperacion");
const participantesEl = document.getElementById("participantesPayload");
const estadosOrderEl = document.getElementById("estadosOrderPayload");
const estadosOrderOpEl = document.getElementById("estadosOrderOpPayload");
const maquinasInfoEl = document.getElementById("maquinasInfoPayload");
const maquinasEstadoEl = document.getElementById("maquinasEstadoPayload");
const participantes = participantesEl ? JSON.parse(participantesEl.textContent) : {};
const estadosOrder = estadosOrderEl ? JSON.parse(estadosOrderEl.textContent) : [];
const estadosOrderOp = estadosOrderOpEl ? JSON.parse(estadosOrderOpEl.textContent) : [];
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
const editIframeModalEl = document.getElementById("editIframeModal");
const editIframeModal = editIframeModalEl ? new bootstrap.Modal(editIframeModalEl) : null;
const editIframeFrame = document.getElementById("editIframeFrame");

function appendQS(url, key, val) {
  const u = String(url || "");
  if (!u) return u;
  const re = new RegExp(`[?&]${String(key).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=`);
  if (re.test(u)) return u;
  const sep = u.indexOf("?") >= 0 ? "&" : "?";
  return `${u}${sep}${encodeURIComponent(String(key))}=${encodeURIComponent(String(val))}`;
}

function openEditIframe(url) {
  if (!editIframeModal || !editIframeFrame) {
    window.location.href = url;
    return;
  }
  saveScroll();
  editIframeFrame.src = appendQS(url, "embedded", "1");
  editIframeModal.show();
}

document.addEventListener("click", (ev) => {
  const a = ev.target && ev.target.closest ? ev.target.closest("a.js-open-edit-iframe") : null;
  if (!a) return;
  ev.preventDefault();
  const href = a.getAttribute("href") || "";
  if (!href) return;
  openEditIframe(href);
});

if (editIframeModalEl) {
  editIframeModalEl.addEventListener("hidden.bs.modal", () => {
    if (editIframeFrame) editIframeFrame.src = "about:blank";
  });
}

window.addEventListener("message", (ev) => {
  try {
    if (ev.origin !== window.location.origin) return;
    const data = ev.data || {};
    if (!data || data.type !== "corte:close-edit") return;
    if (editIframeModal) editIframeModal.hide();
    if (data.reload) {
      saveScroll();
      window.location.reload();
    }
  } catch (e) {}
});


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
    saveScroll();
    window.location.reload();
  } catch (err) {
    alert("No se pudo cambiar el estado.");
  }
}

function updateVigaUI(vid, estado, claseEstado, nextEstado, ultimoMov) {
  document.querySelectorAll(`.js-viga-item[data-viga='${vid}']`).forEach((container) => {
    // El color va en la clase, no en un estilo suelto: así el estado se
    // ve igual aunque este script no llegue a correr.
    container.querySelectorAll(".js-bg").forEach((b) => {
      b.textContent = estado;
      window.MES.aplicarClaseDeEstado(b, claseEstado);
    });
    container.querySelectorAll(".js-next-btn").forEach((btn) => {
      window.MES.aplicarClaseDeEstado(btn, claseEstado);
    });
    if (ultimoMov) {
      container.querySelectorAll(".js-ultimo-mov").forEach((el) => {
        el.textContent = ultimoMov;
      });
    }
  });
}

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
    const estadoActual = ((container?.querySelector(".js-bg")?.textContent || "").toString().trim()) || ((container?.getAttribute("data-estado") || "").toString().trim());
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
    function cleanup() {
      confirmBtn.removeEventListener("click", onConfirm);
      cancelBtn.removeEventListener("click", onCancel);
    }
    function onConfirm() {
      const comentarioHidden = form.querySelector("input[name='comentario']");
      if (comentarioHidden && comentarioInput) comentarioHidden.value = comentarioInput.value || "";
      cleanup();
      modal.hide();
      submitStatusAjax(form);
    }
    function onCancel() {
      cleanup();
      modal.hide();
    }
    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
  });
});

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

function isRetroceso(estadosList, estadoActual, estadoNuevo) {
  const list = Array.isArray(estadosList) ? estadosList : [];
  const a = list.indexOf(estadoActual);
  const b = list.indexOf(estadoNuevo);
  return a >= 0 && b >= 0 && b < a;
}
function updateMotivoVisibility() {
  if (!statusForm || !statusEstadoSel || !statusMotivoWrap || !statusMotivoSel) return;
  const cur = (statusForm.getAttribute("data-estado-actual") || "").trim();
  const next = (statusEstadoSel.value || "").trim();
  const isOp = (statusForm.getAttribute("data-es-op") || "").trim() === "1";
  const retro = isRetroceso(isOp ? estadosOrderOp : estadosOrder, cur, next);
  statusMotivoWrap.style.display = retro ? "" : "none";
  if (!retro) statusMotivoSel.value = "";
}
function setEstadoOptions(isOp, estadoActual) {
  if (!statusEstadoSel) return;
  const list = isOp ? estadosOrderOp : estadosOrder;
  statusEstadoSel.innerHTML = "";
  (Array.isArray(list) ? list : []).forEach((e) => {
    const opt = document.createElement("option");
    opt.value = String(e || "");
    opt.textContent = String(e || "");
    statusEstadoSel.appendChild(opt);
  });
  if (estadoActual && (Array.isArray(list) ? list : []).includes(estadoActual)) {
    statusEstadoSel.value = estadoActual;
  }
}
function openStatusModal(vid, codigo, estadoActual, isOp) {
  if (!statusModal || !statusForm) return;
  statusForm.action = statusUrlTemplate.replace("/0/", `/${vid}/`);
  statusForm.setAttribute("data-estado-actual", estadoActual || "");
  statusForm.setAttribute("data-es-op", isOp ? "1" : "0");
  if (statusVidEl) statusVidEl.textContent = `#${vid}`;
  if (statusCodigoEl) statusCodigoEl.textContent = codigo || "";
  setEstadoOptions(isOp, estadoActual);
  if (statusFecha) statusFecha.valueAsDate = new Date();
  if (statusComentario) statusComentario.value = "";
  updateMotivoVisibility();
  statusModal.show();
}
document.querySelectorAll(".js-open-status-modal").forEach((btn) => {
  btn.addEventListener("click", () => {
    const vid = (btn.getAttribute("data-viga") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    const estado = (btn.getAttribute("data-estado") || "").trim();
    const isOp = (btn.getAttribute("data-es-op") || "").trim() === "1";
    if (!vid) return;
    openStatusModal(vid, codigo, estado, isOp);
  });
});
if (statusEstadoSel) statusEstadoSel.addEventListener("change", updateMotivoVisibility);
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
      .catch(() => window.MES.aviso("No se pudo guardar.", "danger"));
  });
}

const avanceModalEl = document.getElementById("avanceModal");
const avanceModal = avanceModalEl ? new bootstrap.Modal(avanceModalEl) : null;
const avanceForm = document.getElementById("avanceModalForm");
const avanceVigaEl = document.getElementById("avanceModalViga");
const avanceObjetivoEl = document.getElementById("avanceModalObjetivo");
const avanceSoldEl = document.getElementById("avanceModalSold");
const avancePintEl = document.getElementById("avanceModalPint");
const avanceTermEl = document.getElementById("avanceModalTerm");
const avancePendienteWrap = document.getElementById("avancePendienteWrap");
const avancePendienteHastaEl = document.getElementById("avancePendienteHasta");
const avanceRevertBtn = document.getElementById("avanceRevertBtn");
let avanceRevertAction = "";

function setOpAvanceUI(vid, soldadas, pintadas, terminadas, objetivo, soldadasPct, pintadasPct, terminadasPct) {
  const id = String(vid || "");
  const s = Number.isFinite(Number(soldadas)) ? Number(soldadas) : 0;
  const p = Number.isFinite(Number(pintadas)) ? Number(pintadas) : 0;
  const t = Number.isFinite(Number(terminadas)) ? Number(terminadas) : 0;
  const o = Number.isFinite(Number(objetivo)) ? Number(objetivo) : 0;
  const pctS = Number.isFinite(Number(soldadasPct)) ? Number(soldadasPct) : 0;
  const pctP = Number.isFinite(Number(pintadasPct)) ? Number(pintadasPct) : 0;
  const pctT = Number.isFinite(Number(terminadasPct)) ? Number(terminadasPct) : 0;
  document.querySelectorAll(`.js-viga-item[data-viga='${id}']`).forEach((container) => {
    container.querySelectorAll(".js-op-soldadas").forEach((el) => (el.textContent = String(s)));
    container.querySelectorAll(".js-op-pintadas").forEach((el) => (el.textContent = String(p)));
    container.querySelectorAll(".js-op-terminadas").forEach((el) => (el.textContent = String(t)));
    container.querySelectorAll(".js-op-objetivo").forEach((el) => (el.textContent = String(o)));
    container.querySelectorAll(".js-op-bar-sold").forEach((el) => {
      el.style.width = `${pctS}%`;
      el.setAttribute("aria-valuenow", String(pctS));
    });
    container.querySelectorAll(".js-op-bar-pint").forEach((el) => {
      el.style.width = `${pctP}%`;
      el.setAttribute("aria-valuenow", String(pctP));
    });
    container.querySelectorAll(".js-op-bar-term").forEach((el) => {
      el.style.width = `${pctT}%`;
      el.setAttribute("aria-valuenow", String(pctT));
    });
  });
  document.querySelectorAll(`.js-open-avance-modal[data-viga='${id}']`).forEach((b) => {
    b.setAttribute("data-soldadas", String(s));
    b.setAttribute("data-pintadas", String(p));
    b.setAttribute("data-terminadas", String(t));
    b.setAttribute("data-objetivo", String(o));
  });
}

function openAvanceModal(btn) {
  if (!avanceModal || !avanceForm || !avanceSoldEl || !avancePintEl || !avanceTermEl) return;
  const action = (btn.getAttribute("data-action") || "").trim();
  const vid = (btn.getAttribute("data-viga") || "").trim();
  const codigo = (btn.getAttribute("data-codigo") || "").trim();
  const soldadas = (btn.getAttribute("data-soldadas") || "0").trim();
  const pintadas = (btn.getAttribute("data-pintadas") || "0").trim();
  const terminadas = (btn.getAttribute("data-terminadas") || "0").trim();
  const objetivo = (btn.getAttribute("data-objetivo") || "0").trim();
  const estado = (btn.getAttribute("data-estado") || "").trim();
  const pendienteHasta = (btn.getAttribute("data-pendiente-hasta") || "").trim();
  avanceRevertAction = (btn.getAttribute("data-revert-action") || "").trim();
  if (!action || !vid) return;
  avanceForm.action = action;
  avanceForm.setAttribute("data-viga", String(vid));
  avanceForm.setAttribute("data-objetivo", String(objetivo));
  if (avanceVigaEl) avanceVigaEl.textContent = codigo ? `#${vid} · ${codigo}` : `#${vid}`;
  if (avanceObjetivoEl) avanceObjetivoEl.textContent = objetivo;
  avanceSoldEl.value = soldadas;
  avancePintEl.value = pintadas;
  avanceTermEl.value = terminadas;
  avanceSoldEl.max = objetivo;
  avancePintEl.max = objetivo;
  avanceTermEl.max = objetivo;
  if (avancePendienteWrap && avancePendienteHastaEl) {
    if (estado === "Terminado (bloqueo pend.)" && pendienteHasta) {
      avancePendienteHastaEl.textContent = pendienteHasta;
      avancePendienteWrap.style.display = "";
    } else {
      avancePendienteHastaEl.textContent = "";
      avancePendienteWrap.style.display = "none";
    }
  }
  if (avanceRevertBtn) {
    if (estado === "Terminado (bloqueo pend.)" && avanceRevertAction) {
      avanceRevertBtn.style.display = "";
    } else {
      avanceRevertBtn.style.display = "none";
    }
  }
  avanceModal.show();
}

if (avanceRevertBtn) {
  avanceRevertBtn.addEventListener("click", () => {
    if (!avanceRevertAction) return;
    if (!confirm("¿Confirmas revertir el cierre?")) return;
    const csrf = window.MES.cookie("csrftoken");
    const fd = new FormData();
    fd.set("next", window.location.pathname + window.location.search);
    fetch(avanceRevertAction, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: csrf ? { "X-CSRFToken": csrf } : {},
    })
      .then(() => window.location.reload())
      .catch(() => window.location.reload());
  });
}

document.querySelectorAll(".js-open-avance-modal").forEach((btn) => {
  btn.addEventListener("click", () => openAvanceModal(btn));
});
document.querySelectorAll(".js-op-bar-sold, .js-op-bar-pint, .js-op-bar-term").forEach((bar) => {
  const raw = (bar.getAttribute("data-pct") || "").toString().trim();
  const pct = parseFloat(raw.replace(",", "."));
  if (!Number.isFinite(pct)) return;
  bar.style.width = `${pct}%`;
  bar.setAttribute("aria-valuenow", String(pct));
});

if (avanceForm) {
  avanceForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const vid = (avanceForm.getAttribute("data-viga") || "").trim();
    if (!vid || !avanceSoldEl || !avancePintEl || !avanceTermEl) return;
    const objetivo = parseInt((avanceForm.getAttribute("data-objetivo") || "0").toString(), 10);
    const rawSold = (avanceSoldEl.value || "").toString().trim();
    const rawPint = (avancePintEl.value || "").toString().trim();
    const rawTerm = (avanceTermEl.value || "").toString().trim();
    const soldadas = rawSold === "" ? 0 : parseInt(rawSold, 10);
    const pintadas = rawPint === "" ? 0 : parseInt(rawPint, 10);
    const terminadas = rawTerm === "" ? 0 : parseInt(rawTerm, 10);
    if (
      !Number.isFinite(objetivo) ||
      objetivo <= 0 ||
      !Number.isFinite(soldadas) ||
      !Number.isFinite(pintadas) ||
      !Number.isFinite(terminadas) ||
      soldadas < 0 ||
      pintadas < 0 ||
      terminadas < 0 ||
      soldadas > objetivo ||
      pintadas > objetivo ||
      terminadas > objetivo
    ) {
      window.MES.aviso("Cantidades inválidas. Regla: ningún avance puede superar el objetivo.", "danger");
      return;
    }
    const fd = new FormData(avanceForm);
    fd.set("cantidad_soldada", String(soldadas));
    fd.set("cantidad_pintada", String(pintadas));
    fd.set("cantidad_terminada", String(terminadas));
    const csrf = window.MES.cookie("csrftoken");
    fetch(avanceForm.action, {
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
          window.MES.aviso((data && data.error) ? data.error : "No se pudo guardar el avance.", "danger");
          return;
        }
        if (data.reload) {
          saveScroll();
          window.location.reload();
          return;
        }
        setOpAvanceUI(
          String(data.id || vid),
          data.soldadas,
          data.pintadas,
          data.terminadas,
          data.objetivo,
          data.soldadas_pct,
          data.pintadas_pct,
          data.terminadas_pct
        );
        window.MES.aviso("Avance guardado.", "success");
        if (avanceModal) avanceModal.hide();
      })
      .catch(() => window.MES.aviso("No se pudo guardar el avance.", "danger"));
  });
}

const planoModalEl = document.getElementById("planoModal");
const planoModal = planoModalEl ? new bootstrap.Modal(planoModalEl) : null;
const planoEmbed = document.getElementById("planoModalEmbed");
const planoOpenTab = document.getElementById("planoModalOpenTab");
document.querySelectorAll(".js-open-plano").forEach((btn) => {
  btn.addEventListener("click", () => {
    const url = (btn.getAttribute("data-url") || "").trim();
    if (!url || !planoModal || !planoEmbed) return;
    planoEmbed.src = url + "#view=FitH";
    if (planoOpenTab) planoOpenTab.href = url;
    planoModal.show();
  });
});
if (planoModalEl) {
  planoModalEl.addEventListener("hidden.bs.modal", () => {
    if (planoEmbed) planoEmbed.src = "";
  });
}

const asignacionesModalEl = document.getElementById("asignacionesModal");
const asignacionesModal = asignacionesModalEl ? new bootstrap.Modal(asignacionesModalEl) : null;
const asignacionesForm = document.getElementById("asignacionesForm");
const asignacionesVigaCodigo = document.getElementById("asignacionesVigaCodigo");
const corteOperadoresList = document.getElementById("asigCorteOperadoresList");
const soldaduraList = document.getElementById("asigSoldaduraList");
const pinturaList = document.getElementById("asigPinturaList");
const corteMaquinasList = document.getElementById("asigCorteMaquinasList");
const asignUrlTemplate = cfg.urlAsignaciones;

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

document.querySelectorAll(".js-open-asignaciones").forEach((btn) => {
  btn.addEventListener("click", () => {
    const vid = (btn.getAttribute("data-viga") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    if (!vid || !asignacionesForm || !asignacionesModal) return;
    asignacionesForm.action = asignUrlTemplate.replace("/0/", `/${vid}/`);
    asignacionesForm.setAttribute("data-viga", String(vid));
    if (asignacionesVigaCodigo) asignacionesVigaCodigo.textContent = codigo ? `#${vid} · ${codigo}` : `#${vid}`;
    fillChecklist(corteOperadoresList, participantes.Corte?.operadores || [], parseCsvIds(btn.getAttribute("data-corte-operadores")), "corte_operador_ids", false);
    fillChecklist(corteMaquinasList, (participantes.Corte?.maquinas || []).map((m) => ({ id: m.id, nombre: m.nombre, rol: "Máquina" })), parseCsvIds(btn.getAttribute("data-corte-maquinas")), "corte_maquina_ids", true);
    fillChecklist(soldaduraList, participantes.Soldadura?.items || [], parseCsvIds(btn.getAttribute("data-soldadura")), "soldadura_ids", true);
    fillChecklist(pinturaList, participantes.Pintura?.items || [], parseCsvIds(btn.getAttribute("data-pintura")), "pintura_ids", true);
    asignacionesModal.show();
  });
});

if (asignacionesForm) {
  asignacionesForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const vid = (asignacionesForm.getAttribute("data-viga") || "").trim();
    const pageMode = cfg.modo;
    if (pageMode !== "soldadura") {
      const anyChecked = !!asignacionesForm.querySelector("input[name='corte_operador_ids']:checked");
      if (!anyChecked) {
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
      .catch(() => window.MES.aviso("No se pudieron guardar las asignaciones.", "danger"));
  });
}

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
).slice(0, 2000);

function buildSuggestions(q) {
  if (!suggestions) return;
  suggestions.innerHTML = "";
  const val = (q || "").trim().toLowerCase();
  if (!val) return;
  let count = 0;
  for (const c of codigoUniverse) {
    if (c.toLowerCase().includes(val)) {
      const opt = document.createElement("option");
      opt.value = c;
      suggestions.appendChild(opt);
      count += 1;
      if (count >= 15) break;
    }
  }
}

function applyLiveFilter(q) {
  const val = (q || "").trim().toLowerCase();
  if (!val) {
    vigaItems.forEach((el) => (el.style.display = ""));
    return;
  }
  vigaItems.forEach((el) => {
    const codigo = (el.getAttribute("data-codigo") || "").toString().toLowerCase();
    const proyecto = (el.getAttribute("data-proyecto") || "").toString().toLowerCase();
    const desc = (el.getAttribute("data-descripcion") || "").toString().toLowerCase();
    const ok = codigo.includes(val) || proyecto.includes(val) || desc.includes(val);
    el.style.display = ok ? "" : "none";
  });
}

if (liveSearchInput) {
  applyLiveFilter(liveSearchInput.value || "");
  buildSuggestions(liveSearchInput.value || "");
  liveSearchInput.addEventListener("input", () => {
    const val = liveSearchInput.value || "";
    buildSuggestions(val);
    applyLiveFilter(val);
    try { localStorage.setItem("viga_list_q", val); } catch (e) {}
  });
  try {
    const saved = localStorage.getItem("viga_list_q");
    if (saved && !liveSearchInput.value) {
      liveSearchInput.value = saved;
      buildSuggestions(saved);
      applyLiveFilter(saved);
    }
  } catch (e) {}
}
if (clearLiveSearchBtn && liveSearchInput) {
  clearLiveSearchBtn.addEventListener("click", () => {
    liveSearchInput.value = "";
    buildSuggestions("");
    applyLiveFilter("");
    try { localStorage.removeItem("viga_list_q"); } catch (e) {}
    liveSearchInput.focus();
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
  if (!decoteInput || !decoteBtn) return;
  const ok = (decoteInput.value || "").trim().toUpperCase() === "ELIMINAR";
  decoteBtn.disabled = !ok;
}
document.querySelectorAll(".js-decote-open").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!decoteModal || !decoteForm) return;
    const action = (btn.getAttribute("data-action") || "").trim();
    const codigo = (btn.getAttribute("data-codigo") || "").trim();
    const pieza = (btn.getAttribute("data-pieza") || "").trim();
    const dias = (btn.getAttribute("data-dias") || "").trim();
    const next = (btn.getAttribute("data-next") || "").trim();
    if (!action) return;
    decoteForm.action = action;
    if (decoteCodigo) decoteCodigo.textContent = `${codigo} (${pieza})`;
    if (decoteDias) decoteDias.textContent = dias;
    if (decoteNext) decoteNext.value = next;
    if (decoteInput) decoteInput.value = "";
    updateDecoteButton();
    decoteModal.show();
    try { if (decoteInput) decoteInput.focus(); } catch (e) {}
  });
});
if (decoteInput) decoteInput.addEventListener("input", updateDecoteButton);

const decoteBulkModalEl = document.getElementById("decoteBulkModal");
const decoteBulkModal = decoteBulkModalEl ? new bootstrap.Modal(decoteBulkModalEl) : null;
const decoteBulkForm = document.getElementById("decoteBulkForm");
const decoteBulkInput = document.getElementById("decoteBulkConfirmText");
const decoteBulkBtn = document.getElementById("decoteBulkConfirmBtn");
const decoteBulkTotal = document.getElementById("decoteBulkTotal");
const decoteBulkCliente = document.getElementById("decoteBulkCliente");
const decoteBulkQ = document.getElementById("decoteBulkQ");
const decoteBulkNext = document.getElementById("decoteBulkNext");
function updateDecoteBulkButton() {
  if (!decoteBulkInput || !decoteBulkBtn) return;
  const ok = (decoteBulkInput.value || "").trim().toUpperCase() === "ELIMINAR";
  decoteBulkBtn.disabled = !ok;
}
document.querySelectorAll(".js-decote-bulk-open").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (!decoteBulkModal || !decoteBulkForm) return;
    const action = (btn.getAttribute("data-action") || "").trim();
    const next = (btn.getAttribute("data-next") || "").trim();
    const cliente = (btn.getAttribute("data-cliente") || "").trim();
    const q = (btn.getAttribute("data-q") || "").trim();
    const total = (btn.getAttribute("data-total") || "").trim();
    if (!action) return;
    decoteBulkForm.action = action;
    if (decoteBulkNext) decoteBulkNext.value = next;
    if (decoteBulkCliente) decoteBulkCliente.value = cliente;
    if (decoteBulkQ) decoteBulkQ.value = q;
    if (decoteBulkTotal) decoteBulkTotal.textContent = total;
    if (decoteBulkInput) decoteBulkInput.value = "";
    updateDecoteBulkButton();
    decoteBulkModal.show();
    try { if (decoteBulkInput) decoteBulkInput.focus(); } catch (e) {}
  });
});
if (decoteBulkInput) decoteBulkInput.addEventListener("input", updateDecoteBulkButton);

});
