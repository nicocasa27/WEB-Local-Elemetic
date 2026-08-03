"""Pone en marcha el inventario a partir de lo que ya hay catalogado.

El taller lleva años dando de alta placas en `LaserMaterialPlaca`: ciento
trece, con su categoría, su calibre, su geometría y su peso. Es un catálogo de
material de verdad, sólo que sin costo, sin proveedor y sin existencias.
Volver a capturarlo a mano sería tirar ese trabajo.

Este comando lo trae tal cual y añade lo que faltaba. **No inventa
existencias.** Todos los materiales quedan en cero, porque el inventario
arranca con un conteo físico y no con una suposición: un almacén que empieza
con cifras inventadas nunca vuelve a cuadrar, y encima se cree.

    python manage.py sembrar_inventario --simular
    python manage.py sembrar_inventario

Después de esto hay trabajo que no es de programación y que decide si el
módulo sirve para algo:

1. Contar físicamente lo que hay y capturarlo con `inventario_fisico`.
2. Nombrar a una persona responsable de registrar cada entrada.

Sin esas dos cosas el módulo da números peores que no tener módulo.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from catalogos.models import LaserMaterialPlaca
from core import folios
from inventario.models import Almacen, Material
from nucleo.models import MotivoEvento

BASE = "mes"

#: Densidades en kg/dm³. Hoy esta decisión se toma buscando trozos de texto
#: dentro del nombre del material («ALUMIN», «INOX») en medio del método que
#: guarda una orden de corte. Aquí se decide una vez, al dar de alta el
#: material, y luego es un campo que se puede corregir.
DENSIDADES = [
    (("ALUMIN",), Decimal("2.700")),
    (("INOX", "INOXID"), Decimal("8.000")),
    (("ACERO", "LAMINA", "LÁMINA"), Decimal("7.850")),
]
DENSIDAD_POR_DEFECTO = Decimal("7.850")

#: Motivos que necesita el almacén y que no existían en el catálogo heredado.
MOTIVOS = [
    (MotivoEvento.Ambito.AJUSTE, "conteo_fisico", "Ajuste por conteo físico"),
    (MotivoEvento.Ambito.AJUSTE, "inventario_inicial", "Inventario inicial"),
    (MotivoEvento.Ambito.AJUSTE, "merma_de_corte", "Merma de corte"),
    (MotivoEvento.Ambito.AJUSTE, "material_dañado", "Material dañado"),
    (MotivoEvento.Ambito.AJUSTE, "devolucion_a_proveedor", "Devolución a proveedor"),
]


def densidad_de(*textos):
    junto = " ".join((t or "").upper() for t in textos)
    for claves, valor in DENSIDADES:
        if any(clave in junto for clave in claves):
            return valor
    return DENSIDAD_POR_DEFECTO


class Command(BaseCommand):
    help = "Crea el almacén, los motivos y trae el catálogo de material existente."

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="No escribe nada.")

    def handle(self, *args, **opciones):
        self.simular = opciones["simular"]
        if self.simular:
            self.stdout.write(self.style.WARNING("Simulación: no se escribe nada.\n"))

        with transaction.atomic(using=BASE):
            almacen = self._almacen()
            self._motivos()
            traidos, actualizados = self._materiales()
            if self.simular:
                transaction.set_rollback(True, using=BASE)

        self.stdout.write(self.style.MIGRATE_HEADING("\nResumen"))
        self.stdout.write(f"  almacén:            {almacen.nombre}")
        self.stdout.write(f"  materiales nuevos:  {traidos}")
        self.stdout.write(f"  materiales al día:  {actualizados}")

        if not self.simular:
            folios.crear_secuencia("compras")
            self.stdout.write("  secuencia de folios de compra creada")

        self.stdout.write(
            self.style.WARNING(
                "\n  Todos los materiales quedan en existencia CERO, a propósito.\n"
                "  El inventario arranca contando lo que de verdad hay:\n"
                "      python manage.py inventario_fisico --plantilla conteo.csv\n"
                "  se llena a mano y se carga con:\n"
                "      python manage.py inventario_fisico --cargar conteo.csv\n"
            )
        )

    def _almacen(self):
        almacen, creado = Almacen.objects.using(BASE).get_or_create(
            codigo="principal",
            defaults={"nombre": "Almacén principal", "es_principal": True},
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING("\nAlmacén")
            + f"\n  {almacen.nombre}: {'creado' if creado else 'ya existía'}"
        )
        return almacen

    def _motivos(self):
        creados = 0
        for ambito, codigo, nombre in MOTIVOS:
            _, nuevo = MotivoEvento.objects.using(BASE).get_or_create(
                ambito=ambito,
                codigo=codigo,
                defaults={"nombre": nombre, "activo": True, "es_sistema": True},
            )
            creados += int(nuevo)
        self.stdout.write(
            self.style.MIGRATE_HEADING("\nMotivos de almacén") + f"\n  {creados} nuevo(s)"
        )

    def _materiales(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nCatálogo de material"))
        traidos = actualizados = 0

        for placa in LaserMaterialPlaca.objects.using(BASE).all().order_by("pk"):
            densidad = densidad_de(placa.categoria_material, placa.tipo_material, placa.nombre)
            material, creado = Material.objects.using(BASE).update_or_create(
                legacy_modelo="LaserMaterialPlaca",
                legacy_id=placa.pk,
                defaults={
                    "codigo": f"PL-{placa.pk:05d}",
                    "nombre": self._nombre(placa),
                    "nombre_normalizado": self._nombre(placa).upper(),
                    "categoria": placa.categoria_material,
                    "tipo": placa.tipo_material,
                    "calibre": placa.calibre,
                    # Una placa se compra y se consume por piezas enteras.
                    "unidad": Material.Unidad.PIEZA,
                    "espesor_mm": Decimal(str(placa.espesor_mm or 0)).quantize(
                        Decimal("0.001")
                    ),
                    "largo_mm": placa.largo_mm,
                    "ancho_mm": placa.ancho_mm,
                    "peso_kg": Decimal(str(placa.peso_kg or 0)).quantize(Decimal("0.001")),
                    "densidad": densidad,
                    "activo": placa.activo,
                },
            )
            traidos += int(creado)
            actualizados += int(not creado)

            # El peso que trae el catálogo manda; sólo se calcula cuando falta.
            if material.peso_kg <= 0:
                calculado = material.peso_calculado()
                if calculado > 0:
                    Material.objects.using(BASE).filter(pk=material.pk).update(
                        peso_kg=calculado
                    )
                    self.stdout.write(
                        f"  {material.codigo}: sin peso en el catálogo, "
                        f"calculado {calculado} kg por geometría"
                    )

        self.stdout.write(f"  {traidos} nuevo(s), {actualizados} ya existente(s)")
        return traidos, actualizados

    def _nombre(self, placa):
        """Un nombre que distinga las placas entre sí.

        En el catálogo heredado hay decenas de filas llamadas todas «LÁMINA
        NEGRA»: lo que las diferencia es el calibre y la medida, que están en
        otras columnas. Al juntarlas en un solo catálogo eso deja de valer,
        porque nadie sabría cuál está pidiendo.
        """
        partes = [placa.nombre or placa.tipo_material or "Material"]
        if placa.calibre:
            partes.append(f"cal. {placa.calibre}")
        elif placa.espesor_mm:
            partes.append(f"{placa.espesor_mm} mm")
        if placa.largo_mm and placa.ancho_mm:
            partes.append(f"{placa.largo_mm}×{placa.ancho_mm}")
        return " · ".join(partes)[:180]
