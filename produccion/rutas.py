"""Configurar por qué etapas pasa una orden.

Se llega desde «Control de producción», que es donde se ve todo y donde tiene
sentido decidirlo. Una sola pantalla para las cuatro líneas: la ruta es la
misma idea en todas, y hacer una por línea sería repetir el error del que vive
este sistema.

Se marcan las etapas de trabajo —corte, armado, soldadura, pintura— y las de
espera van pegadas a la suya. Nadie tiene que pensar en «espera de pintura»:
es una consecuencia de que haya pintura, no una decisión aparte.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.servicios import ruta as servicio

#: Qué se puede configurar y cómo se encuentra cada cosa. La clave es la que
#: viaja en la dirección; el resto es lo que hace falta para enseñarla.
LINEAS = {
    "estructuras": {
        "nombre": "Estructuras",
        "legacy_modelo": "Viga",
        "modelo": ("produccion.models", "Viga"),
        "campo_codigo": "codigo_viga",
        "campo_etapa": "estado",
        "pk": "internal_id",
    },
    "herreria": {
        "nombre": "Herrería",
        "legacy_modelo": "HerrOrdenProduccion",
        "modelo": ("catalogos.models", "HerrOrdenProduccion"),
        "campo_codigo": "codigo",
        "campo_etapa": "estado_etapa",
        "pk": "pk",
    },
    "corta": {
        "nombre": "Corta.mx",
        "legacy_modelo": "LaserOrdenProduccion",
        "modelo": ("catalogos.models", "LaserOrdenProduccion"),
        "campo_codigo": "codigo",
        "campo_etapa": "estado_etapa",
        "pk": "pk",
    },
}


def _puede_configurar(user):
    """Quién decide la ruta de una orden.

    No es del piso: es de quien recibe el pedido y sabe qué acordó con el
    cliente. Un operador que pudiera quitar pintura de una orden estaría
    cambiando lo que se vendió.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(
        name__in={
            "admin_general",
            "ingenieria_civil",
            "pedidos_ventas",
            "herreria_supervision",
            "corte_laser_supervision",
        }
    ).exists()


def _buscar(linea, identificador):
    from importlib import import_module

    config = LINEAS[linea]
    modulo, clase = config["modelo"]
    modelo = getattr(import_module(modulo), clase)
    return modelo.objects.using("mes").filter(pk=identificador).first()


@login_required
@user_passes_test(_puede_configurar, login_url="produccion:control")
def configurar(request, linea, identificador):
    if linea not in LINEAS:
        return redirect("produccion:control")
    config = LINEAS[linea]
    orden = _buscar(linea, identificador)
    if orden is None:
        messages.error(request, "No se encontró esa orden.")
        return redirect("produccion:control")

    guardada = servicio.de(config["legacy_modelo"], orden.pk)
    return render(
        request,
        "produccion/ruta.html",
        {
            "linea": linea,
            "linea_nombre": config["nombre"],
            "orden": orden,
            "codigo": getattr(orden, config["campo_codigo"], ""),
            "etapa_actual": getattr(orden, config["campo_etapa"], ""),
            "configurables": servicio.CONFIGURABLES,
            "marcadas": servicio.etapas_de_trabajo(
                [] if guardada == servicio.secuencia_completa() else guardada
            ),
            "ruta": guardada,
            "es_la_de_siempre": guardada == servicio.secuencia_completa(),
            "volver": request.GET.get("next") or "",
        },
    )


@login_required
@user_passes_test(_puede_configurar, login_url="produccion:control")
@require_POST
def guardar(request, linea, identificador):
    if linea not in LINEAS:
        return redirect("produccion:control")
    config = LINEAS[linea]
    orden = _buscar(linea, identificador)
    if orden is None:
        messages.error(request, "No se encontró esa orden.")
        return redirect("produccion:control")

    marcadas = request.POST.getlist("etapas")
    ruta = servicio.guardar(config["legacy_modelo"], orden.pk, marcadas)

    if ruta is None:
        # No hay dónde guardarla: esa orden no tiene fila en el núcleo porque
        # se creó con la escritura doble apagada. Se dice, en vez de aceptar
        # el formulario y no aplicar nada.
        messages.error(
            request,
            "Esta orden todavía no está en el motor unificado, así que su ruta "
            "no se puede guardar. Se arregla encendiendo la escritura doble; "
            "está explicado en DESPLIEGUE.md.",
        )
    else:
        quitadas = [
            e for e in servicio.CONFIGURABLES if e not in servicio.etapas_de_trabajo(ruta)
        ]
        if quitadas:
            messages.success(
                request,
                f"Ruta guardada. Esta orden no pasa por {', '.join(e.lower() for e in quitadas)}.",
            )
        else:
            messages.success(request, "Ruta guardada: pasa por todas las etapas.")

    destino = request.POST.get("next") or ""
    if destino.startswith("/"):
        return redirect(destino)
    return redirect("produccion:control")
