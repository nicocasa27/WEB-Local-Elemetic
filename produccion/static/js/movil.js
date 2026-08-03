/* «Mi trabajo»: registrar el avance con un toque.
 *
 * La red del taller se cae a ratos. Por eso el botón no espera a la
 * respuesta del servidor para dar por hecho el avance: lo pinta enseguida y
 * se encarga de que llegue. Si no hay red, la pieza queda marcada como
 * pendiente de sincronizar y se reintenta sola al volver la conexión.
 *
 * Cada envío lleva su propia clave. Si el celular reintenta porque no llegó
 * la respuesta —y no porque no llegara la petición—, el reintento no puede
 * contar el avance dos veces. Hoy esa clave viaja pero el camino heredado
 * todavía no la usa: quien la va a aprovechar es el motor unificado, que
 * lleva un registro con clave de idempotencia. Mientras tanto la protección
 * real es que el cambio de etapa es idempotente por naturaleza: pedir «pasa
 * a Soldadura» dos veces deja la pieza en Soldadura una sola vez.
 */
(function () {
  "use strict";

  var COLA = "mes:movil:pendientes";

  function hoy() {
    var d = new Date();
    return (
      d.getFullYear() +
      "-" +
      String(d.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(d.getDate()).padStart(2, "0")
    );
  }

  function clave() {
    // crypto.randomUUID no existe sin HTTPS en navegadores viejos, y el
    // taller sirve por http en la red local.
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "mov-" + Date.now() + "-" + Math.floor(Math.random() * 1e9);
  }

  // ------------------------------------------------------------ la cola

  function pendientes() {
    try {
      return JSON.parse(localStorage.getItem(COLA) || "[]");
    } catch (e) {
      return [];
    }
  }

  function guardar(lista) {
    try {
      localStorage.setItem(COLA, JSON.stringify(lista));
    } catch (e) {
      /* Sin almacenamiento no hay cola; el envío directo sigue funcionando. */
    }
  }

  function encolar(envio) {
    var lista = pendientes();
    lista.push(envio);
    guardar(lista);
  }

  async function mandar(envio) {
    var cuerpo = new FormData();
    Object.keys(envio.datos).forEach(function (k) {
      cuerpo.append(k, envio.datos[k]);
    });
    var respuesta = await fetch(envio.url, {
      method: "POST",
      headers: {
        "X-CSRFToken": window.MES.cookie("csrftoken"),
        "X-Idempotency-Key": envio.clave,
      },
      body: cuerpo,
    });
    if (!respuesta.ok) throw new Error("HTTP " + respuesta.status);
    var datos = await respuesta.json();
    if (!datos || !datos.ok) throw new Error((datos && datos.error) || "rechazado");
    return datos;
  }

  async function vaciarCola() {
    var lista = pendientes();
    if (!lista.length) return;
    var quedan = [];
    for (var i = 0; i < lista.length; i++) {
      try {
        await mandar(lista[i]);
      } catch (e) {
        quedan.push(lista[i]);
      }
    }
    guardar(quedan);
    if (lista.length && !quedan.length) {
      window.MES.aviso(lista.length + " avance(s) sincronizado(s)", "success");
    }
  }

  // --------------------------------------------------------- el avance

  function montarAvances() {
    document.querySelectorAll("form.js-mov-avanzar").forEach(function (form) {
      var campoFecha = form.querySelector(".js-hoy");
      if (campoFecha) campoFecha.value = hoy();

      form.addEventListener("submit", async function (e) {
        e.preventDefault();
        var boton = form.querySelector("button[type=submit]");
        var tarjeta = form.closest(".mov-tarjeta");
        if (boton) boton.classList.add("mov-enviando");

        var envio = {
          url: form.getAttribute("action"),
          clave: clave(),
          datos: {},
        };
        new FormData(form).forEach(function (valor, nombre) {
          if (nombre !== "csrfmiddlewaretoken") envio.datos[nombre] = valor;
        });

        try {
          await mandar(envio);
          window.MES.aviso("Registrado", "success");
        } catch (err) {
          // El avance no se pierde: se guarda y se reintenta. Lo importante
          // es que quien lo pulsó pueda seguir trabajando.
          encolar(envio);
          window.MES.aviso("Sin red: se enviará al reconectar", "warning");
        }

        // La pieza sale de la lista en cualquiera de los dos casos: para
        // quien está en el piso, ya está hecha.
        if (tarjeta) {
          tarjeta.classList.add("mov-hecha");
          setTimeout(function () {
            tarjeta.remove();
            actualizarCuenta();
          }, 350);
        }
      });
    });
  }

  function actualizarCuenta() {
    var cuenta = document.querySelector(".mov-cuenta");
    if (!cuenta) return;
    var quedan = document.querySelectorAll(".mov-tarjeta").length;
    cuenta.textContent = quedan + " pendiente" + (quedan === 1 ? "" : "s");
  }

  // ------------------------------------------------------- el problema

  function montarProblemas() {
    var hoja = document.getElementById("movProblema");
    if (!hoja) return;
    var etiqueta = hoja.querySelector(".js-mov-problema-pieza");
    document.querySelectorAll(".js-mov-problema").forEach(function (boton) {
      boton.addEventListener("click", function () {
        if (etiqueta) etiqueta.textContent = boton.dataset.codigo || "";
        try {
          bootstrap.Offcanvas.getOrCreateInstance(hoja).show();
        } catch (e) {
          window.location.href = boton.dataset.urlParos || "/catalogos/paros/";
        }
      });
    });
  }

  // ---------------------------------------------------------- arranque

  document.addEventListener("DOMContentLoaded", function () {
    montarAvances();
    montarProblemas();
    vaciarCola();
  });

  window.addEventListener("online", vaciarCola);
})();
