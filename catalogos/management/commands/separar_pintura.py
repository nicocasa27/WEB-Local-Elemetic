"""Mueve a los pintores de «soldadura» al grupo de pintura.

Hasta ahora el grupo «soldadura» cubría armado, soldadura, pintura y
terminado, porque nadie había preguntado si en el taller eran la misma gente.
No lo son. Se creó el grupo «pintura» y hay que repartir las cuentas que ya
existen, que es lo que hace este comando.

Quién es pintor sale de su ficha, no de una lista escrita a mano: o su rol es
«Pintor», o su equipo es del área de pintura. Los dos criterios están ya en
los datos y no hay que capturarlos otra vez.

**Mientras no haya ninguna cuenta en el grupo de pintura, «soldadura» sigue
cubriendo pintura.** Así que si este comando no se corre, nada se rompe: el
sistema se queda como estaba. En cuanto se corre, el reparto se separa.

    manage.py separar_pintura --ensayo    # enseña qué haría, sin tocar nada
    manage.py separar_pintura
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from core.bases import BASE  # noqa: F401


GRUPO_PINTURA = "pintura"
GRUPO_SOLDADURA = "soldadura"

#: El área de los equipos de pintura, como se escribe en `EquipoTrabajo.area`.
AREA_PINTURA = "pintura"


class Command(BaseCommand):
    help = "Pasa las cuentas de los pintores del grupo de soldadura al de pintura."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ensayo",
            action="store_true",
            help="Enseña el reparto que haría y no escribe nada.",
        )
        parser.add_argument(
            "--dejar-en-soldadura",
            action="store_true",
            help=(
                "Añade el grupo de pintura pero no quita el de soldadura. "
                "Para quien pinta y suelda."
            ),
        )

    def handle(self, *args, **opciones):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        from catalogos.models import Colaborador
        from core import roles

        roles.asegurar_grupos()
        Usuario = get_user_model()

        pintores = [
            ficha
            for ficha in Colaborador.objects.using(BASE)
            .filter(activo=True)
            .exclude(usuario="")
            .select_related("equipo")
            if ficha.rol == "Pintor"
            or (ficha.equipo and (ficha.equipo.area or "").strip().casefold() == AREA_PINTURA)
        ]

        if not pintores:
            self.stdout.write(
                self.style.WARNING(
                    "Ninguna ficha activa con rol «Pintor» ni equipo del área de "
                    "pintura tiene cuenta enlazada.\n"
                    "Sin cuentas en el grupo de pintura, «soldadura» sigue "
                    "cubriendo pintura: no se rompe nada, pero tampoco se separa."
                )
            )
            return

        self.stdout.write(self.style.MIGRATE_HEADING("\nPintores con cuenta"))
        cuentas = []
        for ficha in pintores:
            cuenta = Usuario.objects.filter(username__iexact=ficha.usuario).first()
            if cuenta is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {ficha.nombre:28} ficha enlazada a «{ficha.usuario}», "
                        "que no es ninguna cuenta"
                    )
                )
                continue
            equipo = ficha.equipo.nombre if ficha.equipo else "sin equipo"
            self.stdout.write(f"  {ficha.nombre:28} {cuenta.username:14} {ficha.rol} · {equipo}")
            cuentas.append(cuenta)

        if not cuentas:
            self.stdout.write(self.style.ERROR("\nNinguna ficha apunta a una cuenta real."))
            return

        if opciones["ensayo"]:
            quita = "" if opciones["dejar_en_soldadura"] else ", y se les quitaría soldadura"
            self.stdout.write(
                self.style.WARNING(
                    f"\nEnsayo: {len(cuentas)} cuenta(s) pasarían al grupo de pintura{quita}. "
                    "Nada se ha escrito."
                )
            )
            return

        with transaction.atomic():
            pintura = Group.objects.get(name=GRUPO_PINTURA)
            soldadura = Group.objects.filter(name=GRUPO_SOLDADURA).first()
            for cuenta in cuentas:
                cuenta.groups.add(pintura)
                if soldadura and not opciones["dejar_en_soldadura"]:
                    cuenta.groups.remove(soldadura)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nListo: {len(cuentas)} cuenta(s) en el grupo de pintura.\n"
                "A partir de ahora soldadura cubre armado y soldadura, y pintura "
                "cubre pintura y terminado.\n"
            )
        )
