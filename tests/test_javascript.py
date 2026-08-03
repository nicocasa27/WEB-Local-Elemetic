"""El JavaScript vive en archivos, no dentro de las plantillas.

Había 4.192 líneas de JavaScript escritas dentro de 27 plantillas, y las tres
listas de producción —Herrería, Corta.mx y Estructuras— eran casi el mismo
código copiado tres veces, con `getCookie` y `showToast` repetidos literalmente
en cada una. Esa es la razón de fondo de que arreglar algo en una línea nunca
llegara a las otras.

Estos tests no comprueban que el JavaScript haga bien su trabajo —eso se ve
usando la pantalla—. Comprueban que no vuelva a meterse dentro del HTML, que
es lo que hace imposible leerlo, cachearlo y compartirlo.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders

CARPETAS_DE_PLANTILLAS = [
    Path(settings.BASE_DIR) / "produccion" / "templates",
    Path(settings.BASE_DIR) / "catalogos" / "templates",
    Path(settings.BASE_DIR) / "nucleo" / "templates",
    Path(settings.BASE_DIR) / "templates",
]

#: Un `<script>` sin `src`, es decir, con código dentro.
INCRUSTADO = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)

#: Ayudantes que estaban copiados en varias plantillas y ahora viven en uno.
COMPARTIDOS = ["cookie", "aviso", "aplicarClaseDeEstado"]


def plantillas():
    for carpeta in CARPETAS_DE_PLANTILLAS:
        if carpeta.is_dir():
            yield from carpeta.rglob("*.html")


def archivos_js():
    raiz = Path(settings.BASE_DIR) / "produccion" / "static" / "js"
    return sorted(raiz.rglob("*.js"))


class TestNoQuedaJavaScriptDentroDelHtml:
    def test_ninguna_plantilla_lleva_codigo_dentro(self):
        culpables = []
        for archivo in plantillas():
            lineas = sum(
                b.count("\n") for b in INCRUSTADO.findall(archivo.read_text(encoding="utf-8"))
            )
            if lineas:
                culpables.append(f"{archivo.name}: {lineas} líneas")
        assert not culpables, "JavaScript dentro del HTML:\n" + "\n".join(culpables)

    def test_los_datos_del_servidor_viajan_en_atributos(self):
        """Sin esto, sacar el código obligaría a dejar un trozo dentro.

        Las direcciones y los identificadores que sólo conoce la plantilla se
        pasan en `data-*`; el archivo los lee del DOM.
        """
        pagina = (
            Path(settings.BASE_DIR)
            / "catalogos"
            / "templates"
            / "catalogos"
            / "herreria_list.html"
        ).read_text(encoding="utf-8")

        assert 'id="mesLista"' in pagina
        assert "data-url-estado=" in pagina
        assert "js/lista/herreria.js" in pagina


class TestNoHayAyudantesRepetidos:
    @pytest.mark.parametrize("nombre", COMPARTIDOS)
    def test_cada_ayudante_se_define_una_sola_vez(self, nombre):
        definiciones = [
            a.name
            for a in archivos_js()
            if re.search(rf"^\s*function {nombre}\(", a.read_text(encoding="utf-8"), re.M)
        ]
        assert definiciones == ["mes-base.js"], f"{nombre} definido en {definiciones}"

    def test_las_tres_listas_usan_los_compartidos(self):
        for nombre in ["herreria.js", "corta.js", "estructuras.js"]:
            texto = Path(finders.find(f"js/lista/{nombre}")).read_text(encoding="utf-8")
            assert "window.MES.cookie(" in texto, nombre
            assert "window.MES.aviso(" in texto, nombre


class TestLosArchivosSonValidos:
    def test_ninguno_arrastra_marcas_de_plantilla(self):
        """Un `{% url %}` dentro de un .js llega al navegador tal cual.

        No falla al desplegar: falla en silencio, en el navegador, cuando
        alguien pulsa el botón.
        """
        culpables = []
        for archivo in archivos_js():
            marcas = re.findall(r"\{[%{][^}]*[%}]\}", archivo.read_text(encoding="utf-8"))
            if marcas:
                culpables.append(f"{archivo.name}: {marcas[:3]}")
        assert not culpables, "Marcas de Django dentro de un .js:\n" + "\n".join(culpables)

    def test_todos_los_que_piden_las_plantillas_existen(self):
        pedidos = set()
        for archivo in plantillas():
            pedidos |= set(
                re.findall(r"\{%\s*static\s*'(js/[^']+)'\s*%\}", archivo.read_text(encoding="utf-8"))
            )
        assert pedidos, "ninguna plantilla carga un archivo de JavaScript"
        faltan = [r for r in sorted(pedidos) if not finders.find(r)]
        assert not faltan, f"Las plantillas piden archivos que no existen: {faltan}"
