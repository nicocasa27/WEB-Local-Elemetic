"""El espesor y la cédula del pedido: salen de la placa o se escriben.

Estaban en gris, de sólo lectura, y no se guardaban en ningún sitio: eran una
ficha de la placa elegida y nada más. Lo que se pidió es que sirvan para las
dos cosas —que salgan solos de la placa, y que se puedan escribir cuando haga
falta— porque a veces la placa que había en el taller no era exactamente la del
catálogo, y eso hay que poder anotarlo **sin tocar el catálogo**, que es de
todos.

De ahí las dos columnas nuevas en el pedido. En blanco o en cero significan
«los de la placa», que es el caso normal.
"""

import re

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogos.models import LaserMaterialPlaca, LaserOrdenProduccion

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


@pytest.fixture
def quien_captura():
    persona = User.objects.create_user("captura", password="x")
    persona.groups.add(Group.objects.get_or_create(name="corte_laser")[0])
    cliente = Client()
    cliente.force_login(persona)
    return cliente


@pytest.fixture
def placa():
    return LaserMaterialPlaca.objects.create(
        categoria_material="Acero",
        nombre="A36",
        calibre="16",
        espesor_mm=4.76,
        largo_mm=2440,
        ancho_mm=1220,
        peso_kg=148.0,
        activo=True,
    )


def pedido(placa, **cambios):
    datos = {
        "folio_externo": "F-2001",
        "pieza": "Brida",
        "cliente_proyecto": "Ismael",
        "material": str(placa.id),
        "pieza_ancho_mm": "100",
        "pieza_alto_mm": "200",
        "fecha_compromiso": timezone.localdate().isoformat(),
        "estado": "Espera de corte",
        "prioridad": "3",
        "total_piezas": "1",
    }
    datos.update(cambios)
    return datos


class TestSePuedenEscribir:
    def test_ya_no_estan_en_gris(self, quien_captura, placa):
        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        for campo in ("id_espesor_mm", "id_calibre"):
            etiqueta = re.search(rf'<input[^>]*id="{campo}"[^>]*>', html).group(0)
            assert "readonly" not in etiqueta, f"{campo} sigue siendo de sólo lectura"

    def test_lo_escrito_se_guarda(self, quien_captura, placa):
        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            pedido(placa, espesor_mm="4.50", calibre="15"),
        )

        orden = LaserOrdenProduccion.objects.get(folio_externo="F-2001")
        assert orden.espesor_mm == 4.50
        assert orden.calibre == "15"

    def test_el_catalogo_no_se_toca(self, quien_captura, placa):
        """Es la razón de tener columnas propias. Si escribir aquí cambiara la
        placa, se estaría cambiando para todos los pedidos que la usen."""
        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            pedido(placa, espesor_mm="4.50", calibre="15"),
        )

        placa.refresh_from_db()
        assert placa.espesor_mm == 4.76
        assert placa.calibre == "16"

    def test_en_blanco_significa_los_de_la_placa(self, quien_captura, placa):
        quien_captura.post(reverse("catalogos:corte_laser_create"), pedido(placa))

        orden = LaserOrdenProduccion.objects.get(folio_externo="F-2001")
        assert orden.espesor_mm == 0.0
        assert orden.calibre == ""

    def test_no_son_obligatorios(self, quien_captura, placa):
        """Nadie debería quedarse sin poder guardar un pedido por esto."""
        respuesta = quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            pedido(placa, espesor_mm="", calibre=""),
        )

        assert respuesta.status_code == 302
        assert LaserOrdenProduccion.objects.filter(folio_externo="F-2001").exists()


class TestAlEditar:
    def test_vuelven_a_salir_escritos(self, quien_captura, placa):
        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            pedido(placa, espesor_mm="4.50", calibre="15"),
        )
        orden = LaserOrdenProduccion.objects.get(folio_externo="F-2001")

        html = quien_captura.get(
            reverse("catalogos:corte_laser_update", args=[orden.id])
        ).content.decode()

        assert 'value="4.5"' in re.search(r'<input[^>]*id="id_espesor_mm"[^>]*>', html).group(0)
        assert 'value="15"' in re.search(r'<input[^>]*id="id_calibre"[^>]*>', html).group(0)

    def test_se_pueden_borrar_para_volver_a_los_de_la_placa(self, quien_captura, placa):
        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            pedido(placa, espesor_mm="4.50", calibre="15"),
        )
        orden = LaserOrdenProduccion.objects.get(folio_externo="F-2001")

        quien_captura.post(
            reverse("catalogos:corte_laser_update", args=[orden.id]),
            pedido(placa, espesor_mm="", calibre=""),
        )

        orden.refresh_from_db()
        assert orden.espesor_mm == 0.0
        assert orden.calibre == ""


class TestSugerencias:
    def test_ofrece_los_espesores_y_cedulas_que_ya_existen(self, quien_captura, placa):
        """Para que no acaben conviviendo 4.76, 4.8 y 4,76 como tres cosas."""
        LaserMaterialPlaca.objects.create(
            categoria_material="Acero", nombre="A1011", calibre="14",
            espesor_mm=1.9, largo_mm=2440, ancho_mm=1220, activo=True,
        )

        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        espesores = html.split('id="cortaEspesores"', 1)[1].split("</datalist>", 1)[0]
        assert 'value="4.76"' in espesores and 'value="1.9"' in espesores
        calibres = html.split('id="cortaCalibres"', 1)[1].split("</datalist>", 1)[0]
        assert 'value="16"' in calibres and 'value="14"' in calibres

    def test_no_ofrece_las_placas_dadas_de_baja(self, quien_captura, placa):
        LaserMaterialPlaca.objects.create(
            categoria_material="Acero", nombre="VIEJA", calibre="99",
            espesor_mm=99.0, largo_mm=100, ancho_mm=100, activo=False,
        )

        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        calibres = html.split('id="cortaCalibres"', 1)[1].split("</datalist>", 1)[0]
        assert 'value="99"' not in calibres
