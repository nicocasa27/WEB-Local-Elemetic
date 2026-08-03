"""Recorre todas las rutas con cada perfil de usuario y exige que ninguna reviente.

Es el test de mayor rendimiento de la suite en un proyecto sin cobertura: no
comprueba que los resultados sean correctos, pero atraviesa miles de líneas de
vistas y detecta al instante cualquier `NameError`, `AttributeError`, consulta
mal formada o plantilla rota introducida en un refactor.

Sirve de red durante toda la extracción de la capa de servicios: mientras esto
siga en verde, ningún cambio ha dejado una pantalla inservible.

Lo que se afirma es deliberadamente modesto: **nunca un 5xx**. Un 200, un 302
a login, un 403 o un 404 son todos resultados legítimos según el perfil y según
si el objeto de relleno existe.
"""

import pytest

from tests.test_guardias import rutas_propias

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

PERFILES_A_PROBAR = [
    "admin",
    "herreria",
    "corte_laser",
    "robotica",
    "corte",
    "soldadura",
    "pedidos",
    "sin_grupo",
]

# Rutas que cambian datos o generan archivos pesados y no aportan nada al
# recorrerlas con GET.
RUTAS_OMITIDAS = {
    "/accounts/logout/",
}


def _rutas():
    return [(n, u) for n, u in rutas_propias() if u not in RUTAS_OMITIDAS]


@pytest.mark.parametrize("perfil", PERFILES_A_PROBAR)
def test_ninguna_ruta_devuelve_error_de_servidor(perfil, cliente_como):
    """Con cualquier perfil, ninguna pantalla debe terminar en 5xx."""
    cliente = cliente_como(perfil)
    fallos = []

    for nombre, url in _rutas():
        try:
            respuesta = cliente.get(url)
        except Exception as e:  # noqa: BLE001 - el objetivo es cazarlas todas
            fallos.append(f"{url}  ->  {type(e).__name__}: {e}")
            continue
        if respuesta.status_code >= 500:
            fallos.append(f"{url}  ->  HTTP {respuesta.status_code}")

    assert not fallos, (
        f"Con el perfil «{perfil}» estas rutas fallan:\n  " + "\n  ".join(fallos)
    )


def test_el_recorrido_cubre_las_pantallas_principales():
    """Evita que el recorrido se quede vacío por un cambio en el enrutado.

    Sin esto, un fallo al construir la lista de rutas convertiría el smoke en
    un test que no prueba nada y sigue en verde.
    """
    urls = {u for _, u in _rutas()}
    imprescindibles = [
        "/",
        "/vigas/",
        "/dashboard/",
        "/catalogos/herreria/control/",
        "/catalogos/corte-laser/control/",
        "/catalogos/robotica/",
        "/catalogos/pedidos/logistica/",
        "/catalogos/paros/",
    ]
    faltan = [u for u in imprescindibles if u not in urls]
    assert not faltan, f"El recorrido no incluye pantallas principales: {faltan}"
    assert len(urls) >= 90, f"Sólo se recogieron {len(urls)} rutas; se esperaban 90 o más."
