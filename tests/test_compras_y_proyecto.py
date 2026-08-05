"""Lo que falta comprar, lo que se surte por obra y lo que se puede entregar.

Tres pantallas que comparten la misma decisión de fondo que la bandeja de
despacho: **la lista se deduce, y sólo la respuesta se guarda**. Un aviso que
hay que acordarse de disparar se olvida de dispararse, y el fallo es invisible
porque la pantalla vacía se lee como «no hay nada que hacer».
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    HerrPiezaCatalogo,
    LogisticaStock,
    LogisticaStockCorta,
    Proyecto,
)
from catalogos.terminado import disponible_para_entrega
from core import roles
from core.excepciones import StockInsuficiente
from core.servicios import inventario as servicio
from inventario.compras import por_comprar
from inventario.models import (
    Almacen,
    LoteMaterial,
    Material,
    Proveedor,
    SeguimientoCompra,
)

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

BASE = "mes"
Usuario = get_user_model()


@pytest.fixture
def almacen():
    return Almacen.objects.using(BASE).create(
        nombre="Principal", es_principal=True, activo=True
    )


@pytest.fixture
def almacenista(almacen):
    roles.asegurar_grupos()
    persona = Usuario.objects.create_user("mateo", password="x")
    persona.groups.set(Group.objects.filter(name=roles.ALMACEN))
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def material(codigo="PL-3/8", minimo="10", unidad=Material.Unidad.KILOGRAMO):
    return Material.objects.using(BASE).create(
        codigo=codigo, nombre=f"Material {codigo}",
        nombre_normalizado=f"MATERIAL {codigo}".upper(),
        unidad=unidad, stock_minimo=Decimal(minimo),
    )


def meter(item, cantidad, actor=None, lote="L1"):
    lote_obj, _ = LoteMaterial.objects.using(BASE).get_or_create(
        material=item, codigo=lote,
        defaults={"recibido_en": timezone.localdate(), "costo_unitario": Decimal("100")},
    )
    return servicio.registrar_entrada(
        lote=lote_obj, cantidad=Decimal(str(cantidad)), actor=actor
    )


class TestLaListaDeComprasSeDeduce:
    def test_lo_que_baja_del_minimo_aparece_solo(self, almacen):
        item = material(minimo="10")
        meter(item, 4)

        assert item.id in [f["material"].id for f in por_comprar()]

    def test_lo_que_esta_justo_en_el_minimo_tambien(self, almacen):
        """El taller lo pidió con «≤»: el mínimo es lo que cubre el tiempo que
        tarda en llegar el pedido, así que quedarse justo ahí ya es motivo de
        compra. Esta comprobación usaba «<» mientras el aviso de la entrega
        usaba «≤», y un material parado en su mínimo disparaba la alerta y
        luego no salía en la lista.
        """
        item = material(minimo="10")
        meter(item, 10)

        assert item.id in [f["material"].id for f in por_comprar()]

    def test_lo_que_sobra_no_aparece(self, almacen):
        item = material(minimo="10")
        meter(item, 40)

        assert item.id not in [f["material"].id for f in por_comprar()]

    def test_desaparece_solo_al_reponerse(self, almacen):
        """No hay nada que cerrar a mano: la lista se recalcula cada vez."""
        item = material(minimo="10")
        meter(item, 4)
        assert por_comprar()

        meter(item, 50, lote="L2")

        assert not por_comprar()

    def test_ensena_lo_libre_ademas_de_lo_fisico(self, almacen):
        """Material que está en el estante pero comprometido con una orden no
        cubre la siguiente. Comprar mirando sólo el físico llega tarde."""
        item = material(minimo="10")
        meter(item, 8)
        servicio.reservar(material=item, cantidad=Decimal("5"), actor=None)

        fila = por_comprar()[0]

        assert fila["fisico"] == Decimal("8.000000")
        assert fila["disponible"] == Decimal("3.000000")


class TestAnotarLaCompra:
    def test_queda_quien_lo_pidio_y_para_cuando(self, almacenista, almacen):
        item = material(minimo="10")
        meter(item, 2)
        proveedor = Proveedor.objects.using(BASE).create(
            nombre="Aceros SA", nombre_normalizado="ACEROS SA"
        )
        cuando = (timezone.localdate() + timedelta(days=5)).isoformat()

        almacenista.post(reverse("inventario:compras_marcar"), {
            "material": item.id,
            "estado": SeguimientoCompra.Estado.ORDENADO,
            "proveedor": proveedor.id,
            "cantidad_pedida": "100",
            "promesa": cuando,
            "notas": "Confirmado por teléfono",
        })

        seguimiento = SeguimientoCompra.objects.using(BASE).get(material=item)
        assert seguimiento.estado == SeguimientoCompra.Estado.ORDENADO
        assert seguimiento.actor == "mateo"
        assert seguimiento.cantidad_pedida == Decimal("100")
        assert seguimiento.notas == "Confirmado por teléfono"

    def test_anotar_dos_veces_no_duplica(self, almacenista, almacen):
        item = material(minimo="10")
        meter(item, 2)
        datos = {
            "material": item.id,
            "estado": SeguimientoCompra.Estado.SOLICITADO,
            "cantidad_pedida": "50",
        }

        almacenista.post(reverse("inventario:compras_marcar"), datos)
        almacenista.post(reverse("inventario:compras_marcar"), {
            **datos, "estado": SeguimientoCompra.Estado.ORDENADO,
        })

        assert SeguimientoCompra.objects.using(BASE).filter(material=item).count() == 1

    def test_un_estado_inventado_no_se_guarda(self, almacenista, almacen):
        item = material(minimo="10")
        meter(item, 2)

        almacenista.post(reverse("inventario:compras_marcar"), {
            "material": item.id, "estado": "volando",
        })

        assert not SeguimientoCompra.objects.using(BASE).exists()

    def test_quien_no_es_de_almacen_no_puede_anotar(self, almacen):
        roles.asegurar_grupos()
        persona = Usuario.objects.create_user("pepe", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        item = material(minimo="10")
        meter(item, 2)

        cliente.post(reverse("inventario:compras_marcar"), {
            "material": item.id, "estado": SeguimientoCompra.Estado.ORDENADO,
        })

        assert not SeguimientoCompra.objects.using(BASE).exists()

    def test_la_pantalla_se_ve_sin_ser_de_almacen(self, almacen):
        """Ventas y producción necesitan saber qué falta para poder prometer
        fechas. Ver no es lo mismo que mover."""
        persona = Usuario.objects.create_user("ana", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)

        respuesta = cliente.get(reverse("inventario:compras"))

        assert respuesta.status_code == 200
        assert respuesta.context["puede_marcar"] is False


class TestDespachoPorProyecto:
    @pytest.fixture
    def obra(self):
        return Proyecto.objects.using(BASE).create(
            nombre="TORRE NORTE", activo=True
        )

    def test_junta_lo_apartado_de_una_obra(self, almacen, obra):
        uno, dos = material("A", minimo="0"), material("B", minimo="0")
        meter(uno, 100)
        meter(dos, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None, proyecto=obra)
        servicio.reservar(material=dos, cantidad=Decimal("20"), actor=None, proyecto=obra)

        grupos = servicio.proyectos_por_surtir()

        assert len(grupos) == 1
        assert grupos[0]["materiales"] == 2

    def test_entrega_todo_de_una_vez(self, almacenista, almacen, obra):
        uno, dos = material("A", minimo="0"), material("B", minimo="0")
        meter(uno, 100)
        meter(dos, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None, proyecto=obra)
        servicio.reservar(material=dos, cantidad=Decimal("20"), actor=None, proyecto=obra)

        almacenista.post(reverse("inventario:entregar_proyecto"), {"proyecto": obra.id})

        assert servicio.existencia(uno) == Decimal("70.000000")
        assert servicio.existencia(dos) == Decimal("80.000000")
        assert not servicio.proyectos_por_surtir()

    def test_lo_que_falla_no_impide_entregar_lo_demas(self, almacen, obra, monkeypatch):
        """Negarse entero porque falla un renglón deja al taller sin los otros
        trece, y el almacenista acaba entregando a mano fuera del sistema.

        El fallo se provoca a la fuerza porque las restricciones de la base
        hacen muy difícil llegar a él de forma natural: no se puede dejar más
        comprometido del que hay. La rama existe igual, para el día que se
        llegue por un camino que hoy no se ve.
        """
        uno, dos = material("A", minimo="0"), material("B", minimo="0")
        meter(uno, 100)
        meter(dos, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None, proyecto=obra)
        servicio.reservar(material=dos, cantidad=Decimal("20"), actor=None, proyecto=obra)

        real = servicio.entregar

        def falla_solo_el_segundo(*, material, **resto):
            if material.codigo == "B":
                raise StockInsuficiente("No alcanza.")
            return real(material=material, **resto)

        monkeypatch.setattr(servicio, "entregar", falla_solo_el_segundo)

        entregados, faltantes, _ = servicio.entregar_proyecto(
            proyecto=obra, actor=None
        )

        assert len(entregados) == 1
        assert len(faltantes) == 1
        assert servicio.existencia(uno) == Decimal("70.000000")

    def test_reintentar_no_entrega_el_doble(self, almacenista, almacen, obra):
        """Con la red del taller, el segundo envío llega. Cada renglón lleva
        su clave de idempotencia."""
        uno = material("A", minimo="0")
        meter(uno, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None, proyecto=obra)

        almacenista.post(reverse("inventario:entregar_proyecto"), {"proyecto": obra.id})
        almacenista.post(reverse("inventario:entregar_proyecto"), {"proyecto": obra.id})

        assert servicio.existencia(uno) == Decimal("70.000000")

    def test_lo_apartado_sin_proyecto_no_sale_aqui(self, almacen, obra):
        """La manufactura en serie aparta contra la orden, no contra la obra.
        Mezclarlas haría que el almacenista entregara de más."""
        uno = material("A", minimo="0")
        meter(uno, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None)

        assert not servicio.proyectos_por_surtir()

    def test_quien_no_es_de_almacen_no_despacha(self, almacen, obra):
        persona = Usuario.objects.create_user("ana", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        uno = material("A", minimo="0")
        meter(uno, 100)
        servicio.reservar(material=uno, cantidad=Decimal("30"), actor=None, proyecto=obra)

        cliente.post(reverse("inventario:entregar_proyecto"), {"proyecto": obra.id})

        assert servicio.existencia(uno) == Decimal("100.000000")


class TestProductoTerminado:
    def test_junta_las_dos_lineas(self):
        pieza = HerrPiezaCatalogo.objects.using(BASE).create(
            nombre="Andamio", nombre_normalizado="ANDAMIO", peso_kg=18.0
        )
        LogisticaStock.objects.using(BASE).create(producto=pieza, stock=12)
        LogisticaStockCorta.objects.using(BASE).create(
            producto="Placa base", stock=40
        )

        filas = disponible_para_entrega()

        assert {f.linea_nombre for f in filas} == {"Herrería", "Corta.mx"}

    def test_lo_agotado_no_se_ofrece(self):
        pieza = HerrPiezaCatalogo.objects.using(BASE).create(
            nombre="Ancla", nombre_normalizado="ANCLA", peso_kg=2.0
        )
        LogisticaStock.objects.using(BASE).create(producto=pieza, stock=0)

        assert not disponible_para_entrega()

    def test_lo_de_corta_no_finge_tener_peso(self):
        """Corta guarda el producto como texto libre, sin ficha. Un cero se
        leería como «no pesa»; vacío dice que no se sabe."""
        LogisticaStockCorta.objects.using(BASE).create(producto="Tapa", stock=5)

        assert disponible_para_entrega()[0].peso_kg is None

    def test_la_suma_de_kilos_avisa_de_lo_que_no_cuenta(self, client):
        persona = Usuario.objects.create_user("ana", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        LogisticaStockCorta.objects.using(BASE).create(producto="Tapa", stock=5)

        respuesta = cliente.get(reverse("catalogos:producto_terminado"))

        assert respuesta.context["resumen"]["sin_peso"] == 1

    def test_se_puede_buscar(self):
        for nombre in ("Andamio chico", "Ancla J"):
            pieza = HerrPiezaCatalogo.objects.using(BASE).create(
                nombre=nombre, nombre_normalizado=nombre.upper(), peso_kg=1.0
            )
            LogisticaStock.objects.using(BASE).create(producto=pieza, stock=5)

        assert len(disponible_para_entrega("andamio")) == 1
