"""Las listas de producción: un solo recorrido y sin recorte silencioso.

Dos defectos que venían juntos:

**Cada lista se dibujaba dos veces.** Un bloque de tarjetas con `d-lg-none` y
una tabla con `d-none d-lg-block`, sobre el mismo conjunto. Aparte de duplicar
el HTML, los dos bloques se separaron: el botón para avanzar la pieza y el
campo «Fecha de operación (obligatoria)» **sólo existían en el del celular**.
Qué se podía hacer con una orden dependía del ancho de la ventana, y eso no
es un detalle de presentación: es una regla de negocio que cambia según el
navegador.

**El recorte era silencioso.** `qs[:2000]` y un cartel que decía «Mostrando
hasta 2000 registros». El día que el taller pase de dos mil piezas, las que
sobren no aparecerán y nadie recibirá aviso.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from core import paginacion

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

LISTA = Path(settings.BASE_DIR) / "produccion" / "templates" / "produccion" / "viga_list.html"
FILA = Path(settings.BASE_DIR) / "produccion" / "templates" / "produccion" / "_pieza_fila.html"


@pytest.fixture
def pieza():
    """Una pieza en curso, para que la lista tenga algo que enseñar."""
    from django.utils import timezone

    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga="PRUEBA-1",
        pieza_no=1,
        total_piezas=1,
        proyecto="PROYECTO DE PRUEBA",
        descripcion="pieza de prueba",
        fecha_compromiso=timezone.localdate(),
        estado="Espera de corte",
        prioridad=3,
        peso_kg=100,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


@pytest.fixture
def navegador(django_user_model):
    persona = django_user_model.objects.create_user(
        "jefa", password="x", is_staff=True, is_superuser=True
    )
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestUnSoloRecorrido:
    def test_la_plantilla_recorre_las_piezas_una_vez(self):
        texto = LISTA.read_text(encoding="utf-8")
        assert texto.count("{% for v in vigas %}") == 1

    def test_la_lista_principal_ya_no_se_esconde_por_ancho(self):
        """`d-lg-none` + `d-none d-lg-block` sobre el mismo conjunto.

        Las dos tablas de abajo —enviados y decote— siguen con el patrón
        viejo. No comparten este parcial y llevan otras columnas; se cambian
        aparte.
        """
        texto = LISTA.read_text(encoding="utf-8")
        principal = texto[: texto.find("Piezas enviadas")]
        assert "d-none d-lg-block" not in principal

    def test_avanzar_la_pieza_existe_en_las_dos_pantallas(self, navegador, pieza):
        """La acción principal no puede depender del ancho de la ventana.

        Antes vivía sólo dentro del bloque del celular: en la PC había que
        abrir un diálogo para hacer lo mismo.
        """
        pagina = navegador.get(reverse("produccion:viga_list")).content.decode()

        assert "js-next-btn" in pagina
        # Y no dentro de nada que se oculte por ancho.
        for trozo in re.findall(r'<div class="[^"]*d-(?:lg|md)-none[^"]*"[^>]*>', pagina):
            assert "js-next-btn" not in trozo

    def test_la_fecha_de_operacion_existe_siempre(self, navegador, pieza):
        """Era obligatoria y sólo estaba por debajo de 992 píxeles."""
        pagina = navegador.get(reverse("produccion:viga_list")).content.decode()
        posicion = pagina.find('id="globalFechaOperacion"')
        assert posicion > 0
        # El contenedor que la envuelve no puede esconderla por ancho.
        contexto = pagina[max(0, posicion - 400) : posicion]
        assert "d-lg-none" not in contexto

    def test_la_fila_no_depende_de_javascript_para_verse(self):
        texto = FILA.read_text(encoding="utf-8")
        assert "estado_clase" in texto
        assert "estado_color" not in texto


class TestElRecorteYaNoEsSilencioso:
    def test_la_pantalla_dice_cuantas_hay(self, navegador, pieza):
        pagina = navegador.get(reverse("produccion:viga_list")).content.decode()
        assert "Mostrando hasta 2000 registros" not in pagina
        assert "pieza" in pagina

    def test_manda_una_pagina_al_contexto(self, navegador):
        respuesta = navegador.get(reverse("produccion:viga_list"))
        assert respuesta.context["pagina"] is not None

    def test_las_areas_tambien_paginan(self, navegador):
        for ruta in ["produccion:area_corte", "produccion:area_soldadura"]:
            respuesta = navegador.get(reverse(ruta))
            assert respuesta.context["pagina"] is not None, ruta


class TestElPaginador:
    class Peticion:
        """Lo mínimo que mira el paginador de una petición."""

        def __init__(self, get=None, path="/vigas/"):
            from django.http import QueryDict

            self.GET = QueryDict(get or "", mutable=True)
            self.path = path

    def test_una_pagina_que_no_existe_devuelve_la_ultima(self):
        """Quien llega ahí viene de un enlace viejo.

        Una lista vacía sin explicación parece que se borraron los datos.
        """
        pagina = paginacion.paginar(self.Peticion("pagina=99"), list(range(10)), 5)
        assert pagina.number == 2

    def test_una_pagina_que_no_es_un_numero_devuelve_la_primera(self):
        pagina = paginacion.paginar(self.Peticion("pagina=abc"), list(range(10)), 5)
        assert pagina.number == 1

    def test_no_se_puede_pedir_una_pagina_gigante(self):
        """`?por_pagina=100000` volvería a traerlo todo de una vez."""
        assert paginacion.tamano_de_pagina(self.Peticion("por_pagina=100000")) == (
            paginacion.MAXIMO_POR_PAGINA
        )

    def test_un_tamano_absurdo_no_revienta(self):
        assert paginacion.tamano_de_pagina(self.Peticion("por_pagina=hola")) == (
            paginacion.POR_PAGINA
        )
        assert paginacion.tamano_de_pagina(self.Peticion("por_pagina=-3")) == 1

    def test_cambiar_de_pagina_conserva_los_filtros(self):
        """Perderlos hace que la lista cambie de contenido sin motivo."""
        enlace = paginacion.enlace_de_pagina(
            self.Peticion("estado=Corte&q=HSS&pagina=1"), 3
        )
        assert "estado=Corte" in enlace
        assert "q=HSS" in enlace
        assert "pagina=3" in enlace
        assert "pagina=1" not in enlace


class TestHerreriaYCortaTambienDibujanUnaVez:
    """Las otras dos listas tenían el mismo defecto, multiplicado.

    Herrería repartía el resultado en tres listas y las dibujaba las dos
    veces: seis copias del mismo renglón en un solo archivo. Y las copias no
    se habían separado sólo en lo cosmético.
    """

    HERRERIA = Path(settings.BASE_DIR) / "catalogos" / "templates" / "catalogos" / "herreria_list.html"
    CORTA = Path(settings.BASE_DIR) / "catalogos" / "templates" / "catalogos" / "corte_laser_list.html"
    ORDEN = Path(settings.BASE_DIR) / "catalogos" / "templates" / "catalogos" / "_orden_fila.html"

    def test_herreria_recorre_cada_lista_una_vez(self):
        texto = self.HERRERIA.read_text(encoding="utf-8")
        principal = texto[: texto.find("Piezas enviadas")]
        for variable in ["vigas_op_ventas", "vigas_op", "vigas_individual"]:
            assert principal.count("{%% for v in %s %%}" % variable) == 1, variable

    def test_corta_recorre_una_vez(self):
        texto = self.CORTA.read_text(encoding="utf-8")
        principal = texto[: texto.find("Piezas enviadas")]
        assert principal.count("{% for v in vigas %}") == 1

    def test_el_boton_de_avance_ya_no_depende_del_ancho(self):
        """Aparecía en el celular para cualquiera y en la PC sólo para
        administradores. Era la misma acción con dos permisos distintos."""
        texto = self.ORDEN.read_text(encoding="utf-8")
        inicio = texto.find("js-open-avance-modal")
        assert inicio > 0
        # La condición que lo envuelve es sólo op_can_avance.
        anterior = texto[:inicio]
        assert anterior.rstrip().endswith('class="btn btn-outline-success')
        assert "{% if v.op_can_avance %}" in texto

    def test_se_puede_revertir_un_cierre_desde_las_dos(self):
        """El «Avance» de la PC no llevaba los datos del cierre, así que
        desde la PC no se podía deshacer y desde el celular sí."""
        texto = self.ORDEN.read_text(encoding="utf-8")
        assert "data-revert-action" in texto
        assert "data-pendiente-hasta" in texto

    def test_ya_no_mienten_sobre_cuantas_hay(self):
        for archivo in (self.HERRERIA, self.CORTA):
            assert "Mostrando hasta 2000 registros" not in archivo.read_text(encoding="utf-8")
