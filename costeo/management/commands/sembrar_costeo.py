"""Crea un centro de costo por línea y deja las tarifas listas para capturar.

El módulo de costeo no necesita que nadie apunte horas: las deduce del
historial. Lo único que hay que capturar es **cuánto cuesta una hora**, y eso
se hace una vez.

    python manage.py sembrar_costeo
    python manage.py sembrar_costeo --tarifa herreria:180:95:120

El formato de `--tarifa` es `linea:hora_maquina:hora_mano_obra:overhead_hora`.
Sin tarifas, el comando crea los centros y avisa: todos los costos saldrán en
cero hasta que se capturen, y un costo en cero no es un costo barato, es un
costo que no se calculó.

Las tarifas **no se editan**: se añaden con una fecha desde la que rigen. Si
mañana suben los sueldos, se captura una tarifa nueva y lo que costó una orden
del año pasado sigue costando lo mismo. Es lo que permite comparar.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from costeo.models import CentroCosto, Tarifa
from nucleo.models import LineaNegocio

BASE = "mes"


class Command(BaseCommand):
    help = "Crea los centros de costo por línea y, opcionalmente, sus tarifas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tarifa",
            action="append",
            default=[],
            metavar="LINEA:MAQ:OBRA:OVERHEAD",
            help="Captura una tarifa. Se puede repetir.",
        )
        parser.add_argument(
            "--desde",
            help="Fecha desde la que rigen las tarifas (AAAA-MM-DD). Por omisión, hoy.",
        )
        parser.add_argument("--actor", default="", help="Quién captura la tarifa.")

    def handle(self, *args, **opciones):
        lineas = list(LineaNegocio.objects.using(BASE).all())
        if not lineas:
            raise CommandError(
                "No hay líneas de negocio. Ejecutar antes `sembrar_nucleo`."
            )

        desde = self._fecha(opciones.get("desde"))

        with transaction.atomic(using=BASE):
            centros = self._centros(lineas)
            capturadas = self._tarifas(opciones["tarifa"], desde, opciones["actor"])

        self._resumen(centros, capturadas)

    def _fecha(self, texto):
        if not texto:
            return timezone.localdate()
        from datetime import date

        try:
            return date.fromisoformat(texto)
        except ValueError as error:
            raise CommandError(f"«{texto}» no es una fecha AAAA-MM-DD.") from error

    def _centros(self, lineas):
        self.stdout.write(self.style.MIGRATE_HEADING("\nCentros de costo"))
        centros = {}
        for linea in lineas:
            centro, creado = CentroCosto.objects.using(BASE).get_or_create(
                codigo=linea.codigo,
                defaults={"nombre": linea.nombre, "linea": linea},
            )
            centros[linea.codigo] = centro
            self.stdout.write(
                f"  {centro.nombre:<16} {'creado' if creado else 'ya existía'}"
            )
        return centros

    def _tarifas(self, entradas, desde, actor):
        if not entradas:
            return 0

        self.stdout.write(self.style.MIGRATE_HEADING("\nTarifas"))
        capturadas = 0
        for entrada in entradas:
            partes = entrada.split(":")
            if len(partes) != 4:
                raise CommandError(
                    f"«{entrada}» no tiene el formato LINEA:MAQUINA:OBRA:OVERHEAD."
                )
            codigo, maquina, obra, overhead = partes
            centro = CentroCosto.objects.using(BASE).filter(codigo=codigo).first()
            if centro is None:
                raise CommandError(f"No hay ningún centro de costo «{codigo}».")

            try:
                valores = [Decimal(v) for v in (maquina, obra, overhead)]
            except InvalidOperation as error:
                raise CommandError(f"«{entrada}» tiene un importe no válido.") from error
            if any(v < 0 for v in valores):
                raise CommandError(f"«{entrada}» tiene un importe negativo.")

            tarifa, creada = Tarifa.objects.using(BASE).get_or_create(
                centro=centro,
                vigente_desde=desde,
                defaults={
                    "costo_hora_maquina": valores[0],
                    "costo_hora_mano_obra": valores[1],
                    "overhead_hora": valores[2],
                    "creado_por": actor,
                },
            )
            if not creada:
                # No se pisa: una tarifa guardada es inmutable. Corregirla es
                # capturar otra con fecha distinta, y así el costo de lo ya
                # calculado no cambia solo.
                self.stdout.write(
                    self.style.WARNING(
                        f"  {centro.codigo}: ya había una tarifa desde {desde}, "
                        "no se toca. Para corregir, usar otra fecha."
                    )
                )
                continue

            capturadas += 1
            self.stdout.write(
                f"  {centro.codigo:<16} máquina {tarifa.costo_hora_maquina}/h · "
                f"obra {tarifa.costo_hora_mano_obra}/h · "
                f"indirectos {tarifa.overhead_hora}/h  desde {desde}"
            )
        return capturadas

    def _resumen(self, centros, capturadas):
        from core.servicios import costeo

        faltantes = costeo.sin_tarifa()
        self.stdout.write(self.style.MIGRATE_HEADING("\nSituación"))
        self.stdout.write(f"  centros: {len(centros)}   tarifas nuevas: {capturadas}")

        if faltantes:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  {len(faltantes)} centro(s) sin ninguna tarifa: "
                    + ", ".join(c.codigo for c in faltantes)
                    + "\n"
                    "\n  Mientras falte una tarifa, las órdenes de esa línea salen con\n"
                    "  costo cero. Un costo en cero no es un costo barato: es un costo\n"
                    "  que no se calculó, y usarlo para cotizar es peor que no tenerlo.\n"
                    "\n  Se captura así:\n"
                    "      manage.py sembrar_costeo --tarifa herreria:180:95:120\n"
                    "  (máquina/hora, mano de obra/hora, indirectos/hora)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n  Todos los centros tienen tarifa vigente.")
            )
