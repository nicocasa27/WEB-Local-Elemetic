"""Cierra en firme las órdenes cuya ventana de reversión ya venció.

Pensado para ejecutarse cada minuto desde un trabajo programado. Ver la
sección correspondiente de DESPLIEGUE.md.

    python manage.py consolidar_cierres
    python manage.py consolidar_cierres --linea herreria
    python manage.py consolidar_cierres --simular
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion
from core import estados
from core.servicios import cierres


class Command(BaseCommand):
    help = "Consolida los cierres de producción cuya ventana de reversión ha vencido."

    def add_arguments(self, parser):
        parser.add_argument(
            "--linea",
            choices=sorted(cierres.LINEAS),
            help="Consolida sólo una línea. Por omisión, todas.",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Enumera lo que se cerraría, sin tocar nada.",
        )

    def handle(self, *args, **opciones):
        ahora = timezone.now()
        lineas = [opciones["linea"]] if opciones.get("linea") else sorted(cierres.LINEAS)

        if opciones["simular"]:
            self._simular(lineas, ahora)
            return

        total = 0
        for nombre in lineas:
            consolidadas = cierres.consolidar_linea(nombre, ahora)
            total += consolidadas
            if consolidadas:
                self.stdout.write(
                    self.style.SUCCESS(f"{nombre}: {consolidadas} orden(es) cerradas en firme")
                )

        # Sin salida cuando no hay nada que hacer: al correr cada minuto, lo
        # contrario llenaría el registro de ruido.
        if total == 0 and not opciones.get("linea"):
            self.stdout.write("Sin cierres vencidos.")

    def _simular(self, lineas, ahora):
        modelos = {"herreria": HerrOrdenProduccion, "corta": LaserOrdenProduccion}
        for nombre in lineas:
            pendientes = (
                modelos[nombre]
                .objects.using("mes")
                .filter(
                    estado="Abierta",
                    estado_etapa=estados.CIERRE_PENDIENTE,
                    cierre_pendiente_hasta__isnull=False,
                    cierre_pendiente_hasta__lte=ahora,
                )
                .order_by("cierre_pendiente_hasta")
            )
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{nombre}: {pendientes.count()} vencida(s)"))
            for orden in pendientes[:50]:
                vencida_hace = ahora - orden.cierre_pendiente_hasta
                self.stdout.write(
                    f"    {orden.codigo:20} venció hace {int(vencida_hace.total_seconds() // 60)} min"
                )
