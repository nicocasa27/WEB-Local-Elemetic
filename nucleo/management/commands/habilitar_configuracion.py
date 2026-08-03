"""Deja que el taller configure el sistema sin depender de nadie.

Este comando existe porque al montar los módulos nuevos aparecieron dos huecos
que hacían imposible que el propio taller los configurara:

**Los usuarios que administran no podían entrar al administrador.** Siete de
los ocho usuarios del grupo `admin_general` no tienen `is_staff`, así que la
aplicación les enseña el enlace «Admin» en el menú y al pulsarlo los rechaza.
Llevaba así desde siempre; se notó ahora porque hasta ahora no había nada que
configurar ahí.

**Las aplicaciones nuevas no tenían permisos.** Django crea los permisos de
cada modelo al migrar, pero sólo en la base donde vive `auth`. Como el
enrutador manda `nucleo`, `inventario` y `costeo` a PostgreSQL y la
autenticación sigue en SQLite, esos permisos no se crearon en ninguna parte. Y
sin permisos no se le puede dar acceso a nadie que no sea superusuario: la
única forma de configurar sería crear superusuarios, que es exactamente lo que
no se debe hacer.

Lo que hace:

1. Crea los permisos que faltan de `nucleo`, `inventario` y `costeo`.
2. Crea el grupo «configuracion» con **sólo** esos permisos, más los catálogos
   de planta. No incluye usuarios ni contraseñas: quien configura tarifas no
   tiene por qué poder crear cuentas.
3. Pone `is_staff` a los usuarios de `admin_general` y los mete en el grupo.

    python manage.py habilitar_configuracion --simular
    python manage.py habilitar_configuracion
    python manage.py habilitar_configuracion --quitar

Es reversible: `--quitar` deshace el acceso sin borrar el grupo ni los
permisos.
"""

from django.apps import apps
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

#: La autenticación vive aquí mientras las dos bases sigan separadas.
AUTH = "default"

GRUPO = "configuracion"

#: Aplicaciones cuya configuración se delega al taller.
APLICACIONES = ["nucleo", "inventario", "costeo"]

#: Modelos de la aplicación heredada que también hacen falta para configurar:
#: máquinas, colaboradores, equipos y los catálogos de motivos.
MODELOS_HEREDADOS = [
    ("catalogos", "maquina"),
    ("catalogos", "colaborador"),
    ("catalogos", "equipotrabajo"),
    ("catalogos", "maquinaparomotivo"),
    ("catalogos", "maquinafallatipo"),
    ("catalogos", "proyecto"),
]

#: Quién debe poder configurar.
GRUPOS_QUE_CONFIGURAN = ["admin_general", "ingenieria_civil"]


class Command(BaseCommand):
    help = "Crea los permisos que faltan y da acceso al administrador a quien configura."

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="No escribe nada.")
        parser.add_argument(
            "--quitar",
            action="store_true",
            help="Retira el acceso: quita is_staff y saca del grupo.",
        )

    def handle(self, *args, **opciones):
        self.simular = opciones["simular"]
        if self.simular:
            self.stdout.write(self.style.WARNING("Simulación: no se escribe nada.\n"))

        with transaction.atomic(using=AUTH):
            if opciones["quitar"]:
                self._quitar()
            else:
                creados = self._crear_permisos()
                grupo = self._grupo()
                self._usuarios(grupo)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\n  {creados} permiso(s) creados. El taller ya puede configurar\n"
                        "  desde /configuracion/ y desde /admin/."
                    )
                )
            if self.simular:
                transaction.set_rollback(True, using=AUTH)

    # --------------------------------------------------------- permisos

    def _crear_permisos(self):
        """Crea a mano los permisos de las aplicaciones enrutadas a PostgreSQL.

        Se hace explícitamente en vez de llamar a la rutina de Django porque
        ésa da por supuesto que los modelos y la tabla de permisos viven en la
        misma base, y aquí no es el caso. Cuando las dos bases se unifiquen
        esto dejará de hacer falta y se podrá borrar.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("Permisos"))
        creados = 0

        for etiqueta in APLICACIONES:
            configuracion = apps.get_app_config(etiqueta)
            for modelo in configuracion.get_models():
                tipo, _ = ContentType.objects.using(AUTH).get_or_create(
                    app_label=etiqueta, model=modelo._meta.model_name
                )
                opciones = modelo._meta
                for accion in opciones.default_permissions:
                    _, nuevo = Permission.objects.using(AUTH).get_or_create(
                        content_type=tipo,
                        codename=get_permission_codename(accion, opciones),
                        defaults={"name": f"Can {accion} {opciones.verbose_name_raw}"[:255]},
                    )
                    creados += int(nuevo)

        self.stdout.write(f"  {creados} permiso(s) nuevos")
        return creados

    # ----------------------------------------------------------- grupo

    def _grupo(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nGrupo «configuracion»"))
        grupo, creado = Group.objects.using(AUTH).get_or_create(name=GRUPO)

        permisos = list(
            Permission.objects.using(AUTH).filter(content_type__app_label__in=APLICACIONES)
        )
        for etiqueta, modelo in MODELOS_HEREDADOS:
            permisos.extend(
                Permission.objects.using(AUTH).filter(
                    content_type__app_label=etiqueta, content_type__model=modelo
                )
            )

        grupo.permissions.set(permisos)
        self.stdout.write(
            f"  {'creado' if creado else 'actualizado'}, {len(permisos)} permiso(s)\n"
            "  No incluye usuarios ni contraseñas: quien captura una tarifa no tiene\n"
            "  por qué poder crear cuentas."
        )
        return grupo

    # -------------------------------------------------------- usuarios

    def _usuarios(self, grupo):
        self.stdout.write(self.style.MIGRATE_HEADING("\nAcceso al administrador"))
        usuarios = User.objects.using(AUTH).filter(
            groups__name__in=GRUPOS_QUE_CONFIGURAN, is_active=True
        ).distinct()

        if not usuarios:
            self.stdout.write(
                self.style.WARNING(
                    "  Ningún usuario en " + " ni ".join(GRUPOS_QUE_CONFIGURAN) + "."
                )
            )
            return

        for usuario in usuarios:
            cambios = []
            if not usuario.is_staff:
                usuario.is_staff = True
                usuario.save(using=AUTH, update_fields=["is_staff"])
                cambios.append("puede entrar al administrador")
            if not usuario.groups.filter(name=GRUPO).exists():
                usuario.groups.add(grupo)
                cambios.append("añadido al grupo")
            self.stdout.write(
                f"  {usuario.username:<14} " + (", ".join(cambios) or "ya lo tenía")
            )

    # --------------------------------------------------------- retirar

    def _quitar(self):
        self.stdout.write(self.style.MIGRATE_HEADING("Retirando el acceso"))
        grupo = Group.objects.using(AUTH).filter(name=GRUPO).first()
        if grupo is None:
            self.stdout.write("  no estaba habilitado")
            return

        for usuario in User.objects.using(AUTH).filter(groups=grupo).distinct():
            # A los superusuarios no se les toca `is_staff`: quitárselo los
            # dejaría fuera del administrador sin que nadie pudiera volver a
            # entrar a arreglarlo.
            if not usuario.is_superuser and usuario.is_staff:
                usuario.is_staff = False
                usuario.save(using=AUTH, update_fields=["is_staff"])
            usuario.groups.remove(grupo)
            self.stdout.write(f"  {usuario.username}: acceso retirado")

        self.stdout.write(
            "\n  El grupo y los permisos se quedan: volver a habilitarlo es "
            "ejecutar el comando sin --quitar."
        )
