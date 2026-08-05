"""El almacén de producto terminado, con sus cuatro situaciones.

La conversación que tiene que poder contestarse por teléfono:

    — ¿Tienes cuarenta andamios?
    — Tengo treinta.
    — Dame esos treinta y fabrícame diez.

Hasta ahora los cuatro números que hacen falta —lo que se puede prometer, lo
que ya tiene dueño, lo que se está fabricando y lo que falta— vivían en cuatro
pantallas distintas y había que sumarlos de cabeza.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.servicios import almacen_terminado as servicio

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

ANDAMIO = "Andamio estándar"


def pieza(nombre=ANDAMIO, peso=12.5):
    from catalogos.models import HerrPiezaCatalogo

    return HerrPiezaCatalogo.objects.create(nombre=nombre, peso_kg=peso)


def en_almacen(la_pieza, cuantas):
    from catalogos.models import LogisticaStock

    return LogisticaStock.objects.create(producto=la_pieza, stock=cuantas)


def pedido(la_pieza, total, apartado=0, enviado=0, estado="Activa"):
    from catalogos.models import PedidoProduccion, PedidoProduccionItem

    cabecera = PedidoProduccion.objects.create(
        folio=f"P-{PedidoProduccion.objects.count() + 1:04d}",
        cliente="CLIENTE",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
    )
    return PedidoProduccionItem.objects.create(
        pedido=cabecera,
        producto=la_pieza,
        cantidad_total=total,
        apartado=apartado,
        enviado=enviado,
    )


def orden(nombre=ANDAMIO, objetivo=10, terminadas=0, estado="Abierta"):
    from catalogos.models import HerrOrdenProduccion

    return HerrOrdenProduccion.objects.create(
        codigo=f"H-{HerrOrdenProduccion.objects.count() + 1:05d}",
        nombre=nombre,
        total_piezas=objetivo,
        cantidad_objetivo=objetivo,
        cantidad_terminada=terminadas,
        fecha_compromiso=timezone.localdate(),
        peso_kg=10.0,
        estado=estado,
    )


def el(renglones, nombre=ANDAMIO):
    return next(r for r in renglones if r.producto == nombre)


class TestLasCuatroSituaciones:
    def test_lo_apartado_ya_no_se_puede_prometer(self):
        """`LogisticaStock.stock` baja al apartar: es el disponible, no lo que
        hay en el estante. Confundirlos hace que el almacenista cuente y
        encuentre más de lo que dice el sistema."""
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        pedido(la_pieza, total=40, apartado=10)

        renglon = el(servicio.foto())

        assert renglon.disponible == 30
        assert renglon.apartado == 10
        assert renglon.en_almacen == 40

    def test_lo_que_se_esta_fabricando_cuenta_lo_que_falta_de_la_orden(self):
        """Una orden de cincuenta con treinta terminadas aporta veinte. Las
        treinta ya están contadas en el almacén."""
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        orden(objetivo=50, terminadas=30)

        assert el(servicio.foto()).en_produccion == 20

    def test_una_orden_cerrada_ya_no_esta_en_produccion(self):
        pieza()
        orden(objetivo=50, estado="Cerrada")

        assert el(servicio.foto()).en_produccion == 0

    def test_lo_pedido_es_lo_que_no_esta_ni_apartado_ni_enviado(self):
        la_pieza = pieza()
        pedido(la_pieza, total=40, apartado=10, enviado=5)

        assert el(servicio.foto()).pedido_pendiente == 25

    def test_un_pedido_cancelado_no_reserva_nada(self):
        """Un pedido cancelado que dejó material apartado es un problema de
        ese pedido, no una reserva que descuente del taller entero."""
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        pedido(la_pieza, total=40, apartado=10, estado="Cancelada")

        assert el(servicio.foto()).apartado == 0


class TestLaConversacionDelTelefono:
    def test_cuarenta_pedidos_treinta_en_almacen_faltan_diez(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        pedido(la_pieza, total=40)

        renglon = el(servicio.foto())

        assert renglon.disponible == 30
        assert renglon.pedido_pendiente == 40
        assert renglon.falta_por_fabricar == 10

    def test_si_ya_se_mandaron_a_hacer_no_los_vuelve_a_pedir(self):
        """Mandar a fabricar diez cuando ya hay diez en la línea es hacer
        veinte y quedarse con diez parados."""
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        pedido(la_pieza, total=40)
        orden(objetivo=10)

        assert el(servicio.foto()).falta_por_fabricar == 0

    def test_con_suficiente_no_falta_nada(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 50)
        pedido(la_pieza, total=40)

        assert el(servicio.foto()).falta_por_fabricar == 0


class TestElMinimo:
    def test_sin_minimo_no_se_avisa_de_nada(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 1)

        assert el(servicio.foto()).bajo_minimo is False

    def test_por_debajo_del_minimo_se_marca(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 5)
        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 20)

        assert el(servicio.foto()).bajo_minimo is True

    def test_se_compara_contra_lo_disponible_y_no_contra_el_estante(self):
        """Lo apartado ya tiene dueño y no sirve para el siguiente cliente.
        Avisar sobre el físico haría que la alerta llegara cuando ya no queda
        nada que prometer."""
        la_pieza = pieza()
        en_almacen(la_pieza, 5)
        pedido(la_pieza, total=30, apartado=25)
        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 20)

        renglon = el(servicio.foto())

        assert renglon.en_almacen == 30
        assert renglon.bajo_minimo is True

    def test_el_minimo_manda_a_reponer_aunque_no_haya_pedidos(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 5)
        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 20)

        assert el(servicio.foto()).falta_por_fabricar == 15

    def test_el_objetivo_repone_por_encima_del_minimo(self):
        """Reponer justo hasta el mínimo deja el producto en alerta al día
        siguiente."""
        la_pieza = pieza()
        en_almacen(la_pieza, 5)
        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 20, objetivo=50)

        assert el(servicio.foto()).falta_por_fabricar == 45

    def test_un_minimo_en_cero_se_guarda_igual(self):
        """Es la diferencia entre «alguien lo pensó y decidió que no hace
        falta avisar» y «nadie lo ha mirado nunca»."""
        from nucleo.models import NivelMinimo

        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 0)

        assert NivelMinimo.objects.using("mes").filter(minimo=0).exists()

    def test_un_producto_que_no_existe_no_se_puede_fijar(self):
        assert servicio.fijar_minimo(servicio.HERRERIA, "   ", 5) is None
        assert servicio.fijar_minimo("robotica", ANDAMIO, 5) is None

    def test_las_alertas_son_solo_lo_que_esta_bajo_minimo(self):
        floja = pieza("Ancla J")
        sobrada = pieza("Placa base")
        en_almacen(floja, 2)
        en_almacen(sobrada, 500)
        servicio.fijar_minimo(servicio.HERRERIA, "Ancla J", 20)
        servicio.fijar_minimo(servicio.HERRERIA, "Placa base", 20)

        assert [r.producto for r in servicio.alertas()] == ["Ancla J"]


class TestLoQueSeVe:
    def test_un_producto_agotado_no_se_esconde(self):
        """La pantalla anterior filtraba por `stock > 0`, así que escondía
        justo lo que hay que reponer."""
        la_pieza = pieza()
        en_almacen(la_pieza, 0)
        servicio.fijar_minimo(servicio.HERRERIA, ANDAMIO, 20)

        assert el(servicio.foto()).disponible == 0

    def test_pero_el_catalogo_de_entrega_inmediata_si_lo_esconde(self):
        """Ahí un renglón en cero no es información: es ruido."""
        from catalogos.terminado import disponible_para_entrega

        la_pieza = pieza()
        en_almacen(la_pieza, 0)

        assert disponible_para_entrega() == []

    def test_algo_pedido_que_nunca_se_ha_fabricado_aparece(self):
        """Con el filtro anterior era invisible: no tiene fila de almacén."""
        la_pieza = pieza()
        pedido(la_pieza, total=40)

        assert el(servicio.foto()).pedido_pendiente == 40

    def test_lo_urgente_va_primero(self):
        """Ordenar por nombre dejaría la alerta escondida en la letra ese."""
        tranquila = pieza("Ancla J")
        urgente = pieza("Zapata")
        en_almacen(tranquila, 500)
        en_almacen(urgente, 1)
        servicio.fijar_minimo(servicio.HERRERIA, "Zapata", 100)

        assert servicio.foto()[0].producto == "Zapata"

    def test_la_busqueda_no_distingue_mayusculas(self):
        la_pieza = pieza()
        en_almacen(la_pieza, 5)

        assert len(servicio.foto(busqueda="ANDAMIO")) == 1
        assert len(servicio.foto(busqueda="zzz")) == 0


def navegador(django_user_model, nombre="jefa", grupo="admin_general"):
    persona = django_user_model.objects.create_user(nombre, password="x")
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestLasPantallas:
    def test_piden_sesion(self):
        anonimo = Client(SERVER_NAME="127.0.0.1")

        for nombre in (
            "catalogos:producto_terminado",
            "catalogos:producto_terminado_minimos",
        ):
            assert anonimo.get(reverse(nombre)).status_code == 302

    def test_el_almacen_ensena_las_cuatro_columnas(self, django_user_model):
        la_pieza = pieza()
        en_almacen(la_pieza, 30)
        pedido(la_pieza, total=40, apartado=10)
        orden(objetivo=5)

        cuerpo = (
            navegador(django_user_model)
            .get(reverse("catalogos:producto_terminado"))
            .content.decode()
        )

        assert "Disponible" in cuerpo and "Apartado" in cuerpo
        assert "En producción" in cuerpo and "Falta hacer" in cuerpo
        assert ANDAMIO in cuerpo

    def test_el_filtro_de_alertas_deja_solo_lo_que_falta(self, django_user_model):
        sobrada = pieza("Placa base")
        en_almacen(sobrada, 500)
        floja = pieza("Ancla J")
        en_almacen(floja, 1)
        servicio.fijar_minimo(servicio.HERRERIA, "Ancla J", 20)

        cuerpo = (
            navegador(django_user_model)
            .get(reverse("catalogos:producto_terminado") + "?alertas=1")
            .content.decode()
        )

        assert "Ancla J" in cuerpo
        assert "Placa base" not in cuerpo

    def test_fijar_un_minimo_desde_la_pantalla(self, django_user_model):
        la_pieza = pieza()
        en_almacen(la_pieza, 5)

        navegador(django_user_model).post(
            reverse("catalogos:producto_terminado_minimo_guardar"),
            {"linea": servicio.HERRERIA, "producto": ANDAMIO, "minimo": "20"},
            follow=True,
        )

        assert el(servicio.foto()).minimo == 20

    def test_un_objetivo_por_debajo_del_minimo_se_rechaza(self, django_user_model):
        """Quedaría en alerta nada más fabricarlo."""
        pieza()

        respuesta = navegador(django_user_model).post(
            reverse("catalogos:producto_terminado_minimo_guardar"),
            {
                "linea": servicio.HERRERIA,
                "producto": ANDAMIO,
                "minimo": "20",
                "objetivo": "5",
            },
            follow=True,
        )

        assert "no puede ser menor" in respuesta.content.decode()
        assert el(servicio.foto()).minimo == 0

    def test_el_piso_no_fija_minimos(self, django_user_model):
        """No es de quien despacha: un mínimo mal puesto llena el almacén o
        deja al taller vendiendo lo que no tiene."""
        cliente = navegador(django_user_model, nombre="juan", grupo="soldadura")

        respuesta = cliente.get(reverse("catalogos:producto_terminado_minimos"))

        assert respuesta.status_code == 302

    def test_pero_si_ve_el_almacen(self, django_user_model):
        cliente = navegador(django_user_model, nombre="juan", grupo="soldadura")

        assert cliente.get(reverse("catalogos:producto_terminado")).status_code == 200


class TestUnTrabajoUnicoNoEsAlmacen:
    """Herrería no guarda de qué pieza del catálogo sale una orden.

    Copia el nombre, y cuando alguien da de alta un trabajo único escribiendo
    el código del pedido en el nombre, ese código acabaría en la lista del
    almacén como si fuera un producto que se tiene en existencia.
    """

    def test_una_orden_con_nombre_de_codigo_no_inventa_un_producto(self):
        pieza()
        orden(nombre="ORD-00412-007", objetivo=5)

        assert "ORD-00412-007" not in [r.producto for r in servicio.foto()]

    def test_pero_una_orden_de_un_producto_del_catalogo_si_cuenta(self):
        pieza()
        orden(nombre=ANDAMIO, objetivo=5)

        assert el(servicio.foto()).en_produccion == 5
