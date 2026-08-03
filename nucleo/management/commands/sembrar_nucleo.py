"""Siembra la configuración del núcleo: líneas, etapas, transiciones y motivos.

Es el paso 2 de la migración. No toca ni una fila de operación: sólo rellena
las tablas de configuración y crea las secuencias de folio.

Lo importante no es lo que escribe, sino lo que **comprueba**: al terminar,
para cada valor de estado que existe de verdad en la base tiene que haber una
etapa que lo represente. Si falta alguno, el comando se niega a continuar y lo
dice. Descubrir en ese momento que hay datos que nadie sabía que existían es
barato; descubrirlo durante el volcado, no.

Dos decisiones que conviene entender antes de leer el código:

**Se siembran todas las transiciones, no las razonables.** El sistema heredado
permite mover una orden a cualquier estado y sólo comprueba si el movimiento
va hacia atrás, en cuyo caso pide un motivo. Sembrar exactamente eso es lo
correcto: una migración de datos no es el sitio para endurecer reglas. Apretar
se hace después, borrando filas, y se nota en el acto.

**El bloqueo por máquina parada no se enciende solo.** Hoy esa regla vive en
el navegador, así que cualquiera con la dirección se la salta. Pasarla al
servidor es una mejora real, pero cambia el comportamiento, y eso se decide a
propósito: `--endurecer` la activa.

    python manage.py sembrar_nucleo --simular
    python manage.py sembrar_nucleo
    python manage.py sembrar_nucleo --endurecer
"""

import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogos.models import (
    HerrOrdenProduccion,
    LaserOrdenProduccion,
    MaquinaFallaTipo,
    MaquinaParoMotivo,
    RobotOrdenProduccion,
)
from core import estados as estados_core
from core import folios
from nucleo.models import Etapa, EtapaAlias, LineaNegocio, MotivoEvento, TransicionPermitida
from produccion.models import Viga

BASE = "mes"


def clave(valor):
    texto = (valor or "").strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


def codigo_de(nombre):
    """`Espera de corte` → `espera_corte`.

    Se quitan las palabras de enlace para que el código sea corto y estable:
    lo que se lee en los informes es el nombre, no esto.
    """
    palabras = [p for p in clave(nombre).replace("(", " ").replace(")", " ").split() if p != "de"]
    return "_".join(palabras)[:40]


# --------------------------------------------------------------- las líneas
#
# Aquí es donde vive de verdad la diferencia entre los cuatro motores. Son
# cinco opciones; el resto del código que hoy está copiado cuatro veces no
# aportaba ninguna diferencia más.

E = estados_core

LINEAS = [
    {
        "codigo": "vigas",
        "nombre": "Vigas",
        "prefijo_folio": "V",
        # Las vigas salen por pedidos y logística de producto terminado, no
        # por el almacén de piezas.
        "usa_almacen": False,
        "usa_acuse": False,
        "orden_visual": 1,
        "etapas": E.SECUENCIA,
        "legacy": ("Viga", Viga, "estado"),
    },
    {
        "codigo": "herreria",
        "nombre": "Herrería",
        "prefijo_folio": "H",
        "usa_almacen": True,
        "usa_acuse": True,
        "orden_visual": 2,
        "etapas": E.SECUENCIA_COMPLETA,
        "legacy": ("HerrOrdenProduccion", HerrOrdenProduccion, "estado_etapa"),
    },
    {
        "codigo": "corta",
        "nombre": "Corte láser",
        "prefijo_folio": "L",
        "usa_almacen": True,
        "usa_acuse": True,
        "orden_visual": 3,
        "etapas": E.SECUENCIA_COMPLETA,
        "legacy": ("LaserOrdenProduccion", LaserOrdenProduccion, "estado_etapa"),
    },
    {
        "codigo": "robotica",
        "nombre": "Robótica",
        "prefijo_folio": "R",
        "usa_almacen": False,
        "usa_acuse": False,
        "orden_visual": 4,
        # Robótica nunca tuvo máquina de estados: las órdenes sólo están
        # abiertas o cerradas, y las etapas viven en las partidas
        # (`RobotOrdenItem.etapa`). Se siembran esas cuatro más el cierre,
        # que es lo que ya usan las asignaciones. Por eso es la línea con la
        # que se ensaya el corte: es la que menos tiene que perder.
        "etapas": ["Corte", "Armado", "Soldadura", "Pintura", E.TERMINADO],
        "legacy": ("RobotOrdenProduccion", RobotOrdenProduccion, None),
    },
]

ESPERAS = {clave(v) for v in E.ESTADOS_DE_ESPERA}

MOTIVOS_DEL_SISTEMA = [
    (MotivoEvento.Ambito.RETROCESO, "correccion", "Corrección de captura"),
    (MotivoEvento.Ambito.RETROCESO, "retrabajo", "Retrabajo"),
    (MotivoEvento.Ambito.RETRABAJO, "retrabajo", "Retrabajo"),
    (MotivoEvento.Ambito.AJUSTE, "sin_historico", "Ajuste sin historial (migración)"),
    (MotivoEvento.Ambito.AJUSTE, "conteo_fisico", "Ajuste por conteo físico"),
    (MotivoEvento.Ambito.REVERSION, "error_de_captura", "Error de captura"),
    (MotivoEvento.Ambito.CANCELACION, "cancelada_por_cliente", "Cancelada por el cliente"),
]


class Command(BaseCommand):
    help = "Siembra líneas, etapas, transiciones, motivos y secuencias de folio del núcleo."

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true", help="No escribe nada.")
        parser.add_argument(
            "--endurecer",
            action="store_true",
            help=(
                "Activa el bloqueo por máquina parada en las transiciones de avance. "
                "Cambia el comportamiento: hoy esa regla sólo existe en el navegador."
            ),
        )

    def handle(self, *args, **opciones):
        self.simular = opciones["simular"]
        self.endurecer = opciones["endurecer"]

        if self.simular:
            self.stdout.write(self.style.WARNING("Simulación: no se escribe nada.\n"))

        with transaction.atomic(using=BASE):
            for config in LINEAS:
                self._sembrar_linea(config)
            self._sembrar_motivos()
            self._comprobar_cobertura()
            if self.simular:
                transaction.set_rollback(True, using=BASE)

        if not self.simular:
            self._alinear_secuencias()

        self.stdout.write(self.style.SUCCESS("\nConfiguración del núcleo lista."))

    # ------------------------------------------------------------- líneas

    def _sembrar_linea(self, config):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{config['nombre']}"))

        linea, creada = LineaNegocio.objects.using(BASE).update_or_create(
            codigo=config["codigo"],
            defaults={
                "nombre": config["nombre"],
                "prefijo_folio": config["prefijo_folio"],
                "usa_almacen": config["usa_almacen"],
                "usa_acuse": config["usa_acuse"],
                "orden_visual": config["orden_visual"],
            },
        )
        self.stdout.write(f"  línea: {'creada' if creada else 'actualizada'}")

        etapas = {}
        for posicion, nombre in enumerate(config["etapas"], start=1):
            etapa, _ = Etapa.objects.using(BASE).update_or_create(
                linea=linea,
                codigo=codigo_de(nombre),
                defaults={
                    "nombre": nombre,
                    "orden": posicion,
                    "es_espera": clave(nombre) in ESPERAS,
                    "es_cierre_pendiente": nombre == E.CIERRE_PENDIENTE,
                    "es_terminal": nombre == E.ENVIADO,
                    "color": estados_core.color(nombre),
                },
            )
            etapas[nombre] = etapa
            self._sembrar_alias(etapa, nombre)

        self.stdout.write(f"  etapas: {len(etapas)}")
        self._sembrar_transiciones(linea, list(etapas.values()))

    def _sembrar_alias(self, etapa, nombre):
        """Todas las formas conocidas de escribir esta etapa.

        Sin esto, el volcado no sabría que «Espera Armado» y «Espera de
        armado» son la misma cosa, que es el origen de que una orden guardada
        con la variante equivocada desapareciera de los filtros.
        """
        for variante in {nombre, *estados_core.variantes(nombre)}:
            EtapaAlias.objects.using(BASE).update_or_create(
                etapa=etapa,
                valor_normalizado=clave(variante),
                defaults={"valor": variante},
            )

    def _sembrar_transiciones(self, linea, etapas):
        """Todos los pares, tal como se comporta hoy el sistema.

        Se marca como retroceso lo que va hacia atrás en la secuencia, y ésos
        son los que exigen motivo. Es exactamente la regla actual, con dos
        diferencias: ahora vive en el servidor y ahora se puede consultar.
        """
        creadas = 0
        inicial = etapas[0]
        _, nueva = TransicionPermitida.objects.using(BASE).update_or_create(
            linea=linea, desde=None, hasta=inicial, defaults={"es_retroceso": False}
        )
        creadas += int(nueva)

        for desde in etapas:
            for hasta in etapas:
                if desde.pk == hasta.pk:
                    continue
                retroceso = hasta.orden < desde.orden
                _, nueva = TransicionPermitida.objects.using(BASE).update_or_create(
                    linea=linea,
                    desde=desde,
                    hasta=hasta,
                    defaults={
                        "es_retroceso": retroceso,
                        "requiere_motivo": retroceso,
                        "bloquea_si_maquina_en_paro": (
                            self.endurecer and not retroceso and not hasta.es_espera
                        ),
                    },
                )
                creadas += int(nueva)

        total = TransicionPermitida.objects.using(BASE).filter(linea=linea).count()
        self.stdout.write(f"  transiciones: {total} ({creadas} nuevas)")

    # ------------------------------------------------------------ motivos

    def _sembrar_motivos(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nMotivos"))
        heredados = 0

        for modelo, ambito, etiqueta in (
            (MaquinaParoMotivo, MotivoEvento.Ambito.PARO, "MaquinaParoMotivo"),
            (MaquinaFallaTipo, MotivoEvento.Ambito.FALLA, "MaquinaFallaTipo"),
        ):
            for fila in modelo.objects.using(BASE).all():
                MotivoEvento.objects.using(BASE).update_or_create(
                    ambito=ambito,
                    codigo=codigo_de(fila.nombre) or f"motivo_{fila.pk}",
                    defaults={
                        "nombre": fila.nombre,
                        "activo": fila.activo,
                        "es_sistema": fila.es_sistema,
                        "legacy_modelo": etiqueta,
                        "legacy_id": fila.pk,
                    },
                )
                heredados += 1

        for ambito, codigo, nombre in MOTIVOS_DEL_SISTEMA:
            MotivoEvento.objects.using(BASE).update_or_create(
                ambito=ambito,
                codigo=codigo,
                defaults={"nombre": nombre, "activo": True, "es_sistema": True},
            )

        self.stdout.write(
            f"  {heredados} heredado(s) de paros y fallas, "
            f"{len(MOTIVOS_DEL_SISTEMA)} del sistema"
        )

    # --------------------------------------------------------- comprobación

    def _comprobar_cobertura(self):
        """Cada estado que existe en la base tiene que tener su etapa.

        Éste es el control que decide si la migración puede seguir. Un valor
        sin etapa significa que hay datos cuya forma no conocíamos, y en ese
        caso lo correcto es pararse.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nCobertura de los estados reales"))
        huerfanos = []
        total = 0

        for config in LINEAS:
            etiqueta, modelo, campo = config["legacy"]
            if not campo:
                continue
            linea = LineaNegocio.objects.using(BASE).get(codigo=config["codigo"])
            conocidos = set(
                EtapaAlias.objects.using(BASE)
                .filter(etapa__linea=linea)
                .values_list("valor_normalizado", flat=True)
            )
            valores = (
                modelo.objects.using(BASE)
                .exclude(**{f"{campo}__isnull": True})
                .values_list(campo, flat=True)
                .distinct()
            )
            for valor in valores:
                total += 1
                if not (valor or "").strip():
                    continue
                if clave(valor) not in conocidos:
                    huerfanos.append((config["nombre"], valor))

        if huerfanos:
            for nombre_linea, valor in huerfanos:
                self.stdout.write(self.style.ERROR(f"  {nombre_linea}: {valor!r} sin etapa"))
            raise CommandError(
                f"{len(huerfanos)} valor(es) de estado sin etapa que los represente.\n"
                "Hay datos cuya forma no conocíamos. Revisar con `auditar_estados` y\n"
                "añadir el alias correspondiente antes de continuar: seguir ahora\n"
                "significaría perder esas órdenes al volcarlas."
            )

        self.stdout.write(
            self.style.SUCCESS(f"  {total} valor(es) distinto(s), todos con etapa")
        )

    # --------------------------------------------------------- secuencias

    def _alinear_secuencias(self):
        """Cada folio arranca por encima del último ya emitido.

        El margen de mil es deliberado: durante la convivencia las dos
        numeraciones avanzan a la vez, y ningún folio nuevo debe poder
        chocar con uno impreso.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nSecuencias de folio"))
        for config in LINEAS:
            _, modelo, _ = config["legacy"]
            ultimo = modelo.objects.using(BASE).order_by("-pk").values_list("pk", flat=True).first()
            folios.crear_secuencia(config["codigo"])
            valor = folios.alinear(config["codigo"], int(ultimo or 0) + 1000)
            self.stdout.write(
                f"  {config['codigo']:10} última heredada {ultimo or 0:>6} → "
                f"secuencia en {valor}"
            )
