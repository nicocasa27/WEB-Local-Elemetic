"""El archivo `.env` tiene que servir para algo.

Traía un `.env.example` con todas las variables explicadas y DESPLIEGUE.md
decía que se copiara a `.env` y se editara. **Y nada lo leía.** La
configuración llamaba a `os.getenv` a secas.

Quien siguiera las instrucciones al pie de la letra escribía ahí la contraseña
de PostgreSQL, arrancaba, y el sistema se conectaba sin contraseña. El error
que sale entonces habla de autenticación, no de que el archivo se esté
ignorando, así que no lleva a ninguna parte: se acaba pensando que la
contraseña está mal.

Es justo el fallo que rompe una instalación hecha por alguien que no programa,
porque hace lo que se le dijo y no funciona.
"""

import os

import pytest

from mes_vigas_web.settings import _cargar_env


@pytest.fixture
def entorno_limpio(monkeypatch, tmp_path):
    """Un `.env` de mentira y un entorno donde se puede escribir sin consecuencias."""
    def _preparar(contenido):
        archivo = tmp_path / ".env"
        archivo.write_text(contenido, encoding="utf-8")
        # `_cargar_env` busca el archivo tres niveles por encima de su módulo.
        monkeypatch.setattr(
            "mes_vigas_web.settings.Path",
            _RutaFalsa(archivo),
        )
        return archivo
    return _preparar


class _RutaFalsa:
    """Devuelve siempre el `.env` de la prueba, venga la ruta que venga."""

    def __init__(self, destino):
        self._destino = destino

    def __call__(self, *_args, **_kwargs):
        return _Cadena(self._destino)


class _Cadena:
    def __init__(self, destino):
        self._destino = destino

    def resolve(self):
        return self

    @property
    def parent(self):
        return self

    def __truediv__(self, _otro):
        return self._destino


class TestElArchivoSeLee:
    def test_una_variable_del_archivo_llega_al_entorno(self, entorno_limpio, monkeypatch):
        monkeypatch.delenv("ZZ_PRUEBA_ENV", raising=False)
        entorno_limpio("ZZ_PRUEBA_ENV=hola\n")

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_ENV"] == "hola"

    def test_los_comentarios_y_las_lineas_vacias_no_estorban(
        self, entorno_limpio, monkeypatch
    ):
        monkeypatch.delenv("ZZ_PRUEBA_DOS", raising=False)
        entorno_limpio("# esto es un comentario\n\nZZ_PRUEBA_DOS=2\n\n")

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_DOS"] == "2"

    def test_las_comillas_se_quitan(self, entorno_limpio, monkeypatch):
        """Quien edita el archivo a mano las pone por costumbre."""
        monkeypatch.delenv("ZZ_PRUEBA_COMILLAS", raising=False)
        entorno_limpio('ZZ_PRUEBA_COMILLAS="con espacios"\n')

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_COMILLAS"] == "con espacios"

    def test_una_contrasena_con_signo_igual_no_se_parte(
        self, entorno_limpio, monkeypatch
    ):
        """Las contraseñas generadas los llevan, y partirlas la deja mal."""
        monkeypatch.delenv("ZZ_PRUEBA_CLAVE", raising=False)
        entorno_limpio("ZZ_PRUEBA_CLAVE=abc=def==\n")

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_CLAVE"] == "abc=def=="


class TestLoQueYaEstaPuestoManda:
    def test_el_entorno_gana_sobre_el_archivo(self, entorno_limpio, monkeypatch):
        """Si no, no habría forma de cambiar algo sin editar el archivo.

        El `.bat` de arranque define `MES_DB_HOST` y los tests fijan su propia
        base: si el archivo pisara eso, una máquina de pruebas acabaría
        escribiendo en la base del taller.
        """
        monkeypatch.setenv("ZZ_PRUEBA_MANDA", "el del entorno")
        entorno_limpio("ZZ_PRUEBA_MANDA=el del archivo\n")

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_MANDA"] == "el del entorno"


class TestNoSeCaeNunca:
    def test_sin_archivo_no_pasa_nada(self, monkeypatch, tmp_path):
        """Es el caso normal en una máquina de desarrollo."""
        monkeypatch.setattr(
            "mes_vigas_web.settings.Path", _RutaFalsa(tmp_path / "no-existe")
        )

        _cargar_env()  # no lanza

    def test_una_linea_sin_igual_se_salta(self, entorno_limpio, monkeypatch):
        """Un archivo a medio editar no puede impedir que el sistema arranque."""
        monkeypatch.delenv("ZZ_PRUEBA_TRAS_BASURA", raising=False)
        entorno_limpio("esto no es una variable\nZZ_PRUEBA_TRAS_BASURA=si\n")

        _cargar_env()

        assert os.environ["ZZ_PRUEBA_TRAS_BASURA"] == "si"
