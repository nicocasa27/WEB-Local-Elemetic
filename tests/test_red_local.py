"""Que el sistema abra desde las demás computadoras del taller.

El fallo que motiva estos tests: `ALLOWED_HOSTS` traía escrita a mano la IP del
servidor del taller, `192.168.50.92`. En cualquier otra máquina -y en el propio
taller el día que le cambiara la IP- Django contestaba **400** a todo lo que no
viniera por `localhost`. Desde el servidor abría bien; desde las demás
computadoras, no. Eso se parece tanto a un problema de firewall que es por ahí
por donde se busca, y no está ahí.

Peor: la dirección que el propio instalador anuncia al terminar usa el *nombre*
de la máquina, y el nombre tampoco estaba en la lista. O sea que la única
dirección que el sistema reparte era justamente una de las que rechazaba.
"""

import ast
import importlib
import socket

import pytest
from django.conf import settings
from django.http.request import validate_host

from mes_vigas_web.settings.base import nombres_de_esta_maquina


class TestNombresDeEstaMaquina:
    def test_trae_el_nombre_del_equipo(self):
        """Es la dirección que reparte el instalador, así que tiene que estar."""
        assert socket.gethostname().lower() in nombres_de_esta_maquina()

    def test_todo_en_minusculas(self):
        """Django compara los patrones tal cual: uno con mayúsculas no casa.

        En Windows el nombre del equipo suele venir en mayúsculas, así que sin
        esto el nombre de la máquina daría 400 justo donde el sistema corre.
        """
        nombres = nombres_de_esta_maquina()
        assert nombres == [n.lower() for n in nombres]

    def test_trae_alguna_ip_de_verdad(self):
        """No sólo 127.0.0.1: desde otra computadora esa dirección no sirve."""
        direcciones = [
            n
            for n in nombres_de_esta_maquina()
            if n.replace(".", "").isdigit() and not n.startswith("127.")
        ]
        assert direcciones, (
            "No se encontró ninguna IP de red. Sin eso, entrar por la IP desde "
            "otra computadora del taller da 400."
        )

    def test_no_cuela_el_nombre_inverso(self):
        """`getfqdn` a veces devuelve «1.0.0.127.in-addr.arpa». Es basura."""
        assert not [n for n in nombres_de_esta_maquina() if n.endswith(".in-addr.arpa")]

    def test_no_revienta_sin_red(self, monkeypatch):
        """Un servidor que no arranca es peor que uno al que le falta un alias."""
        def sin_red(*args, **kwargs):
            raise OSError("la red está caída")

        monkeypatch.setattr(socket, "getaddrinfo", sin_red)
        monkeypatch.setattr(socket, "getfqdn", sin_red)
        monkeypatch.setattr(socket, "socket", sin_red)

        assert socket.gethostname().lower() in nombres_de_esta_maquina()


class TestNoHayIpEscritaAMano:
    """La IP del taller no puede volver a estar en el código.

    Es el defecto original: funciona en una máquina y en ninguna otra, y no
    avisa. Si algún día hace falta fijarla, se pone en `.env` con
    `DJANGO_ALLOWED_HOSTS`, que es donde se mira cuando algo no abre.
    """

    @pytest.mark.parametrize("modulo", ["base", "dev", "prod"])
    def test_ninguna_configuracion_la_lleva_dentro(self, modulo):
        ruta = settings.BASE_DIR / "mes_vigas_web" / "settings" / f"{modulo}.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))

        # En un comentario o en una explicación de por qué se quitó, bien. En
        # una cadena que el código use, no: eso es la avería.
        docs = set()
        for nodo in ast.walk(arbol):
            cuerpo = getattr(nodo, "body", None)
            if isinstance(cuerpo, list) and cuerpo and isinstance(cuerpo[0], ast.Expr):
                docs.add(id(cuerpo[0].value))
        culpables = [
            nodo.value
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.Constant)
            and isinstance(nodo.value, str)
            and "192.168.50.92" in nodo.value
            and id(nodo) not in docs
        ]
        assert not culpables, f"IP del taller escrita a mano en {modulo}.py: {culpables}"


class TestSeAceptaLaPeticionDeOtraComputadora:
    """Contra la configuración de verdad, no contra la de los tests.

    `settings/test.py` tiene su propia lista, así que hacer una petición con el
    cliente de pruebas no demostraría nada sobre lo que corre en el taller.
    """

    @pytest.mark.parametrize("nombre", nombres_de_esta_maquina())
    def test_dev_la_acepta(self, nombre):
        dev = importlib.reload(importlib.import_module("mes_vigas_web.settings.dev"))
        assert validate_host(nombre, dev.ALLOWED_HOSTS), (
            f"Entrar por «{nombre}» daría 400. Desde otra computadora del "
            "taller eso se ve como que el sistema no abre."
        )

    @pytest.mark.parametrize("nombre", nombres_de_esta_maquina())
    def test_prod_la_acepta(self, nombre, monkeypatch):
        monkeypatch.setenv("DJANGO_SECRET_KEY", "para-la-prueba")
        monkeypatch.setenv("MES_DB_PASSWORD", "para-la-prueba")
        prod = importlib.reload(importlib.import_module("mes_vigas_web.settings.prod"))
        assert validate_host(nombre, prod.ALLOWED_HOSTS)
        assert f"http://{nombre}:8501" in prod.CSRF_TRUSTED_ORIGINS
