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

from produccion import navegacion as navegacion_lateral
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

    def test_toda_pantalla_dice_de_que_area_es(self):
        """El primer escalón era «Menú», porque volver sólo se podía por el
        muro de mosaicos. Con la barra lateral siempre a la vista eso es un
        enlace de sobra en cada cabecera: las migas se quedan con lo que la
        barra no dice, que es en qué parte del área estás.
        """
        migas = navegacion(self.Peticion("herreria_ordenes"))["migas"]
        assert [m["texto"] for m in migas] == ["Herrería"]
        assert migas[0]["url"] == reverse("catalogos:herreria_control")

    def test_la_portada_de_un_area_no_se_repite_a_si_misma(self):
        """«Corte» encima de «Área Corte» es la misma palabra dos veces, dos
        renglones más arriba y sin llevar a ningún sitio."""
        peticion = self.Peticion("herreria_control", reverse("catalogos:herreria_control"))
        assert navegacion(peticion)["migas"] == []

    def test_el_menu_no_lleva_migas(self):
        assert navegacion(self.Peticion("home"))["migas"] == []

    def test_la_pantalla_del_operador_tampoco(self):
        """En el celular, cada renglón que no sea trabajo estorba."""
        assert navegacion(self.Peticion("movil"))["migas"] == []

    def test_una_ruta_sin_area_no_inventa_migas(self):
        """Sin sección a la que pertenecer no hay nada que decir, y la barra
        lateral ya enseña dónde estás."""
        assert navegacion(self.Peticion("una_ruta_rara"))["migas"] == []

    def test_llegan_a_la_pagina(self, navegador):
        """En una pantalla de dentro, no en la portada de su área: ahí las
        migas no se ponen porque repetirían el título."""
        pagina = navegador.get(reverse("catalogos:paros_motivos")).content.decode()
        assert 'aria-label="Ruta de navegación"' in pagina
        assert ">Paros</a>" in pagina


class TestElMenuLlevaALoQueMasSeUsa:
    def test_mi_trabajo_esta_en_el_menu(self, navegador):
        """Si no está en el menú, en el piso no existe."""
        pagina = navegador.get(reverse("produccion:viga_list")).content.decode()
        assert reverse("produccion:movil") in pagina

    def test_el_menu_se_declara_una_sola_vez(self):
        """Estuvo escrito tres veces —barra de escritorio, panel del celular y
        mosaicos de la portada— y las tres se desincronizaron: Almacén,
        Usuarios y «Listo para salir» acabaron existiendo sólo en una.

        El que más dolía era Almacén. El almacenista trabaja con el celular
        junto al anaquel, así que confirmar una entrega —la validación de doble
        factor— exigía ir a una computadora.

        Ahora los destinos viven en `produccion/navegacion.py` y las dos
        formas de enseñarlos incluyen el mismo parcial. Este test vigila que
        nadie vuelva a escribir enlaces de menú a mano en el armazón.
        """
        base = (
            Path(settings.BASE_DIR)
            / "produccion" / "templates" / "produccion" / "base.html"
        ).read_text(encoding="utf-8")

        assert base.count('include "produccion/_menu.html"') == 2

        destinos = {
            item.url
            for grupo in navegacion_lateral.MENU
            for item in grupo.items
        }
        enlaces = set(re.findall(r"{%\s*url\s+'([^']+)'\s*%}", base))
        a_mano = (enlaces & destinos) - {"produccion:home"}

        assert not a_mano, (
            f"Enlaces de menú escritos a mano en base.html: {sorted(a_mano)}. "
            "Van en produccion/navegacion.py."
        )

    def test_todo_lo_que_ofrece_el_menu_se_puede_abrir(self, navegador):
        """Un renglón del menú que lleva a un error es peor que no tenerlo:
        parece que la pantalla existe y está rota.
        """
        rotos = []
        for grupo in navegacion_lateral.MENU:
            for item in grupo.items:
                try:
                    destino = reverse(item.url)
                except Exception as error:
                    rotos.append(f"{item.url}: {error}")
                    continue
                respuesta = navegador.get(destino)
                if respuesta.status_code >= 500:
                    rotos.append(f"{item.url}: {respuesta.status_code}")

        assert not rotos, rotos

    def test_cada_quien_ve_lo_suyo(self):
        """El menú se arma desde los permisos, no desde condiciones sueltas en
        la plantilla. Una condición en una plantilla no se puede probar sola.
        """
        de_corte = navegacion_lateral.para({"can_corte": True})
        titulos = {g["titulo"] for g in de_corte}

        assert "Configuración" not in titulos
        assert "Producción" in titulos

    def test_un_grupo_sin_destinos_no_se_ensena(self):
        """Un título de grupo vacío parece un fallo de carga."""
        pelado = navegacion_lateral.para({})

        assert all(g["items"] for g in pelado)


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
