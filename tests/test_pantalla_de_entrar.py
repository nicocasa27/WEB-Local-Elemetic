"""La pantalla de entrar: centrada, a la medida de la pantalla, y que lleve a donde ibas.

Tres cosas estaban mal a la vez y las tres se veían igual —«la tarjeta no está
centrada»—, que es lo que hace que este tipo de fallo cueste tanto:

1. La pantalla vivía dentro del armazón de la aplicación, que reserva 15.5rem a
   la izquierda para la barra lateral. Aquí no hay barra lateral, pero el hueco
   seguía ahí: todo salía 124 píxeles corrido a la derecha.
2. El velo oscuro era un bloque dentro del contenido, así que no llegaba a los
   bordes y se veía el rectángulo con la foto sin oscurecer alrededor.
3. El velo pedía 100vh **más** el relleno del contenedor, así que la página
   medía más que la ventana y salía una barra de desplazamiento para nada.

Y un cuarto, que no era de diseño: `next` estaba escrito a mano como «/», así
que quien abría un enlace a una pantalla concreta entraba y aterrizaba en la
portada.
"""

import re

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


@pytest.fixture
def html():
    return Client().get(reverse("login")).content.decode()


class TestNoLlevaElArmazonDeLaAplicacion:
    def test_le_quita_el_hueco_de_la_barra_lateral(self, html):
        """Sin esto la tarjeta sale corrida a la derecha y nadie sabe por qué."""
        assert "app-shell--sin-barra" in html

    def test_no_pinta_la_barra_lateral(self, html):
        """Quien está aquí no ha entrado: no hay nada a lo que navegar."""
        assert 'class="mes-lateral' not in html
        assert reverse("personal:lista") not in html

    def test_trae_su_propia_hoja_de_estilo(self, html):
        assert "css/acceso-web.css" in html

    def test_la_hoja_va_dentro_de_la_cabecera(self, html):
        """Si cae en el cuerpo, el navegador ya dio la cabecera por cerrada y
        la página se descoloca entera. Pasó, y por un comentario mal escrito."""
        cabecera = html.split("</head>", 1)[0]
        assert "css/acceso-web.css" in cabecera
        assert "--acceso-foto" in cabecera

    def test_no_quedan_estilos_sueltos_en_la_plantilla(self):
        """Todo menos la foto, que necesita la dirección que calcula Django."""
        from pathlib import Path

        from django.conf import settings

        plantilla = (
            Path(settings.BASE_DIR) / "templates" / "registration" / "login.html"
        ).read_text(encoding="utf-8")
        estilos = re.findall(r"<style>(.*?)</style>", plantilla, re.S)
        assert len(estilos) == 1
        assert "--acceso-foto" in estilos[0]


class TestSeAjustaALaPantalla:
    @pytest.fixture
    def hoja(self):
        from pathlib import Path

        from django.conf import settings

        return (
            Path(settings.BASE_DIR) / "produccion" / "static" / "css" / "acceso-web.css"
        ).read_text(encoding="utf-8")

    def test_la_tarjeta_nunca_es_mas_ancha_que_la_pantalla(self, hoja):
        assert "width: min(100%, 25rem)" in hoja

    def test_mide_la_ventana_con_dvh(self, hoja):
        """En el celular la barra del navegador se mete dentro de `vh`, así que
        con `vh` el botón de entrar queda tapado."""
        assert "100dvh" in hoja
        assert "min-height: 100vh" not in hoja

    def test_en_horizontal_se_va_arriba_en_vez_de_cortarse(self, hoja):
        """Centrado y con la mitad fuera de la pantalla es peor que arriba y
        que se pueda desplazar."""
        assert "max-height: 640px" in hoja
        assert "place-items: start center" in hoja

    def test_el_relleno_se_encoge_con_la_pantalla(self, hoja):
        assert "clamp(" in hoja

    def test_los_botones_se_pulsan_con_guantes(self, hoja):
        """Esta pantalla también se abre desde la tableta del piso."""
        assert "min-height: 3rem" in hoja

    def test_el_fondo_cubre_la_ventana_entera(self, hoja):
        """Era un bloque dentro del contenido: se veía el rectángulo."""
        assert re.search(r"\.acceso-fondo\s*\{[^}]*position:\s*fixed", hoja)
        assert re.search(r"\.acceso-fondo\s*\{[^}]*inset:\s*0", hoja)

    def test_no_usa_background_attachment_fixed(self, hoja):
        """En Safari de iPhone salta al desplazar y a veces se queda en blanco.

        Se miran sólo las reglas, no los comentarios: la hoja lo menciona para
        explicar por qué **no** se usa, y esa explicación es justo lo que hay
        que conservar.
        """
        sin_comentarios = re.sub(r"/\*.*?\*/", "", hoja, flags=re.S)
        assert "background-attachment: fixed" not in sin_comentarios


class TestLlevaADondeIbas:
    def test_conserva_la_pantalla_que_se_pedia(self):
        html = Client().get(reverse("login"), {"next": "/personal/"}).content.decode()

        campo = re.search(r'<input[^>]*name="next"[^>]*>', html).group(0)
        assert 'value="/personal/"' in campo

    def test_sin_next_va_a_la_portada(self, html):
        campo = re.search(r'<input[^>]*name="next"[^>]*>', html).group(0)
        assert 'value="/"' in campo

    def test_al_entrar_aterriza_donde_iba(self):
        persona = User.objects.create_user("jefa", password="clave12345")
        persona.groups.add(Group.objects.get_or_create(name="admin_general")[0])

        respuesta = Client().post(
            reverse("login"),
            {"username": "jefa", "password": "clave12345", "next": "/personal/"},
        )

        assert respuesta.status_code == 302
        assert respuesta["Location"] == "/personal/"

    def test_no_se_puede_mandar_a_otro_sitio(self):
        """`next` viene de la dirección, así que un enlace preparado podría
        intentar sacar a alguien fuera. Django lo valida, pero conviene que
        quede escrito que se cuenta con ello."""
        respuesta = Client().get(reverse("login"), {"next": "https://otro-sitio.mx/"})

        campo = re.search(r'<input[^>]*name="next"[^>]*>', respuesta.content.decode()).group(0)
        assert "otro-sitio" not in campo


class TestLaOtraPuerta:
    def test_ofrece_entrar_con_pin(self, html):
        """Ésta es la pantalla a la que llega la tableta de la nave, y quien
        trabaja en el piso no teclea usuario y contraseña con guantes."""
        assert reverse("acceso:teclado") in html
        assert "Cuatro dígitos" in html
