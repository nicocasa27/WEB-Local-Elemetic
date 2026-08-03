"""Consolidación de los cierres cuya ventana de reversión ya venció.

Cuando una orden llega a su objetivo de piezas queda en «Terminado (bloqueo
pend.)» durante unos minutos, para poder deshacer un error de dedo. Pasada la
ventana, el cierre debe volverse firme.

El problema es **cuándo** ocurre eso. Hasta ahora sólo se consolidaban los
cierres al abrir la pantalla de control, que era además el único sitio desde
donde se invocaba. Consecuencias:

- Un viernes a las 17:05 nadie abre esa pantalla, así que las órdenes se
  quedan en el limbo hasta el lunes. Mientras tanto figuran como pendientes en
  todos los informes y en los cortes por estado.
- El resultado dependía de quién hubiera abierto qué pantalla y cuándo, de
  modo que dos personas mirando a la vez podían ver cifras distintas.
- De paso, cada carga de la pantalla ejecutaba un bloqueo sobre doscientas
  filas antes de pintar nada.

Este módulo saca esa tarea del camino de la petición para que la ejecute un
trabajo programado. La lógica es la misma que había, con dos diferencias: se
procesa por lotes hasta agotar el trabajo, en vez de detenerse en las primeras
doscientas filas, y las dos líneas de negocio comparten una sola
implementación en lugar de tener cada una su copia.
"""

import logging

from django.db import transaction
from django.utils import timezone

from catalogos.models import (
    HerrEstadoCambio,
    HerrOrdenProduccion,
    LaserEstadoCambio,
    LaserOrdenProduccion,
)
from core import estados
from core.constantes import CIERRE_LOTE

logger = logging.getLogger("mes.cierres")

BASE = "mes"

#: Cada línea con su modelo de orden y su modelo de bitácora. Cuando el núcleo
#: esté unificado, esta tabla desaparece porque habrá un solo modelo.
LINEAS = {
    "herreria": (HerrOrdenProduccion, HerrEstadoCambio),
    "corta": (LaserOrdenProduccion, LaserEstadoCambio),
}


def consolidar_linea(nombre_linea, ahora=None, limite_lotes=100):
    """Cierra en firme las órdenes vencidas de una línea.

    Devuelve cuántas se consolidaron. Procesa en lotes para no mantener
    bloqueada media tabla, y con un tope de vueltas como red frente a un fallo
    que impidiera avanzar.
    """
    modelo_orden, modelo_bitacora = LINEAS[nombre_linea]
    ahora = ahora or timezone.now()
    total = 0

    for _ in range(limite_lotes):
        with transaction.atomic(using=BASE):
            vencidas = list(
                modelo_orden.objects.using(BASE)
                .select_for_update()
                .filter(
                    estado="Abierta",
                    estado_etapa=estados.CIERRE_PENDIENTE,
                    cierre_pendiente_hasta__isnull=False,
                    cierre_pendiente_hasta__lte=ahora,
                )
                .order_by("cierre_pendiente_hasta", "id")[:CIERRE_LOTE]
            )
            if not vencidas:
                break

            for orden in vencidas:
                anterior = (orden.estado_etapa or "").strip()
                orden.estado_etapa = estados.TERMINADO
                orden.ultimo_cambio = ahora
                orden.cierre_bloqueado_en = ahora
                orden.cierre_pendiente_hasta = None
                orden.save(
                    update_fields=[
                        "estado_etapa",
                        "ultimo_cambio",
                        "cierre_bloqueado_en",
                        "cierre_pendiente_hasta",
                        "actualizado_en",
                    ]
                )
                modelo_bitacora.objects.using(BASE).create(
                    orden=orden,
                    estado_anterior=anterior,
                    estado_nuevo=estados.TERMINADO,
                    fecha_operacion=timezone.localdate(),
                    actor_username="system",
                    comentario="auto_bloqueo",
                )
                total += 1

        if len(vencidas) < CIERRE_LOTE:
            break
    else:
        logger.warning(
            "La consolidación de cierres de %s agotó el tope de lotes; quedan órdenes por cerrar.",
            nombre_linea,
        )

    if total:
        logger.info("Cierres consolidados en %s: %s", nombre_linea, total)
    return total


def consolidar_todas(ahora=None):
    """Consolida las dos líneas. Devuelve {linea: consolidadas}."""
    return {nombre: consolidar_linea(nombre, ahora) for nombre in LINEAS}
