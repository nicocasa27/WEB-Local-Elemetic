"""Averigua si algo ajeno a esta aplicación escribe en la tabla `vigas`.

Por qué importa: `produccion.Viga` es `managed = False` sobre las tablas
heredadas `vigas` y `production_log`, es decir, Django no controla su esquema
y no sabe quién más las toca. Si resulta que otro programa, una macro de Excel
o un script suelto escriben ahí, la unificación del núcleo de producción
necesita un disparador en PostgreSQL que replique esos cambios, o esa línea
tendrá que quedarse fuera de la migración.

Conviene saberlo ahora y no a mitad de la migración, que es cuando duele.

Este comando hay que ejecutarlo **en el servidor del taller**, contra la base
real, y con el sistema en uso normal:

    python manage.py diagnosticar_vigas

Para ver quién está conectado ahora mismo conviene repetirlo en distintos
momentos del día.
"""
from django.core.management.base import BaseCommand
from django.db import connections

CONSULTAS = [
    (
        "Disparadores sobre vigas y production_log",
        """
        SELECT c.relname || ' -> ' || t.tgname
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relname IN ('vigas', 'production_log') AND NOT t.tgisinternal
        """,
    ),
    (
        "Reglas sobre esas tablas",
        "SELECT tablename || ' -> ' || rulename FROM pg_rules WHERE tablename IN ('vigas','production_log')",
    ),
    (
        "Vistas que las referencian",
        """
        SELECT schemaname || '.' || viewname
        FROM pg_views
        WHERE schemaname NOT IN ('pg_catalog','information_schema')
          AND (definition ILIKE '%vigas%' OR definition ILIKE '%production_log%')
        """,
    ),
    (
        "Claves foráneas que apuntan a vigas",
        """
        SELECT conrelid::regclass || '.' || conname
        FROM pg_constraint
        WHERE confrelid = 'public.vigas'::regclass
        """,
    ),
    (
        "Roles con permiso de escritura sobre vigas",
        """
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_name = 'vigas' AND privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')
        """,
    ),
    (
        "Roles que pueden iniciar sesión en el servidor",
        "SELECT rolname FROM pg_roles WHERE rolcanlogin ORDER BY rolname",
    ),
    (
        "Conexiones abiertas ahora mismo (aplicación, usuario, origen)",
        """
        SELECT coalesce(application_name,'(sin nombre)') || ' | ' || usename || ' | ' ||
               coalesce(host(client_addr)::text,'local') || ' | ' || state
        FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
        ORDER BY usename
        """,
    ),
    (
        "Escrituras acumuladas por tabla (inserciones/actualizaciones/borrados)",
        """
        SELECT relname || ': ins=' || n_tup_ins || ' upd=' || n_tup_upd || ' del=' || n_tup_del
        FROM pg_stat_user_tables
        WHERE relname IN ('vigas','production_log')
        """,
    ),
]


class Command(BaseCommand):
    help = "Busca indicios de escritores externos sobre las tablas heredadas vigas y production_log."

    def handle(self, *args, **opciones):
        with connections["mes"].cursor() as cur:
            for titulo, sql in CONSULTAS:
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n{titulo}"))
                try:
                    cur.execute(sql)
                    filas = cur.fetchall()
                except Exception as e:  # noqa: BLE001 - se informa y se sigue
                    self.stdout.write(self.style.ERROR(f"  no se pudo consultar: {e}"))
                    continue
                if not filas:
                    self.stdout.write("  (ninguno)")
                for fila in filas:
                    self.stdout.write(f"  {fila[0]}")

        self.stdout.write(
            self.style.WARNING(
                "\nCómo leer esto:\n"
                "  - Disparadores, reglas o claves foráneas inesperadas: hay que tenerlos\n"
                "    en cuenta antes de migrar la línea de vigas.\n"
                "  - Roles de escritura o conexiones distintos de los del servidor web:\n"
                "    hay otro programa tocando la tabla. Averiguar cuál antes de seguir.\n"
                "  - Conviene repetir la consulta de conexiones a distintas horas."
            )
        )
