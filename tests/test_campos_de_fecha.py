"""Que las fechas lleguen puestas a la pantalla.

El fallo: el sistema está en `es-mx`, así que Django pintaba
`<input type="date" value="06/08/2026">`. Un campo de fecha del navegador
**sólo** entiende `2026-08-06`; al no reconocer el formato tira el valor y deja
el campo vacío. En la consola queda un aviso que nadie mira.

Estaba en los catorce sitios donde se declaró el widget a mano, así que ninguna
fecha del sistema llegaba puesta:

- al dar de alta un pedido, la fecha de compromiso salía en blanco aunque la
  vista la pusiera en hoy;
- al **editar** cualquier cosa, la fecha guardada desaparecía de la pantalla, y
  si nadie se daba cuenta de volver a teclearla se guardaba otra o el
  formulario se quejaba de un campo obligatorio vacío.

Nadie iba a relacionar eso con el idioma del sistema.
"""

import re

import pytest
from django import forms
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.campos import CampoDeFecha

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


class TestElWidget:
    def test_pinta_la_fecha_como_la_espera_el_navegador(self):
        html = CampoDeFecha().render("f", timezone.datetime(2026, 8, 6).date())
        assert 'value="2026-08-06"' in html

    def test_no_la_pinta_en_el_formato_del_pais(self):
        """Es el fallo exacto: se veía bien y no funcionaba."""
        html = CampoDeFecha().render("f", timezone.datetime(2026, 8, 6).date())
        assert "06/08/2026" not in html

    def test_sigue_siendo_un_campo_de_fecha(self):
        html = CampoDeFecha().render("f", None)
        assert 'type="date"' in html
        assert 'class="form-control"' in html

    def test_acepta_atributos_propios(self):
        html = CampoDeFecha(attrs={"required": "required"}).render("f", None)
        assert "required" in html
        assert 'type="date"' in html


class TestNadieVuelveADeclararloAMano:
    """La forma vieja compila, se ve bien y no funciona: es la peor clase de
    error. Este test es lo único que impide que vuelva a colarse."""

    @pytest.mark.parametrize(
        "ruta",
        ["catalogos/views.py", "produccion/forms.py", "produccion/views.py", "nucleo/models.py"],
    )
    def test_ningun_dateinput_escrito_a_mano(self, ruta):
        archivo = settings.BASE_DIR / ruta
        if not archivo.is_file():
            pytest.skip(f"{ruta} no existe")
        codigo = archivo.read_text(encoding="utf-8")

        culpables = [
            linea.strip()
            for linea in codigo.splitlines()
            if 'DateInput(' in linea and "CampoDeFecha" not in linea
        ]
        assert not culpables, (
            f"En {ruta} hay un campo de fecha escrito a mano. Usar "
            f"core.campos.CampoDeFecha, o la fecha no llegará a la pantalla: {culpables}"
        )


class TestEnLaPantallaDeVerdad:
    @pytest.fixture
    def quien_captura(self):
        persona = User.objects.create_user("captura", password="x")
        persona.groups.add(Group.objects.get_or_create(name="corte_laser")[0])
        cliente = Client()
        cliente.force_login(persona)
        return cliente

    def test_el_pedido_nuevo_trae_la_fecha_de_hoy(self, quien_captura):
        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        campo = re.search(r'<input[^>]*id="id_fecha_compromiso"[^>]*>', html).group(0)
        assert f'value="{timezone.localdate().isoformat()}"' in campo

    def test_al_editar_no_se_pierde_la_fecha_guardada(self, quien_captura):
        """Lo más caro del fallo: la fecha existía en la base y desaparecía de
        la pantalla, así que al guardar se perdía."""
        from catalogos.models import LaserMaterialPlaca, LaserOrdenProduccion

        placa = LaserMaterialPlaca.objects.create(
            categoria_material="Acero", nombre="A36", espesor_mm=4.76,
            largo_mm=2440, ancho_mm=1220, activo=True,
        )
        quien_captura.post(
            reverse("catalogos:corte_laser_create"),
            {
                "folio_externo": "F-9001", "pieza": "Brida", "cliente_proyecto": "Ismael",
                "material": str(placa.id), "pieza_ancho_mm": "100", "pieza_alto_mm": "200",
                "fecha_compromiso": "2026-12-24", "estado": "Espera de corte",
                "prioridad": "3", "total_piezas": "1",
            },
        )
        orden = LaserOrdenProduccion.objects.get(folio_externo="F-9001")

        html = quien_captura.get(
            reverse("catalogos:corte_laser_update", args=[orden.id])
        ).content.decode()

        campo = re.search(r'<input[^>]*id="id_fecha_compromiso"[^>]*>', html).group(0)
        assert 'value="2026-12-24"' in campo
