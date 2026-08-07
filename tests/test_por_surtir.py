"""La pantalla del almacenista y el segundo factor de la entrega.

La regla que pidió el taller: **quien produce no confirma que recibió el
material**. Si el operador pudiera, la confirmación no comprobaría nada — sería
él diciendo que le llegó lo que él mismo pidió, y el inventario volvería a ser
un número que nadie contrastó.

De ahí salen las dos mitades de estos tests: que la puerta esté cerrada para
quien no debe pasar, y que al confirmar la entrega ocurra de verdad todo lo que
tiene que ocurrir —baje el estante, se suelte la reserva y salte el aviso de
comprar si se quedó bajo mínimo—.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core import roles
from core.servicios import inventario as servicio
from inventario.models import LoteMaterial, Material, MovimientoMaterial
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()


@pytest.fixture
def almacen():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("sembrar_inventario", verbosity=0, stdout=StringIO())
    roles.asegurar_grupos()
    return servicio.almacen_principal()


@pytest.fixture
def material(almacen):
    material = Material.objects.using(BASE).create(
        codigo="PL-SURTIR", nombre="Placa de prueba", nombre_normalizado="PLACA DE PRUEBA",
        unidad=Material.Unidad.PIEZA, stock_minimo=Decimal("4"),
    )
    lote = LoteMaterial.objects.using(BASE).create(
        material=material, codigo="L-1", colada="C-9001",
        costo_unitario=Decimal("100"), recibido_en=timezone.localdate(),
    )
    servicio.registrar_entrada(lote=lote, cantidad=Decimal("10"), actor=None, almacen=almacen)
    return material


def cuenta(nombre, *grupos):
    persona = Usuario.objects.create_user(nombre, password="x")
    if grupos:
        persona.groups.set(Group.objects.filter(name__in=grupos))
    return persona


def navegador(persona):
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestQuienProduceNoEntrega:
    def test_un_soldador_no_abre_por_surtir(self, almacen):
        cliente = navegador(cuenta("soldador", "soldadura"))
        assert cliente.get(reverse("inventario:por_surtir")).status_code == 302

    def test_un_soldador_no_puede_confirmar_una_entrega(self, material):
        """La puerta principal no basta: hay que cerrar también el envío.

        Sin esto, quien conozca la dirección puede mandar el formulario a mano
        aunque no vea el botón.
        """
        servicio.reservar(material=material, cantidad=Decimal("5"), actor=None)
        cliente = navegador(cuenta("soldador2", "soldadura"))

        respuesta = cliente.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "5",
        })

        assert respuesta.status_code == 302
        assert servicio.existencia(material) == Decimal("10")

    def test_el_almacenista_si(self, almacen):
        cliente = navegador(cuenta("almacenista", roles.ALMACEN))
        assert cliente.get(reverse("inventario:por_surtir")).status_code == 200

    def test_un_administrador_tambien(self, almacen):
        cliente = navegador(cuenta("jefa", "admin_general"))
        assert cliente.get(reverse("inventario:por_surtir")).status_code == 200

    def test_las_existencias_las_ve_cualquiera_con_sesion(self, material):
        """Ventas y logística necesitan saber qué pueden prometer. No poder
        verlo es lo que lleva a prometer material que no hay."""
        cliente = navegador(cuenta("ventas", "pedidos_ventas"))
        assert cliente.get(reverse("inventario:existencias")).status_code == 200

    def test_sin_sesion_no_se_ve_nada(self, material):
        cliente = Client(SERVER_NAME="127.0.0.1")
        assert cliente.get(reverse("inventario:existencias")).status_code == 302
        assert cliente.get(reverse("inventario:por_surtir")).status_code == 302


class TestConfirmarLaEntrega:
    @pytest.fixture
    def almacenista(self, almacen):
        return navegador(cuenta("marco", roles.ALMACEN))

    def test_baja_el_estante_y_suelta_la_reserva(self, almacenista, material):
        servicio.reservar(material=material, cantidad=Decimal("6"), actor=None)

        almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "6",
        })

        assert servicio.existencia(material) == Decimal("4")
        assert servicio.comprometido(material) == Decimal("0")

    def test_queda_escrito_quien_entrego(self, almacenista, material):
        """Sin el nombre, la confirmación no comprueba nada: es un número que
        cambió sin responsable."""
        servicio.reservar(material=material, cantidad=Decimal("2"), actor=None)

        almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "2",
        })

        consumo = MovimientoMaterial.objects.using(BASE).filter(
            tipo=MovimientoMaterial.Tipo.CONSUMO
        ).first()
        assert consumo.actor_username == "marco"

    def test_avisa_de_comprar_si_queda_en_el_minimo(self, almacenista, material):
        """El mínimo del material es 4 y quedan 4: con «≤» ya es motivo de
        compra, porque el mínimo es lo que cubre lo que tarda en llegar el
        pedido."""
        servicio.reservar(material=material, cantidad=Decimal("6"), actor=None)

        respuesta = almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "6",
        }, follow=True)

        avisos = [str(m) for m in respuesta.context["messages"]]
        assert any("Comprar" in a for a in avisos)

    def test_no_avisa_si_todavia_sobra(self, almacenista, material):
        servicio.reservar(material=material, cantidad=Decimal("2"), actor=None)

        respuesta = almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "2",
        }, follow=True)

        avisos = [str(m) for m in respuesta.context["messages"]]
        assert not any("Comprar" in a for a in avisos)

    def test_dos_pulsaciones_no_descuentan_dos_veces(self, almacenista, material):
        """El doble clic y el reintento de una red de taller son lo mismo para
        el servidor."""
        servicio.reservar(material=material, cantidad=Decimal("3"), actor=None)
        datos = {"material": material.pk, "cantidad": "3", "clave": "e-1"}

        almacenista.post(reverse("inventario:entregar"), datos)
        almacenista.post(reverse("inventario:entregar"), datos)

        assert servicio.existencia(material) == Decimal("7")

    def test_entregar_mas_de_lo_que_hay_no_deja_el_almacen_en_negativo(
        self, almacenista, material
    ):
        respuesta = almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "50",
        }, follow=True)

        assert servicio.existencia(material) == Decimal("10")
        avisos = [str(m) for m in respuesta.context["messages"]]
        assert any("suficiente" in a.lower() for a in avisos)

    def test_una_cantidad_que_no_es_numero_no_revienta(self, almacenista, material):
        respuesta = almacenista.post(reverse("inventario:entregar"), {
            "material": material.pk, "cantidad": "cinco",
        }, follow=True)

        assert respuesta.status_code == 200
        assert servicio.existencia(material) == Decimal("10")

    def test_un_material_que_no_existe_tampoco(self, almacenista):
        respuesta = almacenista.post(reverse("inventario:entregar"), {
            "material": "999999", "cantidad": "1",
        }, follow=True)

        assert respuesta.status_code == 200


class TestLiberarSinEntregar:
    @pytest.fixture
    def almacenista(self, almacen):
        return navegador(cuenta("marco2", roles.ALMACEN))

    def test_devuelve_lo_disponible_sin_mover_el_estante(self, almacenista, material):
        servicio.reservar(material=material, cantidad=Decimal("4"), actor=None)

        almacenista.post(reverse("inventario:liberar"), {
            "material": material.pk, "cantidad": "4",
        })

        assert servicio.comprometido(material) == Decimal("0")
        assert servicio.existencia(material) == Decimal("10")
        assert servicio.disponible(material) == Decimal("10")


class TestLaPantallaDiceLoQueHay:
    @pytest.fixture
    def almacenista(self, almacen):
        return navegador(cuenta("marco3", roles.ALMACEN))

    def test_lo_apartado_aparece_en_por_surtir(self, almacenista, material):
        servicio.reservar(material=material, cantidad=Decimal("7"), actor=None)

        pagina = almacenista.get(reverse("inventario:por_surtir")).content.decode()

        assert "PL-SURTIR" in pagina
        assert "C-9001" in pagina  # la colada de la que va a salir

    def test_sin_nada_apartado_lo_dice(self, almacenista, material):
        pagina = almacenista.get(reverse("inventario:por_surtir")).content.decode()
        assert "Nada por surtir" in pagina

    def test_las_existencias_separan_lo_apartado_de_lo_disponible(
        self, almacenista, material
    ):
        """Las tres columnas son el motivo del módulo entero."""
        servicio.reservar(material=material, cantidad=Decimal("3"), actor=None)

        pagina = almacenista.get(reverse("inventario:existencias")).content.decode()

        assert "En el estante" in pagina
        assert "Apartado" in pagina
        assert "Disponible" in pagina
