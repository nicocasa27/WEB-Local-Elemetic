"""Calcula el costo de las órdenes y enseña dónde se va el dinero.

    python manage.py calcular_costos --orden H-00020
    python manage.py calcular_costos --linea herreria
    python manage.py calcular_costos --desde 2026-01-01
    python manage.py calcular_costos --varianza --linea herreria

No es un asiento contable: es una foto derivada del historial, las tarifas y
los consumos. Se puede volver a calcular tantas veces como se quiera, y si
mañana aparece un consumo que faltaba o se corrige una tarifa vieja, el número
que sale es el bueno.

La columna que hay que mirar primero es **cobertura**. Dice qué parte de la
orden se pudo medir de verdad: si una etapa no tiene a nadie asignado, sus
horas de mano de obra no se pueden calcular y este módulo no se inventa un
operador. Una cobertura del 40 % significa que el costo es real pero
incompleto, y por tanto que no sirve todavía para cotizar.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from core.servicios import costeo as servicio
from costeo.models import CostoOrden
from nucleo.models import OrdenProduccion

BASE = "mes"


class Command(BaseCommand):
    help = "Calcula el costo de las órdenes y enseña la varianza contra el estándar."

    def add_arguments(self, parser):
        parser.add_argument("--orden", help="Un folio concreto.")
        parser.add_argument("--linea", help="Código de línea: herreria, corta…")
        parser.add_argument("--desde", help="Órdenes creadas desde esta fecha.")
        parser.add_argument("--hasta", help="Órdenes creadas hasta esta fecha.")
        parser.add_argument(
            "--directo",
            action="store_true",
            help="Costeo directo: no reparte los gastos indirectos.",
        )
        parser.add_argument(
            "--varianza",
            action="store_true",
            help="Enseña lo real contra lo estándar, etapa por etapa.",
        )

    def handle(self, *args, **opciones):
        faltantes = servicio.sin_tarifa()
        if faltantes:
            self.stdout.write(
                self.style.WARNING(
                    "Aviso: "
                    + ", ".join(c.codigo for c in faltantes)
                    + " no tienen tarifa. Sus órdenes saldrán con costo de máquina y\n"
                    "mano de obra en cero. Capturarlas con `sembrar_costeo --tarifa`.\n"
                )
            )

        ordenes = self._ordenes(opciones)
        if not ordenes:
            raise CommandError("Ningún orden coincide con esos filtros.")

        metodo = (
            CostoOrden.Metodo.DIRECTO if opciones["directo"] else CostoOrden.Metodo.ABSORCION
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nCalculando {len(ordenes)} orden(es) · método {metodo}"
            )
        )
        self.stdout.write(
            f"  {'folio':<12} {'material':>12} {'obra':>10} {'máquina':>10} "
            f"{'indirect.':>10} {'TOTAL':>12} {'/pieza':>10}  cobertura"
        )

        for orden in ordenes:
            costo = servicio.calcular(orden, metodo)
            marca = "" if costo.cobertura >= 1 else "  ←"
            self.stdout.write(
                f"  {orden.folio:<12} {costo.material:>12} {costo.mano_obra:>10} "
                f"{costo.maquina:>10} {costo.overhead:>10} {costo.total:>12} "
                f"{costo.costo_unitario:>10}  {int(costo.cobertura * 100):>3}%{marca}"
            )
            for aviso in costo.detalle.get("avisos", []):
                self.stdout.write(self.style.WARNING(f"      {aviso}"))

            if opciones["varianza"]:
                self._varianza(orden)

        self._resumen()

    def _ordenes(self, opciones):
        consulta = OrdenProduccion.objects.using(BASE).select_related("linea", "pieza")
        if opciones["orden"]:
            consulta = consulta.filter(folio__iexact=opciones["orden"].strip())
        if opciones["linea"]:
            consulta = consulta.filter(linea__codigo=opciones["linea"])
        if opciones["desde"]:
            consulta = consulta.filter(creado_en__date__gte=self._fecha(opciones["desde"]))
        if opciones["hasta"]:
            consulta = consulta.filter(creado_en__date__lte=self._fecha(opciones["hasta"]))
        return list(consulta.order_by("folio"))

    def _fecha(self, texto):
        try:
            return date.fromisoformat(texto)
        except ValueError as error:
            raise CommandError(f"«{texto}» no es una fecha AAAA-MM-DD.") from error

    def _varianza(self, orden):
        """Lo real contra lo estándar. El informe que dice dónde se pierde."""
        informe = servicio.varianza(orden)
        if not informe or not informe["etapas"]:
            self.stdout.write(
                "      sin tiempo estándar capturado: no hay con qué comparar"
            )
            return
        for fila in informe["etapas"]:
            signo = "+" if fila["diferencia"] > 0 else ""
            estilo = self.style.ERROR if fila["diferencia"] > 0 else self.style.SUCCESS
            texto = (
                f"      {fila['etapa'].nombre:<22} real {fila['horas_reales']:>9} h  "
                f"estándar {fila['horas_estandar']:>9} h  "
                f"{signo}{fila['porcentaje']}%"
            )
            if fila["paro"]:
                texto += f"   (descontadas {fila['paro']} h de paro)"
            self.stdout.write(estilo(texto))

    def _resumen(self):
        filas = servicio.resumen_por_linea()
        if not filas:
            return
        self.stdout.write(self.style.MIGRATE_HEADING("\nPor línea"))
        for fila in filas:
            varianza = fila["varianza"]
            texto_varianza = "sin estándar" if varianza is None else str(varianza)
            self.stdout.write(
                f"  {fila['linea'].nombre:<14} {fila['ordenes']:>4} orden(es)  "
                f"total {fila['total']:>14}   varianza {texto_varianza:>14}   "
                f"cobertura {int(fila['cobertura'] * 100):>3}%"
            )
