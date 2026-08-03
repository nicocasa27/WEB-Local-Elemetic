"""Guardias estructurales: propiedades del código, no funcionalidades.

Estos tests no comprueban que el sistema haga bien su trabajo. Comprueban que
no vuelva a entrar la clase de defecto que ya causó daño real, y por eso son
los primeros de la suite: cada uno cierra una familia entera de errores en vez
de un caso concreto.

Los tres corresponden a defectos encontrados y corregidos en la fase de
estabilización.
"""

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import get_resolver

pytestmark = pytest.mark.guardia

MODULOS_VIGILADOS = ["catalogos/views.py", "produccion/views.py"]

# Rutas que por definición no pueden exigir sesión iniciada.
EXENTAS_DE_SESION = {
    "login",
    "logout",
    "password_reset",
    "password_reset_done",
    "password_reset_confirm",
    "password_reset_complete",
}


def _arbol(ruta_relativa):
    ruta = Path(settings.BASE_DIR) / ruta_relativa
    return ast.parse(ruta.read_text(encoding="utf-8")), ruta


RELLENO_PARAMETROS = {"pk": "1", "colab_id": "1", "etapa": "Corte", "ruta": "x.pdf"}


def rutas_propias():
    """Todas las rutas del código propio, con los parámetros ya rellenados.

    Se descartan admin y auth de Django: traen su propia protección y no son
    responsabilidad de este proyecto.
    """
    encontradas = []
    for patron in get_resolver().url_patterns:
        prefijo = str(getattr(patron, "pattern", ""))
        for sub in getattr(patron, "url_patterns", [patron]):
            callback = getattr(sub, "callback", None)
            if callback is None:
                continue
            if not getattr(callback, "__module__", "").startswith(
                ("catalogos.", "produccion.", "mes_vigas_web.")
            ):
                continue

            cruda = prefijo + str(getattr(sub, "pattern", ""))
            url = "/" + cruda.lstrip("/")
            # path() usa <int:pk>; re_path() usa (?P<ruta>...)
            for clave, valor in RELLENO_PARAMETROS.items():
                url = re.sub(rf"<[^:>]*:?{clave}>", valor, url)
                url = re.sub(rf"\(\?P<{clave}>[^)]*\)", valor, url)
            url = re.sub(r"<[^>]+>", "1", url)
            url = re.sub(r"\(\?P<[^>]+>[^)]*\)", "1", url)
            url = url.replace("^", "").replace("$", "")

            if "<" in url or "(?P" in url:
                continue
            encontradas.append((getattr(sub, "name", None), url))
    return sorted(set(encontradas), key=lambda x: x[1])


@pytest.mark.django_db(databases=["default", "mes"])
def test_ninguna_vista_propia_responde_a_un_anonimo(client):
    """Trece vistas estaban ruteadas sin comprobar la sesión.

    Entre ellas los borrados de equipos, colaboradores y maquinaria. La
    cadena de ataque no necesitaba credenciales: un GET público devolvía el
    token CSRF y con él se podía borrar por POST.

    Esta comprobación es funcional a propósito. La versión por introspección
    (buscar `login_required` entre los decoradores) daba un falso negativo:
    `require_http_methods` también envuelve la función y deja los mismos
    rastros, así que las trece vistas desprotegidas habrían pasado en verde.
    Se comprueba lo único que importa de verdad: que un anónimo no obtenga
    contenido.
    """
    filtradas = []
    for nombre, url in rutas_propias():
        if nombre in EXENTAS_DE_SESION:
            continue
        respuesta = client.get(url)
        if respuesta.status_code == 200:
            filtradas.append(f"{nombre or '(sin nombre)'}  {url}")

    assert not filtradas, (
        "Estas rutas devuelven contenido a un usuario sin sesión:\n  " + "\n  ".join(filtradas)
    )


@pytest.mark.parametrize("ruta_modulo", MODULOS_VIGILADOS)
def test_las_transacciones_indican_siempre_la_base(ruta_modulo):
    """`transaction.atomic()` sin `using` abre la transacción sobre SQLite.

    El proyecto guarda los datos de negocio en PostgreSQL (`mes`) y sólo la
    autenticación en SQLite (`default`). Un bloque sin `using` que escriba en
    Postgres no tiene atomicidad ninguna: si falla a la mitad, lo escrito se
    queda escrito. Afectaba a nueve bloques, cinco de ellos borrados en
    cascada del Decote.
    """
    arbol, ruta = _arbol(ruta_modulo)
    culpables = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        f = nodo.func
        es_atomic = (
            isinstance(f, ast.Attribute)
            and f.attr == "atomic"
            and isinstance(f.value, ast.Name)
            and f.value.id == "transaction"
        )
        if es_atomic and not (any(k.arg == "using" for k in nodo.keywords) or nodo.args):
            culpables.append(nodo.lineno)

    assert not culpables, (
        f"{ruta_modulo}: transaction.atomic() sin `using` en las líneas {culpables}. "
        'Los datos de negocio viven en la base "mes".'
    )


@pytest.mark.parametrize("ruta_modulo", MODULOS_VIGILADOS + ["mes_vigas_web/middleware.py"])
def test_ningun_except_se_traga_el_error_en_silencio(ruta_modulo):
    """Un `except` cuyo cuerpo es sólo `pass` hace desaparecer el error.

    Había diecisiete. Sin configuración de registro, además, no quedaba
    rastro en ningún sitio, así que un fallo en producción era literalmente
    invisible. Ahora todos registran la traza.
    """
    arbol, _ = _arbol(ruta_modulo)
    silenciosos = [
        manejador.lineno
        for manejador in ast.walk(arbol)
        if isinstance(manejador, ast.ExceptHandler)
        and len(manejador.body) == 1
        and isinstance(manejador.body[0], ast.Pass)
    ]
    assert not silenciosos, (
        f"{ruta_modulo}: `except` con sólo `pass` en las líneas {silenciosos}. "
        "Registrar la excepción con logger.exception()."
    )


@pytest.mark.parametrize("ruta_modulo", MODULOS_VIGILADOS)
def test_ningun_bloque_queda_sobreindentado(ruta_modulo):
    """Un cuerpo indentado de más suele ser un `else` colgado del `if` que no era.

    Es el rastro que dejó la limpieza de artefactos de tool-calls sobre
    catalogos/views.py: al borrar líneas de en medio, el cuerpo conservó la
    indentación profunda y la sentencia que lo encabeza quedó un nivel más
    afuera. Python no protesta, porque la indentación sigue siendo coherente
    dentro del bloque, pero la condición de la que cuelga cambió.

    Así se colaron seis defectos, entre ellos el que hacía imposible
    registrar un paro de máquina.
    """
    arbol, ruta = _arbol(ruta_modulo)
    lineas = ruta.read_text(encoding="utf-8").split("\n")
    sospechosos = []

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
            continue

        bloques = [(nodo.body, nodo.col_offset)]
        orelse = getattr(nodo, "orelse", None)
        if orelse:
            for k in range(orelse[0].lineno - 2, nodo.lineno - 2, -1):
                if k < 0:
                    break
                if lineas[k].strip().startswith(("else:", "elif ")):
                    bloques.append((orelse, len(lineas[k]) - len(lineas[k].lstrip())))
                    break

        for cuerpo, col_control in bloques:
            if cuerpo and cuerpo[0].col_offset > col_control + 4:
                sospechosos.append(cuerpo[0].lineno)

    assert not sospechosos, (
        f"{ruta_modulo}: cuerpos indentados de más en las líneas {sorted(sospechosos)}. "
        "Revisar de qué condición cuelgan en realidad."
    )
