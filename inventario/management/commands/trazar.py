"""Responde las dos preguntas que hoy no se pueden responder.

Cuando la acería avisa de que una colada salió mal, o cuando un cliente
reclama una pieza, la pregunta es siempre una de estas dos:

    python manage.py trazar --colada H-48213     ¿dónde está esta colada?
    python manage.py trazar --orden H-00031      ¿de qué está hecha esta orden?

Hoy la respuesta es buscar en el correo de alguien y confiar en la memoria.
Con el lote y el registro de movimientos, es una consulta.

Esto es lo que justifica que dar de alta un lote sea obligatorio al recibir
material. Sin lote, estas dos preguntas siguen sin respuesta por muy bonito
que sea el resto del inventario.
"""

from django.core.management.base import BaseCommand, CommandError

from core.servicios import inventario as servicio
from nucleo.models import OrdenProduccion

BASE = "mes"


class Command(BaseCommand):
    help = "Traza una colada hasta las órdenes, o una orden hasta sus coladas."

    def add_arguments(self, parser):
        parser.add_argument("--colada", help="Número de colada del fabricante.")
        parser.add_argument("--orden", help="Folio de la orden de producción.")

    def handle(self, *args, **opciones):
        if opciones["colada"]:
            self._por_colada(opciones["colada"])
        elif opciones["orden"]:
            self._por_orden(opciones["orden"])
        else:
            raise CommandError("Hay que indicar --colada o --orden.")

    def _por_colada(self, colada):
        movimientos = servicio.ordenes_de_la_colada(colada)
        self.stdout.write(self.style.MIGRATE_HEADING(f"Colada {colada}"))
        if not movimientos:
            self.stdout.write(
                "  no se ha consumido en ninguna orden, o no está registrada.\n"
                "  Si el material entró antes de que existiera el inventario, no hay\n"
                "  forma de reconstruirlo: eso es lo que este módulo viene a evitar\n"
                "  hacia adelante."
            )
            return

        por_orden = {}
        for movimiento in movimientos:
            por_orden.setdefault(movimiento.orden, []).append(movimiento)

        self.stdout.write(f"  presente en {len(por_orden)} orden(es):\n")
        for orden, apuntes in por_orden.items():
            total = sum(abs(a.cantidad) for a in apuntes)
            self.stdout.write(
                f"  {orden.folio:<12} {orden.codigo[:34]:<34} "
                f"{orden.linea.nombre:<12} {total} {apuntes[0].material.unidad}"
            )
            if orden.cliente_id:
                self.stdout.write(f"      cliente: {orden.cliente.nombre}")

    def _por_orden(self, folio):
        orden = OrdenProduccion.objects.using(BASE).filter(folio__iexact=folio.strip()).first()
        if orden is None:
            raise CommandError(f"No existe ninguna orden con folio {folio!r}.")

        self.stdout.write(self.style.MIGRATE_HEADING(f"{orden.folio} · {orden.codigo}"))
        movimientos = servicio.coladas_de_la_orden(orden)
        if not movimientos:
            self.stdout.write("  no tiene material registrado.")
        else:
            for movimiento in movimientos:
                lote = movimiento.lote
                proveedor = lote.proveedor.nombre if lote.proveedor_id else "sin proveedor"
                certificado = "con certificado" if lote.certificado else "SIN CERTIFICADO"
                self.stdout.write(
                    f"  {movimiento.material.codigo:<12} {abs(movimiento.cantidad)} "
                    f"{movimiento.material.unidad:<3} "
                    f"lote {lote.codigo:<14} colada {lote.colada or '(sin colada)':<14} "
                    f"{proveedor:<20} {certificado}"
                )

        self.stdout.write(
            self.style.MIGRATE_HEADING("\nCosto de material")
        )
        self.stdout.write(f"  {servicio.costo_material_de(orden)}")
