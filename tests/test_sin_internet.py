"""El taller tiene que poder trabajar con el internet caído.

Hasta ahora Bootstrap, los iconos, las gráficas y el generador de códigos QR
se descargaban de un CDN en cada carga de página, y no había ni un solo
archivo de estilos o de JavaScript propio en el proyecto. Sin red, la
aplicación se veía sin formato y sin ningún botón que funcionara: el taller no
podía trabajar. Peor todavía, la exportación de reportes descargaba esos
archivos **durante la petición**, con quince segundos de espera, así que un
corte de internet no dejaba la página fea: la dejaba colgada.

Estos tests son una guardia estructural. No comprueban que la página se vea
bien —eso se mira con los ojos—, comprueban que no haya vuelto a entrar una
dependencia de un servidor ajeno, que es un defecto que desde el navegador de
la oficina, con internet, es literalmente invisible.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

#: Cualquier `src=` o `href=` que apunte fuera del servidor del taller.
EXTERNO = re.compile(r'(?:src|href)\s*=\s*["\'](https?:)?//[^"\']+', re.IGNORECASE)

#: Las carpetas de plantillas del proyecto.
PLANTILLAS = [
    Path(settings.BASE_DIR) / "produccion" / "templates",
    Path(settings.BASE_DIR) / "catalogos" / "templates",
    Path(settings.BASE_DIR) / "nucleo" / "templates",
    Path(settings.BASE_DIR) / "templates",
]

#: Lo que antes venía de jsdelivr y ahora vive en el proyecto.
DEL_PROYECTO = [
    "vendor/bootstrap/css/bootstrap.min.css",
    "vendor/bootstrap/js/bootstrap.bundle.min.js",
    "vendor/bootstrap-icons/bootstrap-icons.min.css",
    "vendor/bootstrap-icons/fonts/bootstrap-icons.woff2",
    "vendor/bootstrap-icons/fonts/bootstrap-icons.woff",
    "vendor/chartjs/chart.umd.min.js",
    "vendor/qrcode/qrcode.min.js",
]


def _plantillas():
    for carpeta in PLANTILLAS:
        if carpeta.is_dir():
            yield from carpeta.rglob("*.html")


class TestNingunaPlantillaPideNadaDeFuera:
    def test_no_queda_ni_una_referencia_externa(self):
        culpables = []
        for archivo in _plantillas():
            for linea, texto in enumerate(
                archivo.read_text(encoding="utf-8").splitlines(), 1
            ):
                if EXTERNO.search(texto):
                    culpables.append(f"{archivo.name}:{linea}  {texto.strip()[:90]}")
        assert not culpables, "Recursos servidos desde fuera:\n" + "\n".join(culpables)

    @pytest.mark.parametrize("ruta", DEL_PROYECTO)
    def test_el_archivo_esta_en_el_disco(self, ruta):
        """Que la plantilla lo pida en local no sirve si nadie lo descargó."""
        assert finders.find(ruta), f"Falta {ruta} en produccion/static/"


class TestLasPaginasSeSirvenSolas:
    """Lo que de verdad importa: lo que llega al navegador."""

    @pytest.fixture
    def navegador(self, django_user_model):
        persona = django_user_model.objects.create_user("operador", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        return cliente

    def test_el_login_no_depende_de_internet(self):
        """La pantalla de entrada es la primera que se ve y la más grave.

        Si sólo ésta se rompiera, nadie podría ni siquiera reportar el fallo.
        """
        pagina = Client(SERVER_NAME="127.0.0.1").get(reverse("login")).content.decode()
        assert not EXTERNO.search(pagina)

    def test_el_menu_principal_no_depende_de_internet(self, navegador):
        pagina = navegador.get("/").content.decode()
        assert not EXTERNO.search(pagina)

    def test_bootstrap_se_sirve_de_verdad(self, navegador):
        """Que el enlace apunte a casa y que en casa haya algo que servir."""
        respuesta = navegador.get("/static/vendor/bootstrap/css/bootstrap.min.css")
        assert respuesta.status_code == 200

    def test_los_iconos_encuentran_su_tipografia(self):
        """El CSS de los iconos pide las fuentes por una ruta relativa.

        Si la carpeta `fonts/` no queda al lado del CSS, la página carga sin
        un solo icono y con los botones descolocados.
        """
        css = Path(finders.find("vendor/bootstrap-icons/bootstrap-icons.min.css"))
        for destino in set(re.findall(r'url\(["\']?([^"\')?]+)', css.read_text())):
            assert (css.parent / destino).is_file(), destino


class TestLaExportacionNoSaleAInternet:
    """El reporte descargable se abre fuera de la aplicación, sin servidor."""

    def test_incrusta_los_estilos_y_las_fuentes(self):
        from produccion.views import _inline_html_assets

        html = _inline_html_assets(
            '<link href="/static/vendor/bootstrap-icons/bootstrap-icons.min.css"'
            ' rel="stylesheet">'
        )

        assert "<style>" in html
        # Las fuentes van dentro del CSS: una ruta relativa no resolvería al
        # abrir el archivo desde el escritorio o desde un correo.
        assert "data:font/woff2;base64," in html
        assert "url(fonts/" not in html

    def test_incrusta_el_javascript(self):
        from produccion.views import _inline_html_assets

        html = _inline_html_assets('<script src="/static/vendor/chartjs/chart.umd.min.js"></script>')

        assert "<script>" in html
        assert len(html) > 100_000, "no se leyó el archivo"
        # Un `</script>` dentro del código cerraría la etiqueta y partiría el
        # archivo exportado por la mitad.
        assert html.count("</script>") == 1

    def test_no_revienta_si_el_archivo_no_existe(self):
        """Un reporte a medias es mejor que un error 500 al exportar."""
        from produccion.views import _inline_html_assets

        original = '<script src="/static/no/existe.js"></script>'
        assert _inline_html_assets(original) == original
