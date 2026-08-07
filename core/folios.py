"""Folios que no se repiten nunca, con una secuencia de PostgreSQL.

El sistema heredado construye el folio a partir del identificador de la fila:
`f"H-{self.id:05d}"`. Eso trae dos problemas, y el segundo es serio.

El primero es que dos altas simultáneas pueden calcular el mismo número
mientras ninguna ha confirmado todavía.

El segundo es que **los folios se reutilizan**. Al purgar una orden queda un
hueco, y la siguiente lo ocupa. Como el folio va impreso en los acuses de
entrega firmados, acaba habiendo dos documentos distintos con el mismo número
y no hay forma de saber cuál es cuál.

Una secuencia de PostgreSQL resuelve las dos cosas: entrega números sin
esperar a nadie y **no los devuelve** aunque la transacción se deshaga. Eso
produce huecos, que es exactamente lo que se quiere: un hueco es un folio que
no llegó a existir; un folio repetido es un documento ambiguo.

Al sembrar, cada secuencia se coloca por encima del identificador más alto ya
emitido en la tabla heredada, más un margen. Los folios históricos no se
renumeran jamás.
"""

import re

from django.db import connections
from core.bases import BASE  # noqa: F401


#: Los códigos de línea vienen de un `SlugField`, pero el nombre de la
#: secuencia se interpola en SQL y los identificadores no admiten parámetros.
#: Se comprueba igual: una comprobación barata en el sitio donde el descuido
#: sería caro.
_CODIGO_VALIDO = re.compile(r"^[a-z0-9_]{1,30}$")


def nombre_secuencia(codigo_linea):
    if not _CODIGO_VALIDO.match(codigo_linea or ""):
        raise ValueError(f"código de línea no admisible para una secuencia: {codigo_linea!r}")
    return f"nucleo_folio_{codigo_linea}"


def crear_secuencia(codigo_linea, empezar_en=1):
    """Crea la secuencia si no existe. Idempotente."""
    secuencia = nombre_secuencia(codigo_linea)
    # PostgreSQL no admite parámetros en las sentencias de definición, así que
    # el valor se interpola. Va convertido a entero antes, que es lo que
    # impide que por ahí entre nada más.
    empezar_en = max(int(empezar_en or 1), 1)
    with connections[BASE].cursor() as cursor:
        cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {secuencia} START WITH {empezar_en}")


def alinear(codigo_linea, minimo):
    """Coloca la secuencia por encima de `minimo`, nunca por debajo.

    Se llama al sembrar con el identificador más alto ya emitido en la tabla
    heredada. Bajar una secuencia significaría volver a entregar folios ya
    impresos, así que esta función sólo sube.
    """
    secuencia = nombre_secuencia(codigo_linea)
    minimo = max(int(minimo or 0), 0)
    with connections[BASE].cursor() as cursor:
        cursor.execute(f"SELECT last_value, is_called FROM {secuencia}")
        ultimo, llamada = cursor.fetchone()
        actual = int(ultimo) if llamada else int(ultimo) - 1
        if minimo > actual:
            cursor.execute("SELECT setval(%s, %s, true)", [secuencia, minimo])
            return minimo
        return actual


def siguiente_numero(codigo_linea):
    secuencia = nombre_secuencia(codigo_linea)
    with connections[BASE].cursor() as cursor:
        cursor.execute("SELECT nextval(%s)", [secuencia])
        return int(cursor.fetchone()[0])


def siguiente(linea):
    """El folio siguiente de una línea, ya formateado: `H-00042`."""
    return formatear(linea.prefijo_folio, siguiente_numero(linea.codigo))


def formatear(prefijo, numero):
    return f"{prefijo}-{int(numero):05d}"
