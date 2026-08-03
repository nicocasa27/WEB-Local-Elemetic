"""Compara cada día lo heredado con el núcleo y anota lo que no coincida.

Es el paso 5 de la migración, y el que decide si se puede seguir. La regla es
simple y no se negocia: **una línea no se corta hasta que esta comprobación
lleve siete días seguidos sin encontrar ni una diferencia.**

Ese control es lo que convierte la migración en algo aburrido. Sin él, el
corte es una apuesta: se cambia la fuente de verdad y se espera que nadie note
nada. Con él, cuando llega el día del corte ya se sabe desde hace una semana
que las dos mitades dicen lo mismo.

Pensado para correr una vez al día desde una tarea programada:

    python manage.py reconciliar_nucleo
    python manage.py reconciliar_nucleo --linea herreria
    python manage.py reconciliar_nucleo --resumen

Lo que encuentra se guarda en `DivergenciaReconciliacion`, no sólo se imprime:
hace falta poder mirar la racha hacia atrás para decidir el corte, y para eso
tiene que estar escrito.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion, RobotOrdenProduccion
from core import banderas
from nucleo.management.commands.sembrar_nucleo import clave
from nucleo.models import DivergenciaReconciliacion, LineaNegocio, OrdenProduccion
from produccion.models import Viga

BASE = "mes"

#: Días seguidos sin diferencias que hacen falta antes de cortar una línea.
RACHA_EXIGIDA = 7

FUENTES = {
    "vigas": ("Viga", Viga, "internal_id"),
    "herreria": ("HerrOrdenProduccion", HerrOrdenProduccion, "id"),
    "corta": ("LaserOrdenProduccion", LaserOrdenProduccion, "id"),
    "robotica": ("RobotOrdenProduccion", RobotOrdenProduccion, "id"),
}


def _texto(valor):
    if valor is None:
        return ""
    return str(valor)[:255]


class Command(BaseCommand):
    help = "Compara las tablas heredadas con el núcleo y registra las divergencias."

    def add_arguments(self, parser):
        parser.add_argument("--linea", choices=sorted(FUENTES), help="Sólo una línea.")
        parser.add_argument(
            "--resumen",
            action="store_true",
            help="No compara: enseña la racha de días limpios de cada línea.",
        )
        parser.add_argument(
            "--corregir",
            action="store_true",
            help=(
                "Vuelve a reflejar en el núcleo las filas que difieren. "
                "No toca las tablas heredadas: la verdad sigue siendo la suya."
            ),
        )

    def handle(self, *args, **opciones):
        if opciones["resumen"]:
            self._resumen()
            return

        self.corregir = opciones["corregir"]
        lineas = [opciones["linea"]] if opciones.get("linea") else sorted(FUENTES)
        total = 0
        for codigo in lineas:
            total += self._reconciliar(codigo)

        if total:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{total} divergencia(s). La racha vuelve a cero: "
                    "ninguna línea con diferencias se corta."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Sin divergencias."))

    # ------------------------------------------------------- comparación

    def _reconciliar(self, codigo):
        etiqueta, modelo, campo_pk = FUENTES[codigo]
        linea = LineaNegocio.objects.using(BASE).filter(codigo=codigo).first()
        if linea is None:
            return 0

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{linea.nombre}  ({banderas.modo(codigo)})"
            )
        )

        migradas = {
            orden.legacy_id: orden
            for orden in OrdenProduccion.objects.using(BASE)
            .filter(legacy_modelo=etiqueta)
            .select_related("etapa_actual")
        }

        divergencias = []
        vistas = set()

        for fila in modelo.objects.using(BASE).all().iterator(chunk_size=500):
            legacy_id = getattr(fila, campo_pk)
            vistas.add(legacy_id)
            orden = migradas.get(legacy_id)
            if orden is None:
                divergencias.append((legacy_id, None, "existencia", "presente", "ausente"))
                continue
            divergencias.extend(
                (legacy_id, orden, campo, heredado, nucleo)
                for campo, heredado, nucleo in self._comparar(codigo, fila, orden)
            )

        # Lo que está en el núcleo y ya no está en lo heredado. Puede ser una
        # orden purgada; si es otra cosa, hay que saberlo antes del corte.
        for legacy_id, orden in migradas.items():
            if legacy_id not in vistas:
                divergencias.append((legacy_id, orden, "existencia", "ausente", "presente"))

        for legacy_id, orden, campo, heredado, nucleo in divergencias:
            DivergenciaReconciliacion.objects.using(BASE).create(
                linea=linea,
                legacy_modelo=etiqueta,
                legacy_id=legacy_id,
                orden=orden,
                campo=campo,
                valor_heredado=_texto(heredado),
                valor_nucleo=_texto(nucleo),
            )
            self.stdout.write(
                self.style.ERROR(
                    f"  {etiqueta}#{legacy_id}.{campo}: heredado {heredado!r} · núcleo {nucleo!r}"
                )
            )

        if not divergencias:
            self.stdout.write(f"  {len(vistas)} orden(es), sin diferencias")
            return 0

        if self.corregir:
            self._corregir(etiqueta, {d[0] for d in divergencias})

        return len(divergencias)

    def _corregir(self, etiqueta, identificadores):
        """Vuelve a reflejar las filas que difieren.

        Cubre las escrituras en bloque, que no disparan señales y por tanto no
        se reflejan solas. Se hace aquí y no en la señal porque hacerlo aquí
        deja constancia previa de la diferencia: primero se anota qué estaba
        mal y luego se arregla, en vez de arreglarlo sin que nadie sepa que
        pasó.
        """
        from nucleo.management.commands.backfill_nucleo import Command as Volcado

        volcado = Volcado.para_espejo()
        arregladas = 0
        for legacy_id in sorted(identificadores):
            try:
                if volcado.volcar_una(etiqueta, legacy_id) is not None:
                    arregladas += 1
            except Exception:
                self.stderr.write(f"  no se pudo corregir {etiqueta}#{legacy_id}")
        self.stdout.write(self.style.WARNING(f"  {arregladas} fila(s) vueltas a reflejar"))

    def _comparar(self, codigo, fila, orden):
        """Campo a campo. Devuelve las diferencias encontradas.

        Se comparan sólo los campos que **significan** algo para la operación.
        Añadir aquí un campo que el núcleo calcula de otra forma llenaría el
        informe de ruido y haría que nadie lo mirase, que es la manera de que
        una comprobación así deje de servir.
        """
        etapa_nucleo = orden.etapa_actual.nombre if orden.etapa_actual_id else ""

        if codigo == "vigas":
            yield from self._diferencias(
                ("etapa", fila.estado, etapa_nucleo, clave),
                ("codigo", fila.codigo_viga, orden.codigo, clave),
                ("prioridad", fila.prioridad, orden.prioridad, int),
                ("fecha_compromiso", fila.fecha_compromiso, orden.fecha_compromiso, None),
            )
            return

        if codigo == "robotica":
            yield from self._diferencias(
                ("estado", fila.estado, orden.estado, lambda v: clave(v)),
                ("cantidad_objetivo", fila.cantidad_objetivo, orden.cantidad_objetivo, int),
            )
            return

        yield from self._diferencias(
            ("etapa", fila.estado_etapa, etapa_nucleo, clave),
            ("estado", fila.estado, orden.estado, clave),
            ("codigo", fila.codigo, orden.codigo, clave),
            ("total_piezas", fila.total_piezas, orden.total_piezas, int),
            ("cantidad_objetivo", fila.cantidad_objetivo, orden.cantidad_objetivo, int),
            ("cantidad_producida", fila.cantidad_producida, orden.cantidad_producida, int),
            ("cantidad_pintada", fila.cantidad_pintada, orden.cantidad_pintada, int),
            ("cantidad_terminada", fila.cantidad_terminada, orden.cantidad_terminada, int),
            ("prioridad", fila.prioridad, orden.prioridad, int),
            ("fecha_compromiso", fila.fecha_compromiso, orden.fecha_compromiso, None),
        )

    def _diferencias(self, *campos):
        for nombre, heredado, nucleo, normaliza in campos:
            a, b = heredado, nucleo
            if normaliza is not None:
                try:
                    a, b = normaliza(heredado), normaliza(nucleo)
                except (TypeError, ValueError):
                    pass
            if a != b:
                yield nombre, heredado, nucleo

    # ---------------------------------------------------------- resumen

    def _resumen(self):
        """Cuántos días seguidos lleva limpia cada línea."""
        self.stdout.write(self.style.MIGRATE_HEADING("Racha de días sin divergencias"))
        hoy = timezone.now().date()

        for codigo in sorted(FUENTES):
            linea = LineaNegocio.objects.using(BASE).filter(codigo=codigo).first()
            if linea is None:
                continue

            por_dia = {
                fila["dia"]
                for fila in DivergenciaReconciliacion.objects.using(BASE)
                .filter(linea=linea)
                .extra(select={"dia": "date(detectada_en)"})
                .values("dia")
                .annotate(n=Count("id"))
            }

            racha = 0
            while racha < 60:
                dia = hoy - timedelta(days=racha)
                if any(str(d) == str(dia) for d in por_dia):
                    break
                racha += 1

            modo = banderas.modo(codigo)
            if modo == banderas.CORTE:
                estado = "ya cortada"
                estilo = self.style.SUCCESS
            elif racha >= RACHA_EXIGIDA:
                estado = f"lista para cortar ({racha} días limpios)"
                estilo = self.style.SUCCESS
            else:
                estado = f"faltan {RACHA_EXIGIDA - racha} día(s) limpios"
                estilo = self.style.WARNING

            self.stdout.write(f"  {linea.nombre:<14} {modo:<8} " + estilo(estado))

        self.stdout.write(
            "\n  El corte se hace con la variable de entorno correspondiente\n"
            "  (por ejemplo MES_NUCLEO_HERRERIA=corte) y se deshace poniéndola\n"
            "  de nuevo en «doble». Ver core/banderas.py y DESPLIEGUE.md."
        )
