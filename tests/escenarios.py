"""Constructores de escenarios de negocio para los tests.

Montar un pedido con su orden de producción a mano son treinta líneas que se
repetirían en cada test. Aquí están una sola vez y con nombres que dicen qué
representan en el taller.
"""

from django.utils import timezone

from catalogos.models import (
    HerrOrdenItem,
    HerrOrdenProduccion,
    HerrPiezaCatalogo,
    LogisticaStock,
    PedidoProduccion,
    PedidoProduccionItem,
)
from core import estados


def crear_pieza(nombre="Marco de prueba", peso_kg=10.0):
    return HerrPiezaCatalogo.objects.create(nombre=nombre, peso_kg=peso_kg, activo=True)


def crear_pedido(folio="ORD-90001", cliente="Cliente de prueba"):
    return PedidoProduccion.objects.create(
        folio=folio,
        cliente=cliente,
        telefono="9990000000",
        fecha_compromiso=timezone.localdate(),
        estado="Activa",
    )


def crear_linea_de_pedido(pedido, pieza, cantidad=10):
    return PedidoProduccionItem.objects.create(
        pedido=pedido,
        producto=pieza,
        cantidad_total=cantidad,
        apartado=0,
        enviado=0,
        estado_herreria="Pendiente",
    )


def crear_orden_de_herreria(pieza, cantidad=10, item_pedido=None, codigo="H-90001"):
    """Orden grande: la que avanza por contadores en vez de por etapas."""
    orden = HerrOrdenProduccion.objects.create(
        codigo=codigo,
        pieza_no=1,
        total_piezas=cantidad,
        cantidad_objetivo=cantidad,
        es_op=cantidad >= 2,
        es_individual=cantidad < 2,
        nombre=codigo,
        descripcion=pieza.nombre,
        fecha_compromiso=timezone.localdate(),
        prioridad=3,
        peso_kg=float(pieza.peso_kg or 0) * cantidad,
        ultimo_cambio=timezone.now(),
        estado_etapa=estados.SOLDADURA,
        estado="Abierta",
    )
    HerrOrdenItem.objects.create(
        orden=orden,
        etapa="Corte",
        pieza=pieza,
        pieza_custom_nombre="",
        pieza_custom_peso_kg=0.0,
        cantidad_requerida=cantidad,
    )
    if item_pedido is not None:
        item_pedido.orden_herreria = orden
        item_pedido.estado_herreria = "En producción"
        item_pedido.save(update_fields=["orden_herreria", "estado_herreria"])
    return orden


def pedido_completo_de_venta(cantidad=10, peso_kg=10.0):
    """El escenario habitual: pedido de ventas ya aceptado y en producción.

    Devuelve (pedido, linea, orden, pieza).
    """
    pieza = crear_pieza(peso_kg=peso_kg)
    pedido = crear_pedido()
    linea = crear_linea_de_pedido(pedido, pieza, cantidad)
    orden = crear_orden_de_herreria(pieza, cantidad, item_pedido=linea)
    return pedido, linea, orden, pieza


def stock_de(pieza):
    """Existencia actual de una pieza, o cero si nunca se creó la fila."""
    fila = LogisticaStock.objects.filter(producto=pieza).first()
    return int(fila.stock or 0) if fila else 0
