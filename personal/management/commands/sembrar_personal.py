"""Deja los puestos que el sistema ya usaba, para no empezar de cero.

Los cuatro roles de producción —Soldador, Auxiliar, Pintor, Operador— estaban
escritos dentro del modelo `Colaborador` y todo el reparto de trabajo depende
de ellos. Aquí se crean como puestos de verdad, y a la gente que ya está dada
de alta se le enlaza el suyo, para que la pantalla de personal no salga vacía
el primer día.

**Los departamentos no se siembran.** Cómo se divide este taller lo sabe el
taller. Inventar cuatro nombres plausibles sólo conseguiría que alguien los
diera por buenos.

Es idempotente: correrlo dos veces no duplica nada.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from catalogos.models import Colaborador
from personal.models import Puesto, normalizar


class Command(BaseCommand):
    help = "Crea los puestos de producción que ya usaba el sistema y los enlaza."

    def handle(self, *args, **opciones):
        creados = 0
        enlazados = 0

        with transaction.atomic(using="mes"):
            for clave, etiqueta in Puesto.ROLES_DE_PRODUCCION:
                puesto, nuevo = Puesto.objects.get_or_create(
                    nombre_normalizado=normalizar(etiqueta),
                    departamento=None,
                    defaults={"nombre": etiqueta, "rol_de_produccion": clave, "activo": True},
                )
                if nuevo:
                    creados += 1
                elif not puesto.rol_de_produccion:
                    puesto.rol_de_produccion = clave
                    puesto.save(update_fields=["rol_de_produccion", "actualizado_en"])

                enlazados += Colaborador.objects.filter(
                    rol=clave, puesto__isnull=True
                ).update(puesto=puesto)

        self.stdout.write(f"Puestos creados: {creados}")
        self.stdout.write(f"Personas enlazadas a su puesto: {enlazados}")
        sin_puesto = Colaborador.objects.filter(activo=True, puesto__isnull=True).count()
        if sin_puesto:
            self.stdout.write(
                self.style.WARNING(
                    f"Quedan {sin_puesto} personas activas sin puesto. "
                    "Se les pone desde Recursos humanos → Personal."
                )
            )
