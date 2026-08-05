"""Por qué etapas pasa cada orden.

No todas pasan por todas. Hay piezas que se cortan, se sueldan y se entregan
sin pintar. Hasta ahora la secuencia estaba configurada **por línea**, así que
no había forma de decirlo: en el taller se pasaba la pieza por pintura igual y
se declaraba sin pintar nada. El sistema registraba una etapa que no ocurrió,
y todo lo que se calcula encima de eso —cuánto le falta, cuánto tardó, cuánto
costó, quién lo hizo— quedaba apoyado en un dato falso.

Aquí la ruta es **de la orden**. Se guarda en `OrdenProduccion.ruta` como la
lista de etapas por las que pasa. Vacía significa «las de su línea, todas»,
que es lo que hacía el sistema y sigue siendo lo normal.

Por qué se consulta desde el camino heredado
---------------------------------------------

Las cuatro líneas todavía corren sobre sus tablas de siempre. Escribir la ruta
cuatro veces, una por tabla, sería repetir el error del que vive este sistema.
Así que se escribe **una vez**, en el núcleo, y las pantallas heredadas la
consultan por la referencia al legado que el volcado ya dejó puesta.

Si esa orden no tiene fila en el núcleo —porque se creó con la escritura doble
apagada— no se rompe nada: se responde la secuencia completa de la línea, que
es exactamente el comportamiento de antes. La función nueva sólo puede quitar
etapas, nunca añadirlas.
"""

from core import estados

BASE = "mes"

#: Las etapas que no se pueden quitar de una ruta.
#:
#: Terminado y enviado no son trabajo de taller: son el cierre y la salida.
#: Y la primera etapa tampoco: una orden tiene que entrar por algún lado.
SIEMPRE = {estados.TERMINADO, estados.ENVIADO}

#: Qué etapa de espera precede a cada etapa de trabajo. Quitar «pintura» de
#: una ruta tiene que quitar también «espera de pintura»: dejar la cola de una
#: etapa que no se hace es dejar la pieza esperando a nadie.
ESPERA_DE = {
    estados.CORTE: estados.ESPERA_CORTE,
    estados.ARMADO: estados.ESPERA_ARMADO,
    estados.SOLDADURA: estados.ESPERA_SOLDADURA,
    estados.PINTURA: estados.ESPERA_PINTURA,
}

#: Las etapas que se pueden marcar o desmarcar al crear la orden. Son las de
#: trabajo: su espera va pegada y no se pregunta aparte.
CONFIGURABLES = [estados.CORTE, estados.ARMADO, estados.SOLDADURA, estados.PINTURA]


def secuencia_completa():
    """La secuencia de siempre, sin “enviado”: eso es logística."""
    return [e for e in estados.SECUENCIA if e != estados.ENVIADO]


def armar(etapas_de_trabajo):
    """La ruta que corresponde a un conjunto de etapas de trabajo marcadas.

    Recibe cuáles se hacen —corte, armado, soldadura, pintura— y devuelve la
    secuencia completa con sus esperas, en orden. Marcar sólo corte y
    soldadura da: espera de corte, corte, espera de soldadura, soldadura,
    terminado.

    Sin ninguna marcada devuelve la secuencia entera. Una orden que no pasa
    por ninguna etapa no es una orden, y lo más probable es que sea un
    formulario mandado sin tocar las casillas.
    """
    marcadas = {estados.normalizar(e) for e in (etapas_de_trabajo or [])}
    marcadas = {e for e in marcadas if e in CONFIGURABLES}
    if not marcadas:
        return secuencia_completa()

    ruta = []
    for etapa in secuencia_completa():
        if etapa in SIEMPRE:
            ruta.append(etapa)
        elif etapa in CONFIGURABLES:
            if etapa in marcadas:
                ruta.append(etapa)
        elif etapa in ESPERA_DE.values():
            # La espera va si va su etapa de trabajo.
            trabajo = next(t for t, espera in ESPERA_DE.items() if espera == etapa)
            if trabajo in marcadas:
                ruta.append(etapa)
    return ruta


def etapas_de_trabajo(ruta):
    """Lo contrario de `armar`: qué casillas hay que enseñar marcadas."""
    if not ruta:
        return list(CONFIGURABLES)
    puestas = {estados.normalizar(e) for e in ruta}
    return [e for e in CONFIGURABLES if e in puestas]


def _orden_del_nucleo(legacy_modelo, legacy_id):
    from nucleo.models import OrdenProduccion

    if not legacy_modelo or not legacy_id:
        return None
    return (
        OrdenProduccion.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id=int(legacy_id))
        .only("ruta")
        .first()
    )


def de(legacy_modelo, legacy_id):
    """La ruta de una orden heredada, o la secuencia completa.

    Nunca devuelve una lista vacía: sin ruta configurada, la respuesta es el
    comportamiento de siempre.
    """
    orden = _orden_del_nucleo(legacy_modelo, legacy_id)
    guardada = [estados.normalizar(e) for e in (orden.ruta if orden else [])]
    guardada = [e for e in guardada if e]
    return guardada or secuencia_completa()


def guardar(legacy_modelo, legacy_id, etapas_de_trabajo_marcadas):
    """Fija la ruta de una orden. Devuelve la ruta guardada, o `None`.

    `None` significa que esa orden no tiene fila en el núcleo, y entonces no
    hay dónde guardarla. Se dice en vez de fingir que se guardó: una
    configuración que la pantalla acepta y el sistema ignora es peor que un
    error.
    """
    orden = _orden_del_nucleo(legacy_modelo, legacy_id)
    if orden is None:
        return None
    ruta = armar(etapas_de_trabajo_marcadas)
    if ruta == secuencia_completa():
        # Guardar la ruta completa es guardar «lo de siempre». Se deja vacía
        # para que se distinga lo que alguien decidió de lo que nadie tocó.
        ruta = []
    orden.ruta = ruta
    orden.save(using=BASE, update_fields=["ruta", "actualizado_en"])
    return ruta or secuencia_completa()


def siguiente(legacy_modelo, legacy_id, etapa_actual):
    """A qué etapa pasa esta orden desde donde está. Cadena vacía si ninguna.

    Es lo que hace útil la ruta: en una orden sin pintura, «terminé soldadura»
    lleva a Terminado y no a «Espera de pintura».
    """
    etapa = estados.normalizar(etapa_actual)
    ruta = de(legacy_modelo, legacy_id)
    if etapa not in ruta:
        # La orden está en una etapa que su ruta no contempla. Pasa cuando se
        # recorta la ruta de algo que ya iba por en medio. Se la manda a la
        # siguiente de la ruta que quede por delante, en vez de dejarla
        # atascada sin ningún botón.
        completa = secuencia_completa()
        if etapa not in completa:
            return ""
        posicion = completa.index(etapa)
        siguientes = [e for e in ruta if completa.index(e) > posicion]
        return siguientes[0] if siguientes else ""
    posicion = ruta.index(etapa)
    return ruta[posicion + 1] if posicion + 1 < len(ruta) else ""


def avance(legacy_modelo, legacy_id, etapa_actual):
    """Cuánto lleva recorrido, de 0 a 100, **sobre su propia ruta**.

    Una pieza que no lleva pintura está al cien por cien cuando sale de
    soldadura. Medirla contra la secuencia completa la dejaría en 75 % para
    siempre, y una lista de control llena de órdenes que nunca llegan al final
    deja de leerse.
    """
    etapa = estados.normalizar(etapa_actual)
    ruta = de(legacy_modelo, legacy_id)
    if etapa not in ruta or len(ruta) < 2:
        return 0
    return round(ruta.index(etapa) / (len(ruta) - 1) * 100)
