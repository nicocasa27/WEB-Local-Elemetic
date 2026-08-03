"""Definición única de la máquina de estados de producción.

Hoy los estados son cadenas sueltas: la secuencia completa aparece copiada en
media docena de sitios de `catalogos/views.py`, hay unos ciento cuarenta
literales repartidos por el código y los campos que los guardan no declaran
`choices`. De ahí salen dos problemas reales:

- **Variantes ortográficas.** "Espera Armado" y "Espera de armado" son el
  mismo estado escrito de dos formas. En vigas se parchea con `ESTADO_ALIASES`
  y `_norm_estado`; en herrería y corte láser no, así que una orden guardada
  con la variante equivocada desaparece de los filtros.
- **Estados fuera de la secuencia.** `"Terminado (bloqueo pend.)"` no está en
  ninguna de las listas que usan las pantallas, de modo que al buscar su
  posición se obtiene -1 y la comprobación de retroceso queda desactivada:
  desde ese estado se podía saltar a cualquier otro sin justificar nada. Es
  un fallo de control de acceso disfrazado de detalle de interfaz.

Este módulo pone la secuencia en un solo lugar y ofrece `normalizar()` para
leer cualquier variante histórica. **No cambia lo que hay guardado en la
base**: el valor almacenado sigue siendo la etiqueta legible, como hasta
ahora. La conversión a claves estables y a una tabla de etapas es parte de la
unificación del núcleo, y necesita una migración de datos.
"""

import unicodedata

# --------------------------------------------------------------- secuencia

ESPERA_CORTE = "Espera de corte"
CORTE = "Corte"
ESPERA_ARMADO = "Espera de armado"
ARMADO = "Armado"
ESPERA_SOLDADURA = "Espera de soldadura"
SOLDADURA = "Soldadura"
ESPERA_PINTURA = "Espera de pintura"
PINTURA = "Pintura"
TERMINADO = "Terminado"
ENVIADO = "Enviado"

#: Estado intermedio del cierre con ventana de reversión. Va **entre**
#: Terminado y Enviado a propósito: si queda fuera de la secuencia, la
#: comprobación de retroceso no funciona para las órdenes que lo tienen.
CIERRE_PENDIENTE = "Terminado (bloqueo pend.)"

#: Secuencia completa para una pieza individual.
SECUENCIA = [
    ESPERA_CORTE,
    CORTE,
    ESPERA_ARMADO,
    ARMADO,
    ESPERA_SOLDADURA,
    SOLDADURA,
    ESPERA_PINTURA,
    PINTURA,
    TERMINADO,
    ENVIADO,
]

#: Secuencia que sigue una orden grande, cuyo avance se lleva por contadores
#: en vez de por etapas: de soldadura pasa directamente al cierre.
SECUENCIA_ORDEN_GRANDE = [
    ESPERA_CORTE,
    CORTE,
    SOLDADURA,
    CIERRE_PENDIENTE,
    TERMINADO,
    ENVIADO,
]

#: Secuencia con el estado de cierre incluido, para comprobar retrocesos sin
#: que ninguna orden quede fuera de la lista.
SECUENCIA_COMPLETA = [
    ESPERA_CORTE,
    CORTE,
    ESPERA_ARMADO,
    ARMADO,
    ESPERA_SOLDADURA,
    SOLDADURA,
    ESPERA_PINTURA,
    PINTURA,
    CIERRE_PENDIENTE,
    TERMINADO,
    ENVIADO,
]

ESTADOS_DE_ESPERA = {ESPERA_CORTE, ESPERA_ARMADO, ESPERA_SOLDADURA, ESPERA_PINTURA}

# ------------------------------------------------------------ equivalencias
#
# Variantes históricas encontradas en la base y en el código. La clave es la
# forma normalizada; el valor, la escritura buena.
EQUIVALENCIAS = {
    "espera armado": ESPERA_ARMADO,
    "espera soldadura": ESPERA_SOLDADURA,
    "espera pintura": ESPERA_PINTURA,
    "espera corte": ESPERA_CORTE,
    "espera de armado": ESPERA_ARMADO,
    "espera de soldadura": ESPERA_SOLDADURA,
    "espera de pintura": ESPERA_PINTURA,
    "espera de corte": ESPERA_CORTE,
}


def _clave(valor):
    """Minúsculas, sin acentos y sin espacios sobrantes."""
    texto = (valor or "").strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def normalizar(valor):
    """Devuelve la escritura buena de un estado, venga como venga.

    Absorbe `ESTADO_ALIASES` y `_norm_estado` de produccion/views.py, con dos
    diferencias: no distingue mayúsculas ni acentos, y se aplica también a
    herrería y a corte láser, que hasta ahora no pasaban por ninguna
    normalización.

    Un valor desconocido se devuelve tal cual, sólo con los espacios
    recortados: es preferible mostrar un estado raro que perder la orden.
    """
    texto = (valor or "").strip()
    if not texto:
        return ""
    return EQUIVALENCIAS.get(_clave(texto), texto)


def variantes(valor):
    """Todas las formas conocidas de escribir un estado.

    Necesario para filtrar en la base mientras convivan escrituras distintas,
    porque la consulta tiene que buscarlas todas.
    """
    canonico = normalizar(valor)
    if not canonico:
        return []
    formas = {canonico}
    for clave, destino in EQUIVALENCIAS.items():
        if destino == canonico:
            formas.add(clave.title())
    return sorted(formas)


def posicion(valor, secuencia=None):
    """Posición del estado en la secuencia, o None si no pertenece.

    Devolver None en lugar de -1 es deliberado. Con -1, las comparaciones del
    tipo `destino < actual` daban falso por accidente y desactivaban la
    comprobación de retroceso sin que nadie se enterara. Con None hay que
    tratar el caso a propósito.
    """
    secuencia = secuencia or SECUENCIA_COMPLETA
    canonico = normalizar(valor)
    try:
        return secuencia.index(canonico)
    except ValueError:
        return None


def es_retroceso(actual, destino, secuencia=None):
    """¿El cambio va hacia atrás en la secuencia?

    Devuelve None cuando alguno de los dos estados no está en la secuencia, en
    vez de suponer que no hay retroceso. Quien llame decide qué hacer, pero
    tiene que decidirlo.
    """
    i_actual = posicion(actual, secuencia)
    i_destino = posicion(destino, secuencia)
    if i_actual is None or i_destino is None:
        return None
    return i_destino < i_actual


# ------------------------------------------------------------------ colores
#
# Un solo diccionario, con las variantes resueltas por normalizar(). Antes
# había dos copias, una en cada módulo de vistas, y no coincidían: la de
# catalogos usaba "Espera Armado" y la de produccion "Espera de armado".
COLORES = {
    ESPERA_CORTE: "#ff8f00",
    CORTE: "#f39c12",
    ESPERA_ARMADO: "#d35400",
    ARMADO: "#3498db",
    ESPERA_SOLDADURA: "#5d6d7e",
    SOLDADURA: "#9b59b6",
    ESPERA_PINTURA: "#7f8c8d",
    PINTURA: "#16a085",
    CIERRE_PENDIENTE: "#fb6340",
    TERMINADO: "#2dce89",
    ENVIADO: "#11cdef",
}

COLOR_POR_DEFECTO = "#8898aa"


def color(valor):
    """Color de un estado, tolerante con las variantes de escritura."""
    return COLORES.get(normalizar(valor), COLOR_POR_DEFECTO)
