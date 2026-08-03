/* Lo que hace toda página del MES: avisos, memoria de posición y el QR.
 *
 * Estaba escrito dentro de produccion/base.html. Aquí se puede leer, se
 * guarda en la caché del navegador y —lo importante— no se vuelve a copiar y
 * pegar en la siguiente plantilla.
 *
 * No hay empaquetador a propósito: en un servidor sin Node, añadirlo es
 * añadir una dependencia de compilación que nadie va a mantener.
 */
(function () {
  "use strict";

  // --------------------------------------------- color del estado de orden
  //
  // El color del estado lo pone la hoja de estilos, por la clase `est-*` que
  // manda el servidor. Cuando una respuesta AJAX cambia el estado hay que
  // cambiar la clase, no pintar un color a mano: si el color se escribiera en
  // el elemento, la etiqueta dejaría de verse el día que este script falle.

  function aplicarClaseDeEstado(elemento, clase) {
    if (!elemento) return;
    elemento.classList.forEach(function (nombre) {
      if (nombre.startsWith("est-")) elemento.classList.remove(nombre);
    });
    if (clase) elemento.classList.add(clase);
    // El color suelto que hubiera puesto una versión anterior ganaría a la
    // clase nueva y dejaría el estado viejo pintado.
    elemento.style.background = "";
    elemento.style.borderColor = "";
  }

  window.MES = window.MES || {};
  window.MES.aplicarClaseDeEstado = aplicarClaseDeEstado;

  // --------------------------------------------------------------- avisos

  function mostrarAvisos() {
    document.querySelectorAll(".toast").forEach(function (el) {
      try {
        bootstrap.Toast.getOrCreateInstance(el).show();
      } catch (e) {
        // Sin Bootstrap el aviso se queda en la página en lugar de
        // desvanecerse. Se ve raro, pero se lee, que es lo que importa.
        el.classList.add("show");
      }
    });
  }

  // ------------------------------------------------- memoria de posición
  //
  // Casi toda acción termina recargando la página. Sin esto, quien avanza la
  // orden número cuarenta vuelve al principio de la lista cada vez.

  function clave(url) {
    return "scroll:" + url.pathname + url.search;
  }

  function guardar(url) {
    try {
      sessionStorage.setItem(clave(url), String(window.scrollY || 0));
    } catch (e) {
      /* Navegación privada o almacenamiento lleno: se pierde la posición. */
    }
  }

  function recordarPosicion() {
    document.addEventListener(
      "submit",
      function (e) {
        var form = e.target;
        if (!form || form.tagName !== "FORM") return;
        var campo = form.querySelector('input[name="next"]');
        var destino = campo ? (campo.value || "").trim() : "";
        if (destino && destino.startsWith("/")) {
          guardar(new URL(destino, window.location.origin));
        } else {
          guardar(new URL(window.location.href));
        }
      },
      true
    );

    document.addEventListener(
      "click",
      function (e) {
        var enlace = e.target && e.target.closest ? e.target.closest("a") : null;
        if (!enlace) return;
        var href = (enlace.getAttribute("href") || "").trim();
        if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;
        try {
          var destino = new URL(href, window.location.href);
          if (destino.origin === window.location.origin) guardar(destino);
        } catch (err) {
          /* href que no es una dirección válida: no hay nada que recordar. */
        }
      },
      true
    );
  }

  function restaurarPosicion() {
    try {
      var k = clave(window.location);
      var valor = sessionStorage.getItem(k);
      if (valor === null) return;
      sessionStorage.removeItem(k);
      var y = parseInt(valor, 10);
      if (!Number.isNaN(y) && y > 0) window.scrollTo(0, y);
    } catch (e) {
      /* Ver guardar(). */
    }
  }

  // ------------------------------------------------------------------ QR
  //
  // Para abrir la aplicación en otro celular sin dictar la dirección IP.

  function montarCompartir() {
    var panel = document.getElementById("shareCanvas");
    var lienzo = document.getElementById("shareQr");
    var campo = document.getElementById("shareUrl");
    var boton = document.getElementById("copyShareUrl");
    if (!panel || !lienzo || !campo || !boton) return;

    // La dirección de entrada la pone el servidor: la plantilla la conoce y
    // el JavaScript no tiene por qué adivinarla.
    var entrada = document.body.dataset.urlLogin || "/";

    panel.addEventListener("shown.bs.offcanvas", function () {
      var url = window.location.origin + entrada;
      campo.value = url;
      lienzo.innerHTML = "";
      if (typeof QRCode === "undefined") return;
      new QRCode(lienzo, {
        text: url,
        width: 220,
        height: 220,
        correctLevel: QRCode.CorrectLevel.M,
      });
    });

    boton.addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(campo.value);
        boton.textContent = "Copiado";
        setTimeout(function () {
          boton.textContent = "Copiar";
        }, 1200);
      } catch (e) {
        // Sin HTTPS el portapapeles no está disponible, y el taller sirve por
        // http en la red local. Se selecciona el texto para copiarlo a mano.
        campo.select();
      }
    });
  }

  // --------------------------------------------------------------- arranque

  recordarPosicion();

  document.addEventListener("DOMContentLoaded", function () {
    restaurarPosicion();
    mostrarAvisos();
    montarCompartir();
  });
})();
