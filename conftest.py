"""Configuración compartida de la suite de tests."""

import pytest
from django.conf import settings
from django.db import connections

RUTA_ESQUEMA_HEREDADO = "tests/sql/esquema_heredado.sql"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Deja las tablas heredadas con el esquema que tienen en producción.

    Aquí hay una trampa del proyecto que conviene explicar, porque afecta a
    la fiabilidad de toda la suite.

    `produccion.Viga` y `produccion.ProductionLog` declaran `managed = False`
    en el modelo, pero la migración 0001 las creó como tablas normales y la
    0002 se limitó a cambiar las opciones, que es una operación de sólo
    estado. Resultado: al montar cualquier base nueva, Django **sí** crea
    `vigas` y `production_log`, y las crea con su propio esquema, que no es
    el de producción. Por ejemplo `internal_id` queda como columna de
    identidad en vez de un integer con `nextval`, y los textos quedan como
    varchar(40) en vez de text.

    Un test que pase contra ese esquema no demuestra que el código funcione
    contra el real. Así que se tiran las tablas que creó Django y se cargan
    desde tests/sql/esquema_heredado.sql, que es un volcado del esquema de
    verdad y, de paso, su única documentación escrita.
    """
    with django_db_blocker.unblock():
        nombre_base = connections["mes"].settings_dict["NAME"]

        # Salvaguarda: esto hace DROP TABLE. Si por una configuración mal
        # puesta la conexión apuntara a la base real, aquí se para.
        if not nombre_base.startswith("test_"):
            raise RuntimeError(
                f"La suite iba a modificar la base «{nombre_base}», que no es de pruebas. "
                "Se aborta. Revisar DJANGO_SETTINGS_MODULE y las variables MES_DB_*."
            )

        sql = (settings.BASE_DIR / RUTA_ESQUEMA_HEREDADO).read_text(encoding="utf-8")
        with connections["mes"].cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS public.production_log CASCADE")
            cur.execute("DROP TABLE IF EXISTS public.vigas CASCADE")
            cur.execute(sql)


@pytest.fixture
def cliente_anonimo(client):
    """Cliente sin sesión iniciada."""
    return client


def _crear_usuario(django_user_model, nombre, grupos=(), staff=False, superusuario=False):
    from django.contrib.auth.models import Group

    usuario = django_user_model.objects.create_user(
        username=nombre, password="prueba", is_staff=staff, is_superuser=superusuario
    )
    for nombre_grupo in grupos:
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        usuario.groups.add(grupo)
    return usuario


# Los seis perfiles que existen de verdad en el sistema. La lista sale de los
# grupos que comprueban las vistas, no de una invención: admin_general,
# herreria, corte_laser, robotica, corte, soldadura y pedidos_ventas.
PERFILES = {
    "admin": {"grupos": ["admin_general"]},
    "herreria": {"grupos": ["herreria"]},
    "corte_laser": {"grupos": ["corte_laser"]},
    "robotica": {"grupos": ["robotica"]},
    "corte": {"grupos": ["corte"]},
    "soldadura": {"grupos": ["soldadura"]},
    "pedidos": {"grupos": ["pedidos_ventas"]},
    "sin_grupo": {"grupos": []},
}


@pytest.fixture
def crear_usuario(db, django_user_model):
    """Fábrica de usuarios por perfil."""

    def _fabrica(perfil="admin", nombre=None):
        if perfil not in PERFILES:
            raise ValueError(f"perfil desconocido: {perfil}")
        return _crear_usuario(
            django_user_model,
            nombre or f"prueba_{perfil}",
            grupos=PERFILES[perfil]["grupos"],
        )

    return _fabrica


@pytest.fixture
def cliente_como(client, crear_usuario):
    """Devuelve un cliente con sesión iniciada para el perfil pedido."""

    def _fabrica(perfil="admin"):
        usuario = crear_usuario(perfil)
        client.force_login(usuario)
        return client

    return _fabrica
