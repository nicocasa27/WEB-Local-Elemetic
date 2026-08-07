"""Bandeja de despacho: qué está listo para salir del taller.

El taller pidió «un disparador automático que avise a Logística al marcar una
orden como Terminado». Está hecho, pero **no con un disparador**, y el primer
test de este archivo es el que explica por qué.

Un disparador crea el aviso cuando alguien cambia el estado. En este sistema el
estado se cambia desde cuatro motores distintos y desde decenas de sitios del
código —incluidos `update()` en bloque y SQL a mano en las tablas heredadas—,
así que cualquier camino que se olvide de disparar deja una orden terminada de
la que Logística nunca se entera. Y ese fallo no se ve: la bandeja sale vacía y
se confunde con «hoy no hubo trabajo».

La bandeja se deduce de los datos. Lo que se guarda es la respuesta: quién la
vio, quién la apartó para el camión.
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

from catalogos.despacho import cuantos_esperan_despacho, listos_para_salir
from catalogos.models import HerrOrdenProduccion, SeguimientoDespacho
from core import estados as est
from core import roles
from produccion.models import Viga
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()


@pytest.fixture
def grupos():
    roles.asegurar_grupos()


@pytest.fixture
def logistica(grupos):
    persona = Usuario.objects.create_user("ana", password="x")
    persona.groups.set(Group.objects.filter(name="pedidos_ventas"))
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def pieza(codigo="V-1", estado=est.TERMINADO, proyecto="TORRE NORTE", peso="50"):
    return Viga.objects.using(BASE).create(
        codigo_viga=codigo, pieza_no=1, total_piezas=1, proyecto=proyecto,
        descripcion="HSS 4x3/16", fecha_compromiso=timezone.localdate(),
        estado=estado, prioridad=3, peso_kg=Decimal(peso),
        fecha_creacion=timezone.now(), ultimo_cambio=timezone.now(),
    )


def orden_herreria(codigo="H-1", etapa=est.TERMINADO):
    return HerrOrdenProduccion.objects.using(BASE).create(
        codigo=codigo, codigo_normalizado=codigo, nombre="Barandal",
        nombre_normalizado="BARANDAL", descripcion="Barandal tipo A",
        pieza_no=1, total_piezas=4, peso_kg=Decimal("180"),
        fecha_compromiso=timezone.localdate(), prioridad=3,
        estado_etapa=etapa, ultimo_cambio=timezone.now(),
    )


class TestLaBandejaSeDeduce:
    """El motivo de no usar un disparador."""

    def test_una_pieza_terminada_aparece_sola(self):
        pieza("V-NUEVA")

        codigos = [f["codigo"] for f in listos_para_salir()]

        assert "V-NUEVA" in codigos

    def test_aparece_aunque_se_haya_terminado_sin_pasar_por_el_codigo(self):
        """La prueba de que un disparador no habría bastado.

        Aquí el estado se cambia con un `update()` en bloque, que no dispara
        señales ni pasa por ninguna vista. Es exactamente lo que hacen las
        correcciones a mano y los comandos de mantenimiento, y con un aviso
        disparado esta orden no habría aparecido nunca.
        """
        suelta = pieza("V-BULK", estado=est.PINTURA)

        Viga.objects.using(BASE).filter(pk=suelta.pk).update(estado=est.TERMINADO)

        assert "V-BULK" in [f["codigo"] for f in listos_para_salir()]

    def test_lo_que_ya_salio_no_aparece(self):
        pieza("V-ENVIADA", estado=est.ENVIADO)

        assert "V-ENVIADA" not in [f["codigo"] for f in listos_para_salir()]

    def test_lo_que_todavia_se_produce_tampoco(self):
        pieza("V-PINTURA", estado=est.PINTURA)

        assert "V-PINTURA" not in [f["codigo"] for f in listos_para_salir()]

    def test_junta_las_tres_lineas(self):
        pieza("V-2")
        orden_herreria("H-2")

        lineas = {f["linea"] for f in listos_para_salir()}

        assert SeguimientoDespacho.Linea.VIGAS in lineas
        assert SeguimientoDespacho.Linea.HERRERIA in lineas


class TestAgrupadoPorCliente:
    def test_lo_del_mismo_cliente_va_junto(self, logistica):
        """Es como se carga un camión: una lista plana obliga a leerla entera
        para saber qué sale en el mismo viaje."""
        pieza("V-A", proyecto="TORRE NORTE", peso="100")
        pieza("V-B", proyecto="TORRE NORTE", peso="50")
        pieza("V-C", proyecto="BODEGA SUR", peso="30")

        respuesta = logistica.get(reverse("catalogos:despacho"))
        grupos = {g["cliente"]: g for g in respuesta.context["grupos"]}

        assert len(grupos["TORRE NORTE"]["filas"]) == 2
        assert grupos["TORRE NORTE"]["peso_kg"] == pytest.approx(150.0)

    def test_el_mas_pesado_va_primero(self, logistica):
        pieza("V-A", proyecto="POCO", peso="10")
        pieza("V-B", proyecto="MUCHO", peso="900")

        respuesta = logistica.get(reverse("catalogos:despacho"))

        assert respuesta.context["grupos"][0]["cliente"] == "MUCHO"


class TestMarcarLoAtendido:
    def test_marcar_lo_saca_de_pendientes(self, logistica):
        suelta = pieza("V-MARCAR")
        assert cuantos_esperan_despacho() == 1

        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": suelta.internal_id,
            "estado": SeguimientoDespacho.Estado.DESPACHADO,
        })

        assert cuantos_esperan_despacho() == 0

    def test_pero_sigue_en_la_lista_hasta_que_salga_de_verdad(self, logistica):
        """Marcarlo es una anotación de Logística, no un cambio de producción.

        Si desapareciera al marcarlo, se perdería de vista lo que está apartado
        esperando el camión, que es justo lo que hay que vigilar.
        """
        suelta = pieza("V-SIGUE")
        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": suelta.internal_id,
            "estado": SeguimientoDespacho.Estado.DESPACHADO,
        })

        assert "V-SIGUE" in [f["codigo"] for f in listos_para_salir()]

    def test_queda_escrito_quien_y_cuando(self, logistica):
        suelta = pieza("V-QUIEN")

        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": suelta.internal_id,
            "estado": SeguimientoDespacho.Estado.DESPACHADO,
            "notas": "Sale el jueves",
        })

        seguimiento = SeguimientoDespacho.objects.using(BASE).get(
            referencia=suelta.internal_id
        )
        assert seguimiento.actor == "ana"
        assert seguimiento.notas == "Sale el jueves"
        assert seguimiento.despachado_en is not None

    def test_preparando_no_sella_la_salida(self, logistica):
        """Sin la distinción, «lo estoy preparando» contaría como entregado y
        el tiempo de entrega saldría más corto de lo que fue."""
        suelta = pieza("V-PREP")

        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": suelta.internal_id,
            "estado": SeguimientoDespacho.Estado.PREPARANDO,
        })

        seguimiento = SeguimientoDespacho.objects.using(BASE).get(
            referencia=suelta.internal_id
        )
        assert seguimiento.despachado_en is None
        assert seguimiento.visto_en is not None

    def test_marcar_dos_veces_no_duplica(self, logistica):
        """Dos filas para el mismo renglón lo enseñarían dos veces con estados
        distintos."""
        suelta = pieza("V-DOS")
        datos = {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": suelta.internal_id,
            "estado": SeguimientoDespacho.Estado.PREPARANDO,
        }

        logistica.post(reverse("catalogos:despacho_marcar"), datos)
        logistica.post(reverse("catalogos:despacho_marcar"), {
            **datos, "estado": SeguimientoDespacho.Estado.DESPACHADO,
        })

        assert SeguimientoDespacho.objects.using(BASE).filter(
            referencia=suelta.internal_id
        ).count() == 1

    def test_una_linea_inventada_no_se_guarda(self, logistica):
        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": "inventada", "referencia": "1", "estado": "despachado",
        })

        assert SeguimientoDespacho.objects.using(BASE).count() == 0

    def test_un_estado_inventado_tampoco(self, logistica):
        logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": "1", "estado": "volando",
        })

        assert SeguimientoDespacho.objects.using(BASE).count() == 0

    def test_una_referencia_que_no_es_numero_no_revienta(self, logistica):
        respuesta = logistica.post(reverse("catalogos:despacho_marcar"), {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": "ninguna", "estado": "despachado",
        }, follow=True)

        assert respuesta.status_code == 200


class TestQuienLaVe:
    def test_sin_sesion_no(self):
        cliente = Client(SERVER_NAME="127.0.0.1")
        assert cliente.get(reverse("catalogos:despacho")).status_code == 302

    def test_marcar_exige_post(self, logistica):
        """Un enlace no puede cambiar el estado de un despacho."""
        assert logistica.get(
            reverse("catalogos:despacho_marcar")
        ).status_code == 405


class TestConElTallerSembrado:
    def test_la_bandeja_tiene_algo_que_ensenar(self):
        """El sembrado deja piezas terminadas a propósito: una bandeja vacía
        no se puede explorar."""
        call_command("sembrar_demo", verbosity=0, stdout=StringIO())

        assert len(listos_para_salir()) > 0
