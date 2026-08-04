"""Movimientos de materia prima: entradas, consumos, ajustes y traslados.

Mismas reglas que el motor de producción, porque los mismos fallos se cometen
igual con kilos que con piezas:

- **Se piden incrementos, no totales.** Nadie «pone el inventario en 40»: se
  registra que entraron 12 o que se consumieron 3.
- **Clave de idempotencia.** Un reenvío desde el celular del almacén no
  descuenta dos veces.
- **Corregir es insertar el movimiento contrario.** Un consumo mal capturado
  no se borra: se devuelve, y quedan las dos cosas.
- **Las existencias son caché.** La verdad es la suma de los movimientos.

Y dos reglas propias del almacén:

**No se puede sacar lo que no hay.** Ni en total ni de un lote concreto. La
base también lo impide, para que no exista ningún camino —ni un `update` en
bloque, ni una consulta a mano— capaz de dejar el almacén debiendo material.

**El consumo sale por antigüedad de lote.** Primero lo que entró antes. Es lo
que el taller pidió, es lo que hace que el costo de una orden sea el costo
real de lo que se metió en ella, y es lo que permite responder de qué colada
salió una pieza.

Lo que este módulo **no** hace, a propósito: descontar solo a partir de la
lista de materiales. `consumo_sugerido` propone y una persona confirma. Una
lista incorrecta que descuenta automáticamente vacía el inventario en una
semana sin que nadie se entere hasta que hay que comprar. Se automatiza cuando
lo propuesto y lo real coincidan, y eso se mide antes con
`comparar_consumo`.
"""

import logging
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.excepciones import (
    CantidadInvalida,
    ErrorDeDominio,
    MotivoRequerido,
    StockInsuficiente,
)
from inventario.models import (
    Almacen,
    Existencia,
    ListaMateriales,
    LoteMaterial,
    Material,
    MovimientoMaterial,
    RenglonOrdenCompra,
)

logger = logging.getLogger("mes.inventario")

BASE = "mes"
CERO = Decimal("0")
PRECISION = Decimal("0.000001")

#: Movimientos que suman a la existencia. El resto resta.
TIPOS_QUE_SUMAN = {
    MovimientoMaterial.Tipo.ENTRADA,
    MovimientoMaterial.Tipo.DEVOLUCION,
    MovimientoMaterial.Tipo.TRASLADO_ENTRADA,
}

#: Movimientos que **no tocan el estante**: mueven la promesa, no la cosa.
#:
#: Hay que dejarlos fuera de cualquier suma del físico. Reconstruir las
#: existencias sumando todos los movimientos —que es como se comprueba que la
#: caché no miente— daría de más por cada reserva y de menos por cada
#: liberación, y el descuadre parecería un fallo del almacén cuando sería del
#: recálculo.
TIPOS_DE_PROMESA = {
    MovimientoMaterial.Tipo.RESERVA,
    MovimientoMaterial.Tipo.LIBERACION,
}


class LoteAgotado(ErrorDeDominio):
    """Se pidió consumir de un lote concreto que ya no tiene suficiente."""

    mensaje_por_defecto = "Ese lote no tiene material suficiente."


class SinAlmacen(ErrorDeDominio):
    """No hay ningún almacén dado de alta."""

    mensaje_por_defecto = (
        "No hay ningún almacén configurado. Ejecutar `sembrar_inventario` primero."
    )


def a_cantidad(valor):
    try:
        return Decimal(str(valor)).quantize(PRECISION)
    except Exception as error:
        raise CantidadInvalida(f"Cantidad no válida: {valor!r}.") from error


def nombre_de(actor):
    if actor is None:
        return "system"
    return getattr(actor, "username", None) or str(actor)


def almacen_principal():
    almacen = (
        Almacen.objects.using(BASE).filter(activo=True).order_by("-es_principal", "id").first()
    )
    if almacen is None:
        raise SinAlmacen()
    return almacen


# =========================================================== consultas

def existencia(material, almacen=None, lote=None):
    """Cuánto hay. Sin almacén, la suma de todos."""
    consulta = Existencia.objects.using(BASE).filter(material=material)
    if almacen is not None:
        consulta = consulta.filter(almacen=almacen)
    if lote is not None:
        consulta = consulta.filter(lote=lote)
    return consulta.aggregate(total=Sum("cantidad"))["total"] or CERO


def lotes_disponibles(material, almacen):
    """Los lotes con existencia, del más antiguo al más nuevo.

    El orden es el que decide de dónde sale el material y, con él, el costo
    que se le carga a la orden. Que sea por fecha de recepción y no por
    identificador importa: un lote dado de alta tarde puede haberse recibido
    antes.
    """
    return (
        Existencia.objects.using(BASE)
        .filter(material=material, almacen=almacen, cantidad__gt=CERO, lote__isnull=False)
        .select_related("lote")
        .order_by("lote__recibido_en", "lote__id")
    )


def valor_de_existencias(material=None, almacen=None):
    """Cuánto dinero hay parado en el almacén.

    Se calcula lote a lote con su propio costo, no con un promedio: es lo que
    hace que el número cuadre con lo que se pagó de verdad.
    """
    consulta = Existencia.objects.using(BASE).filter(cantidad__gt=CERO).select_related("lote")
    if material is not None:
        consulta = consulta.filter(material=material)
    if almacen is not None:
        consulta = consulta.filter(almacen=almacen)
    total = CERO
    for fila in consulta:
        costo = fila.lote.costo_unitario if fila.lote_id else CERO
        total += fila.cantidad * costo
    return total.quantize(Decimal("0.0001"))


def bajo_minimo(almacen=None):
    """Materiales por debajo de su mínimo. Lo que hay que comprar."""
    faltantes = []
    for material in Material.objects.using(BASE).filter(activo=True, stock_minimo__gt=CERO):
        hay = existencia(material, almacen=almacen)
        if hay < material.stock_minimo:
            faltantes.append((material, hay, material.stock_minimo - hay))
    return faltantes


# ======================================================== trazabilidad
#
# Las dos preguntas que hoy no se pueden responder, y que son la razón de que
# el lote exista.

def ordenes_de_la_colada(colada):
    """En qué órdenes de producción se metió esta colada.

    La pregunta que llega cuando la acería avisa de un lote defectuoso, o
    cuando un cliente reclama. Hoy la respuesta es buscar en el correo.
    """
    return (
        MovimientoMaterial.objects.using(BASE)
        .filter(
            lote__colada__iexact=(colada or "").strip(),
            tipo=MovimientoMaterial.Tipo.CONSUMO,
            orden__isnull=False,
        )
        .select_related("orden", "lote", "material")
        .order_by("ocurrido_en")
    )


def coladas_de_la_orden(orden):
    """De qué coladas está hecha esta orden. La pregunta inversa."""
    return (
        MovimientoMaterial.objects.using(BASE)
        .filter(orden=orden, tipo=MovimientoMaterial.Tipo.CONSUMO, lote__isnull=False)
        .select_related("lote", "lote__proveedor", "material")
        .order_by("ocurrido_en")
    )


def costo_material_de(orden):
    """Cuánto material lleva una orden, en dinero.

    Es la mitad del costeo. La otra mitad —mano de obra y máquina— sale del
    historial del núcleo, y por eso el ledger tenía que existir antes que esto.
    """
    total = CERO
    for movimiento in MovimientoMaterial.objects.using(BASE).filter(orden=orden):
        # La cantidad de un consumo es negativa y la de una devolución
        # positiva, así que invertir el signo da directamente lo que la orden
        # se lleva cargado. El costo es el que tenía el lote en ese momento,
        # no el que tenga hoy: si mañana se corrige el precio de un lote, lo
        # ya consumido tiene que seguir valiendo lo que valía.
        total += -movimiento.cantidad * movimiento.costo_unitario
    return total.quantize(Decimal("0.0001"))


# ========================================================== operaciones

def _repetido(clave_idempotencia):
    if not clave_idempotencia:
        return None
    return (
        MovimientoMaterial.objects.using(BASE)
        .filter(clave_idempotencia=clave_idempotencia)
        .first()
    )


def _aplicar(material, lote, almacen, delta):
    """Suma el incremento a la caché de existencias, bloqueando la fila.

    El bloqueo es sobre la fila de existencia y no sobre el material entero:
    dos personas moviendo lotes distintos del mismo material no tienen por qué
    esperarse.
    """
    fila, _ = Existencia.objects.using(BASE).get_or_create(
        material=material, lote=lote, almacen=almacen, defaults={"cantidad": CERO}
    )
    fila = Existencia.objects.using(BASE).select_for_update().get(pk=fila.pk)
    resultado = (fila.cantidad + delta).quantize(PRECISION)
    if resultado < CERO:
        raise StockInsuficiente(
            f"No hay suficiente {material.nombre}: hay {fila.cantidad}, "
            f"se pidieron {abs(delta)}.",
            material=material.codigo,
            disponible=str(fila.cantidad),
            solicitado=str(abs(delta)),
        )
    fila.cantidad = resultado
    fila.save(using=BASE, update_fields=["cantidad", "actualizado_en"])
    return fila


def _movimiento(**campos):
    campos.setdefault("ocurrido_en", timezone.now())
    return MovimientoMaterial.objects.using(BASE).create(**campos)


@transaction.atomic(using=BASE)
def registrar_entrada(
    *,
    lote,
    cantidad,
    actor,
    almacen=None,
    renglon_compra=None,
    comentario="",
    ocurrido_en=None,
    clave_idempotencia=None,
):
    """Entra material al almacén, siempre contra un lote.

    Exigir el lote no es burocracia: es lo que hace posible responder después
    de qué colada salió una pieza y cuánto costó de verdad. Un ingreso sin
    lote es un número sin historia.
    """
    repetido = _repetido(clave_idempotencia)
    if repetido is not None:
        return repetido

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Una entrada tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()
    _aplicar(lote.material, lote, almacen, cantidad)

    if renglon_compra is not None:
        RenglonOrdenCompra.objects.using(BASE).filter(pk=renglon_compra.pk).update(
            cantidad_recibida=renglon_compra.cantidad_recibida + cantidad
        )
        _actualizar_estado_compra(renglon_compra.orden)

    movimiento = _movimiento(
        tipo=MovimientoMaterial.Tipo.ENTRADA,
        material=lote.material,
        lote=lote,
        almacen=almacen,
        cantidad=cantidad,
        costo_unitario=lote.costo_unitario,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
        ocurrido_en=ocurrido_en or timezone.now(),
        clave_idempotencia=clave_idempotencia,
    )
    logger.info(
        "entrada %s de %s (lote %s) por %s",
        cantidad, lote.material.codigo, lote.codigo, nombre_de(actor),
    )
    return movimiento


def _actualizar_estado_compra(orden_compra):
    renglones = list(orden_compra.renglones.all())
    if not renglones:
        return
    if all(r.pendiente <= CERO for r in renglones):
        estado = orden_compra.Estado.RECIBIDA
    elif any(r.cantidad_recibida > CERO for r in renglones):
        estado = orden_compra.Estado.PARCIAL
    else:
        return
    type(orden_compra).objects.using(BASE).filter(pk=orden_compra.pk).update(estado=estado)


@transaction.atomic(using=BASE)
def consumir(
    *,
    material,
    cantidad,
    actor,
    orden=None,
    almacen=None,
    lote=None,
    evento=None,
    comentario="",
    ocurrido_en=None,
    clave_idempotencia=None,
):
    """Saca material para producción, por antigüedad de lote.

    Sin indicar lote, va tomando del más antiguo hacia el más nuevo y genera
    un movimiento por cada lote del que sale algo. Eso es lo que deja escrito
    de qué coladas está hecha la orden, en vez de un único apunte que no dice
    nada.

    Devuelve la lista de movimientos, uno por lote tocado.
    """
    repetido = _repetido(clave_idempotencia)
    if repetido is not None:
        return [repetido]

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Un consumo tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()
    ocurrido_en = ocurrido_en or timezone.now()

    if lote is not None:
        disponible = existencia(material, almacen=almacen, lote=lote)
        if disponible < cantidad:
            raise LoteAgotado(
                f"El lote {lote.codigo} tiene {disponible} y se pidieron {cantidad}.",
                lote=lote.codigo,
                disponible=str(disponible),
            )
        reparto = [(lote, cantidad)]
    else:
        reparto = _repartir_por_antiguedad(material, almacen, cantidad)

    movimientos = []
    for lote_origen, porcion in reparto:
        _aplicar(material, lote_origen, almacen, -porcion)
        movimientos.append(
            _movimiento(
                tipo=MovimientoMaterial.Tipo.CONSUMO,
                material=material,
                lote=lote_origen,
                almacen=almacen,
                cantidad=-porcion,
                costo_unitario=lote_origen.costo_unitario if lote_origen else CERO,
                orden=orden,
                evento=evento,
                comentario=comentario[:255],
                actor_username=nombre_de(actor),
                ocurrido_en=ocurrido_en,
                # La clave se guarda en el primero: identifica la petición
                # entera, y el reintento la encuentra igual.
                clave_idempotencia=clave_idempotencia if not movimientos else None,
            )
        )

    logger.info(
        "consumo %s de %s en %s por %s (%s lote(s))",
        cantidad, material.codigo, orden.folio if orden else "sin orden",
        nombre_de(actor), len(movimientos),
    )
    return movimientos


def _repartir_por_antiguedad(material, almacen, cantidad):
    """Cuánto sale de cada lote, del más antiguo al más nuevo."""
    reparto = []
    pendiente = cantidad
    for fila in lotes_disponibles(material, almacen):
        if pendiente <= CERO:
            break
        porcion = min(fila.cantidad, pendiente)
        reparto.append((fila.lote, porcion))
        pendiente -= porcion

    if pendiente > CERO:
        hay = existencia(material, almacen=almacen)
        raise StockInsuficiente(
            f"No hay suficiente {material.nombre}: hay {hay} y se pidieron {cantidad}.",
            material=material.codigo,
            disponible=str(hay),
            solicitado=str(cantidad),
        )
    return reparto


# ================================================ reserva y entrega
#
# Dos hechos distintos que antes eran uno solo:
#
#   reservar   la orden aparta el material. Sigue en el estante.
#   entregar   el almacenista lo saca y lo da. Ahí baja el físico.
#
# Separarlos es lo que pedía el taller y resuelve un problema real. Si el
# descuento ocurre al generar la orden, el sistema dice que no hay material
# que sí está ahí, y el almacenista —que cuenta el estante— deja de creerle.
# Si ocurre sólo al entregar, dos órdenes se prometen la misma lámina y nadie
# se entera hasta el día de la entrega, cuando ya no da tiempo de comprar.
#
# Con los dos apuntes: el físico es lo que hay para contar, lo comprometido es
# lo que ya tiene dueño, y lo disponible —la resta— es lo único que se le
# puede prometer a una orden nueva.


def disponible(material, almacen=None, lote=None):
    """Lo que se le puede prometer a una orden nueva.

    Es lo que hay menos lo que ya está apalabrado. **No** es lo que hay: esa
    diferencia es justo el motivo de este módulo.
    """
    consulta = Existencia.objects.using(BASE).filter(material=material)
    if almacen is not None:
        consulta = consulta.filter(almacen=almacen)
    if lote is not None:
        consulta = consulta.filter(lote=lote)
    totales = consulta.aggregate(hay=Sum("cantidad"), preso=Sum("comprometido"))
    return (totales["hay"] or CERO) - (totales["preso"] or CERO)


def comprometido(material, almacen=None):
    consulta = Existencia.objects.using(BASE).filter(material=material)
    if almacen is not None:
        consulta = consulta.filter(almacen=almacen)
    return consulta.aggregate(total=Sum("comprometido"))["total"] or CERO


def _filas_con_disponible(material, almacen):
    """Las existencias que todavía tienen algo sin apalabrar, de la más
    antigua a la más nueva."""
    return [
        fila
        for fila in Existencia.objects.using(BASE)
        .filter(material=material, almacen=almacen)
        .select_related("lote")
        .order_by("lote__recibido_en", "lote__id")
        if fila.disponible > CERO
    ]


def _repartir_disponible(material, almacen, cantidad):
    """De qué lotes sale la reserva.

    Se reparte por antigüedad, igual que el consumo, y por el mismo motivo:
    lo que se aparta hoy es lo que se entregará mañana, así que la colada
    queda decidida desde la reserva y la trazabilidad no depende de quién
    tome la lámina del estante.
    """
    reparto = []
    pendiente = cantidad
    for fila in _filas_con_disponible(material, almacen):
        if pendiente <= CERO:
            break
        porcion = min(fila.disponible, pendiente)
        reparto.append((fila.lote, porcion))
        pendiente -= porcion

    if pendiente > CERO:
        libre = disponible(material, almacen=almacen)
        raise StockInsuficiente(
            f"No hay suficiente {material.nombre} sin comprometer: "
            f"libre {libre} de {existencia(material, almacen=almacen)} "
            f"y se pidieron {cantidad}.",
            material=material.codigo,
            disponible=str(libre),
            solicitado=str(cantidad),
        )
    return reparto


def _comprometer(material, lote, almacen, delta):
    """Suma el incremento a lo comprometido, bloqueando la fila."""
    fila, _ = Existencia.objects.using(BASE).get_or_create(
        material=material, lote=lote, almacen=almacen,
        defaults={"cantidad": CERO, "comprometido": CERO},
    )
    fila = Existencia.objects.using(BASE).select_for_update().get(pk=fila.pk)
    resultado = (fila.comprometido + delta).quantize(PRECISION)
    if resultado < CERO:
        raise CantidadInvalida(
            f"Se quiso liberar {abs(delta)} de {material.nombre} pero sólo "
            f"hay {fila.comprometido} comprometido."
        )
    if resultado > fila.cantidad:
        raise StockInsuficiente(
            f"No se puede comprometer {resultado} de {material.nombre}: "
            f"en el estante sólo hay {fila.cantidad}.",
            material=material.codigo,
            disponible=str(fila.cantidad - fila.comprometido),
            solicitado=str(abs(delta)),
        )
    fila.comprometido = resultado
    fila.save(using=BASE, update_fields=["comprometido", "actualizado_en"])
    return fila


@transaction.atomic(using=BASE)
def reservar(
    *,
    material,
    cantidad,
    actor,
    orden=None,
    almacen=None,
    comentario="",
    ocurrido_en=None,
    clave_idempotencia=None,
):
    """Aparta material para una orden. No lo saca del estante.

    Lo físico no se toca: lo que baja es lo disponible. Devuelve la lista de
    movimientos, uno por lote apartado.

    Si el material no es inventariable —un flete, un porcentaje de
    consumibles— no hay nada que apartar y se devuelve una lista vacía. No es
    un error: es que ese renglón del presupuesto no vive en ningún estante.
    """
    if not material.inventariable:
        logger.info("no se reserva %s: no es inventariable", material.codigo)
        return []

    repetido = _repetido(clave_idempotencia)
    if repetido is not None:
        return [repetido]

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Una reserva tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()
    ocurrido_en = ocurrido_en or timezone.now()
    reparto = _repartir_disponible(material, almacen, cantidad)

    movimientos = []
    for lote, porcion in reparto:
        _comprometer(material, lote, almacen, porcion)
        movimientos.append(
            _movimiento(
                tipo=MovimientoMaterial.Tipo.RESERVA,
                material=material,
                lote=lote,
                almacen=almacen,
                # En positivo: es lo que se apartó. No mueve existencia.
                cantidad=porcion,
                costo_unitario=lote.costo_unitario if lote else CERO,
                orden=orden,
                comentario=comentario[:255],
                actor_username=nombre_de(actor),
                ocurrido_en=ocurrido_en,
                clave_idempotencia=clave_idempotencia if not movimientos else None,
            )
        )

    logger.info(
        "reserva %s de %s para %s por %s",
        cantidad, material.codigo, orden.folio if orden else "sin orden", nombre_de(actor),
    )
    return movimientos


@transaction.atomic(using=BASE)
def liberar(
    *,
    material,
    cantidad,
    actor,
    orden=None,
    almacen=None,
    lote=None,
    comentario="",
    ocurrido_en=None,
    clave_idempotencia=None,
):
    """Suelta una reserva sin entregar nada. La orden se canceló o se recortó.

    Devuelve el material a disponible. Es lo contrario de `reservar`, no de
    `consumir`: aquí no se mueve nada del estante.
    """
    repetido = _repetido(clave_idempotencia)
    if repetido is not None:
        return [repetido]

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Una liberación tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()
    ocurrido_en = ocurrido_en or timezone.now()

    if lote is not None:
        reparto = [(lote, cantidad)]
    else:
        # Se suelta al revés de como se apartó: primero lo más nuevo, para
        # que lo viejo siga comprometido y salga antes.
        reparto = []
        pendiente = cantidad
        filas = (
            Existencia.objects.using(BASE)
            .filter(material=material, almacen=almacen, comprometido__gt=CERO)
            .select_related("lote")
            .order_by("-lote__recibido_en", "-lote__id")
        )
        for fila in filas:
            if pendiente <= CERO:
                break
            porcion = min(fila.comprometido, pendiente)
            reparto.append((fila.lote, porcion))
            pendiente -= porcion
        if pendiente > CERO:
            raise CantidadInvalida(
                f"Se quiso liberar {cantidad} de {material.nombre} pero sólo "
                f"hay {comprometido(material, almacen)} comprometido."
            )

    movimientos = []
    for lote_origen, porcion in reparto:
        _comprometer(material, lote_origen, almacen, -porcion)
        movimientos.append(
            _movimiento(
                tipo=MovimientoMaterial.Tipo.LIBERACION,
                material=material,
                lote=lote_origen,
                almacen=almacen,
                cantidad=-porcion,
                costo_unitario=lote_origen.costo_unitario if lote_origen else CERO,
                orden=orden,
                comentario=comentario[:255],
                actor_username=nombre_de(actor),
                ocurrido_en=ocurrido_en,
                clave_idempotencia=clave_idempotencia if not movimientos else None,
            )
        )
    return movimientos


@transaction.atomic(using=BASE)
def entregar(
    *,
    material,
    cantidad,
    actor,
    orden=None,
    almacen=None,
    comentario="",
    ocurrido_en=None,
    clave_idempotencia=None,
):
    """El almacenista saca el material y lo da. **Aquí baja el inventario.**

    Es el segundo factor que pedía el taller: la orden aparta, pero el
    descuento real no ocurre hasta que una persona con el material en la mano
    confirma que lo entregó. Quien produce no puede hacer esto.

    Suelta la reserva y descuenta el físico en el mismo apunte, así que el
    comprometido no se queda colgado si alguien se olvida de liberarlo.

    Devuelve `(movimientos, faltantes)`, donde `faltantes` son los materiales
    que quedaron en o por debajo de su mínimo después de entregar: es lo que
    hay que comprar, y se calcula aquí porque es el único momento en que el
    físico baja.
    """
    repetido = _repetido(clave_idempotencia)
    if repetido is not None:
        return [repetido], []

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Una entrega tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()

    # Primero se suelta lo apartado, si lo había. Se entrega lo que esté
    # comprometido y, si se pide más, el resto sale de lo libre: entregar de
    # más es una decisión del almacenista y el sistema lo deja, pero queda
    # escrito quién y cuánto.
    apartado = comprometido(material, almacen)
    if apartado > CERO:
        liberar(
            material=material,
            cantidad=min(apartado, cantidad),
            actor=actor,
            orden=orden,
            almacen=almacen,
            comentario="Entrega de material",
            ocurrido_en=ocurrido_en,
        )

    movimientos = consumir(
        material=material,
        cantidad=cantidad,
        actor=actor,
        orden=orden,
        almacen=almacen,
        comentario=comentario or "Entregado por almacén",
        ocurrido_en=ocurrido_en,
        clave_idempotencia=clave_idempotencia,
    )

    faltantes = []
    if material.stock_minimo > CERO:
        queda = existencia(material, almacen=almacen)
        # El taller lo pidió con «≤»: quedarse justo en el mínimo ya es
        # motivo de compra, porque el mínimo es lo que cubre el tiempo que
        # tarda en llegar el pedido.
        if queda <= material.stock_minimo:
            faltantes.append((material, queda, material.stock_minimo - queda))
            logger.warning(
                "reorden: %s quedó en %s con mínimo %s",
                material.codigo, queda, material.stock_minimo,
            )

    return movimientos, faltantes


@transaction.atomic(using=BASE)
def devolver(*, movimiento, actor, cantidad=None, motivo=None, comentario=""):
    """Deshace un consumo devolviendo el material a su lote.

    Se anula el movimiento original en vez de editarlo, igual que en el
    historial de producción: quedan los dos apuntes y se puede explicar qué
    pasó.
    """
    if movimiento.tipo != MovimientoMaterial.Tipo.CONSUMO:
        raise ErrorDeDominio("Sólo se devuelve un consumo.")

    devuelto = (
        MovimientoMaterial.objects.using(BASE)
        .filter(anula_a=movimiento)
        .aggregate(total=Sum("cantidad"))["total"]
        or CERO
    )
    maximo = abs(movimiento.cantidad) - devuelto
    cantidad = a_cantidad(cantidad if cantidad is not None else maximo)
    if cantidad <= CERO or cantidad > maximo:
        raise CantidadInvalida(
            f"De ese consumo quedan {maximo} por devolver."
        )

    _aplicar(movimiento.material, movimiento.lote, movimiento.almacen, cantidad)
    return _movimiento(
        tipo=MovimientoMaterial.Tipo.DEVOLUCION,
        material=movimiento.material,
        lote=movimiento.lote,
        almacen=movimiento.almacen,
        cantidad=cantidad,
        costo_unitario=movimiento.costo_unitario,
        orden=movimiento.orden,
        motivo=motivo,
        comentario=comentario[:255] or f"devolución del movimiento {movimiento.pk}",
        actor_username=nombre_de(actor),
        anula_a=movimiento,
    )


@transaction.atomic(using=BASE)
def ajustar(*, material, cantidad, actor, motivo, almacen=None, lote=None, comentario=""):
    """Corrección explícita, con motivo obligatorio.

    Es para cuadrar con el conteo físico. Que exija motivo no es formalismo:
    un inventario que se ajusta sin explicar por qué deja de ser una medición
    y pasa a ser una opinión.
    """
    if motivo is None:
        raise MotivoRequerido("Un ajuste de inventario exige indicar el motivo.")

    cantidad = a_cantidad(cantidad)
    if cantidad == CERO:
        raise CantidadInvalida("Un ajuste de cero no ajusta nada.")

    almacen = almacen or almacen_principal()
    _aplicar(material, lote, almacen, cantidad)
    return _movimiento(
        tipo=MovimientoMaterial.Tipo.AJUSTE,
        material=material,
        lote=lote,
        almacen=almacen,
        cantidad=cantidad,
        costo_unitario=lote.costo_unitario if lote else CERO,
        motivo=motivo,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
    )


@transaction.atomic(using=BASE)
def trasladar(*, material, lote, origen, destino, cantidad, actor, comentario=""):
    """Mueve material de un almacén a otro, en dos apuntes emparejados.

    Dos movimientos y no uno para que cada almacén tenga su propio historial
    completo: mirando sólo el de destino se ve de dónde vino.
    """
    if origen.pk == destino.pk:
        raise ErrorDeDominio("El origen y el destino son el mismo almacén.")

    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Un traslado tiene que ser de más de cero.")

    pareja = uuid.uuid4()
    _aplicar(material, lote, origen, -cantidad)
    _aplicar(material, lote, destino, cantidad)
    costo = lote.costo_unitario if lote else CERO

    salida = _movimiento(
        tipo=MovimientoMaterial.Tipo.TRASLADO_SALIDA,
        material=material, lote=lote, almacen=origen,
        cantidad=-cantidad, costo_unitario=costo,
        comentario=comentario[:255], actor_username=nombre_de(actor), traslado=pareja,
    )
    entrada = _movimiento(
        tipo=MovimientoMaterial.Tipo.TRASLADO_ENTRADA,
        material=material, lote=lote, almacen=destino,
        cantidad=cantidad, costo_unitario=costo,
        comentario=comentario[:255], actor_username=nombre_de(actor), traslado=pareja,
    )
    return salida, entrada


@transaction.atomic(using=BASE)
def registrar_merma(*, material, lote, cantidad, actor, motivo, almacen=None, comentario=""):
    """Material que se perdió: recorte inservible, pieza mal cortada, daño.

    Va como tipo propio y no como ajuste porque son dos cosas distintas: la
    merma es una pérdida que se puede medir y reducir, el ajuste es que la
    cuenta estaba mal. Mezclarlas hace imposible saber cuánto se está tirando.
    """
    if motivo is None:
        raise MotivoRequerido("Una merma exige indicar el motivo.")
    cantidad = a_cantidad(cantidad)
    if cantidad <= CERO:
        raise CantidadInvalida("Una merma tiene que ser de más de cero.")

    almacen = almacen or almacen_principal()
    _aplicar(material, lote, almacen, -cantidad)
    return _movimiento(
        tipo=MovimientoMaterial.Tipo.MERMA,
        material=material,
        lote=lote,
        almacen=almacen,
        cantidad=-cantidad,
        costo_unitario=lote.costo_unitario if lote else CERO,
        motivo=motivo,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
    )


# ================================================= lista de materiales
#
# Propone. No descuenta.

def consumo_sugerido(pieza, cantidad_piezas):
    """Qué material haría falta, según la lista vigente de la pieza.

    **Es una propuesta.** Una persona la revisa y confirma antes de que salga
    nada del almacén. Se automatizará cuando `comparar_consumo` demuestre que
    lo propuesto y lo real coinciden; hacerlo antes vacía el inventario en una
    semana sin que nadie lo note.
    """
    lista = (
        ListaMateriales.objects.using(BASE)
        .filter(pieza=pieza, vigente=True)
        .prefetch_related("renglones__material")
        .first()
    )
    if lista is None:
        return []

    cantidad_piezas = a_cantidad(cantidad_piezas)
    return [
        {
            "material": renglon.material,
            "cantidad": (renglon.cantidad_con_merma * cantidad_piezas).quantize(PRECISION),
            "lista": lista,
        }
        for renglon in lista.renglones.all()
    ]


def comparar_consumo(orden):
    """Lo que la lista decía frente a lo que de verdad se consumió.

    Es el informe que decide si se puede automatizar el descuento, y de paso
    dice dónde está mal una lista o dónde se está gastando de más.
    """
    if orden.pieza_id is None:
        return []

    previsto = {
        fila["material"].pk: fila["cantidad"]
        for fila in consumo_sugerido(orden.pieza, orden.cantidad_objetivo)
    }
    real = {}
    for movimiento in MovimientoMaterial.objects.using(BASE).filter(
        orden=orden, tipo=MovimientoMaterial.Tipo.CONSUMO
    ):
        real[movimiento.material_id] = real.get(movimiento.material_id, CERO) + abs(
            movimiento.cantidad
        )

    filas = []
    for material_id in sorted(set(previsto) | set(real)):
        material = Material.objects.using(BASE).get(pk=material_id)
        esperado = previsto.get(material_id, CERO)
        gastado = real.get(material_id, CERO)
        filas.append(
            {
                "material": material,
                "previsto": esperado,
                "real": gastado,
                "diferencia": (gastado - esperado).quantize(PRECISION),
            }
        )
    return filas


# ==================================================== caché y verificación

def recalcular_existencias(material=None):
    """Reconstruye las existencias desde los movimientos.

    Es lo que hace que «la verdad son los movimientos» sea una propiedad
    comprobable y no una frase. Devuelve cuántas filas cambió.
    """
    consulta = MovimientoMaterial.objects.using(BASE)
    if material is not None:
        consulta = consulta.filter(material=material)

    # Se reconstruyen los dos números por separado, de dos conjuntos de
    # movimientos que no se mezclan: el estante de los que mueven material y
    # la promesa de los que sólo la apalabran.
    fisico, promesa = {}, {}
    for movimiento in consulta.iterator(chunk_size=1000):
        clave = (movimiento.material_id, movimiento.lote_id, movimiento.almacen_id)
        destino = promesa if movimiento.tipo in TIPOS_DE_PROMESA else fisico
        destino[clave] = destino.get(clave, CERO) + movimiento.cantidad

    corregidas = 0
    for clave in set(fisico) | set(promesa):
        material_id, lote_id, almacen_id = clave
        fila, _ = Existencia.objects.using(BASE).get_or_create(
            material_id=material_id,
            lote_id=lote_id,
            almacen_id=almacen_id,
            defaults={"cantidad": CERO, "comprometido": CERO},
        )
        cantidad = fisico.get(clave, CERO)
        apartado = promesa.get(clave, CERO)
        if fila.cantidad != cantidad or fila.comprometido != apartado:
            fila.cantidad = cantidad
            fila.comprometido = apartado
            fila.save(
                using=BASE,
                update_fields=["cantidad", "comprometido", "actualizado_en"],
            )
            corregidas += 1
    return corregidas


def descuadres():
    """Dónde la caché y los movimientos no dicen lo mismo.

    Devuelve una lista de (existencia, cantidad_segun_movimientos). Vacía es
    lo que se espera; cualquier cosa distinta es que alguien escribió por un
    camino que no pasa por el servicio.
    """
    suma = {}
    for movimiento in MovimientoMaterial.objects.using(BASE).iterator(chunk_size=1000):
        if movimiento.tipo in TIPOS_DE_PROMESA:
            # No tocan el estante: contarlos aquí inventaría un descuadre.
            continue
        clave = (movimiento.material_id, movimiento.lote_id, movimiento.almacen_id)
        suma[clave] = suma.get(clave, CERO) + movimiento.cantidad

    encontrados = []
    for fila in Existencia.objects.using(BASE).select_related("material", "lote", "almacen"):
        clave = (fila.material_id, fila.lote_id, fila.almacen_id)
        esperado = suma.pop(clave, CERO)
        if fila.cantidad != esperado:
            encontrados.append((fila, esperado))

    # Lo que hay en los movimientos y no tiene fila de existencia.
    for (material_id, lote_id, almacen_id), cantidad in suma.items():
        if cantidad != CERO:
            encontrados.append(
                (
                    Existencia(
                        material_id=material_id, lote_id=lote_id,
                        almacen_id=almacen_id, cantidad=CERO,
                    ),
                    cantidad,
                )
            )
    return encontrados
