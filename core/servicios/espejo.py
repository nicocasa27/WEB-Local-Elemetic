"""Escritura doble: lo que se escribe en lo heredado se refleja en el núcleo.

Es el paso 4 de la migración, y el que permite que no haya un «día del
cambio». Mientras una línea está en escritura doble:

- las vistas siguen escribiendo donde siempre, y esa sigue siendo la verdad;
- justo después, en la misma transacción, la fila se refleja en el núcleo;
- un trabajo diario compara las dos y anota lo que no coincida.

Cuando la comparación lleva siete días seguidos sin encontrar nada, esa línea
se puede cortar. Y si algo sale mal después del corte, se vuelve atrás
poniendo la bandera en `doble`: no hay que restaurar nada, porque las tablas
heredadas siguen ahí y siguen actualizadas.

**El reflejo nunca debe impedir que alguien registre su trabajo.** Durante el
rodaje, un fallo aquí se anota en el registro y la operación continúa: la
escritura nueva todavía no manda nada, y dejar al taller sin poder apuntar una
pieza por culpa de una tabla que aún no se usa sería absurdo. Es la única
situación de toda esta reforma donde tragarse una excepción es lo correcto, y
por eso está en un solo sitio y con nombre propio. `MES_NUCLEO_ESTRICTO=1`
quita la red cuando ya se ha comprobado que no salta.
"""

import logging

from django.db import transaction

from core import banderas

logger = logging.getLogger("mes.nucleo.espejo")

BASE = "mes"

#: De qué modelo heredado sale cada línea de negocio.
LINEA_DE = {
    "HerrOrdenProduccion": "herreria",
    "LaserOrdenProduccion": "corta",
    "RobotOrdenProduccion": "robotica",
    "Viga": "vigas",
}


def reflejar(etiqueta, pk):
    """Refleja en el núcleo la fila heredada indicada.

    Devuelve la orden del núcleo, o `None` si la línea no está en escritura
    doble, si la fila ya no existe o si el reflejo falló y se decidió
    continuar.
    """
    linea = LINEA_DE.get(etiqueta)
    if linea is None:
        raise ValueError(f"modelo heredado desconocido: {etiqueta!r}")

    if not banderas.escribe_en_nucleo(linea):
        return None

    try:
        # Punto de retorno propio: si el reflejo falla a medias, se deshace
        # sólo el reflejo. Lo que la vista escribió en las tablas heredadas no
        # se toca, porque eso es lo que el operador acaba de hacer y sigue
        # siendo la verdad.
        with transaction.atomic(using=BASE):
            from nucleo.management.commands.backfill_nucleo import Command

            return Command.para_espejo().volcar_una(etiqueta, pk)
    except Exception:
        if banderas.estricto():
            raise
        logger.exception(
            "no se pudo reflejar %s#%s en el núcleo; la operación heredada sigue en pie",
            etiqueta,
            pk,
        )
        return None


def reflejar_muchas(etiqueta, identificadores):
    """Varias filas de golpe. Cada una falla por su cuenta."""
    return [reflejar(etiqueta, pk) for pk in identificadores]
