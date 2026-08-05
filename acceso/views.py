"""El teclado de la tableta del taller.

Se llega, se teclean cuatro dígitos, y se abre lo que esa persona tiene que
hacer. Se termina, se toca un botón grande, y la tableta vuelve al teclado
lista para el siguiente.

Dos cosas que no son evidentes y sostienen todo lo demás:

**Entrar cierra lo que hubiera abierto.** La tableta es de todos. Si alguien
teclea su PIN y encima queda la sesión del anterior, el trabajo del turno se
registra a nombre de quien pasó por ahí primero. Por eso `entrar` hace
`logout` antes del `login`, siempre, aunque sea la misma persona.

**Y salir no depende de que alguien se acuerde.** Nadie va a tocar «salir»
cuando le llaman de la nave. De eso se encarga
`acceso.middleware.CierreDePinPorInactividad`.
"""

import time

from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from acceso import servicios

#: Marca en la sesión de que se entró por el teclado. La usa el middleware
#: para cerrar por inactividad, y las plantillas para enseñar el botón grande
#: de salir. Una sesión normal de oficina no la lleva y no se cierra sola.
CLAVE_SESION = "entro_con_pin"

#: Cuándo se vio a esta sesión por última vez, en segundos desde la época.
CLAVE_VISTO = "pin_visto_en"

_CLAVE_FALLOS = "pin_fallos"
_CLAVE_ESPERA = "pin_espera_hasta"

#: El backend con el que se firma la entrada. Se dice explícitamente porque
#: `login()` sólo lo adivina cuando la contraseña pasó por `authenticate()`, y
#: aquí no hay contraseña.
BACKEND = "django.contrib.auth.backends.ModelBackend"


def destino_de(usuario):
    """Dónde se le deja a esta persona después de entrar.

    A su trabajo, no al menú. Quien entra por el teclado viene a apuntar lo que
    acaba de hacer; un menú en medio son dos toques que no informan de nada.
    """
    return reverse("produccion:movil")


def marcar_visto(sesion):
    sesion[CLAVE_VISTO] = int(time.time())


def _pantalla(request, error="", estado=200):
    """La pantalla del teclado.

    El error va en el contexto y no por `messages` a propósito. Los mensajes
    del sistema salen como un aviso flotante en la esquina que se va solo a los
    dos segundos: bien para confirmar algo, inservible para lo único que esta
    pantalla tiene que decir, a un brazo de distancia y con guantes. Aquí el
    error se queda escrito debajo del título hasta que se vuelva a teclear.
    """
    espera = max(0, int(request.session.get(_CLAVE_ESPERA, 0)) - int(time.time()))
    return render(request, "acceso/teclado.html", {
        "largo": servicios.LARGO,
        "segundos_de_espera": espera,
        "error": error,
    }, status=estado)


def teclado(request):
    """El teclado. Pública, como la pantalla de iniciar sesión."""
    if request.user.is_authenticated:
        return redirect(destino_de(request.user))
    return _pantalla(request)


@require_POST
def entrar(request):
    ahora = int(time.time())
    espera_hasta = int(request.session.get(_CLAVE_ESPERA, 0))
    if ahora < espera_hasta:
        return _pantalla(
            request,
            f"Demasiados intentos. Espera {espera_hasta - ahora} segundos.",
            estado=429,
        )

    tecleado = servicios.normalizar(request.POST.get("pin"))
    usuario = servicios.quien_es(tecleado)

    if usuario is None:
        fallos = int(request.session.get(_CLAVE_FALLOS, 0)) + 1
        request.session[_CLAVE_FALLOS] = fallos
        if fallos >= servicios.INTENTOS_ANTES_DE_ESPERAR:
            request.session[_CLAVE_FALLOS] = 0
            request.session[_CLAVE_ESPERA] = ahora + servicios.SEGUNDOS_DE_ESPERA
            return _pantalla(
                request,
                f"Demasiados intentos. Espera {servicios.SEGUNDOS_DE_ESPERA} segundos.",
                estado=429,
            )
        # No se distingue entre un PIN que no existe y uno de una cuenta
        # apagada. Para quien está delante son el mismo problema y tienen la
        # misma salida, y decir cuál es enseñaría qué PINes existen.
        # Se contesta 200 con el formulario otra vez, igual que hace la
        # pantalla de contraseña de Django. Un PIN equivocado no es un fallo
        # de la petición: es la pantalla esperando el siguiente intento.
        return _pantalla(request, "Ese PIN no es de nadie. Revísalo, o pide que te lo pongan.")

    # Cerrar lo que hubiera antes. La tableta es compartida: sin esto, el
    # trabajo del siguiente se registraría a nombre del anterior.
    logout(request)
    login(request, usuario, backend=BACKEND)
    request.session[CLAVE_SESION] = True
    marcar_visto(request.session)

    nombre = usuario.get_short_name() or usuario.get_username()
    messages.success(request, f"Hola, {nombre}.")
    return redirect(destino_de(usuario))


@require_POST
def salir(request):
    """El botón grande de terminar. Cierra y deja el teclado listo."""
    logout(request)
    messages.success(request, "Listo. Puede pasar el siguiente.")
    return redirect("acceso:teclado")
