"""Interruptores para migrar una línea a la vez, y poder volver atrás.

La migración al núcleo unificado no es un cambio grande: son cuatro cambios
pequeños, uno por línea de negocio, cada uno reversible en un reinicio. Estas
banderas son el mecanismo.

Cada línea pasa por tres situaciones:

1. **Apagada.** El núcleo existe pero nadie lo usa. Es el estado por omisión y
   el que hay hoy en el taller.
2. **Escritura doble.** Las vistas siguen escribiendo en las tablas heredadas
   y además, en la misma transacción, en el núcleo. La verdad sigue estando en
   lo heredado. Un trabajo diario compara las dos y anota cualquier diferencia
   en `DivergenciaReconciliacion`.
3. **Corte.** El núcleo pasa a ser la fuente de verdad. Se hace **sólo**
   cuando la reconciliación lleva siete días seguidos sin encontrar nada, y se
   deshace poniendo la bandera de vuelta a `doble`.

El orden de corte va de menos a más riesgo: robótica (que ni siquiera tiene
máquina de estados) → corte láser (una orden viva) → herrería → vigas.

Se leen del entorno para poder cambiarlas sin tocar código ni base:

    MES_NUCLEO_HERRERIA=doble
    MES_NUCLEO_ROBOTICA=corte

Durante las primeras cuarenta y ocho horas de escritura doble, el fallo al
escribir en el núcleo se registra y se continúa: es la única situación de todo
este trabajo donde tragarse una excepción es lo correcto, porque lo contrario
es que el operador no pueda registrar su trabajo por culpa de una tabla que
todavía no manda nada. `MES_NUCLEO_ESTRICTO=1` quita esa red cuando se ha
comprobado que no salta.
"""

import os

from core.constantes import LINEAS

APAGADA = "apagada"
DOBLE = "doble"
CORTE = "corte"

MODOS = (APAGADA, DOBLE, CORTE)


def _variable(linea):
    return f"MES_NUCLEO_{linea.upper()}"


def modo(linea):
    """En qué situación está una línea. Por omisión, apagada.

    Un valor irreconocible se trata como apagado a propósito: una errata en
    una variable de entorno no debe encender una escritura nueva sobre la base
    de producción.
    """
    valor = (os.environ.get(_variable(linea)) or "").strip().lower()
    return valor if valor in MODOS else APAGADA


def escribe_en_nucleo(linea):
    """¿Hay que escribir en el núcleo al procesar esta línea?"""
    return modo(linea) in (DOBLE, CORTE)


def nucleo_manda(linea):
    """¿El núcleo es ya la fuente de verdad de esta línea?"""
    return modo(linea) == CORTE


def estricto():
    """Si un fallo al escribir en el núcleo debe interrumpir la operación.

    Apagado mientras dure el rodaje. Encenderlo es la señal de que ya se
    confía en la escritura nueva.
    """
    return (os.environ.get("MES_NUCLEO_ESTRICTO") or "").strip() in ("1", "true", "sí", "si")


def resumen():
    """El estado de las cuatro líneas, para los informes y el diagnóstico."""
    return {linea: modo(linea) for linea in LINEAS}
