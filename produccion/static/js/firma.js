/* Firmar con el dedo, y las dos preguntas del traspaso.
 *
 * Dos momentos, y son distintos a propósito:
 *
 * - **Al recibir**, antes de poder trabajar: «te entregaron esto, ¿está
 *   correcto?». Si dice que sí, firma y empieza. Si dice que no, lo devuelve.
 * - **Al entregar**, antes de pasar la pieza: «¿revisaste que quedó como la
 *   pidieron?». Firma y avanza.
 *
 * Sin esto la pieza avanza igual y el servidor levanta el acta con quien la
 * movió, sólo que sin trazo. Es a propósito: si el lienzo fallara —un
 * navegador viejo, la pantalla sucia— el taller tiene que poder seguir
 * moviendo material. Lo que no puede pasar es que se pierda quién fue.
 */
(function () {
  "use strict";

  var LIENZO_ALTO = 170;

  /* ------------------------------------------------------------- el lienzo */

  function prepararLienzo(lienzo) {
    var pixeles = window.devicePixelRatio || 1;
    var ancho = lienzo.clientWidth || 300;
    lienzo.width = ancho * pixeles;
    lienzo.height = LIENZO_ALTO * pixeles;
    var pincel = lienzo.getContext("2d");
    pincel.scale(pixeles, pixeles);
    pincel.lineWidth = 2.5;
    pincel.lineCap = "round";
    pincel.lineJoin = "round";
    pincel.strokeStyle = "#10171f";
    return pincel;
  }

  function firmable(lienzo, alCambiar) {
    var pincel = prepararLienzo(lienzo);
    var trazando = false;
    var hayTrazo = false;

    function punto(evento) {
      var caja = lienzo.getBoundingClientRect();
      return { x: evento.clientX - caja.left, y: evento.clientY - caja.top };
    }

    lienzo.addEventListener("pointerdown", function (evento) {
      trazando = true;
      lienzo.setPointerCapture(evento.pointerId);
      var p = punto(evento);
      pincel.beginPath();
      pincel.moveTo(p.x, p.y);
      /* Un punto solo también es un trazo: hay quien firma con una cruz. */
      pincel.lineTo(p.x + 0.1, p.y);
      pincel.stroke();
      hayTrazo = true;
      alCambiar(true);
      evento.preventDefault();
    });

    lienzo.addEventListener("pointermove", function (evento) {
      if (!trazando) return;
      var p = punto(evento);
      pincel.lineTo(p.x, p.y);
      pincel.stroke();
      evento.preventDefault();
    });

    ["pointerup", "pointercancel", "pointerleave"].forEach(function (nombre) {
      lienzo.addEventListener(nombre, function () { trazando = false; });
    });

    return {
      borrar: function () {
        pincel.clearRect(0, 0, lienzo.width, lienzo.height);
        hayTrazo = false;
        alCambiar(false);
      },
      hayTrazo: function () { return hayTrazo; },
      comoImagen: function () { return hayTrazo ? lienzo.toDataURL("image/png") : ""; },
    };
  }

  /* ---------------------------------------------------------- las preguntas */

  /* La hoja se abre encima, con el lienzo grande. Un cuadro de firma de dos
   * centímetros embutido en la tarjeta no se puede firmar con un dedo. */
  var hoja = document.getElementById("movFirma");
  if (!hoja) return;

  /* La hoja se instancia cuando se va a abrir, no ahora.
   *
   * Este archivo se carga dentro del contenido de la página y Bootstrap al
   * final, así que aquí `window.bootstrap` todavía no existe. Si la instancia
   * se guardara ahora quedaría nula para siempre: la pregunta se preparaba con
   * su texto y su lienzo, y no se abría nunca. El operador pulsaba «Terminé
   * corte» y no pasaba nada de nada. */
  function laHoja(elemento) {
    if (!window.bootstrap) return null;
    return window.bootstrap.Offcanvas.getOrCreateInstance(elemento);
  }

  var titulo = hoja.querySelector(".js-firma-titulo");
  var texto = hoja.querySelector(".js-firma-texto");
  var lienzo = hoja.querySelector(".js-firma-lienzo");
  var aceptar = hoja.querySelector(".js-firma-aceptar");
  var limpiar = hoja.querySelector(".js-firma-limpiar");
  var pluma = null;
  var enCurso = null;

  function alCambiar(hay) {
    aceptar.disabled = !hay;
  }

  function abrir(config) {
    enCurso = config;
    titulo.textContent = config.titulo;
    texto.textContent = config.texto;
    aceptar.textContent = config.boton;
    var caja = laHoja(hoja);
    if (caja) caja.show();
    /* El lienzo se dimensiona cuando ya está visible: mientras la hoja está
     * cerrada mide cero de ancho y el trazo saldría desplazado. */
    window.setTimeout(function () {
      pluma = firmable(lienzo, alCambiar);
      alCambiar(false);
    }, 250);
  }

  aceptar.addEventListener("click", function () {
    if (!enCurso || !pluma || !pluma.hayTrazo()) return;
    enCurso.alFirmar(pluma.comoImagen());
    var caja = laHoja(hoja);
    if (caja) caja.hide();
    enCurso = null;
  });

  limpiar.addEventListener("click", function () {
    if (pluma) pluma.borrar();
  });

  /* ------------------------------------------------------------- devolver */

  var hojaDevolver = document.getElementById("movDevolver");
  if (hojaDevolver) {
    var campoPieza = hojaDevolver.querySelector(".js-devolver-pieza");
    var rotuloCodigo = hojaDevolver.querySelector(".js-devolver-codigo");
    document.querySelectorAll(".js-mov-devolver").forEach(function (boton) {
      boton.addEventListener("click", function () {
        campoPieza.value = boton.getAttribute("data-pieza");
        rotuloCodigo.textContent = "Devolver " + boton.getAttribute("data-codigo");
        var caja = laHoja(hojaDevolver);
        if (caja) caja.show();
      });
    });
  }

  /* --------------------------------------------------- enganchar los botones */

  /* Recibir. El botón de la tarjeta no envía: abre la pregunta. La firma se
   * mete en el formulario y entonces sí se envía. */
  document.querySelectorAll(".js-mov-avanzar").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      var campoRecibo = formulario.querySelector(".js-firma-recibo");
      var campoEntrega = formulario.querySelector(".js-firma-entrega");
      var pendiente = campoRecibo && !campoRecibo.value;
      var entregando = campoEntrega && !campoEntrega.value;
      if (!pendiente && !entregando) return;

      evento.preventDefault();
      evento.stopImmediatePropagation();

      if (pendiente) {
        abrir({
          titulo: "¿Está correcto lo que te entregaron?",
          texto: campoRecibo.getAttribute("data-texto"),
          boton: "Sí, lo recibo",
          alFirmar: function (imagen) {
            campoRecibo.value = imagen;
            formulario.requestSubmit
              ? formulario.requestSubmit()
              : formulario.submit();
          },
        });
        return;
      }

      abrir({
        titulo: "¿Revisaste que quedó como la pidieron?",
        texto: campoEntrega.getAttribute("data-texto"),
        boton: "Sí, la entrego",
        alFirmar: function (imagen) {
          campoEntrega.value = imagen;
          formulario.requestSubmit
            ? formulario.requestSubmit()
            : formulario.submit();
        },
      });
    // En captura, para adelantarse al envío por fetch de movil.js: si el otro
    // corriera primero, la pieza avanzaría sin haber preguntado nada.
    }, true);
  });
})();
