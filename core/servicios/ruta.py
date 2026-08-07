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

from django.utils import timezone

from core import estados
from core.bases import BASE  # noqa: F401


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


def _para_guardar(etapas_de_trabajo_marcadas):
    """La ruta tal y como se almacena.

    La ruta completa se guarda vacía, para que se distinga lo que alguien
    decidió de lo que nadie tocó.
    """
    ruta = armar(etapas_de_trabajo_marcadas)
    return [] if ruta == secuencia_completa() else ruta


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
    ruta = _para_guardar(etapas_de_trabajo_marcadas)
    orden.ruta = ruta
    orden.save(using=BASE, update_fields=["ruta", "actualizado_en"])
    return ruta or secuencia_completa()


# ----------------------------------------------------------------- el lote
#
# En Estructuras metálicas, una orden de cincuenta vigas son cincuenta filas,
# una por pieza. La ruta, en cambio, es del pedido: si esas vigas no se
# pintan, no se pinta ninguna. Recortarle la ruta a una sola dejaba a las
# cuarenta y nueve restantes formadas en una cola de pintura por la que no
# iban a pasar, y quien la configuró creía haberlo dicho.
#
# Las otras tres líneas llevan una fila por orden, así que su lote es ella
# misma y estas funciones se comportan como las de arriba.


def hermanas(legacy_modelo, legacy_id):
    """Las filas heredadas que forman el mismo lote que ésta, ella incluida.

    Se agrupa por código y obra, que es como se identifica un pedido en el
    piso. La etapa **no** entra: que media orden vaya por soldadura y la otra
    media siga en corte no la convierte en dos pedidos.
    """
    if legacy_modelo != "Viga":
        return [int(legacy_id)] if legacy_id else []

    from produccion.models import Viga

    pieza = Viga.objects.using(BASE).filter(pk=legacy_id).only(
        "internal_id", "codigo_viga", "proyecto"
    ).first()
    if pieza is None:
        return []
    return list(
        Viga.objects.using(BASE)
        .filter(codigo_viga=pieza.codigo_viga, proyecto=pieza.proyecto)
        .order_by("pieza_no", "internal_id")
        .values_list("internal_id", flat=True)
    )


def guardar_en_el_lote(legacy_modelo, legacy_id, etapas_de_trabajo_marcadas):
    """Fija la ruta de todas las piezas del lote. Devuelve `(ruta, cuántas)`.

    `(None, 0)` si ninguna de ellas tiene fila en el núcleo: no hay dónde
    guardarla y se dice, igual que en `guardar`.
    """
    from nucleo.models import OrdenProduccion

    ruta = _para_guardar(etapas_de_trabajo_marcadas)
    identificadores = hermanas(legacy_modelo, legacy_id)
    if not identificadores:
        return None, 0

    cuantas = (
        OrdenProduccion.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id__in=identificadores)
        .update(ruta=ruta, actualizado_en=timezone.now())
    )
    if not cuantas:
        return None, 0
    return (ruta or secuencia_completa()), cuantas


# --------------------------------------------------- las que se hacen siempre
#
# Hay piezas que se fabrican una vez y piezas que salen todas las semanas. Un
# andamio tipo A no se pinta nunca. Sin memoria, alguien tiene que acordarse
# de quitarle la pintura en cada pedido; el día que se le olvide, el andamio
# se forma en una cola por la que no va a pasar y nadie se entera hasta que
# el pintor pregunta.
#
# Así que la ruta se puede recordar en la pieza del catálogo, y las órdenes
# nuevas de esa pieza nacen ya con ella puesta.


def pieza_de_catalogo(legacy_modelo, legacy_id):
    """La pieza de catálogo de una orden heredada, o `None`.

    Es lo que decide si la pantalla puede ofrecer «recordar esto para todas
    las piezas iguales». Estructuras no tiene catálogo, así que ahí no se
    ofrece: no habría dónde recordarlo.
    """
    from nucleo.models import OrdenProduccion

    if not legacy_modelo or not legacy_id:
        return None
    orden = (
        OrdenProduccion.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id=int(legacy_id))
        .select_related("pieza")
        .only("pieza")
        .first()
    )
    return orden.pieza if orden else None


def de_la_pieza(pieza):
    """La ruta recordada de una pieza de catálogo, o `[]` si no hay ninguna."""
    guardada = [estados.normalizar(e) for e in (getattr(pieza, "ruta", None) or [])]
    return [e for e in guardada if e]


def recordar_en_la_pieza(pieza, etapas_de_trabajo_marcadas):
    """Deja fijada la ruta por omisión de una pieza de catálogo.

    No toca las órdenes que ya existen. Cambiar cómo se hace algo de aquí en
    adelante no puede reescribir lo que ya se acordó con un cliente ni lo que
    ya va por medio taller.
    """
    if pieza is None:
        return None
    pieza.ruta = _para_guardar(etapas_de_trabajo_marcadas)
    pieza.save(using=BASE, update_fields=["ruta", "actualizado_en"])
    return pieza.ruta or secuencia_completa()


def olvidar_en_la_pieza(pieza):
    """Quita la ruta recordada: sus órdenes nuevas vuelven a pasar por todo."""
    if pieza is None or not (pieza.ruta or []):
        return
    pieza.ruta = []
    pieza.save(using=BASE, update_fields=["ruta", "actualizado_en"])


def heredada(orden):
    """La ruta que le toca a una orden recién creada, o `[]`.

    Dos fuentes, en este orden:

    1. **Su pieza de catálogo**, si alguien recordó una ruta ahí. Es el caso
       de lo que se fabrica siempre.
    2. **Sus hermanas de lote**, para Estructuras, que no tiene catálogo. Las
       piezas de un pedido de cincuenta vigas se dan de alta una por una: sin
       esto, la ruta que se configuró al dar de alta la primera no la
       heredarían las otras cuarenta y nueve.

    Devuelve la lista tal y como se almacena: vacía significa «la de siempre».
    """
    from nucleo.models import OrdenProduccion

    if orden.pieza_id:
        recordada = de_la_pieza(orden.pieza)
        if recordada:
            return recordada

    if orden.legacy_modelo != "Viga":
        return []

    del_lote = [i for i in hermanas("Viga", orden.legacy_id) if i != orden.legacy_id]
    if not del_lote:
        return []
    hermana = (
        OrdenProduccion.objects.using(BASE)
        .filter(legacy_modelo="Viga", legacy_id__in=del_lote)
        .exclude(ruta=[])
        .only("ruta")
        .first()
    )
    return list(hermana.ruta) if hermana else []


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
