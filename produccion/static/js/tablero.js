/* El tablero de reportes.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

const payload = JSON.parse(document.getElementById("chartPayload").textContent);
const prod = JSON.parse(document.getElementById("productividadPayload").textContent);
const flow = JSON.parse(document.getElementById("flowPayload").textContent);
const sla = JSON.parse(document.getElementById("slaPayload").textContent);
const aging = JSON.parse(document.getElementById("agingPayload").textContent);
const weekly = JSON.parse(document.getElementById("weeklyPayload").textContent);
const terminadoProgress = JSON.parse(document.getElementById("terminadoProgressPayload").textContent);
const kpiCorteMaquinas = JSON.parse(document.getElementById("kpiMaquinasCortePayload").textContent);

const chartThroughputEl = document.getElementById("chartThroughput");
if (chartThroughputEl) {
new Chart(chartThroughputEl, {
  type: "bar",
  data: {
    labels: flow.labels,
    datasets: [
      {
        label: "Ton terminadas",
        data: flow.ton_terminadas,
        backgroundColor: "#2dce89",
        borderRadius: 8,
        yAxisID: "y",
      },
      {
        type: "line",
        label: "Piezas terminadas",
        data: flow.piezas_terminadas,
        borderColor: "#5e72e4",
        backgroundColor: "rgba(94,114,228,0.15)",
        tension: 0.25,
        fill: true,
        pointRadius: 2,
        yAxisID: "y2",
      }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom" },
      tooltip: { mode: "index", intersect: false }
    },
    scales: {
      x: { ticks: { maxRotation: 0, autoSkip: true } },
      y: { beginAtZero: true, title: { display: true, text: "Ton" } },
      y2: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Piezas" } },
    }
  }
});
}

const chartSlaDonutEl = document.getElementById("chartSlaDonut");
if (chartSlaDonutEl) {
new Chart(chartSlaDonutEl, {
  type: "doughnut",
  data: {
    labels: ["On-time", "Late", "Sin fecha"],
    datasets: [{
      data: [sla.on_time || 0, sla.late || 0, sla.no_due || 0],
      backgroundColor: ["#2dce89", "#f5365c", "#e9ecef"],
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom" } },
    cutout: "70%",
  }
});
}

const chartAgingEl = document.getElementById("chartAging");
if (chartAgingEl) {
new Chart(chartAgingEl, {
  type: "bar",
  data: {
    labels: aging.labels,
    datasets: [{
      label: "Días (promedio)",
      data: aging.days,
      backgroundColor: aging.colors,
      borderRadius: 8,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true } }
  }
});
}

const chartWeeklyEl = document.getElementById("chartWeekly");
if (chartWeeklyEl) {
new Chart(chartWeeklyEl, {
  type: "bar",
  data: {
    labels: weekly.labels,
    datasets: [
      {
        label: "Ton terminadas",
        data: weekly.ton,
        backgroundColor: "#2dce89",
        borderRadius: 8,
        yAxisID: "y",
      },
      {
        type: "line",
        label: "Piezas terminadas",
        data: weekly.piezas,
        borderColor: "#5e72e4",
        backgroundColor: "rgba(94,114,228,0.15)",
        tension: 0.25,
        fill: true,
        pointRadius: 2,
        yAxisID: "y2",
      }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom" } },
    scales: {
      x: { ticks: { maxRotation: 0, autoSkip: true } },
      y: { beginAtZero: true, title: { display: true, text: "Ton" } },
      y2: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Piezas" } },
    }
  }
});
}

const corteLabels = (kpiCorteMaquinas || []).map((r) => r.maquina);
const cortePiezas = (kpiCorteMaquinas || []).map((r) => r.piezas);
const corteTon = (kpiCorteMaquinas || []).map((r) => r.ton);
const corteTonProm = (kpiCorteMaquinas || []).map((r) => r.ton_promedio);
const corteChartEl = document.getElementById("chartCorteMaquinas");
if (corteChartEl) {
  new Chart(corteChartEl, {
    data: {
      labels: corteLabels,
      datasets: [
        {
          type: "bar",
          label: "Ton (total)",
          data: corteTon,
          backgroundColor: "#2dce89",
          borderRadius: 8,
          yAxisID: "y",
        },
        {
          type: "bar",
          label: "Piezas",
          data: cortePiezas,
          backgroundColor: "#11cdef",
          borderRadius: 8,
          yAxisID: "y2",
        },
        {
          type: "line",
          label: "Ton/pieza",
          data: corteTonProm,
          borderColor: "#5e72e4",
          backgroundColor: "rgba(94,114,228,0.15)",
          tension: 0.25,
          fill: false,
          pointRadius: 2,
          yAxisID: "y",
        },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        x: { ticks: { maxRotation: 0, autoSkip: true } },
        y: { beginAtZero: true, title: { display: true, text: "Ton" } },
        y2: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Piezas" } },
      }
    }
  });
}

const chartTerminadoProgressEl = document.getElementById("chartTerminadoProgress");
if (chartTerminadoProgressEl) {
new Chart(chartTerminadoProgressEl, {
  type: "doughnut",
  data: {
    labels: ["Terminado", "Restante"],
    datasets: [{
      data: [
        terminadoProgress.terminado_piezas || 0,
        Math.max((terminadoProgress.total_piezas || 0) - (terminadoProgress.terminado_piezas || 0), 0),
      ],
      backgroundColor: ["#2dce89", "#e9ecef"],
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const v = ctx.raw || 0;
            const t = terminadoProgress.total_piezas || 0;
            const pct = t ? (v / t * 100) : 0;
            return `${ctx.label}: ${v} (${pct.toFixed(1)}%)`;
          }
        }
      }
    },
    cutout: "75%",
  },
  plugins: [{
    id: "centerText",
    afterDraw: (chart) => {
      const {ctx, chartArea} = chart;
      if (!chartArea) return;
      const cx = (chartArea.left + chartArea.right) / 2;
      const cy = (chartArea.top + chartArea.bottom) / 2;
      const t = terminadoProgress.total_piezas || 0;
      const d = terminadoProgress.terminado_piezas || 0;
      const pct = t ? (d / t * 100) : 0;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#2dce89";
      ctx.font = "600 18px system-ui, -apple-system, Segoe UI, Roboto, Arial";
      ctx.fillText(`${pct.toFixed(0)}%`, cx, cy - 6);
      ctx.fillStyle = "#6c757d";
      ctx.font = "12px system-ui, -apple-system, Segoe UI, Roboto, Arial";
      ctx.fillText(`${d}/${t}`, cx, cy + 14);
      ctx.restore();
    }
  }]
});
}

document.querySelectorAll(".js-weekly-recalc").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    const ok = confirm("Vas a recalcular el reporte semanal y SOBRESCRIBIR el snapshot guardado.\n\nSi ya eliminaste piezas o cambió información, este reporte puede cambiar.\n\n¿Deseas continuar?");
    if (!ok) e.preventDefault();
  });
});

const chartPiezasPctEl = document.getElementById("chartPiezasPct");
if (chartPiezasPctEl) {
new Chart(chartPiezasPctEl, {
  type: "doughnut",
  data: {
    labels: payload.labels,
    datasets: [{
      data: payload.pct_piezas,
      backgroundColor: payload.colors,
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom" },
      tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${ctx.parsed}%` } }
    },
    cutout: "68%",
  },
  plugins: [{
    id: "pctLabels",
    afterDatasetsDraw: (chart) => {
      const ctx = chart.ctx;
      const ds = chart.data.datasets && chart.data.datasets[0];
      if (!ctx || !ds) return;
      const meta = chart.getDatasetMeta(0);
      const bg = ds.backgroundColor || [];
      const vals = ds.data || [];
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "700 12px system-ui, -apple-system, Segoe UI, Roboto, Arial";
      for (let i = 0; i < meta.data.length; i++) {
        const el = meta.data[i];
        const v = Number(vals[i] || 0);
        if (!el || !Number.isFinite(v) || v <= 0) continue;
        const p = el.tooltipPosition();
        const txt = `${v}%`;
        const c = String(bg[i] || "#111");
        ctx.lineWidth = 4;
        ctx.strokeStyle = c;
        ctx.strokeText(txt, p.x, p.y);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(txt, p.x, p.y);
      }
      ctx.restore();
    }
  }]
});
}

const chartTonEl = document.getElementById("chartTon");
if (chartTonEl) {
new Chart(chartTonEl, {
  type: "bar",
  data: {
    labels: payload.labels,
    datasets: [{
      label: "Ton",
      data: payload.ton,
      backgroundColor: payload.colors,
      borderRadius: 8,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, ticks: { callback: (v) => v } },
      x: { ticks: { maxRotation: 0, autoSkip: true } }
    }
  }
});
}

const chartProdPorIntegranteEl = document.getElementById("chartProdPorIntegrante");
if (chartProdPorIntegranteEl) {
new Chart(chartProdPorIntegranteEl, {
  type: "doughnut",
  data: {
    labels: ["Avance a meta", "Faltante"],
    datasets: [{
      data: (() => {
        const meta = Number(prod.ton_por_persona_meta || 0);
        const val = Number(prod.ton_por_integrante_global || 0);
        const pct = meta > 0 ? Math.min((val / meta) * 100, 100) : 0;
        return [Math.round(pct * 10) / 10, Math.round((100 - pct) * 10) / 10];
      })(),
      backgroundColor: ["#2dce89", "#e9ecef"],
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const meta = Number(prod.ton_por_persona_meta || 0);
            const val = Number(prod.ton_por_integrante_global || 0);
            if (ctx.dataIndex === 0) return `Avance: ${ctx.parsed}% (Ton/persona: ${val}, Meta: ${meta})`;
            return `Faltante: ${ctx.parsed}%`;
          }
        }
      }
    },
    cutout: "75%",
  }
});
}

const totalPersonal = prod.integrantes.reduce((a, b) => a + b, 0);
const pctPersonal = prod.integrantes.map((v) => totalPersonal ? Math.round((v / totalPersonal) * 1000) / 10 : 0);

const chartIntegrantesEquipoEl = document.getElementById("chartIntegrantesEquipo");
if (chartIntegrantesEquipoEl) {
new Chart(chartIntegrantesEquipoEl, {
  type: "bar",
  data: {
    labels: prod.labels,
    datasets: [{
      label: "Integrantes",
      data: prod.integrantes,
      backgroundColor: prod.colors,
      borderRadius: 8,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const idx = ctx.dataIndex;
            const integ = prod.integrantes[idx] || 0;
            const pct = pctPersonal[idx] || 0;
            return `Integrantes: ${integ} (${pct}%)`;
          }
        }
      }
    },
    scales: {
      y: { beginAtZero: true },
      x: { ticks: { maxRotation: 0, autoSkip: true } }
    }
  }
});
}

function buildMachineColorMap() {
  const map = {};
  const ids = [];
  const add = (arr) => (arr || []).forEach((m) => { if (m && m.id != null) ids.push(Number(m.id)); });
  add(weekly.paros_maquinas_corte);
  add(weekly.paros_maquinas_soldadura);
  add(weekly.paros_maquinas_robot);

  let i = 0;
  ids.forEach((id) => {
    if (!Number.isFinite(id) || map[id]) return;
    let hue = (i * 137.508) % 360;
    if (hue <= 45 || hue >= 350) hue = (hue + 70) % 360;
    const color = `hsl(${hue.toFixed(1)} 72% 45%)`;
    map[id] = color;
    i += 1;
  });
  return map;
}

const machineColorMap = buildMachineColorMap();
function machineColor(machineId) {
  const id = Number(machineId || 0);
  const c = machineColorMap[id];
  return c || "#2dce89";
}

function renderParosPie(elId, uptimeH, downH, uptimeColor) {
  const el = document.getElementById(elId);
  if (!el) return;
  new Chart(el, {
    type: "pie",
    data: {
      labels: ["Funcionamiento (h)", "Paro (h)"],
      datasets: [{
        data: [Number(uptimeH || 0), Number(downH || 0)],
        backgroundColor: [uptimeColor || "#2dce89", "#fb6340"],
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.label}: ${Number(ctx.raw || 0).toFixed(2)}`
          }
        }
      }
    }
  });
}

renderParosPie("chartParosCorte", weekly.paros_uptime_horas_corte, weekly.paros_downtime_horas_corte);
renderParosPie("chartParosSoldadura", weekly.paros_uptime_horas_soldadura, weekly.paros_downtime_horas_soldadura);
renderParosPie("chartParosRobot", weekly.paros_uptime_horas_robot, weekly.paros_downtime_horas_robot);
(weekly.paros_maquinas_corte || []).forEach((m) => renderParosPie(`chartParosMachine${m.id}`, m.up_h, m.down_h, machineColor(m.id)));
(weekly.paros_maquinas_soldadura || []).forEach((m) => renderParosPie(`chartParosMachine${m.id}`, m.up_h, m.down_h, machineColor(m.id)));
(weekly.paros_maquinas_robot || []).forEach((m) => renderParosPie(`chartParosMachine${m.id}`, m.up_h, m.down_h, machineColor(m.id)));

document.querySelectorAll(".js-bg").forEach((el) => {
  const c = el.getAttribute("data-color");
  if (c) el.style.background = c;
});
document.querySelectorAll(".js-progress").forEach((el) => {
  const w = (el.getAttribute("data-width") || "0").replace(",", ".");
  const c = el.getAttribute("data-color") || "";
  el.style.width = w + "%";
  if (c) el.style.background = c;
});

const quienModalEl = document.getElementById("quienDetalleModal");
const quienModal = quienModalEl ? new bootstrap.Modal(quienModalEl) : null;
const quienBody = document.getElementById("quienDetalleBody");
const quienSubtitle = document.getElementById("quienDetalleSubtitle");
const quienUrlTemplate = cfg.urlQuien;
const quienCacheEl = document.getElementById("quienDetalleCache");
const quienCache = quienCacheEl ? JSON.parse(quienCacheEl.textContent) : null;

function buildUrl(colabId, etapa) {
  return quienUrlTemplate.replace("/0/Corte/", `/${colabId}/${encodeURIComponent(etapa)}/`);
}

function setLoading() {
  if (!quienBody) return;
  quienBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">Cargando…</td></tr>';
}

function setRows(items) {
  if (!quienBody) return;
  if (!items || items.length === 0) {
    quienBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">Sin piezas asignadas en WIP.</td></tr>';
    return;
  }
  quienBody.innerHTML = "";
  items.forEach((it) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="text-muted">${it.area || ""}</td>
      <td class="text-muted">${it.id}</td>
      <td class="fw-semibold">${it.codigo || ""}</td>
      <td class="text-muted">${it.pieza || ""}</td>
      <td class="text-muted">${it.proyecto || ""}</td>
      <td class="fw-semibold">${it.estado || ""}</td>
      <td class="text-end">${Number(it.ton || 0).toFixed(3)}</td>
      <td class="text-muted">${it.fecha_compromiso || ""}</td>
    `;
    quienBody.appendChild(tr);
  });
}

document.querySelectorAll(".js-quien-detalle").forEach((el) => {
  el.addEventListener("click", async () => {
    const colabId = (el.getAttribute("data-colab") || "").trim();
    const etapa = (el.getAttribute("data-etapa") || "").trim();
    if (!colabId || !etapa || !quienModal) return;
    if (quienSubtitle) quienSubtitle.textContent = "";
    setLoading();
    quienModal.show();
    try {
      let data = null;
      const key = `${colabId}|${etapa}`;
      if (quienCache && quienCache[key]) {
        data = quienCache[key];
      } else {
        const res = await fetch(buildUrl(colabId, etapa), { headers: { "Accept": "application/json" } });
        data = await res.json();
      }
      if (!data.ok) {
        setRows([]);
        if (quienSubtitle) quienSubtitle.textContent = "No se pudo cargar.";
        return;
      }
      const name = (data.colaborador && data.colaborador.nombre) ? data.colaborador.nombre : "";
      const team = (data.colaborador && data.colaborador.equipo) ? data.colaborador.equipo : "";
      if (quienSubtitle) quienSubtitle.textContent = `${name}${team ? " · " + team : ""} · ${data.etapa} · ${data.count} piezas`;
      setRows(data.items || []);
    } catch (e) {
      setRows([]);
      if (quienSubtitle) quienSubtitle.textContent = "No se pudo cargar.";
    }
  });
});
