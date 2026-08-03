/* Pantalla de entrada.
 *
 * Estaba escrito dentro de la plantilla.
 */

const pwd = document.getElementById("loginPassword");
const btn = document.getElementById("togglePasswordBtn");
if (pwd && btn) {
  btn.addEventListener("click", () => {
    const isPwd = (pwd.getAttribute("type") || "password") === "password";
    pwd.setAttribute("type", isPwd ? "text" : "password");
    btn.textContent = isPwd ? "Ocultar" : "Mostrar";
  });
}
