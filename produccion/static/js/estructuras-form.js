/* Alta y edición de piezas de Estructuras.
 *
 * Estaba escrito dentro de la plantilla.
 */

(function () {
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
