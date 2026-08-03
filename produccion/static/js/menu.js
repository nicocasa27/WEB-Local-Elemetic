/* El menú principal.
 *
 * Estaba escrito dentro de la plantilla.
 */

const shareModalEl = document.getElementById("menuShareModal");
const qrEl = document.getElementById("menuShareQr");
const urlEl = document.getElementById("menuShareUrl");
const copyBtn = document.getElementById("menuCopyShareUrl");
let qrInstance = null;
function shareUrl() {
  return window.location.origin + document.body.dataset.urlLogin;
}
function renderQr() {
  const url = shareUrl();
  if (urlEl) urlEl.value = url;
  if (qrEl) qrEl.innerHTML = "";
  qrInstance = new QRCode(qrEl, { text: url, width: 220, height: 220, correctLevel: QRCode.CorrectLevel.M });
}
if (shareModalEl) {
  shareModalEl.addEventListener("shown.bs.modal", () => {
    if (qrInstance) return;
    renderQr();
  });
}
if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText((urlEl && urlEl.value) ? urlEl.value : shareUrl());
      copyBtn.textContent = "Copiado";
      setTimeout(() => (copyBtn.textContent = "Copiar"), 1200);
    } catch (e) {
      if (urlEl) {
        urlEl.select();
        document.execCommand("copy");
      }
    }
  });
}
