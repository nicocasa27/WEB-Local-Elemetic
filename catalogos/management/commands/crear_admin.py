"""Deja siempre una forma de entrar al sistema.

El taller pidió un administrador fijo: el servidor se abre casi siempre en la
red local y no quieren quedarse fuera si alguien olvida su contraseña.

Va con la contraseña escrita aquí abajo, tal como se pidió. Dos matices que no
le quitan nada a eso y evitan el problema de siempre:

- Si existe la variable de entorno `MES_ADMIN_PASSWORD`, se usa esa. Así el
  día que el servidor salga de la red local se cambia sin tocar el código.
- Mientras siga puesta la de fábrica, el sistema lo dice en pantalla a los
  administradores y lo escribe en el registro. No estorba y no se olvida.

Es idempotente: correrlo dos veces no duplica nada ni pisa una contraseña ya
cambiada, salvo que se pida con `--restablecer`.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core import roles

USUARIO = "admin"
CONTRASENA_DE_FABRICA = "Elemetic2026!"
CORREO = "admin@elemetic.local"


def contrasena_configurada():
    return os.environ.get("MES_ADMIN_PASSWORD") or CONTRASENA_DE_FABRICA


def usa_la_de_fabrica():
    """Para que la pantalla pueda avisarlo."""
    return not os.environ.get("MES_ADMIN_PASSWORD")


class Command(BaseCommand):
    help = "Crea (o restablece) el administrador fijo y los grupos de permisos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--restablecer",
            action="store_true",
            help="Vuelve a poner la contraseña y reactiva la cuenta si estaba apagada.",
        )

    def handle(self, *args, **opciones):
        creados = roles.asegurar_grupos()
        if creados:
            self.stdout.write(f"Grupos creados: {', '.join(creados)}")

        Usuario = get_user_model()
        contrasena = contrasena_configurada()

        usuario, nuevo = Usuario.objects.get_or_create(
            username=USUARIO,
            defaults={
                "email": CORREO,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        if nuevo:
            usuario.set_password(contrasena)
            usuario.save()
            self.stdout.write(self.style.SUCCESS(f"Administrador «{USUARIO}» creado."))
        elif opciones["restablecer"]:
            usuario.set_password(contrasena)
            usuario.is_active = True
            usuario.is_staff = True
            usuario.is_superuser = True
            usuario.save()
            self.stdout.write(self.style.SUCCESS(
                f"Administrador «{USUARIO}» restablecido."
            ))
        else:
            # Sin `--restablecer` no se pisa una contraseña que alguien ya
            # cambió a propósito.
            cambios = []
            if not usuario.is_active:
                usuario.is_active = True
                cambios.append("reactivado")
            if not usuario.is_superuser:
                usuario.is_superuser = True
                usuario.is_staff = True
                cambios.append("devueltos los permisos")
            if cambios:
                usuario.save()
                self.stdout.write(self.style.WARNING(
                    f"Administrador «{USUARIO}»: {', '.join(cambios)}."
                ))
            else:
                self.stdout.write(f"Administrador «{USUARIO}» ya estaba bien.")

        grupo = Group.objects.filter(name="admin_general").first()
        if grupo:
            usuario.groups.add(grupo)

        self.stdout.write("")
        self.stdout.write(f"  Usuario:    {USUARIO}")
        if usa_la_de_fabrica():
            self.stdout.write(f"  Contraseña: {CONTRASENA_DE_FABRICA}")
            self.stdout.write(self.style.WARNING(
                "\n  Es la contraseña de fábrica y está escrita en el código.\n"
                "  Mientras siga así, el sistema lo avisa en pantalla.\n"
                "  Para cambiarla: definir MES_ADMIN_PASSWORD y volver a correr\n"
                "  este comando con --restablecer.\n"
            ))
        else:
            self.stdout.write("  Contraseña: la de MES_ADMIN_PASSWORD")
            self.stdout.write("")
