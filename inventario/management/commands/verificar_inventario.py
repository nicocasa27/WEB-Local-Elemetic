"""Comprueba que las existencias cuadren con los movimientos.

Las existencias son una caché: el número bueno es la suma del historial. Si
las dos cosas se separan, es que alguien escribió por un camino que no pasa
por el servicio —un `update` en bloque, una consulta a mano, una corrección de
madrugada— y a partir de ahí el inventario ya no vale.

Pensado para correr una vez al día, como la reconciliación del núcleo.

    python manage.py verificar_inventario
    python manage.py verificar_inventario --corregir

Informa además de dos cosas que no son errores pero conviene mirar: qué hay
por debajo de su mínimo, y cuánto dinero hay parado en el almacén.
"""

from django.core.management.base import BaseCommand

from core.servicios import inventario as servicio
from core.bases import BASE  # noqa: F401



class Command(BaseCommand):
    help = "Compara las existencias contra los movimientos y avisa de lo que falta."

    def add_arguments(self, parser):
        parser.add_argument(
            "--corregir",
            action="store_true",
            help="Reconstruye las existencias desde los movimientos. El historial manda.",
        )

    def handle(self, *args, **opciones):
        descuadres = servicio.descuadres()

        self.stdout.write(self.style.MIGRATE_HEADING("Existencias contra movimientos"))
        if descuadres:
            for fila, esperado in descuadres:
                lote = fila.lote.codigo if fila.lote_id else "(sin lote)"
                self.stdout.write(
                    self.style.ERROR(
                        f"  {fila.material.codigo:<12} {lote:<16} "
                        f"caché {fila.cantidad}  historial {esperado}"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("  cuadran"))

        if opciones["corregir"] and descuadres:
            corregidas = servicio.recalcular_existencias()
            self.stdout.write(
                self.style.WARNING(
                    f"\n  {corregidas} fila(s) reconstruidas desde el historial."
                )
            )

        self._faltantes()
        self._valor()

        if descuadres and not opciones["corregir"]:
            raise SystemExit(1)

    def _faltantes(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nPor debajo del mínimo"))
        faltantes = servicio.bajo_minimo()
        if not faltantes:
            self.stdout.write("  nada por debajo de su mínimo")
            return
        for material, hay, falta in faltantes:
            self.stdout.write(
                self.style.WARNING(
                    f"  {material.codigo:<12} hay {hay}, mínimo {material.stock_minimo} "
                    f"→ faltan {falta}"
                )
            )

    def _valor(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nValor del almacén"))
        total = servicio.valor_de_existencias()
        self.stdout.write(f"  {total} (valuado lote a lote, no por promedio)")
