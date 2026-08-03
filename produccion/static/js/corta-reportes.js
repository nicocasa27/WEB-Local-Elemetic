/* Reportes de Corta.mx.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 */

(function () {
  const modalEl = document.getElementById("terminadoModal");
  const modal = modalEl ? new bootstrap.Modal(modalEl) : null;
  const titleEl = document.getElementById("terminadoTitle");
  const subtitleEl = document.getElementById("terminadoSubtitle");
  const bodyEl = document.getElementById("terminadoEtapasBody");
  const canvas = document.getElementById("terminadoChart");
  let chart = null;

  function n(v) {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  }

  function fmtHours(h) {
    const x = n(h);
    return (Math.round((x + Number.EPSILON) * 100) / 100).toFixed(2);
  }

  let exportMap = null;
  try {
    const el = document.getElementById("cortaExportDetail");
    exportMap = el ? JSON.parse(el.textContent || "{}") : null;
  } catch (e) {
    exportMap = null;
  }

  async function open(url, id) {
    if (!modal) return;
    if (titleEl) titleEl.textContent = "Cargando…";
    if (subtitleEl) subtitleEl.textContent = "";
    if (bodyEl) bodyEl.innerHTML = "";
    modal.show();

    let payload = null;
    const key = id != null ? String(id) : "";
    if (exportMap && key && exportMap[key]) {
      payload = exportMap[key];
    } else {
      try {
        const resp = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        payload = await resp.json();
      } catch (e) {
        payload = { ok: false, error: "No se pudo cargar." };
      }
    }
    if (!payload || !payload.ok) {
      if (titleEl) titleEl.textContent = "Error";
      if (subtitleEl) subtitleEl.textContent = String((payload && payload.error) || "No se pudo cargar.");
      return;
    }

    const o = payload.orden || {};
    const etapas = payload.etapas || [];
    if (titleEl) titleEl.textContent = (o.codigo || o.folio || "Pedido") + " · " + (o.kg != null ? String(o.kg) + " kg" : "");
    if (subtitleEl) subtitleEl.textContent = (o.cliente || "") + (o.piezas != null ? " · " + String(o.piezas) + " pzs" : "");

    const labels = [];
    const hours = [];
    for (const e of etapas) {
      labels.push(String(e.etapa || ""));
      hours.push(n(e.horas));
    }

    if (bodyEl) {
      bodyEl.innerHTML = "";
      for (const e of etapas) {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.textContent = String(e.etapa || "");
        const td2 = document.createElement("td");
        td2.className = "text-end";
        td2.textContent = fmtHours(e.horas) + " h";
        tr.appendChild(td1);
        tr.appendChild(td2);
        bodyEl.appendChild(tr);
      }
    }

    if (chart) {
      try { chart.destroy(); } catch (e) {}
      chart = null;
    }
    if (canvas && typeof Chart !== "undefined") {
      chart = new Chart(canvas, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [{
            label: "Horas",
            data: hours,
            backgroundColor: "#11cdef",
            borderRadius: 8,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, title: { display: true, text: "Horas" } } }
        }
      });
    }
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target && ev.target.closest ? ev.target.closest(".js-open-terminado") : null;
    if (!btn) return;
    ev.preventDefault();
    open(btn.getAttribute("data-url") || "", btn.getAttribute("data-id") || "");
  });

  if (modalEl) {
    modalEl.addEventListener("hidden.bs.modal", () => {
      if (chart) {
        try { chart.destroy(); } catch (e) {}
        chart = null;
      }
    });
  }
})();
