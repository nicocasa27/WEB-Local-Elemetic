"""Cómo se hace una orden: por qué etapas pasa y qué hay que saber para hacerla.

Se llega desde «Control de producción», que es donde se ve todo y donde tiene
sentido decidirlo. Una sola pantalla para las cuatro líneas: es la misma idea
en todas, y hacer una por línea sería repetir el error del que vive este
sistema.

Dos cosas se deciden aquí, y son la misma clase de cosa —lo que hay que saber
antes de empezar a fabricar—, por eso comparten pantalla y formulario:

**La ruta.** Se marcan las etapas de trabajo —corte, armado, soldadura,
pintura— y las de espera van pegadas a la suya. Nadie tiene que pensar en
«espera de pintura»: es una consecuencia de que haya pintura, no una decisión
aparte.

**Las especificaciones.** El detalle que el operador necesita en la mano:
«vigas de 70 cm con un corte a los 30 cm a noventa grados». Sale en su
tarjeta del celular, que hasta ahora sólo decía el código y la obra.

Y las dos se pueden **recordar en la pieza del catálogo**, para lo que se
fabrica todas las semanas. Un andamio tipo A no se pinta nunca: se dice una
vez y los pedidos siguientes nacen bien.

Todo esto es del **lote**, no de la pieza suelta. En Estructuras, cincuenta
vigas son cincuenta filas; si esas vigas no se pintan, no se pinta ninguna.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.servicios import especificaciones as servicio_especificaciones
from core.servicios import ruta as servicio
from core.bases import BASE  # noqa: F401

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
    """Quién decide cómo se hace una orden.

    No es del piso: es de quien recibe el pedido y sabe qué acordó con el
    cliente, y de quien dibuja la pieza. Un operador que pudiera quitar
    pintura de una orden estaría cambiando lo que se vendió.
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
    return modelo.objects.using(BASE).filter(pk=identificador).first()


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

    etiqueta = config["legacy_modelo"]
    guardada = servicio.de(etiqueta, orden.pk)
    pieza = servicio.pieza_de_catalogo(etiqueta, orden.pk)
    del_lote = servicio.hermanas(etiqueta, orden.pk)
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
            "especificaciones": servicio_especificaciones.de(etiqueta, orden.pk),
            "largo_maximo": servicio_especificaciones.LARGO_MAXIMO,
            #: Cuántas filas heredadas toca este formulario. Se dice cuando es
            #: más de una: quien lo configura tiene que saber que está
            #: decidiendo por las cincuenta y no por la que abrió.
            "piezas_del_lote": len(del_lote),
            "pieza_catalogo": pieza,
            "ya_recordada": bool(pieza and (pieza.ruta or pieza.especificaciones)),
            "volver": request.GET.get("next") or "",
        },
    )


def _aviso_de_la_ruta(request, ruta, piezas):
    quitadas = [
        e for e in servicio.CONFIGURABLES if e not in servicio.etapas_de_trabajo(ruta)
    ]
    de_cuantas = f" en {piezas} piezas" if piezas > 1 else ""
    if quitadas:
        messages.success(
            request,
            f"Ruta guardada{de_cuantas}. No pasa por "
            f"{', '.join(e.lower() for e in quitadas)}.",
        )
    else:
        messages.success(request, f"Ruta guardada{de_cuantas}: pasa por todas las etapas.")


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

    etiqueta = config["legacy_modelo"]
    marcadas = request.POST.getlist("etapas")
    texto = request.POST.get("especificaciones") or ""

    # Las especificaciones primero, y a propósito: no dependen del motor
    # unificado, así que se guardan aunque la ruta no se pueda. Al revés,
    # un servidor con el motor apagado perdería lo que alguien escribió por
    # culpa de una configuración que no tiene nada que ver.
    servicio_especificaciones.guardar(
        etiqueta, orden.pk, texto, quien=request.user.get_username()
    )

    ruta, piezas = servicio.guardar_en_el_lote(etiqueta, orden.pk, marcadas)
    if ruta is None:
        # No hay dónde guardarla: esa orden no tiene fila en el núcleo porque
        # se creó con la escritura doble apagada. Se dice, en vez de aceptar
        # el formulario y no aplicar nada.
        messages.error(
            request,
            "Las instrucciones sí quedaron guardadas, pero la ruta no: esta "
            "orden todavía no está en el motor unificado. Se arregla "
            "encendiendo la escritura doble; está explicado en DESPLIEGUE.md.",
        )
    else:
        _aviso_de_la_ruta(request, ruta, piezas)

    if request.POST.get("recordar"):
        pieza = servicio.pieza_de_catalogo(etiqueta, orden.pk)
        if pieza is None:
            messages.warning(
                request,
                "Esto no se pudo recordar para las piezas iguales: esta orden "
                "no está ligada a ninguna pieza del catálogo.",
            )
        else:
            servicio.recordar_en_la_pieza(pieza, marcadas)
            servicio_especificaciones.recordar_en_la_pieza(pieza, texto)
            messages.success(
                request,
                f"Los pedidos nuevos de «{pieza.nombre}» van a nacer así. "
                "Lo que ya está en producción no se toca.",
            )

    destino = request.POST.get("next") or ""
    if destino.startswith("/"):
        return redirect(destino)
    return redirect("produccion:control")
