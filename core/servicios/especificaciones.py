"""Cómo se hace una pieza, escrito para quien la va a hacer.

En el celular, un soldador leía «V-118 · 3/50 · Obra Norte». Eso identifica
la pieza; no dice cómo es. Lo que hace falta en la mano es el detalle: «vigas
de 70 cm con un corte a los 30 cm a noventa grados». Hoy ese detalle viaja en
un plano impreso o de boca en boca, y por eso se rehacen piezas.

Se guarda contra la fila heredada (`legacy_modelo`, `legacy_id`), no contra
la orden del núcleo. La razón está en el modelo `EspecificacionOrden`: esto es
contenido que alguien escribió, y tiene que poder escribirse y leerse aunque
el motor unificado todavía no esté encendido en ese servidor.

Igual que la ruta, es **del lote**. Cincuenta vigas iguales son cincuenta
filas en la tabla heredada, pero se hacen todas igual: escribir la
especificación en una y no en las otras cuarenta y nueve sería escribirla
donde nadie la va a leer.
"""

from django.utils import timezone

from core.servicios import ruta as servicio_ruta

BASE = "mes"

#: Tope de lo que se puede escribir. No es una restricción de la base —el
#: campo es de texto libre— sino de la pantalla en la que se lee: una tarjeta
#: de teléfono. Lo que no cabe ahí no son instrucciones, es un plano, y para
#: eso está el PDF.
LARGO_MAXIMO = 1000


def de(legacy_modelo, legacy_id):
    """Las especificaciones de una orden. Cadena vacía si no hay ninguna."""
    from nucleo.models import EspecificacionOrden

    if not legacy_modelo or not legacy_id:
        return ""
    fila = (
        EspecificacionOrden.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id=int(legacy_id))
        .only("texto")
        .first()
    )
    return (fila.texto if fila else "") or ""


def de_muchas(legacy_modelo, identificadores):
    """Las de varias órdenes de golpe, en un diccionario por identificador.

    Existe para las listas. Consultarlas una por una convertía una pantalla
    de cuarenta tarjetas en cuarenta consultas más, que es exactamente el
    defecto que este sistema tiene repartido por todas partes.
    """
    from nucleo.models import EspecificacionOrden

    identificadores = [int(i) for i in identificadores if i]
    if not legacy_modelo or not identificadores:
        return {}
    return {
        fila.legacy_id: fila.texto
        for fila in EspecificacionOrden.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id__in=identificadores)
        .only("legacy_id", "texto")
        if fila.texto
    }


def guardar_en_una(legacy_modelo, legacy_id, texto, quien=""):
    """Como `guardar`, pero sin tocar el resto del lote.

    Es lo que usa el alta: la orden que acaba de nacer copia lo que ya estaba
    escrito. Si escribiera en todo el lote, dar de alta la viga número
    cincuenta pisaría el texto de las cuarenta y nueve anteriores con el que
    la número cincuenta acaba de heredar de ellas —el mismo, casi siempre, y
    cuarenta y nueve escrituras para nada.
    """
    from nucleo.models import EspecificacionOrden

    texto = (texto or "").strip()[:LARGO_MAXIMO]
    if not legacy_modelo or not legacy_id or not texto:
        return ""
    EspecificacionOrden.objects.using(BASE).update_or_create(
        legacy_modelo=legacy_modelo,
        legacy_id=int(legacy_id),
        defaults={"texto": texto, "actualizado_por": (quien or "")[:120]},
    )
    return texto


def heredadas(orden):
    """Las especificaciones que le tocan a una orden recién creada, o "".

    Mismas dos fuentes que la ruta: su pieza de catálogo primero —lo que se
    fabrica siempre se describe una vez— y sus hermanas de lote después, para
    Estructuras, que no tiene catálogo y da de alta las piezas de un pedido
    una por una.
    """
    if orden.pieza_id:
        recordadas = (orden.pieza.especificaciones or "").strip()
        if recordadas:
            return recordadas[:LARGO_MAXIMO]

    if orden.legacy_modelo != "Viga":
        return ""

    del_lote = [
        i
        for i in servicio_ruta.hermanas("Viga", orden.legacy_id)
        if i != orden.legacy_id
    ]
    for texto in de_muchas("Viga", del_lote).values():
        return texto
    return ""


def recordar_en_la_pieza(pieza, texto):
    """Deja fijadas las instrucciones por omisión de una pieza de catálogo.

    No toca las órdenes que ya existen, igual que la ruta: corregir cómo se
    hace algo de aquí en adelante no puede reescribir lo que el taller ya
    tiene en la mano.
    """
    if pieza is None:
        return ""
    pieza.especificaciones = (texto or "").strip()[:LARGO_MAXIMO]
    pieza.save(using=BASE, update_fields=["especificaciones", "actualizado_en"])
    return pieza.especificaciones


def guardar(legacy_modelo, legacy_id, texto, quien=""):
    """Escribe las especificaciones en todo el lote. Devuelve el texto guardado.

    Un texto vacío borra la fila: quien vació el campo está diciendo que no
    hay instrucciones, y dejar una fila vacía haría que la tarjeta del piso
    reservara un hueco para nada.
    """
    from nucleo.models import EspecificacionOrden

    texto = (texto or "").strip()[:LARGO_MAXIMO]
    identificadores = servicio_ruta.hermanas(legacy_modelo, legacy_id)
    if not identificadores:
        return ""

    consulta = EspecificacionOrden.objects.using(BASE).filter(
        legacy_modelo=legacy_modelo, legacy_id__in=identificadores
    )
    if not texto:
        consulta.delete()
        return ""

    actualizadas = set(consulta.values_list("legacy_id", flat=True))
    consulta.update(
        texto=texto, actualizado_por=quien[:120], actualizado_en=timezone.now()
    )
    EspecificacionOrden.objects.using(BASE).bulk_create(
        [
            EspecificacionOrden(
                legacy_modelo=legacy_modelo,
                legacy_id=identificador,
                texto=texto,
                actualizado_por=quien[:120],
            )
            for identificador in identificadores
            if identificador not in actualizadas
        ],
        # Dos personas guardando el mismo lote a la vez chocan contra la
        # restricción de unicidad. La segunda no tiene nada que aportar —el
        # texto ya está escrito— así que se ignora en vez de reventar la
        # pantalla de quien guardó segundo.
        ignore_conflicts=True,
    )
    return texto
