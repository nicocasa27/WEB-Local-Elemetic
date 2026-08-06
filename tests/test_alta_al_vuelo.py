"""Dar de alta lo que falta sin salir del formulario del pedido.

Quien captura pedidos en Corta.mx se encontraba con dos listas desplegables
—la pieza y la placa— que sólo ofrecían lo que ya existía. Si lo que llegaba
no estaba, había que irse a otra pantalla con el formulario a medio llenar,
darlo de alta, volver y empezar de cero. Varias veces al día.

El cliente ya se resolvía escribiéndolo: si no existe, se crea al guardar.
Estos tests comprueban que la pieza hace lo mismo, y que la placa —que no cabe
en una palabra, porque de sus medidas sale el peso del pedido— se puede dar de
alta desde la misma pantalla.
"""

import json

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    CortaPiezaCatalogo,
    LaserMaterialPlaca,
    LaserOrdenProduccion,
)

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
        tipo_material="Rolado en caliente",
        nombre="A36",
        espesor_mm=6.35,
        largo_mm=2440,
        ancho_mm=1220,
        peso_kg=148.0,
        activo=True,
    )


def datos_de_pedido(placa, **cambios):
    datos = {
        "folio_externo": "F-1001",
        "pieza": "Placa 3 x 16 Pulgadas",
        "cliente_proyecto": "Ismael",
        "material": str(placa.id),
        "pieza_ancho_mm": "300",
        "pieza_alto_mm": "160",
        "fecha_compromiso": timezone.localdate().isoformat(),
        "estado": "Espera de corte",
        "prioridad": "3",
        "total_piezas": "1",
    }
    datos.update(cambios)
    return datos


class TestLaPiezaSeEscribe:
    def test_una_pieza_que_no_existe_se_crea_al_guardar(self, quien_captura, placa):
        assert not CortaPiezaCatalogo.objects.filter(nombre_normalizado="BRIDA NUEVA").exists()

        respuesta = quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            datos_de_pedido(placa, pieza="Brida nueva"),
        )

        assert respuesta.status_code == 302
        pieza = CortaPiezaCatalogo.objects.get(nombre_normalizado="BRIDA NUEVA")
        assert pieza.nombre == "Brida nueva"
        assert pieza.activo
        assert LaserOrdenProduccion.objects.get(folio_externo="F-1001").corta_pieza_id == pieza.id

    def test_una_que_ya_existe_se_reutiliza(self, quien_captura, placa):
        """No se crea una copia: el nombre es único y dos filas iguales no valen."""
        vieja = CortaPiezaCatalogo.objects.create(nombre="Brida", activo=True)

        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            datos_de_pedido(placa, pieza="  brida  "),
        )

        assert CortaPiezaCatalogo.objects.filter(nombre_normalizado="BRIDA").count() == 1
        assert LaserOrdenProduccion.objects.get(folio_externo="F-1001").corta_pieza_id == vieja.id

    def test_una_dada_de_baja_se_reactiva(self, quien_captura, placa):
        """Si alguien vuelve a pedirla, es que sigue viva. Crear otra igual no se puede."""
        vieja = CortaPiezaCatalogo.objects.create(nombre="Brida", activo=False)

        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            datos_de_pedido(placa, pieza="Brida"),
        )

        vieja.refresh_from_db()
        assert vieja.activo
        assert CortaPiezaCatalogo.objects.filter(nombre_normalizado="BRIDA").count() == 1

    def test_sin_pieza_no_se_guarda(self, quien_captura, placa):
        respuesta = quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            datos_de_pedido(placa, pieza="   "),
        )

        assert respuesta.status_code == 200
        assert not LaserOrdenProduccion.objects.filter(folio_externo="F-1001").exists()

    def test_el_formulario_ofrece_las_que_ya_hay(self, quien_captura, placa):
        CortaPiezaCatalogo.objects.create(nombre="Brida", activo=True)

        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        assert 'id="cortaPiezaList"' in html
        assert 'value="Brida"' in html


class TestLaPlacaSeDaDeAltaDesdeElPedido:
    def url(self):
        return reverse("catalogos:corte_laser_material_nuevo")

    def campos(self, **cambios):
        datos = {
            "categoria_material": "Acero",
            "tipo_material": "Rolado en frio",
            "nombre": "A1011",
            "calibre": "16",
            "espesor_mm": "1.52",
            "largo_cm": "244",
            "ancho_cm": "122",
            "peso_kg": "35.5",
            "activo": "on",
        }
        datos.update(cambios)
        return datos

    def test_se_crea_y_vuelve_lista_para_elegirla(self, quien_captura):
        respuesta = quien_captura.post(self.url(), self.campos())

        assert respuesta.status_code == 200
        cuerpo = json.loads(respuesta.content)
        assert cuerpo["ok"] and cuerpo["creada"]

        placa = LaserMaterialPlaca.objects.get(nombre_normalizado="A1011")
        assert cuerpo["material"]["id"] == placa.id
        # En centímetros se captura, en milímetros se guarda.
        assert placa.largo_mm == 2440
        assert placa.ancho_mm == 1220
        # La etiqueta es la misma que en la lista, o la placa recién creada se
        # leería distinta que las demás.
        assert "Acero" in cuerpo["etiqueta"] and "A1011" in cuerpo["etiqueta"]

    def test_si_ya_existe_se_devuelve_la_que_hay(self, quien_captura):
        """La tabla tiene unicidad sobre esos siete campos: crearla otra vez
        reventaría, y quien captura no tiene por qué saber si alguien se le
        adelantó."""
        quien_captura.post(self.url(), self.campos())
        respuesta = quien_captura.post(self.url(), self.campos())

        cuerpo = json.loads(respuesta.content)
        assert cuerpo["ok"] and not cuerpo["creada"]
        assert LaserMaterialPlaca.objects.filter(nombre_normalizado="A1011").count() == 1

    def test_el_peso_se_puede_dejar_vacio(self, quien_captura):
        """Se estima con las medidas. Exigir un número que nadie tiene a mano
        sólo consigue que se invente."""
        respuesta = quien_captura.post(self.url(), self.campos(peso_kg=""))

        cuerpo = json.loads(respuesta.content)
        assert cuerpo["ok"]
        assert cuerpo["material"]["peso_kg"] == 0.0

    def test_sin_medidas_no_se_guarda(self, quien_captura):
        respuesta = quien_captura.post(self.url(), self.campos(largo_cm="0"))

        assert respuesta.status_code == 400
        cuerpo = json.loads(respuesta.content)
        assert not cuerpo["ok"]
        assert "largo_cm" in cuerpo["errores"]
        assert not LaserMaterialPlaca.objects.filter(nombre_normalizado="A1011").exists()

    def test_una_dada_de_baja_se_reactiva(self, quien_captura):
        quien_captura.post(self.url(), self.campos())
        LaserMaterialPlaca.objects.filter(nombre_normalizado="A1011").update(activo=False)

        quien_captura.post(self.url(), self.campos())

        assert LaserMaterialPlaca.objects.get(nombre_normalizado="A1011").activo

    def test_pide_sesion(self):
        respuesta = Client().post(self.url(), self.campos())
        assert respuesta.status_code in {302, 403}
        assert not LaserMaterialPlaca.objects.exists()

    def test_quien_no_es_de_corta_no_puede(self):
        persona = User.objects.create_user("ajeno", password="x")
        persona.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        cliente = Client()
        cliente.force_login(persona)

        respuesta = cliente.post(self.url(), self.campos())

        assert respuesta.status_code == 403
        assert not LaserMaterialPlaca.objects.exists()

    def test_no_contesta_a_un_get(self, quien_captura):
        assert quien_captura.get(self.url()).status_code == 405


class TestElBotonEstaDondeSeNecesita:
    def test_el_formulario_trae_el_alta_de_placa(self, quien_captura):
        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        assert 'id="nuevaPlacaPanel"' in html
        assert reverse("catalogos:corte_laser_material_nuevo") in html

    def test_los_campos_del_alta_no_viajan_con_el_pedido(self, quien_captura):
        """Van dentro del formulario del pedido. Con `name` se enviarían junto
        a él y el pedido llegaría al servidor con campos que no son suyos."""
        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        panel = html.split('id="nuevaPlacaPanel"', 1)[1].split("</div>\n        </div>", 1)[0]
        assert 'id="nuevaPlacaNombre"' in panel
        assert "name=" not in panel


class TestEditar:
    def test_la_pieza_llega_escrita_al_editar(self, quien_captura, placa):
        quien_captura.post(reverse("catalogos:corte_laser_create"), datos_de_pedido(placa))
        orden = LaserOrdenProduccion.objects.get(folio_externo="F-1001")

        html = quien_captura.get(
            reverse("catalogos:corte_laser_update", args=[orden.id])
        ).content.decode()

        # El nombre, no el número: antes el campo llevaba el id de la fila y al
        # convertirlo en texto se habría quedado escrito un «7».
        assert 'value="Placa 3 x 16 Pulgadas"' in html

    def test_se_puede_cambiar_a_una_pieza_nueva(self, quien_captura, placa):
        quien_captura.post(reverse("catalogos:corte_laser_create"), datos_de_pedido(placa))
        orden = LaserOrdenProduccion.objects.get(folio_externo="F-1001")

        quien_captura.post(
            reverse("catalogos:corte_laser_update", args=[orden.id]),
            datos_de_pedido(placa, pieza="Otra cosa"),
        )

        orden.refresh_from_db()
        assert orden.corta_pieza.nombre == "Otra cosa"
        assert orden.codigo == "Otra cosa"
