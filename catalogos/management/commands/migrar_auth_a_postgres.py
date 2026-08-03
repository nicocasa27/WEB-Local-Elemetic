"""Copia usuarios, grupos y permisos de SQLite a PostgreSQL.

Es el primer paso para dejar de tener dos bases. Hoy la autenticación vive en
`db.sqlite3` y todo lo demás en PostgreSQL, lo que trae tres problemas:

- **No se puede relacionar un dato con quien lo hizo.** Django no permite
  claves foráneas entre bases distintas, así que la identidad se guarda como
  texto libre en catorce campos (`actor_username`, `registrado_por`,
  `creado_por`…). Cambiar el nombre de un usuario deja huérfano su historial,
  y nada impide que ahí se escriba cualquier cosa.
- **Hay que respaldar dos bases y cuadrarlas entre sí.** Un respaldo de
  PostgreSQL sin su SQLite correspondiente no sirve para restaurar.
- **SQLite admite un escritor a la vez.** Con el taller entero conectado, las
  sesiones son un cuello de botella que nadie ve.

No hay ninguna razón arquitectónica para esa separación: es lo que deja
`startproject` por omisión y nadie lo cambió.

Este comando **sólo copia los datos**. No cambia a qué base apunta la
aplicación: eso es un cambio de configuración aparte, que se hace en la
ventana de mantenimiento y se puede revertir. Ver DESPLIEGUE.md.

    python manage.py migrar_auth_a_postgres --simular
    python manage.py migrar_auth_a_postgres
"""
from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand
from django.db import transaction

ORIGEN = "default"
DESTINO = "mes"


class Command(BaseCommand):
    help = "Copia usuarios, grupos y sus permisos de la base default a la base mes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Enumera lo que se copiaría, sin escribir nada.",
        )

    def handle(self, *args, **opciones):
        simular = opciones["simular"]

        usuarios = list(User.objects.using(ORIGEN).all())
        grupos = list(Group.objects.using(ORIGEN).all())

        self.stdout.write(self.style.MIGRATE_HEADING("\nEn la base de origen (SQLite)"))
        self.stdout.write(f"  usuarios: {len(usuarios)}")
        self.stdout.write(f"  grupos:   {len(grupos)}")

        ya_en_destino = User.objects.using(DESTINO).count()
        self.stdout.write(self.style.MIGRATE_HEADING("\nEn la base de destino (PostgreSQL)"))
        self.stdout.write(f"  usuarios ya presentes: {ya_en_destino}")

        if simular:
            self.stdout.write(self.style.MIGRATE_HEADING("\nSe copiarían"))
            for grupo in grupos:
                self.stdout.write(f"  grupo    {grupo.name}")
            for usuario in usuarios:
                marca = " (superusuario)" if usuario.is_superuser else ""
                nombres = ", ".join(g.name for g in usuario.groups.all()) or "sin grupo"
                self.stdout.write(f"  usuario  {usuario.username}{marca}  [{nombres}]")
            self.stdout.write(
                self.style.WARNING("\nSimulación: no se ha escrito nada. Repetir sin --simular.")
            )
            return

        with transaction.atomic(using=DESTINO):
            # Los permisos ya existen en destino: los crea `migrate` a partir
            # de los modelos. Se localizan por su pareja natural (etiqueta de
            # aplicación y código), no por identificador, porque los números
            # no tienen por qué coincidir entre las dos bases.
            permisos_destino = {
                (p.content_type.app_label, p.codename): p
                for p in Permission.objects.using(DESTINO).select_related("content_type")
            }

            equivalencia_grupos = {}
            for grupo in grupos:
                nuevo, creado = Group.objects.using(DESTINO).get_or_create(name=grupo.name)
                equivalencia_grupos[grupo.id] = nuevo

                permisos = []
                for permiso in grupo.permissions.using(ORIGEN).select_related("content_type"):
                    clave = (permiso.content_type.app_label, permiso.codename)
                    if clave in permisos_destino:
                        permisos.append(permisos_destino[clave])
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  permiso sin equivalente en destino: {clave[0]}.{clave[1]}"
                            )
                        )
                nuevo.permissions.set(permisos)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  grupo {grupo.name}: {'creado' if creado else 'ya existía'}, "
                        f"{len(permisos)} permiso(s)"
                    )
                )

            for usuario in usuarios:
                nuevo, creado = User.objects.using(DESTINO).get_or_create(
                    username=usuario.username,
                    defaults={
                        "first_name": usuario.first_name,
                        "last_name": usuario.last_name,
                        "email": usuario.email,
                        "is_staff": usuario.is_staff,
                        "is_active": usuario.is_active,
                        "is_superuser": usuario.is_superuser,
                        "date_joined": usuario.date_joined,
                        "last_login": usuario.last_login,
                    },
                )
                # La contraseña se copia ya cifrada: no hay que conocerla ni
                # pedir a nadie que la cambie.
                nuevo.password = usuario.password
                nuevo.is_staff = usuario.is_staff
                nuevo.is_active = usuario.is_active
                nuevo.is_superuser = usuario.is_superuser
                nuevo.save(using=DESTINO)

                nuevo.groups.set(
                    [equivalencia_grupos[g.id] for g in usuario.groups.all() if g.id in equivalencia_grupos]
                )

                permisos_propios = []
                for permiso in usuario.user_permissions.using(ORIGEN).select_related("content_type"):
                    clave = (permiso.content_type.app_label, permiso.codename)
                    if clave in permisos_destino:
                        permisos_propios.append(permisos_destino[clave])
                nuevo.user_permissions.set(permisos_propios)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  usuario {usuario.username}: {'creado' if creado else 'actualizado'}"
                    )
                )

        self._comprobar(usuarios, grupos)

    def _comprobar(self, usuarios_origen, grupos_origen):
        """Verificación posterior: mismo censo y mismas contraseñas."""
        self.stdout.write(self.style.MIGRATE_HEADING("\nComprobación"))
        problemas = []

        for usuario in usuarios_origen:
            copia = User.objects.using(DESTINO).filter(username=usuario.username).first()
            if not copia:
                problemas.append(f"falta el usuario {usuario.username}")
                continue
            if copia.password != usuario.password:
                problemas.append(f"la contraseña de {usuario.username} no coincide")
            if copia.is_superuser != usuario.is_superuser:
                problemas.append(f"el nivel de acceso de {usuario.username} no coincide")
            grupos_o = sorted(g.name for g in usuario.groups.all())
            grupos_d = sorted(g.name for g in copia.groups.all())
            if grupos_o != grupos_d:
                problemas.append(f"los grupos de {usuario.username} no coinciden: {grupos_o} vs {grupos_d}")

        for grupo in grupos_origen:
            if not Group.objects.using(DESTINO).filter(name=grupo.name).exists():
                problemas.append(f"falta el grupo {grupo.name}")

        if problemas:
            for problema in problemas:
                self.stdout.write(self.style.ERROR(f"  {problema}"))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"  {len(usuarios_origen)} usuario(s) y {len(grupos_origen)} grupo(s) copiados, "
                "con sus contraseñas y permisos.\n"
                "  Los datos están en las dos bases. Cambiar a cuál apunta la aplicación\n"
                "  es un paso aparte: ver DESPLIEGUE.md."
            )
        )
