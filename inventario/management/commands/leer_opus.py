"""Lee una explosión de OPUS y dice qué encontró. No escribe nada.

Sirve para dos cosas antes de que exista el importador:

- **Probar un archivo nuevo.** Si mañana llega una exportación de otra versión
  de OPUS, esto dice en un segundo si se lee bien, sin arriesgar nada.
- **Ver cuántas claves ya están en el catálogo** y cuántas habría que dar de
  alta, que es la conversación que hay que tener con el taller antes de
  importar nada.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core import opus

BASE = "mes"


class Command(BaseCommand):
    help = "Lee una explosión de insumos de OPUS y resume lo que trae. Sólo lectura."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del CSV exportado desde OPUS")
        parser.add_argument(
            "--insumos",
            action="store_true",
            help="Enseña también el renglón por renglón",
        )

    def handle(self, *args, **opciones):
        ruta = Path(opciones["archivo"])
        if not ruta.is_file():
            raise CommandError(f"No existe: {ruta}")

        lectura = opus.leer(ruta.read_bytes())

        if not lectura.partidas and any(a.clase == "sin encabezado" for a in lectura.avisos):
            raise CommandError(
                "No parece una explosión de insumos de OPUS: no se encontró el "
                "renglón de encabezado con «Clave» y «Cantidad»."
            )

        self._portada(lectura.cabecera)
        self._cuadre(lectura)
        if opciones["insumos"]:
            self._insumos(lectura)
        self._catalogo(lectura)
        self._avisos(lectura)

    # ------------------------------------------------------------ secciones

    def _portada(self, cabecera):
        self.stdout.write(self.style.MIGRATE_HEADING("\nProyecto"))
        for rotulo, valor in (
            ("Descripción", cabecera.proyecto),
            ("Cliente", cabecera.cliente),
            ("Ubicación", cabecera.ubicacion),
            ("Propuesta", cabecera.fecha_propuesta),
            ("Inicio", cabecera.inicio_obra),
            ("Fin", cabecera.fin_obra),
            ("Duración", f"{cabecera.duracion_dias} días" if cabecera.duracion_dias else ""),
        ):
            if valor:
                self.stdout.write(f"  {rotulo:12} {valor}")

    def _cuadre(self, lectura):
        self.stdout.write(self.style.MIGRATE_HEADING("\nCuadre"))
        self.stdout.write(f"  {'Insumos leídos':22} {len(lectura.partidas)}")
        self.stdout.write(f"  {'Suma de renglones':22} {lectura.importe_leido:,.2f}")
        for tipo, importe in lectura.totales.items():
            self.stdout.write(f"  {'Total ' + tipo:22} {importe:,.2f}")

        if lectura.cuadra is True:
            self.stdout.write(self.style.SUCCESS(
                "  Cuadra. El archivo se separó bien."
            ))
        elif lectura.cuadra is False:
            self.stdout.write(self.style.ERROR(
                "  NO cuadra. Casi siempre significa que algún renglón se "
                "partió mal: no importar sin revisarlo."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "  El archivo no trae total, así que no hay contra qué cuadrar."
            ))

    def _insumos(self, lectura):
        self.stdout.write(self.style.MIGRATE_HEADING("\nInsumos"))
        for p in lectura.partidas:
            marca = "  " if p.inventariable else " ·"
            self.stdout.write(
                f"{marca}{p.clave:24} {p.cantidad:>14,.6f} {p.unidad:<6} "
                f"{p.importe:>12,.2f}  {p.descripcion[:44]}"
            )

    def _catalogo(self, lectura):
        """Cuántas claves ya existen como material y cuántas habría que crear."""
        from inventario.models import Material

        inventariables = [p for p in lectura.partidas if p.inventariable]
        claves = {p.clave for p in inventariables}
        existentes = set(
            Material.objects.using(BASE)
            .filter(codigo__in=claves)
            .values_list("codigo", flat=True)
        )
        faltan = sorted(claves - existentes)

        self.stdout.write(self.style.MIGRATE_HEADING("\nContra el catálogo de materiales"))
        self.stdout.write(f"  {'Claves inventariables':22} {len(claves)}")
        self.stdout.write(f"  {'Ya en el catálogo':22} {len(existentes)}")
        self.stdout.write(f"  {'Habría que darlas de alta':22} {len(faltan)}")
        if faltan:
            self.stdout.write(self.style.WARNING("  " + ", ".join(faltan[:20])))
            if len(faltan) > 20:
                self.stdout.write(f"  …y {len(faltan) - 20} más")

    def _avisos(self, lectura):
        if not lectura.avisos:
            self.stdout.write(self.style.SUCCESS("\nSin avisos.\n"))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nPara revisar antes de importar ({len(lectura.avisos)})"
        ))
        por_clase = {}
        for aviso in lectura.avisos:
            por_clase.setdefault(aviso.clase, []).append(aviso)

        for clase, avisos in por_clase.items():
            self.stdout.write(self.style.WARNING(f"\n  {clase} ({len(avisos)})"))
            for aviso in avisos[:8]:
                sitio = f"r{aviso.renglon}" if aviso.renglon else "  "
                self.stdout.write(f"    {sitio:>5}  {aviso.detalle}")
            if len(avisos) > 8:
                self.stdout.write(f"           …y {len(avisos) - 8} más")
        self.stdout.write("")
