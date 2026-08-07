"""Audita los tipos de movimiento de logística guardados en la base.

Django no valida `choices` en `Model.objects.create()`, así que un tipo mal
escrito llega a PostgreSQL sin protestar y luego esas filas desaparecen de
cualquier filtro o reporte que agrupe por tipo.

Pasó con `revertir_apartado` en la logística de Corta, que debía ser
`revertir` (el valor que usa herrería para la misma operación). El código ya
está corregido, pero las filas escritas antes de la corrección siguen en la
base de producción, que es más reciente que la copia con la que se trabajó.

Uso:

    python manage.py auditar_movimientos              # solo informa
    python manage.py auditar_movimientos --corregir   # además reescribe
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from catalogos.models import LogisticaMovimiento, LogisticaMovimientoCorta
from core.bases import BASE  # noqa: F401

# Tipos históricos y el valor declarado al que corresponden.
EQUIVALENCIAS = {
    "revertir_apartado": "revertir",
}


class Command(BaseCommand):
    help = "Informa de los tipos de movimiento de logística fuera de TIPO_CHOICES."

    def add_arguments(self, parser):
        parser.add_argument(
            "--corregir",
            action="store_true",
            help="Reescribe los tipos conocidos según la tabla de equivalencias.",
        )

    def handle(self, *args, **opciones):
        corregir = opciones["corregir"]
        total_huerfanos = 0

        for modelo in (LogisticaMovimiento, LogisticaMovimientoCorta):
            declarados = {c[0] for c in (modelo._meta.get_field("tipo").choices or [])}
            filas = (
                modelo.objects.using(BASE)
                .values("tipo")
                .annotate(n=Count("id"))
                .order_by("-n")
            )

            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{modelo.__name__}"))
            self.stdout.write(f"  declarados: {sorted(declarados)}")

            if not filas:
                self.stdout.write("  (sin registros)")
                continue

            for fila in filas:
                tipo, n = fila["tipo"], fila["n"]
                if tipo in declarados:
                    self.stdout.write(f"    {tipo!r:24} {n:6}")
                    continue

                total_huerfanos += n
                destino = EQUIVALENCIAS.get(tipo)
                aviso = f"    {tipo!r:24} {n:6}  FUERA DE CHOICES"
                self.stdout.write(self.style.WARNING(aviso))

                if not destino:
                    self.stdout.write(
                        self.style.ERROR(
                            f"      sin equivalencia conocida: revisar a mano antes de tocar nada"
                        )
                    )
                    continue

                if not corregir:
                    self.stdout.write(f"      se reescribiría como {destino!r} (usar --corregir)")
                    continue

                with transaction.atomic(using=BASE):
                    actualizadas = (
                        modelo.objects.using(BASE).filter(tipo=tipo).update(tipo=destino)
                    )
                self.stdout.write(
                    self.style.SUCCESS(f"      {actualizadas} fila(s) reescritas como {destino!r}")
                )

        if not total_huerfanos:
            self.stdout.write(self.style.SUCCESS("\nTodos los tipos están dentro de TIPO_CHOICES."))
        elif not corregir:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{total_huerfanos} fila(s) con tipo fuera de choices. "
                    "Repetir con --corregir tras respaldar la base."
                )
            )
