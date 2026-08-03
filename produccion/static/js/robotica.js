/* Robótica.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 */

window.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form.js-confirm-delete").forEach((f) => {
    f.addEventListener("submit", (e) => {
      const ok = confirm("¿Seguro que deseas eliminar? Esta acción no se puede deshacer.");
      if (!ok) e.preventDefault();
    });
  });

  const payloadEl = document.getElementById("robotWeeklyPayload");
  const payload = payloadEl ? JSON.parse(payloadEl.textContent) : {labels: [], ton: [], piezas: []};
  const ctx = document.getElementById("chartRobotWeekly");
  if (!ctx) return;
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: payload.labels,
      datasets: [
        { label: "Ton", data: payload.ton, backgroundColor: "#5e72e4", yAxisID: "y" },
        { label: "Piezas", data: payload.piezas, backgroundColor: "#11cdef", yAxisID: "y1" },
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
      scales: {
        y: { beginAtZero: true, position: "left" },
        y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } },
      }
    }
  });
});
