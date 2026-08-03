/* Catálogo de materiales de Corta.mx.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

(function () {
  try { window.parent.postMessage({type: "corte:close-edit", reload: true}, window.location.origin); } catch (e) {}
  try { setTimeout(() => window.close(), 250); } catch (e) {}
})();

      (function () {
        const payloadEl = document.getElementById("laserNomenclaturasPayload");
        const payload = payloadEl ? JSON.parse(payloadEl.textContent) : [];
        const catEl = document.getElementById(cfg.campoCategoria);
        const tipoEl = document.getElementById(cfg.campoTipo);
        const nombreEl = document.getElementById(cfg.campoNombre);
        const listEl = document.getElementById("laserNomenclaturaList");
        const itemsEl = document.getElementById("laserNomenclaturaItems");
        if (nombreEl) nombreEl.setAttribute("list", "laserNomenclaturaList");

        function norm(s) {
          return String(s || "").trim().toUpperCase();
        }

        function render() {
          const cat = norm(catEl ? catEl.value : "");
          const tipo = norm(tipoEl ? tipoEl.value : "");
          const q = norm(nombreEl ? nombreEl.value : "");
          const names = [];
          const seen = new Set();
          (payload || []).forEach((r) => {
            if (!r) return;
            if (cat && norm(r.categoria) !== cat) return;
            if (tipo && norm(r.tipo) !== tipo) return;
            const nm = String(r.nombre || "").trim();
            const nk = norm(nm);
            if (!nk) return;
            if (q && nk.indexOf(q) < 0) return;
            if (seen.has(nk)) return;
            seen.add(nk);
            names.push(nm);
          });
          names.sort((a, b) => norm(a).localeCompare(norm(b)));
          if (listEl) {
            listEl.innerHTML = names.map((n) => `<option value="${String(n).replaceAll('"', "&quot;")}"></option>`).join("");
          }
          if (itemsEl) {
            itemsEl.innerHTML = names
              .map((n) => `<button type="button" class="list-group-item list-group-item-action">${n}</button>`)
              .join("");
            Array.from(itemsEl.querySelectorAll("button")).forEach((btn) => {
              btn.addEventListener("click", function () {
                if (nombreEl) nombreEl.value = btn.textContent || "";
                render();
              });
            });
          }
        }

        if (catEl) catEl.addEventListener("input", render);
        if (tipoEl) tipoEl.addEventListener("input", render);
        if (nombreEl) nombreEl.addEventListener("input", render);
        render();
      })();

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

  const modalEl = document.getElementById("editIframeModal");
  const frame = document.getElementById("editIframeFrame");
  const modal = modalEl ? new bootstrap.Modal(modalEl) : null;

  document.addEventListener("click", (ev) => {
    const a = ev.target && ev.target.closest ? ev.target.closest("a.js-open-edit-iframe") : null;
    if (!a) return;
    ev.preventDefault();
    const href = a.getAttribute("href") || "";
    if (!href) return;
    if (!modal || !frame) {
      window.location.href = href;
      return;
    }
    saveScroll();
    frame.src = href;
    modal.show();
  });

  if (modalEl) {
    modalEl.addEventListener("hidden.bs.modal", () => {
      if (frame) frame.src = "about:blank";
    });
  }

  window.addEventListener("message", (ev) => {
    try {
      if (ev.origin !== window.location.origin) return;
      const data = ev.data || {};
      if (!data || data.type !== "corte:close-edit") return;
      if (modal) modal.hide();
      if (data.reload) {
        saveScroll();
        window.location.reload();
      }
    } catch (e) {}
  });
});
