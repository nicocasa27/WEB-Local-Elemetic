/* El teclado del PIN.
 *
 * Todo lo de aquí es comodidad. Sin JavaScript la pantalla sigue funcionando:
 * el campo es un campo de verdad, el teclado numérico del aparato lo llena, y
 * la tecla de la flecha es un `submit`. Eso importa porque esta pantalla es la
 * puerta: si se cae, no entra nadie al sistema.
 */
(function () {
  "use strict";

  var form = document.querySelector(".pin-form");
  if (!form) return;

  var campo = form.querySelector(".js-pin-campo");
  var largo = parseInt(campo.getAttribute("maxlength"), 10) || 4;
  var teclas = form.querySelectorAll(".pin-tecla");

  /* En sólo lectura para que al tocarlo no salte el teclado del sistema
   * encima de las teclas grandes. Se pone desde aquí y no en la plantilla:
   * sin JavaScript el campo tiene que poder escribirse. */
  campo.readOnly = true;

  function escribir(digito) {
    if (campo.value.length >= largo) return;
    campo.value += digito;
    if (campo.value.length === largo) {
      /* Cuatro dígitos y va. Un botón de confirmar sería un toque más para
       * decir lo que ya se dijo: nadie teclea un PIN de cuatro y se detiene. */
      form.requestSubmit ? form.requestSubmit() : form.submit();
    }
  }

  function borrar() {
    campo.value = campo.value.slice(0, -1);
  }

  form.addEventListener("click", function (evento) {
    var tecla = evento.target.closest(".js-pin-tecla");
    if (tecla) {
      escribir(tecla.getAttribute("data-digito"));
      return;
    }
    if (evento.target.closest(".js-pin-borrar")) borrar();
  });

  /* Con teclado físico —hay tabletas con funda— se teclea igual. */
  document.addEventListener("keydown", function (evento) {
    if (evento.key >= "0" && evento.key <= "9") {
      escribir(evento.key);
      evento.preventDefault();
    } else if (evento.key === "Backspace") {
      borrar();
      evento.preventDefault();
    }
  });

  /* La espera por intentos fallidos. Las teclas se apagan y se vuelven a
   * encender solas: si no, quien está delante sigue tecleando contra una
   * pantalla que no le va a contestar y concluye que está descompuesta. */
  var restan = parseInt(form.getAttribute("data-espera"), 10) || 0;
  if (restan > 0) {
    teclas.forEach(function (t) { t.disabled = true; });
    var reloj = setInterval(function () {
      restan -= 1;
      if (restan > 0) return;
      clearInterval(reloj);
      teclas.forEach(function (t) { t.disabled = false; });
    }, 1000);
  }
})();
