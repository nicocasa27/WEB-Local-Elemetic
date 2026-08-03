"""Arranca y cuadra el inventario contando lo que de verdad hay.

Un inventario no empieza con un número escrito a ojo: empieza contando. Este
comando saca una plantilla para bajar al almacén, y luego carga lo contado.

    python manage.py inventario_fisico --plantilla conteo.csv
    python manage.py inventario_fisico --cargar conteo.csv --simular
    python manage.py inventario_fisico --cargar conteo.csv

**La primera carga y las siguientes no hacen lo mismo, y eso es deliberado.**
La primera es el inventario inicial: se registra lo que hay y punto. Las
siguientes registran **la diferencia** entre lo contado y lo que el sistema
creía, con motivo «conteo físico». Esa diferencia es la única medida real de
si el inventario se está llevando bien, y por eso queda escrita en vez de
sustituirse en silencio.

La plantilla lleva una fila por material dado de alta, con lo que el sistema
cree que hay. Se baja al almacén, se cuenta y se rellena la columna
`contado`. Las filas vacías no se tocan: contar medio almacén un día y la otra
mitad al siguiente es lo normal, y el comando lo admite.
"""

import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.servicios import inventario as servicio
from inventario.models import Existencia, LoteMaterial, Material, MovimientoMaterial
from nucleo.models import MotivoEvento

BASE = "mes"
CERO = Decimal("0")

#: Qué le pasó a una línea de la hoja. Tres estados y no un texto suelto:
#: distinguir «no había nada que hacer» de «salió bien» y de «está mal» con el
#: tipo del valor devuelto es exactamente cómo se cuela un error silencioso.
SIN_CONTAR = "sin_contar"
APLICADO = "aplicado"
PROBLEMA = "problema"

COLUMNAS = [
    "codigo",
    "nombre",
    "unidad",
    "sistema",
    "contado",
    "lote",
    "colada",
    "costo_unitario",
    "observaciones",
]


class Command(BaseCommand):
    help = "Saca la plantilla de conteo físico y carga lo contado."

    def add_arguments(self, parser):
        parser.add_argument("--plantilla", metavar="ARCHIVO", help="Genera la hoja de conteo.")
        parser.add_argument("--cargar", metavar="ARCHIVO", help="Carga la hoja rellenada.")
        parser.add_argument("--simular", action="store_true", help="No escribe nada.")
        parser.add_argument(
            "--actor", default="conteo_fisico", help="Quién firma los ajustes."
        )

    def handle(self, *args, **opciones):
        if opciones["plantilla"]:
            self._plantilla(opciones["plantilla"])
        elif opciones["cargar"]:
            self._cargar(opciones["cargar"], opciones["simular"], opciones["actor"])
        else:
            raise CommandError("Hay que indicar --plantilla o --cargar.")

    # ---------------------------------------------------------- plantilla

    def _plantilla(self, ruta):
        almacen = servicio.almacen_principal()
        materiales = Material.objects.using(BASE).filter(activo=True).order_by(
            "categoria", "tipo", "nombre"
        )

        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
            escritor.writeheader()
            for material in materiales:
                escritor.writerow(
                    {
                        "codigo": material.codigo,
                        "nombre": material.nombre,
                        "unidad": material.unidad,
                        "sistema": servicio.existencia(material, almacen=almacen),
                        "contado": "",
                        "lote": "",
                        "colada": "",
                        "costo_unitario": "",
                        "observaciones": "",
                    }
                )

        self.stdout.write(
            self.style.SUCCESS(f"{materiales.count()} material(es) escritos en {ruta}")
        )
        self.stdout.write(
            "\n  Rellenar sólo la columna `contado`. Las filas que se dejen en blanco\n"
            "  no se tocan, así que se puede contar por partes.\n"
            "\n"
            "  `lote` y `colada` importan más de lo que parece: son lo que después\n"
            "  permite responder de qué colada salió una pieza cuando un cliente\n"
            "  reclame. Si no se saben, se dejan vacías y el comando agrupa todo lo\n"
            "  contado en un lote de inventario inicial, dejando constancia de que\n"
            "  ese material entró sin certificado."
        )

    # ------------------------------------------------------------ carga

    def _cargar(self, ruta, simular, actor):
        try:
            with open(ruta, newline="", encoding="utf-8-sig") as archivo:
                filas = list(csv.DictReader(archivo))
        except FileNotFoundError as error:
            raise CommandError(f"No existe el archivo {ruta}.") from error

        if not filas:
            raise CommandError("El archivo no tiene ninguna fila.")

        almacen = servicio.almacen_principal()
        es_primera_carga = not MovimientoMaterial.objects.using(BASE).exists()
        motivo = self._motivo(es_primera_carga)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "\nInventario inicial" if es_primera_carga else "\nConteo físico"
            )
        )
        if simular:
            self.stdout.write(self.style.WARNING("  Simulación: no se escribe nada."))

        aplicados = ignorados = 0
        problemas = []

        with transaction.atomic(using=BASE):
            for numero, fila in enumerate(filas, start=2):
                estado, mensaje = self._fila(fila, almacen, motivo, actor, es_primera_carga)
                if estado == SIN_CONTAR:
                    ignorados += 1
                elif estado == PROBLEMA:
                    problemas.append(f"línea {numero}: {mensaje}")
                else:
                    aplicados += 1
                    self.stdout.write(f"  {mensaje}")

            if problemas:
                for problema in problemas:
                    self.stdout.write(self.style.ERROR(f"  {problema}"))
                raise CommandError(
                    f"{len(problemas)} línea(s) con problemas. No se aplicó nada: "
                    "un conteo a medias es peor que ninguno."
                )
            if simular:
                transaction.set_rollback(True, using=BASE)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  {aplicados} material(es) ajustados, {ignorados} sin contar."
            )
        )
        if simular:
            self.stdout.write(self.style.WARNING("  Simulación: nada de esto se guardó."))

    def _motivo(self, es_primera_carga):
        codigo = "inventario_inicial" if es_primera_carga else "conteo_fisico"
        motivo = (
            MotivoEvento.objects.using(BASE)
            .filter(ambito=MotivoEvento.Ambito.AJUSTE, codigo=codigo)
            .first()
        )
        if motivo is None:
            raise CommandError(
                f"Falta el motivo «{codigo}». Ejecutar antes `sembrar_inventario`."
            )
        return motivo

    def _fila(self, fila, almacen, motivo, actor, es_primera_carga):
        """Procesa una línea. Devuelve (estado, mensaje)."""
        contado = (fila.get("contado") or "").strip()
        if not contado:
            return SIN_CONTAR, ""

        codigo = (fila.get("codigo") or "").strip()
        material = Material.objects.using(BASE).filter(codigo=codigo).first()
        if material is None:
            return PROBLEMA, f"no existe ningún material con código {codigo!r}"

        try:
            contado = Decimal(contado.replace(",", ""))
        except InvalidOperation:
            return PROBLEMA, f"«{contado}» no es una cantidad"
        if contado < CERO:
            return PROBLEMA, "no se puede contar una cantidad negativa"

        lote = self._lote(fila, material, es_primera_carga)
        actual = servicio.existencia(material, almacen=almacen, lote=lote)
        diferencia = (contado - actual).quantize(Decimal("0.000001"))
        if diferencia == CERO:
            return SIN_CONTAR, ""

        servicio.ajustar(
            material=material,
            cantidad=diferencia,
            actor=actor,
            motivo=motivo,
            almacen=almacen,
            lote=lote,
            comentario=(fila.get("observaciones") or "")[:255],
        )
        signo = "+" if diferencia > 0 else ""
        return APLICADO, (
            f"{material.codigo:<12} sistema {actual} → contado {contado} "
            f"({signo}{diferencia})"
        )

    def _lote(self, fila, material, es_primera_carga):
        """El lote de la fila, creándolo si hace falta.

        Sin lote no hay trazabilidad, así que siempre se crea uno: o el que
        venga en la hoja, o uno de inventario inicial que deja constancia
        explícita de que ese material entró sin certificado y sin colada
        conocida. Es información, no un hueco.
        """
        codigo_lote = (fila.get("lote") or "").strip()
        colada = (fila.get("colada") or "").strip()
        if not codigo_lote:
            codigo_lote = "INICIAL" if es_primera_carga else f"CONTEO-{timezone.localdate():%Y%m%d}"

        costo = (fila.get("costo_unitario") or "").strip()
        try:
            costo = Decimal(costo.replace(",", "")) if costo else CERO
        except InvalidOperation:
            costo = CERO

        lote, creado = LoteMaterial.objects.using(BASE).get_or_create(
            material=material,
            codigo=codigo_lote,
            defaults={
                "colada": colada,
                "costo_unitario": costo,
                "recibido_en": timezone.localdate(),
                "observaciones": (
                    "alta por inventario inicial: sin certificado ni colada conocida"
                    if es_primera_carga and not colada
                    else ""
                ),
            },
        )
        # Un costo que llega después sí se recoge; el resto del lote no se
        # toca, porque ya puede haber material consumido valorado con él.
        if not creado and costo > CERO and lote.costo_unitario <= CERO:
            LoteMaterial.objects.using(BASE).filter(pk=lote.pk).update(costo_unitario=costo)
            lote.refresh_from_db(using=BASE)
        return lote
