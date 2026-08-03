"""Tests del servicio de almacén.

Comprueban las reglas directamente, sin montar una petición HTTP. Esa es
justamente la ventaja de sacar la lógica de las vistas: una regla de negocio
se puede probar en dos líneas.
"""

import pytest

from catalogos.models import LogisticaMovimiento
from core.excepciones import CantidadInvalida, StockInsuficiente
from core.servicios import almacen
from tests import escenarios

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


class TestEntradaYSalida:
    def test_la_entrada_aumenta_la_existencia(self):
        pieza = escenarios.crear_pieza()
        resultado = almacen.registrar_entrada(pieza, 10, actor="operario")

        assert almacen.disponible(pieza) == 10
        assert resultado.disponible_antes == 0
        assert resultado.disponible_despues == 10

    def test_apartar_reserva_material_disponible(self):
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="operario")

        almacen.apartar(pieza, 4, actor="logística")

        assert almacen.disponible(pieza) == 6

    def test_no_se_puede_apartar_mas_de_lo_que_hay(self):
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 3, actor="operario")

        with pytest.raises(StockInsuficiente) as excepcion:
            almacen.apartar(pieza, 5, actor="logística")

        assert excepcion.value.detalles["disponible"] == 3
        assert excepcion.value.detalles["solicitado"] == 5
        assert almacen.disponible(pieza) == 3, "un intento fallido no debe alterar la existencia"

    def test_devolver_al_disponible_libera_la_reserva(self):
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="operario")
        almacen.apartar(pieza, 4, actor="logística")

        almacen.devolver_al_disponible(pieza, 4, actor="logística")

        assert almacen.disponible(pieza) == 10

    @pytest.mark.parametrize("cantidad", [0, -1, None])
    def test_las_cantidades_no_positivas_se_rechazan(self, cantidad):
        pieza = escenarios.crear_pieza()
        with pytest.raises(CantidadInvalida):
            almacen.registrar_entrada(pieza, cantidad, actor="operario")


class TestEnvio:
    def test_enviar_no_toca_la_existencia(self):
        """El envío sale del apartado, que ya se descontó al reservar.

        Es la distinción que hacía imposible reconstruir el stock: si se cuenta
        el envío como salida del disponible, la pieza se descuenta dos veces.
        """
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="operario")
        almacen.apartar(pieza, 4, actor="logística")
        disponible_antes = almacen.disponible(pieza)

        almacen.registrar_envio(pieza, 4, actor="logística")

        assert almacen.disponible(pieza) == disponible_antes == 6

    def test_devolver_al_apartado_tampoco_la_toca(self):
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="operario")
        almacen.apartar(pieza, 4, actor="logística")
        almacen.registrar_envio(pieza, 4, actor="logística")

        almacen.devolver_al_apartado(pieza, 4, actor="logística")

        assert almacen.disponible(pieza) == 6


class TestReconstruccionDelHistorial:
    def test_la_existencia_se_puede_reconstruir_desde_los_movimientos(self):
        """La propiedad que el registro ambiguo impedía cumplir.

        Sumando los movimientos que afectan al disponible se tiene que obtener
        exactamente la existencia guardada. Antes, las dos clases de reversión
        escribían el mismo tipo y no había forma de saber cuáles contar.
        """
        from django.db.models import Sum

        from core.constantes import TIPOS_MOVIMIENTO_DISPONIBLE

        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="a")
        almacen.apartar(pieza, 6, actor="b")
        almacen.registrar_envio(pieza, 4, actor="c")
        almacen.devolver_al_apartado(pieza, 4, actor="d")
        almacen.devolver_al_disponible(pieza, 2, actor="e")
        almacen.registrar_entrada(pieza, 5, actor="f")

        suma = (
            LogisticaMovimiento.objects.filter(
                producto=pieza, tipo__in=TIPOS_MOVIMIENTO_DISPONIBLE
            ).aggregate(total=Sum("cantidad"))["total"]
            or 0
        )
        assert suma == almacen.disponible(pieza)

    def test_cada_operacion_deja_su_tipo_propio(self):
        pieza = escenarios.crear_pieza()
        almacen.registrar_entrada(pieza, 10, actor="a")
        almacen.apartar(pieza, 5, actor="b")
        almacen.registrar_envio(pieza, 5, actor="c")
        almacen.devolver_al_apartado(pieza, 2, actor="d")
        almacen.devolver_al_disponible(pieza, 1, actor="e")

        tipos = list(
            LogisticaMovimiento.objects.filter(producto=pieza)
            .order_by("id")
            .values_list("tipo", flat=True)
        )
        assert tipos == [
            "stock_in",
            "apartar",
            "enviar",
            "revertir_a_apartado",
            "revertir_a_stock",
        ]


class TestAlmacenDeCorta:
    def test_funciona_igual_identificando_por_nombre(self):
        almacen.registrar_entrada_corta("CAJÓN D04", 8, actor="operario")
        assert almacen.disponible_corta("CAJÓN D04") == 8

        almacen.apartar_corta("CAJÓN D04", 3, actor="logística")
        assert almacen.disponible_corta("CAJÓN D04") == 5

    def test_el_nombre_no_distingue_mayusculas(self):
        almacen.registrar_entrada_corta("Cajón D04", 8, actor="operario")
        assert almacen.disponible_corta("CAJÓN D04") == 8
        assert almacen.disponible_corta("cajón d04") == 8

    def test_tampoco_se_puede_apartar_de_mas(self):
        almacen.registrar_entrada_corta("PLACA A36", 2, actor="operario")
        with pytest.raises(StockInsuficiente):
            almacen.apartar_corta("PLACA A36", 3, actor="logística")

    def test_el_nombre_de_producto_sale_de_la_orden(self):
        from django.utils import timezone

        from catalogos.models import LaserOrdenProduccion

        orden = LaserOrdenProduccion.objects.create(
            codigo="L-1",
            pieza_no=1,
            total_piezas=1,
            cantidad_objetivo=1,
            nombre="nombre de la orden",
            descripcion="descripción de la pieza",
            fecha_compromiso=timezone.localdate(),
            prioridad=3,
            peso_kg=1,
            ultimo_cambio=timezone.now(),
            estado_etapa="Corte",
            estado="Abierta",
        )
        # La descripción manda sobre el nombre de la orden.
        assert almacen.nombre_de_producto(orden) == "descripción de la pieza"
