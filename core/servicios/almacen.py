"""Movimientos de almacén de producto terminado.

Es donde está el dinero del sistema y donde más se nota la duplicación: el
almacén de herrería y el de Corta hacen lo mismo con dos juegos de modelos y
dos copias del código, que además ya divergieron. Este módulo los pone tras
una interfaz común sin fusionar todavía las tablas, que es trabajo de la
unificación del núcleo.

El material recorre tres situaciones y cada operación es un salto entre dos:

    producción --entrada--> DISPONIBLE --apartar--> APARTADO --enviar--> ENVIADO
                                 ^                      |
                                 +--revertir_a_stock----+

    (y revertir_a_apartado devuelve de ENVIADO a APARTADO)

Cada salto deja constancia en la tabla de movimientos con el tipo que le
corresponde. Que el tipo diga a dónde fue el material es lo que permite
reconstruir la existencia a partir del historial: antes las dos reversiones
escribían el mismo tipo y esa reconstrucción era imposible.

Lo que este módulo **todavía no** arregla, porque exige cambiar el modelo de
datos: la entrada sigue calculándose como diferencia contra el contador de la
orden, así que dos avances simultáneos que informen del mismo dato lo suman
dos veces. Está documentado con un test en xfail y se resuelve con el libro de
movimientos de la fase siguiente.
"""

from dataclasses import dataclass

from django.db import transaction

from catalogos.models import (
    HerrPiezaCatalogo,
    LaserOrdenProduccion,
    LogisticaMovimiento,
    LogisticaMovimientoCorta,
    LogisticaStock,
    LogisticaStockCorta,
)
from core.excepciones import CantidadInvalida, StockInsuficiente

BASE = "mes"

TIPO_ENTRADA = "stock_in"
TIPO_APARTAR = "apartar"
TIPO_ENVIAR = "enviar"
TIPO_REVERTIR_A_STOCK = "revertir_a_stock"
TIPO_REVERTIR_A_APARTADO = "revertir_a_apartado"
TIPO_AJUSTE = "ajuste"


@dataclass(frozen=True)
class ResultadoMovimiento:
    """Qué pasó, para que la vista pueda decírselo al usuario."""

    cantidad: int
    disponible_antes: int
    disponible_despues: int
    movimiento_id: int | None = None


# ---------------------------------------------------------------- herrería


def _fila_de_stock(pieza):
    """Fila de existencias de una pieza, bloqueada, creándola si no existe.

    El bloqueo es imprescindible: sin él, dos operaciones simultáneas sobre la
    misma pieza leen el mismo valor y una pisa a la otra.
    """
    fila = LogisticaStock.objects.using(BASE).select_for_update().filter(producto=pieza).first()
    if fila:
        return fila
    return LogisticaStock.objects.using(BASE).create(producto=pieza, stock=0)


def _validar_cantidad(cantidad):
    cantidad = int(cantidad or 0)
    if cantidad <= 0:
        raise CantidadInvalida("La cantidad tiene que ser mayor que cero.")
    return cantidad


def _mover(pieza, cantidad, tipo, actor, linea_pedido=None, permitir_negativo=False):
    """Aplica un movimiento sobre la existencia de una pieza de herrería.

    `cantidad` lleva el signo del movimiento: positivo si entra material en el
    disponible, negativo si sale.
    """
    fila = _fila_de_stock(pieza)
    antes = int(fila.stock or 0)
    despues = antes + cantidad

    if despues < 0 and not permitir_negativo:
        raise StockInsuficiente(
            f"No hay suficiente material disponible: hay {antes} y se piden {abs(cantidad)}.",
            disponible=antes,
            solicitado=abs(cantidad),
        )

    fila.stock = despues
    fila.save(update_fields=["stock", "actualizado_en"])

    movimiento = LogisticaMovimiento.objects.using(BASE).create(
        tipo=tipo,
        producto=pieza,
        pedido_item=linea_pedido,
        cantidad=cantidad,
        actor=actor or "",
    )
    return ResultadoMovimiento(abs(cantidad), antes, despues, movimiento.id)


@transaction.atomic(using=BASE)
def registrar_entrada(pieza, cantidad, actor, linea_pedido=None):
    """Producción entrega material terminado al almacén."""
    cantidad = _validar_cantidad(cantidad)
    return _mover(pieza, cantidad, TIPO_ENTRADA, actor, linea_pedido)


@transaction.atomic(using=BASE)
def apartar(pieza, cantidad, actor, linea_pedido=None):
    """Reserva material disponible para un pedido concreto."""
    cantidad = _validar_cantidad(cantidad)
    return _mover(pieza, -cantidad, TIPO_APARTAR, actor, linea_pedido)


@transaction.atomic(using=BASE)
def devolver_al_disponible(pieza, cantidad, actor, linea_pedido=None):
    """El material vuelve al almacén: se libera una reserva o se anula un envío."""
    cantidad = _validar_cantidad(cantidad)
    return _mover(pieza, cantidad, TIPO_REVERTIR_A_STOCK, actor, linea_pedido)


@transaction.atomic(using=BASE)
def registrar_envio(pieza, cantidad, actor, linea_pedido=None):
    """El material sale al cliente.

    Sale del apartado, no del disponible, así que la existencia no cambia: se
    anota el movimiento para el historial y nada más. Sumar este tipo al
    calcular la existencia descuenta dos veces la misma pieza.
    """
    cantidad = _validar_cantidad(cantidad)
    movimiento = LogisticaMovimiento.objects.using(BASE).create(
        tipo=TIPO_ENVIAR,
        producto=pieza,
        pedido_item=linea_pedido,
        cantidad=-cantidad,
        actor=actor or "",
    )
    disponible = int(getattr(_fila_de_stock(pieza), "stock", 0) or 0)
    return ResultadoMovimiento(cantidad, disponible, disponible, movimiento.id)


@transaction.atomic(using=BASE)
def devolver_al_apartado(pieza, cantidad, actor, linea_pedido=None):
    """Se anula un envío y el material vuelve a la reserva, no al almacén."""
    cantidad = _validar_cantidad(cantidad)
    movimiento = LogisticaMovimiento.objects.using(BASE).create(
        tipo=TIPO_REVERTIR_A_APARTADO,
        producto=pieza,
        pedido_item=linea_pedido,
        cantidad=cantidad,
        actor=actor or "",
    )
    disponible = int(getattr(_fila_de_stock(pieza), "stock", 0) or 0)
    return ResultadoMovimiento(cantidad, disponible, disponible, movimiento.id)


def disponible(pieza):
    """Existencia actual de una pieza."""
    fila = LogisticaStock.objects.using(BASE).filter(producto=pieza).first()
    return int(fila.stock or 0) if fila else 0


# -------------------------------------------------------------------- corta
#
# El almacén de Corta identifica el producto por su nombre normalizado en
# lugar de por una clave: no hay catálogo de piezas de Corta equiparable al de
# herrería. Es una diferencia real de modelo, no de código, y por eso las dos
# familias conviven aquí en vez de fusionarse todavía.


def nombre_de_producto(orden: LaserOrdenProduccion) -> str:
    """Nombre con el que una orden de Corta figura en el almacén.

    Va probando de lo más concreto a lo más genérico. Si el nombre cambia
    entre dos operaciones, el material acaba en dos filas distintas: es una
    fragilidad conocida del modelo de Corta.
    """
    pieza = getattr(orden, "corta_pieza", None)
    if pieza and (getattr(pieza, "nombre", "") or "").strip():
        return pieza.nombre.strip()
    for campo in ("descripcion", "nombre", "codigo"):
        valor = (getattr(orden, campo, "") or "").strip()
        if valor:
            return valor
    return ""


def _fila_de_stock_corta(producto):
    clave = (producto or "").strip().upper()
    fila = (
        LogisticaStockCorta.objects.using(BASE)
        .select_for_update()
        .filter(producto_normalizado=clave)
        .first()
    )
    if fila:
        return fila
    return LogisticaStockCorta.objects.using(BASE).create(producto=(producto or "").strip(), stock=0)


def _mover_corta(producto, cantidad, tipo, actor, orden=None, permitir_negativo=False):
    fila = _fila_de_stock_corta(producto)
    antes = int(fila.stock or 0)
    despues = antes + cantidad

    if despues < 0 and not permitir_negativo:
        raise StockInsuficiente(
            f"No hay suficiente material disponible: hay {antes} y se piden {abs(cantidad)}.",
            disponible=antes,
            solicitado=abs(cantidad),
        )

    fila.stock = despues
    fila.save(update_fields=["stock", "actualizado_en"])

    movimiento = LogisticaMovimientoCorta.objects.using(BASE).create(
        tipo=tipo,
        producto=producto,
        orden=orden,
        cantidad=cantidad,
        actor=actor or "",
    )
    return ResultadoMovimiento(abs(cantidad), antes, despues, movimiento.id)


@transaction.atomic(using=BASE)
def registrar_entrada_corta(producto, cantidad, actor, orden=None):
    cantidad = _validar_cantidad(cantidad)
    return _mover_corta(producto, cantidad, TIPO_ENTRADA, actor, orden)


@transaction.atomic(using=BASE)
def apartar_corta(producto, cantidad, actor, orden=None):
    cantidad = _validar_cantidad(cantidad)
    return _mover_corta(producto, -cantidad, TIPO_APARTAR, actor, orden)


@transaction.atomic(using=BASE)
def devolver_al_disponible_corta(producto, cantidad, actor, orden=None):
    cantidad = _validar_cantidad(cantidad)
    return _mover_corta(producto, cantidad, TIPO_REVERTIR_A_STOCK, actor, orden)


def disponible_corta(producto):
    clave = (producto or "").strip().upper()
    fila = LogisticaStockCorta.objects.using(BASE).filter(producto_normalizado=clave).first()
    return int(fila.stock or 0) if fila else 0


__all__ = [
    "ResultadoMovimiento",
    "registrar_entrada",
    "apartar",
    "devolver_al_disponible",
    "devolver_al_apartado",
    "registrar_envio",
    "disponible",
    "nombre_de_producto",
    "registrar_entrada_corta",
    "apartar_corta",
    "devolver_al_disponible_corta",
    "disponible_corta",
]
