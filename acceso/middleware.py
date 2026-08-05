"""Cerrar solas las sesiones que se abrieron con el PIN.

Nadie va a tocar «salir» cuando le llaman de la nave. Y una tableta compartida
con la sesión de alguien abierta es peor que no tener sesión: el siguiente que
pasa apunta su trabajo, de buena fe, a nombre del anterior. Cuando a fin de
mes se mira el rendimiento, el dato está mal y nada indica por qué.

Así que la sesión abierta por el teclado caduca por sí sola tras un rato sin
tocar nada. **Sólo esa.** Una sesión de oficina, abierta con usuario y
contraseña, no se cierra: quien está en la PC de arriba está en su sitio y
sacarlo cada rato es una molestia sin motivo.

Se cuenta desde la última petición y no desde que se entró, que es la
diferencia entre «el que está trabajando sigue dentro» y «a los veinte minutos
todo el mundo fuera, esté o no esté en medio de algo».
"""

import time

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from acceso.servicios import minutos_de_inactividad
from acceso.views import CLAVE_SESION, CLAVE_VISTO


class CierreDePinPorInactividad:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sesion = getattr(request, "session", None)
        usuario = getattr(request, "user", None)

        if sesion is not None and sesion.get(CLAVE_SESION) and getattr(
            usuario, "is_authenticated", False
        ):
            minutos = minutos_de_inactividad()
            ahora = int(time.time())
            visto = int(sesion.get(CLAVE_VISTO, ahora))
            if ahora - visto > minutos * 60:
                logout(request)
                messages.info(
                    request,
                    f"La sesión se cerró sola tras {minutos} minutos sin usarse. "
                    "Teclea tu PIN para seguir.",
                )
                return redirect(reverse("acceso:teclado"))
            sesion[CLAVE_VISTO] = ahora

        return self.get_response(request)
