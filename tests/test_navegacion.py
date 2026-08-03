"""Saber dónde estás, poder volver, y que los formularios se puedan usar.

Dos problemas distintos con la misma raíz —nadie diseñó la navegación, se fue
añadiendo pantalla a pantalla—:

**No había migas de pan.** Desde una pantalla de detalle no se sabía de dónde
venías, y para volver al menú había que adivinar que el logotipo era un
enlace. En su lugar había treinta variantes artesanales de «Volver», cada una
con su destino escrito a mano, que a menudo te sacaban de donde estabas.

**291 de las 324 etiquetas de formulario no apuntaban a su campo.** Sin el
`for`, pulsar el texto de la etiqueta no enfoca el campo —en un celular, con
el dedo, eso importa— y quien use un lector de pantalla no sabe qué se le está
pidiendo.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from produccion.context_processors import navegacion

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

CARPETAS = [
    Path(settings.BASE_DIR) / "produccion" / "templates",
    Path(settings.BASE_DIR) / "catalogos" / "templates",
    Path(settings.BASE_DIR) / "nucleo" / "templates",
    Path(settings.BASE_DIR) / "templates",
]

ETIQUETA = re.compile(r"<label\b[^>]*>")


def plantillas():
    for carpeta in CARPETAS:
        if carpeta.is_dir():
            yield from carpeta.rglob("*.html")


@pytest.fixture
def navegador(django_user_model):
    persona = django_user_model.objects.create_user(
        "jefa", password="x", is_staff=True, is_superuser=True
    )
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestMigasDePan:
    class Peticion:
        def __init__(self, url_name, path="/x/"):
            self.resolver_match = type("R", (), {"url_name": url_name})()
            self.path = path

    def test_toda_pantalla_sabe_volver_al_menu(self):
        migas = navegacion(self.Peticion("herreria_ordenes"))["migas"]
        assert migas[0]["texto"] == "Menú"
        assert migas[0]["url"] == reverse("produccion:home")

    def test_lleva_tambien_a_la_portada_de_su_area(self):
        migas = navegacion(self.Peticion("herreria_ordenes"))["migas"]
        assert [m["texto"] for m in migas] == ["Menú", "Herrería"]
        assert migas[1]["url"] == reverse("catalogos:herreria_control")

    def test_la_portada_de_un_area_no_se_enlaza_a_si_misma(self):
        """«Herrería › Herrería» con el segundo enlazado no dice nada."""
        peticion = self.Peticion("herreria_control", reverse("catalogos:herreria_control"))
        migas = navegacion(peticion)["migas"]
        assert migas[1]["url"] == ""

    def test_el_menu_no_lleva_migas(self):
        assert navegacion(self.Peticion("home"))["migas"] == []

    def test_la_pantalla_del_operador_tampoco(self):
        """En el celular, cada renglón que no sea trabajo estorba."""
        assert navegacion(self.Peticion("movil"))["migas"] == []

    def test_una_ruta_sin_area_al_menos_vuelve_al_menu(self):
        migas = navegacion(self.Peticion("una_ruta_rara"))["migas"]
        assert [m["texto"] for m in migas] == ["Menú"]

    def test_llegan_a_la_pagina(self, navegador):
        pagina = navegador.get(reverse("catalogos:paros")).content.decode()
        assert 'aria-label="Ruta de navegación"' in pagina
        assert ">Menú</a>" in pagina


class TestElMenuLlevaALoQueMasSeUsa:
    def test_mi_trabajo_esta_en_el_menu(self, navegador):
        """Si no está en el menú, en el piso no existe."""
        pagina = navegador.get(reverse("produccion:viga_list")).content.decode()
        assert reverse("produccion:movil") in pagina


class TestLasEtiquetasApuntanASuCampo:
    def test_casi_ninguna_queda_suelta(self):
        """Eran 291 de 324. Las que quedan no tienen campo propio al lado.

        Son las etiquetas de bloques de sólo lectura y las de grupos de
        botones, donde no hay un campo al que apuntar.
        """
        sueltas = []
        for archivo in plantillas():
            for etiqueta in ETIQUETA.findall(archivo.read_text(encoding="utf-8")):
                if "for=" not in etiqueta:
                    sueltas.append(archivo.name)
        assert len(sueltas) <= 35, f"{len(sueltas)} etiquetas sin campo"

    def test_no_hay_identificadores_repetidos_en_una_pantalla(self):
        """Dos campos con el mismo id: la etiqueta enfoca el que no es."""
        culpables = []
        for archivo in plantillas():
            ids = re.findall(r'id="(campo-[^"]+)"', archivo.read_text(encoding="utf-8"))
            repetidos = {i for i in ids if ids.count(i) > 1}
            if repetidos:
                culpables.append(f"{archivo.name}: {sorted(repetidos)}")
        assert not culpables, "\n".join(culpables)

    def test_las_de_django_usan_el_identificador_que_genera_el_formulario(self):
        """Escribir el id a mano se rompe en cuanto el formulario cambia."""
        texto = (
            Path(settings.BASE_DIR)
            / "catalogos"
            / "templates"
            / "catalogos"
            / "colaborador_editar.html"
        ).read_text(encoding="utf-8")
        assert 'for="{{ form.nombre.id_for_label }}"' in texto
