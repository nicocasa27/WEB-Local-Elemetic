"""Engancha la escritura doble a las tablas heredadas.

Se hace con señales y no editando las vistas por una razón práctica: la
lógica de escritura está repartida por ocho mil líneas y veinte vistas que
despachan por un parámetro `action`. Buscar a mano todos los sitios donde se
guarda una orden garantiza olvidarse de alguno, y un olvido en la escritura
doble significa una divergencia silenciosa justo en lo que se está intentando
verificar.

Con `post_save` queda cubierto cualquier camino que guarde por el ORM, lo
llame quien lo llame: una vista, un comando, el admin o una tarea programada.

**Lo que las señales no cubren** son las escrituras en bloque
(`.filter(...).update(...)`), que no las disparan. En este código hay nueve, y
de ésas se ocupa la reconciliación diaria, que además sabe repararlas
(`reconciliar_nucleo --corregir`). Esa es la red, y por eso el corte de una
línea exige siete días de reconciliación limpia y no la palabra de nadie.

Nada de esto hace nada mientras la línea esté apagada, que es como está todo
por omisión.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core import banderas
from core.servicios import espejo

logger = logging.getLogger("mes.nucleo.espejo")


def _reflejar_al_confirmar(etiqueta, pk):
    """Refleja después de que la transacción de la vista haya confirmado.

    Importa que sea después: si la operación heredada se deshace, no debe
    quedar en el núcleo una orden que en realidad no existe. Y al revés, un
    fallo del reflejo no puede tumbar una operación que ya salió bien.
    """
    transaction.on_commit(lambda: espejo.reflejar(etiqueta, pk), using="mes")


def conectar():
    from catalogos.models import (
        HerrOrdenProduccion,
        LaserOrdenProduccion,
        RobotOrdenProduccion,
    )
    from produccion.models import Viga

    for modelo, etiqueta in (
        (HerrOrdenProduccion, "HerrOrdenProduccion"),
        (LaserOrdenProduccion, "LaserOrdenProduccion"),
        (RobotOrdenProduccion, "RobotOrdenProduccion"),
        (Viga, "Viga"),
    ):
        _conectar_uno(modelo, etiqueta)


def _conectar_uno(modelo, etiqueta):
    linea = espejo.LINEA_DE[etiqueta]

    @receiver(post_save, sender=modelo, weak=False, dispatch_uid=f"espejo_{etiqueta}")
    def _al_guardar(sender, instance, **kwargs):
        if not banderas.escribe_en_nucleo(linea):
            return
        _reflejar_al_confirmar(etiqueta, instance.pk)
