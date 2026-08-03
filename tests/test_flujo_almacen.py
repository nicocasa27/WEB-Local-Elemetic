"""Flujo del material desde que producción lo termina hasta que sale al cliente.

Es la superficie donde un fallo cuesta dinero: piezas que existen en el
sistema y no en la nave, o al revés. Estos tests se escriben **antes** de
tocar el código para dejar constancia de cómo se comporta hoy, incluidos sus
defectos, y poder cambiarlo sabiendo qué se rompe.

Los que documentan un defecto conocido van marcados con `xfail(strict=True)`:
fallan a propósito mientras el defecto siga ahí, y avisarán en cuanto quede
corregido, en vez de quedarse en verde para siempre sin que nadie los mire.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    HerrOrdenProduccion,
    LogisticaAcuseEntrega,
    LogisticaMovimiento,
    LogisticaStock,
    PedidoProduccionItem,
)
from core import constantes, estados
from tests import escenarios

pytestmark = [pytest.mark.django_db(databases=["default", "mes"]), pytest.mark.flujo]


def registrar_avance(cliente, orden, soldadas, pintadas, terminadas, recibido_por="Almacén"):
    """Llama al endpoint que usa la pantalla de control para anotar avance."""
    item = PedidoProduccionItem.objects.filter(orden_herreria=orden).first()
    datos = {
        "cantidad_soldada": soldadas,
        "cantidad_pintada": pintadas,
        "cantidad_terminada": terminadas,
        "recibido_por": recibido_por,
    }
    if item:
        datos["pedido_item_id"] = item.id
    return cliente.post(
        reverse("catalogos:herreria_update_avance_json", args=[orden.id]), datos
    )


class TestEntradaDeMaterial:
    def test_terminar_piezas_las_mete_en_el_almacen(self, cliente_como):
        """El avance de producción es lo que da de alta material en almacén."""
        cliente = cliente_como("admin")
        _, _, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)

        assert escenarios.stock_de(pieza) == 0
        respuesta = registrar_avance(cliente, orden, 5, 5, 5)

        assert respuesta.status_code == 200, respuesta.content
        assert escenarios.stock_de(pieza) == 5

        movimientos = LogisticaMovimiento.objects.filter(producto=pieza)
        assert movimientos.count() == 1
        assert movimientos.first().tipo == "stock_in"
        assert movimientos.first().cantidad == 5

    def test_el_avance_genera_acuse_de_entrega(self, cliente_como):
        """El acuse es el documento que firma quien recibe en almacén."""
        cliente = cliente_como("admin")
        _, linea, orden, _ = escenarios.pedido_completo_de_venta(cantidad=10)

        registrar_avance(cliente, orden, 4, 4, 4, recibido_por="Juan Pérez")

        acuses = LogisticaAcuseEntrega.objects.filter(pedido_item=linea)
        assert acuses.count() == 1
        assert acuses.first().cantidad == 4

    def test_sin_indicar_quien_recibe_no_se_registra_entrega(self, cliente_como):
        """En un pedido de ventas el acuse es obligatorio."""
        cliente = cliente_como("admin")
        _, _, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)

        respuesta = registrar_avance(cliente, orden, 3, 3, 3, recibido_por="")

        assert respuesta.status_code == 400
        assert escenarios.stock_de(pieza) == 0

    def test_solo_entra_al_almacen_la_diferencia(self, cliente_como):
        """Dos avances seguidos suman lo nuevo, no lo acumulado."""
        cliente = cliente_como("admin")
        _, _, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)

        registrar_avance(cliente, orden, 3, 3, 3)
        assert escenarios.stock_de(pieza) == 3

        registrar_avance(cliente, orden, 7, 7, 7)
        assert escenarios.stock_de(pieza) == 7  # y no 10


class TestCierreDeOrden:
    def test_al_llegar_al_objetivo_la_orden_queda_en_cierre_pendiente(self, cliente_como):
        """Hay una ventana para deshacer el cierre antes de que sea firme."""
        cliente = cliente_como("admin")
        _, _, orden, _ = escenarios.pedido_completo_de_venta(cantidad=6)

        registrar_avance(cliente, orden, 6, 6, 6)

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.CIERRE_PENDIENTE
        assert orden.cierre_pendiente_hasta is not None
        margen = orden.cierre_pendiente_hasta - timezone.now()
        assert 0 < margen.total_seconds() <= constantes.CIERRE_VENTANA_MINUTOS * 60

    def test_bajar_el_contador_reabre_la_orden(self, cliente_como):
        """Corregir un error de dedo dentro de la ventana devuelve la orden a producción."""
        cliente = cliente_como("admin")
        _, _, orden, _ = escenarios.pedido_completo_de_venta(cantidad=6)

        registrar_avance(cliente, orden, 6, 6, 6)
        registrar_avance(cliente, orden, 6, 6, 5)

        orden.refresh_from_db()
        assert orden.estado_etapa != estados.CIERRE_PENDIENTE

    def test_revertir_el_cierre_devuelve_la_orden_a_produccion(self, cliente_como):
        cliente = cliente_como("admin")
        _, _, orden, _ = escenarios.pedido_completo_de_venta(cantidad=6)
        registrar_avance(cliente, orden, 6, 6, 6)

        respuesta = cliente.post(reverse("catalogos:herreria_revertir_cierre", args=[orden.id]))

        # Esta vista redirige a la pantalla de control; no devuelve JSON,
        # aunque el JavaScript que la invoca la trate como si lo hiciera.
        assert respuesta.status_code == 302
        orden.refresh_from_db()
        assert orden.estado_etapa == estados.SOLDADURA
        assert orden.cierre_revertido_en is not None


class TestDefectosConocidos:
    """Comportamientos que hoy son incorrectos y que la reforma debe arreglar.

    Van en `xfail(strict=True)` para que el día que se corrijan el test avise
    en vez de quedarse callado.
    """

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Revertir el cierre no deshace la entrada en almacén ni anula el acuse. "
            "Las piezas siguen contando como disponibles aunque la orden vuelva a "
            "producción, y el acuse firmado queda vivo. Se corrige con el libro de "
            "movimientos de la unificación del núcleo."
        ),
    )
    def test_revertir_el_cierre_deberia_deshacer_la_entrada_en_almacen(self, cliente_como):
        cliente = cliente_como("admin")
        _, linea, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=6)

        registrar_avance(cliente, orden, 6, 6, 6)
        assert escenarios.stock_de(pieza) == 6
        assert LogisticaAcuseEntrega.objects.filter(pedido_item=linea).count() == 1

        cliente.post(reverse("catalogos:herreria_revertir_cierre", args=[orden.id]))

        assert escenarios.stock_de(pieza) == 0, "el material volvió a producción pero sigue en almacén"
        assert not LogisticaAcuseEntrega.objects.filter(
            pedido_item=linea, anulado_en__isnull=True
        ).exists(), "el acuse de entrega sigue vigente"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "El avance manda la cantidad total en vez de la diferencia, así que dos "
            "envíos simultáneos con el mismo valor se aplican dos veces y el almacén "
            "cuenta el doble. Se corrige registrando diferencias y una clave de "
            "idempotencia."
        ),
    )
    def test_dos_avances_identicos_no_deberian_duplicar_el_almacen(self, cliente_como):
        cliente = cliente_como("admin")
        _, _, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)

        # Dos pestañas abiertas que leyeron 0 y envían 5 cada una. Lo correcto
        # sería que la segunda no añadiera nada, porque informa del mismo
        # avance, no de uno nuevo.
        registrar_avance(cliente, orden, 5, 5, 5)
        HerrOrdenProduccion.objects.filter(pk=orden.pk).update(cantidad_terminada=0)
        registrar_avance(cliente, orden, 5, 5, 5)

        assert escenarios.stock_de(pieza) == 5, "el mismo avance entró dos veces en almacén"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "No existe la invariante terminadas <= pintadas <= soldadas, así que se "
            "puede declarar material terminado que nunca se soldó ni se pintó. Se "
            "corrige con una restricción en la base y la validación en el servicio."
        ),
    )
    def test_no_deberia_poder_terminarse_mas_de_lo_que_se_soldo(self, cliente_como):
        cliente = cliente_como("admin")
        _, _, orden, _ = escenarios.pedido_completo_de_venta(cantidad=10)

        respuesta = registrar_avance(cliente, orden, 0, 0, 10)

        assert respuesta.status_code == 400, (
            "aceptó diez piezas terminadas con cero soldadas y cero pintadas"
        )


class TestAlmacenDeCorta:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Una orden de Corta de una sola pieza nunca da de alta material en "
            "almacén, mientras que la de herrería sí. La orden queda sin poder "
            "apartarse ni enviarse: colgada para siempre. Pendiente de decidir con "
            "el taller si esas piezas pasan por almacén o se entregan directas."
        ),
    )
    def test_una_orden_de_corta_individual_deberia_generar_existencia(self, cliente_como):
        from catalogos.models import LaserOrdenProduccion, LogisticaStockCorta

        cliente = cliente_como("admin")
        orden = LaserOrdenProduccion.objects.create(
            codigo="L-90001",
            pieza_no=1,
            total_piezas=1,
            cantidad_objetivo=1,
            nombre="pieza suelta",
            descripcion="pieza suelta",
            fecha_compromiso=timezone.localdate(),
            prioridad=3,
            peso_kg=5.0,
            ultimo_cambio=timezone.now(),
            estado_etapa=estados.PINTURA,
            estado="Abierta",
        )
        cliente.post(
            reverse("catalogos:corte_laser_change_status_json", args=[orden.id]),
            {"estado": estados.TERMINADO, "fecha_operacion": timezone.localdate().isoformat()},
        )
        assert LogisticaStockCorta.objects.filter(stock__gt=0).exists(), (
            "la orden terminó pero no hay existencia que apartar ni enviar"
        )


class TestApartarYEnviarPorLaPantalla:
    """Recorre la logística por las vistas, ya apoyadas en el servicio.

    Comprueba que la extracción del servicio no cambió el comportamiento que
    ve el usuario, que es lo único que garantiza que el refactor fue seguro.
    """

    def test_apartar_descuenta_del_disponible_y_suma_al_apartado(self, cliente_como):
        cliente = cliente_como("admin")
        _, linea, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)
        registrar_avance(cliente, orden, 10, 10, 10)
        assert escenarios.stock_de(pieza) == 10

        cliente.post(
            reverse("catalogos:pedidos_logistica"),
            {"action": "apartar", "item_id": linea.id, "cantidad": 4},
        )

        linea.refresh_from_db()
        assert escenarios.stock_de(pieza) == 6
        assert linea.apartado == 4

    def test_no_se_aparta_mas_de_lo_disponible(self, cliente_como):
        cliente = cliente_como("admin")
        _, linea, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)
        registrar_avance(cliente, orden, 3, 3, 3)

        cliente.post(
            reverse("catalogos:pedidos_logistica"),
            {"action": "apartar", "item_id": linea.id, "cantidad": 9},
        )

        linea.refresh_from_db()
        assert escenarios.stock_de(pieza) == 3, "no debería haber salido material que no existe"
        assert linea.apartado == 0

    def test_liberar_el_apartado_devuelve_el_material_al_almacen(self, cliente_como):
        cliente = cliente_como("admin")
        _, linea, orden, pieza = escenarios.pedido_completo_de_venta(cantidad=10)
        registrar_avance(cliente, orden, 10, 10, 10)
        cliente.post(
            reverse("catalogos:pedidos_logistica"),
            {"action": "apartar", "item_id": linea.id, "cantidad": 4},
        )

        cliente.post(
            reverse("catalogos:pedidos_logistica"),
            {"action": "revertir_apartado", "item_id": linea.id, "cantidad": 4},
        )

        linea.refresh_from_db()
        assert escenarios.stock_de(pieza) == 10
        assert linea.apartado == 0
