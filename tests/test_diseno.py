"""El sistema de diseño: que la pantalla siga siendo legible cuando algo falla.

Los tres defectos que vigila este archivo tienen la misma forma: en la
oficina, con buena red y JavaScript funcionando, son invisibles. Se notan en el
piso, con el celular y la red del taller.

- El color del estado de una orden lo ponía el JavaScript. Si no cargaba, la
  etiqueta quedaba blanca sobre blanco: la orden aparecía sin estado.
- El acento de área lo decidía una cadena de seis condiciones en la plantilla,
  así que unas cuarenta pantallas no lo tenían y el color cambiaba al navegar
  sin que hubiera pasado nada.
- Los botones grandes estaban dentro de `min-width: 768px`: existían en la PC
  y no en el celular, que es justo al revés de lo que hace falta.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client

from core import estados
from produccion.context_processors import seccion_de

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


@pytest.fixture(scope="module")
def hoja():
    return Path(finders.find("css/mes.css")).read_text(encoding="utf-8")


def _luminancia(hexadecimal):
    """Luminancia relativa de un color, según WCAG 2.1."""
    crudo = hexadecimal.lstrip("#")
    canales = [int(crudo[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineales = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]


def contraste(uno, otro):
    a, b = sorted((_luminancia(uno), _luminancia(otro)), reverse=True)
    return (a + 0.05) / (b + 0.05)


class TestElBotonPrincipalSeLee:
    """El botón de la acción principal toma el color del área.

    Varios acentos están elegidos para verse como señal —una franja, un
    filete— y no sirven de fondo bajo texto blanco. El verde de Herrería con
    blanco daba **2,2:1** cuando el mínimo legible son 4,5:1, y ese botón es
    «Nueva pieza». En una nave con sol entrando no se leía.

    Por eso `--section-boton` va aparte de `--section-accent`. Este test es lo
    que impide que alguien vuelva a igualarlos sin darse cuenta.
    """

    MINIMO = 4.5

    def _tonos_de_boton(self, hoja):
        """Color de botón efectivo de cada sección, con su herencia."""
        por_defecto = re.search(r"--section-accent-dark:\s*(#[0-9a-fA-F]{6})", hoja).group(1)
        tonos = {}
        for bloque in re.finditer(
            r'body\[data-section="(\w+)"\]\s*\{([^}]*)\}', hoja
        ):
            seccion, cuerpo = bloque.group(1), bloque.group(2)
            propio = re.search(r"--section-boton:\s*(#[0-9a-fA-F]{6})", cuerpo)
            heredado = re.search(r"--section-accent-dark:\s*(#[0-9a-fA-F]{6})", cuerpo)
            tonos[seccion] = (
                propio.group(1) if propio
                else (heredado.group(1) if heredado else por_defecto)
            )
        return tonos

    def test_hay_un_tono_de_boton_por_seccion(self, hoja):
        tonos = self._tonos_de_boton(hoja)
        assert len(tonos) >= 10, f"Sólo se resolvieron {len(tonos)} secciones"

    def test_todas_pasan_el_minimo_con_texto_blanco(self, hoja):
        flojos = {
            seccion: round(contraste(tono, "#ffffff"), 2)
            for seccion, tono in self._tonos_de_boton(hoja).items()
            if contraste(tono, "#ffffff") < self.MINIMO
        }
        assert not flojos, f"Botón ilegible (mínimo {self.MINIMO}:1): {flojos}"

    def test_el_acento_crudo_no_se_usa_de_fondo_del_boton(self, hoja):
        """La regresión concreta: `background: var(--section-accent)`."""
        regla = re.search(r"\.btn-argon\s*\{([^}]*)\}", hoja).group(1)
        assert "var(--section-boton)" in regla
        assert "var(--section-accent)" not in regla


class TestLosEstadosSePintanSinJavaScript:
    def test_cada_estado_tiene_su_clase_en_la_hoja(self, hoja):
        faltan = [e for e in estados.COLORES if f".{estados.clase(e)} " not in hoja]
        assert not faltan, f"Sin color en mes.css: {faltan}"

    def test_los_colores_no_se_han_separado(self, hoja):
        """La hoja y el servidor tienen que decir lo mismo.

        El color vive en los dos sitios porque el servidor lo necesita para el
        HTML que se exporta y para las gráficas. Dos copias que nadie compara
        acaban divergiendo: ya pasó con STATUS_COLORS, que estaba duplicado en
        catalogos y en produccion y no coincidía.
        """
        for estado, color in estados.COLORES.items():
            regla = re.search(
                rf"\.{estados.clase(estado)}\s*\{{([^}}]*)\}}", hoja
            )
            assert regla, estado
            assert color in regla.group(1), f"{estado}: {color} no está en la hoja"

    def test_un_estado_raro_se_ve_igual(self):
        """Mejor un estado en gris que una etiqueta invisible."""
        assert estados.clase("Granallado") == "est-desconocido"

    def test_la_clase_tolera_las_variantes_de_escritura(self):
        assert estados.clase("Espera Armado") == estados.clase("Espera de armado")

    def test_ninguna_pantalla_inyecta_ya_el_color(self):
        """El color no puede volver a viajar en un atributo que pinta el JS.

        Mientras exista un solo `estado_color` en una plantilla, hay una
        etiqueta que desaparece si el JavaScript falla.
        """
        culpables = []
        for carpeta in ("produccion", "catalogos", "nucleo"):
            raiz = Path(settings.BASE_DIR) / carpeta / "templates"
            if not raiz.is_dir():
                continue
            for archivo in raiz.rglob("*.html"):
                for n, linea in enumerate(
                    archivo.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if "estado_color" in linea:
                        culpables.append(f"{archivo.name}:{n}")
        assert not culpables, "Estado que sólo se ve si corre el JavaScript:\n" + "\n".join(
            culpables
        )


class TestElAcentoDeAreaLoDecideElServidor:
    @pytest.mark.parametrize(
        "ruta,esperada",
        [
            ("herreria_control", "herreria"),
            ("herreria_ordenes", "herreria"),
            ("corte_laser_control", "corta"),
            # Trampa: empieza por "corte" pero es de Corta.mx. El orden de los
            # prefijos es lo único que lo distingue.
            ("corte_laser_reportes", "corta"),
            ("area_corte", "corte"),
            ("area_soldadura", "soldadura"),
            ("robotica_ordenes", "robotica"),
            ("robot_editar", "robotica"),
            ("viga_list", "estructuras"),
            ("pedidos_logistica", "pedidos"),
            ("dashboard", "reportes"),
            ("paros_motivos", "paros"),
            ("maquinas", "configuracion"),
            ("configuracion", "configuracion"),
        ],
    )
    def test_reparte_bien_las_rutas(self, ruta, esperada):
        assert seccion_de(ruta) == esperada

    def test_una_ruta_desconocida_no_revienta(self):
        assert seccion_de("una_ruta_que_no_existe") == ""
        assert seccion_de(None) == ""

    def test_toda_seccion_tiene_su_color(self, hoja):
        from produccion.context_processors import (
            SECCION_POR_PREFIJO,
            SECCION_POR_RUTA,
        )

        usadas = set(SECCION_POR_RUTA.values()) | {s for _, s in SECCION_POR_PREFIJO}
        faltan = [s for s in usadas if f'body[data-section="{s}"]' not in hoja]
        assert not faltan, f"Secciones sin acento en mes.css: {faltan}"

    def test_llega_a_la_pagina(self, django_user_model):
        persona = django_user_model.objects.create_user("mirona", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)

        pagina = cliente.get("/dashboard/").content.decode()

        assert 'data-section="reportes"' in pagina


class TestTactilPrimero:
    def test_los_botones_grandes_no_estan_encerrados_en_pantalla_ancha(self, hoja):
        """La regla tiene que valer por defecto, no sólo en la PC.

        Este es el defecto tal cual estaba: `min-width: 768px` alrededor de
        los objetivos de 44 píxeles.
        """
        # Trozo de la hoja hasta la primera media query de pantalla ancha.
        base = hoja.split("@media (min-width")[0]
        assert "--mes-touch: 44px" in base
        assert re.search(r"\.js-action-wrap \.btn,[^}]*min-height: var\(--mes-touch\)", base)

    def test_los_campos_no_provocan_zoom_en_el_celular(self, hoja):
        """Menos de 16px y iOS amplía la pantalla al enfocar el campo."""
        assert "font-size: 16px !important" in hoja


class TestLosComentariosNoSeVenEnPantalla:
    """`{# ... #}` es de una sola línea; repartido en varias, se imprime.

    No falla al desplegar ni aparece en ningún registro: sale escrito en medio
    de la página, en producción, delante del taller.
    """

    def test_ningun_comentario_se_queda_abierto(self):
        """Mira **todas** las carpetas de plantillas, no tres escritas a mano.

        Miraba sólo `produccion`, `catalogos` y `nucleo`, así que se le
        escapaban `templates/` —donde está la pantalla de entrar—, `acceso`,
        `inventario`, `costeo` y `personal`. Un guardia que sólo vigila tres
        puertas de siete da la sensación de estar cubierto sin estarlo, que es
        peor que no tenerlo.

        Y eso no es teórico: uno de estos comentarios dentro del `<head>` es
        texto suelto, así que el navegador da la cabecera por terminada y mete
        el resto —hojas de estilo incluidas— dentro del cuerpo. La página se
        descoloca entera y el motivo no se parece en nada a lo que se ve.
        """
        raiz = Path(settings.BASE_DIR)
        carpetas = sorted(
            d for d in raiz.rglob("templates")
            if d.is_dir() and ".venv" not in d.parts and "attic" not in d.parts
        )
        assert len(carpetas) >= 5, f"Se esperaban más carpetas de plantillas: {carpetas}"

        culpables = []
        for carpeta in carpetas:
            for archivo in carpeta.rglob("*.html"):
                for n, linea in enumerate(
                    archivo.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if "{#" in linea and "#}" not in linea:
                        relativa = archivo.relative_to(raiz)
                        culpables.append(f"{relativa}:{n}  {linea.strip()[:70]}")
        assert not culpables, (
            "Comentario que se va a imprimir en la página.\n"
            "Para varias líneas hay que usar {% comment %}:\n" + "\n".join(culpables)
        )


class TestLaPlantillaBaseYaNoLlevaNadaDentro:
    def test_no_quedan_estilos_ni_scripts_incrustados(self):
        base = (
            Path(settings.BASE_DIR)
            / "produccion"
            / "templates"
            / "produccion"
            / "base.html"
        ).read_text(encoding="utf-8")

        assert "<style>" not in base
        # Los `<script src=...>` sí; lo que no puede volver es el código
        # escrito dentro de la plantilla.
        assert not re.search(r"<script>\s*\n", base)
