"""Comprueba que el núcleo dice lo mismo que las tablas heredadas.

Un volcado que «parece que fue bien» no vale para nada: la única forma de
poder cortar una línea sin miedo es tener una comprobación que se ejecute sola
y que se pueda enseñar. Ésta compara cuatro cosas, y termina con código de
salida distinto de cero si alguna falla:

1. **Censo.** Tantas órdenes en el núcleo como en la tabla heredada, ni una
   más ni una menos.
2. **Kilos.** El peso total tiene que coincidir hasta el gramo. Es la
   comprobación que más rápido delata un error de unidades —confundir el peso
   por pieza con el peso de la orden es exactamente la clase de fallo que se
   cuela sin ruido.
3. **Reparto por etapas.** Cuántas órdenes hay en cada estado a un lado y a
   otro.
4. **Historial contra contadores.** Que la suma de los eventos dé el mismo
   número que la caché de la orden. Ésta es la que hace que el registro sea
   una fuente de verdad y no una decoración.

Además informa —sin considerarlo un fallo— de dos cosas que conviene mirar:
cuántos movimientos no se pudieron reconstruir, y cuántas órdenes venían ya
con los contadores incoherentes.

    python manage.py verificar_backfill
    python manage.py verificar_backfill --linea herreria
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion, RobotOrdenProduccion
from nucleo.management.commands.sembrar_nucleo import clave
from nucleo.models import EventoProduccion, LineaNegocio, OrdenProduccion
from produccion.models import Viga
from core.bases import BASE  # noqa: F401


FUENTES = {
    "vigas": ("Viga", Viga, "estado", "peso_kg", 1),
    "herreria": ("HerrOrdenProduccion", HerrOrdenProduccion, "estado_etapa", "peso_kg", None),
    "corta": ("LaserOrdenProduccion", LaserOrdenProduccion, "estado_etapa", "peso_kg", None),
    "robotica": ("RobotOrdenProduccion", RobotOrdenProduccion, None, None, None),
}

CENTIMO = Decimal("0.001")


class Command(BaseCommand):
    help = "Compara el núcleo con las tablas heredadas y falla si no cuadran."

    def add_arguments(self, parser):
        parser.add_argument("--linea", choices=sorted(FUENTES), help="Sólo una línea.")

    def handle(self, *args, **opciones):
        lineas = [opciones["linea"]] if opciones.get("linea") else sorted(FUENTES)
        problemas = []

        for codigo in lineas:
            problemas.extend(self._verificar(codigo))

        self._historial_contra_contadores(lineas, problemas)
        self._informar_calidad(lineas)

        self.stdout.write("")
        if problemas:
            for problema in problemas:
                self.stdout.write(self.style.ERROR(f"  {problema}"))
            self.stdout.write(
                self.style.ERROR(
                    f"\n{len(problemas)} diferencia(s). El volcado no está listo: "
                    "no cortar ninguna línea hasta que esto salga limpio."
                )
            )
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS("Sin diferencias: el núcleo dice lo mismo que lo heredado.")
        )

    # ------------------------------------------------------------ por línea

    def _verificar(self, codigo):
        etiqueta, modelo, campo_estado, campo_peso, piezas_por_fila = FUENTES[codigo]
        linea = LineaNegocio.objects.using(BASE).filter(codigo=codigo).first()
        if linea is None:
            return [f"{codigo}: no está sembrada"]

        problemas = []
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{linea.nombre}"))

        heredadas = modelo.objects.using(BASE).count()
        migradas = OrdenProduccion.objects.using(BASE).filter(legacy_modelo=etiqueta).count()
        self.stdout.write(f"  órdenes      heredadas {heredadas:>6}   núcleo {migradas:>6}")
        if heredadas != migradas:
            problemas.append(
                f"{linea.nombre}: {heredadas} órdenes heredadas frente a {migradas} en el núcleo"
            )

        if campo_peso:
            kg_heredado = Decimal(
                str(modelo.objects.using(BASE).aggregate(t=Sum(campo_peso))["t"] or 0)
            ).quantize(CENTIMO)
            # En el núcleo el peso se guarda por pieza, así que hay que
            # multiplicarlo para poder compararlo con lo heredado, que lo
            # guarda por orden (salvo en vigas, donde cada fila es una pieza).
            kg_nucleo = Decimal("0.000")
            for orden in OrdenProduccion.objects.using(BASE).filter(legacy_modelo=etiqueta):
                unidades = piezas_por_fila or orden.total_piezas
                kg_nucleo += (orden.peso_kg_unitario or Decimal("0")) * unidades
            kg_nucleo = kg_nucleo.quantize(CENTIMO)
            self.stdout.write(
                f"  kilos        heredados {kg_heredado:>9}   núcleo {kg_nucleo:>9}"
            )
            # Un gramo de holgura por orden: el peso heredado es coma
            # flotante y el del núcleo decimal, así que la división por el
            # número de piezas y la vuelta a multiplicar no siempre cierra al
            # milésimo. Más de eso ya no es redondeo.
            if abs(kg_heredado - kg_nucleo) > Decimal(migradas or 1) * CENTIMO:
                problemas.append(
                    f"{linea.nombre}: {kg_heredado} kg heredados frente a {kg_nucleo} en el núcleo"
                )

        if campo_estado:
            problemas.extend(
                self._comparar_etapas(linea, etiqueta, modelo, campo_estado)
            )

        return problemas

    def _comparar_etapas(self, linea, etiqueta, modelo, campo_estado):
        heredado = {}
        for fila in (
            modelo.objects.using(BASE).values(campo_estado).annotate(n=Count("pk"))
        ):
            heredado[clave(fila[campo_estado])] = fila["n"]

        migrado = {}
        for fila in (
            OrdenProduccion.objects.using(BASE)
            .filter(legacy_modelo=etiqueta)
            .values("etapa_actual__nombre")
            .annotate(n=Count("pk"))
        ):
            migrado[clave(fila["etapa_actual__nombre"])] = fila["n"]

        problemas = []
        for etapa in sorted(set(heredado) | set(migrado)):
            a, b = heredado.get(etapa, 0), migrado.get(etapa, 0)
            marca = "  " if a == b else "!!"
            self.stdout.write(f"  {marca} {etapa:<28} heredado {a:>5}   núcleo {b:>5}")
            if a != b:
                problemas.append(
                    f"{linea.nombre}: la etapa {etapa!r} tiene {a} órdenes heredadas y {b} en el núcleo"
                )
        return problemas

    # -------------------------------------------------- historial vs caché

    def _historial_contra_contadores(self, lineas, problemas):
        """La suma del historial tiene que dar el contador de la orden.

        Si esto falla, el registro de eventos no sirve para nada: significaría
        que la caché y la verdad se han separado, que es justo lo que se está
        arreglando.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nHistorial contra contadores"))
        descuadres = 0
        revisadas = 0

        consulta = OrdenProduccion.objects.using(BASE).filter(linea__codigo__in=lineas)
        for orden in consulta.iterator(chunk_size=500):
            revisadas += 1
            suma = {"producida": 0, "pintada": 0, "terminada": 0}
            eventos = EventoProduccion.objects.using(BASE).filter(
                orden=orden,
                tipo__in=[EventoProduccion.Tipo.AVANCE, EventoProduccion.Tipo.AJUSTE],
            ).exclude(contador="")
            for evento in eventos:
                suma[evento.contador] += evento.delta_cantidad

            esperado = {
                "producida": orden.cantidad_producida,
                "pintada": orden.cantidad_pintada,
                "terminada": orden.cantidad_terminada,
            }
            for contador, valor in esperado.items():
                if suma[contador] != valor:
                    descuadres += 1
                    problemas.append(
                        f"{orden.folio}: el historial suma {suma[contador]} {contador}(s) "
                        f"y el contador dice {valor}"
                    )

        self.stdout.write(
            f"  {revisadas} orden(es) revisadas, {descuadres} descuadre(s)"
        )

    # ------------------------------------------------------- calidad del dato

    def _informar_calidad(self, lineas):
        """Lo que no es un fallo del volcado, pero hay que saber.

        Los dos números salen de los datos heredados, no del proceso de
        migración: uno dice cuánto historial no existía, el otro cuántas
        órdenes llevaban ya los contadores en un estado imposible. Se informan
        aparte para que nadie los confunda con un error de la migración ni los
        use para justificar que no la hubo.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nCalidad del dato heredado"))

        sin_historico = (
            EventoProduccion.objects.using(BASE)
            .filter(orden__linea__codigo__in=lineas, sin_historico=True)
            .exclude(tipo=EventoProduccion.Tipo.CREACION)
            .count()
        )
        self.stdout.write(
            f"  {sin_historico} movimiento(s) sin historial que reconstruir"
        )

        incoherentes = [
            orden.folio
            for orden in OrdenProduccion.objects.using(BASE).filter(linea__codigo__in=lineas)
            if not orden.contadores_coherentes
        ]
        if incoherentes:
            self.stdout.write(
                self.style.WARNING(
                    f"  {len(incoherentes)} orden(es) con contadores incoherentes "
                    "(terminadas > pintadas > producidas, o por encima del objetivo):"
                )
            )
            for folio in incoherentes[:20]:
                self.stdout.write(f"      {folio}")
            if len(incoherentes) > 20:
                self.stdout.write(f"      … y {len(incoherentes) - 20} más")
            self.stdout.write(
                "  Venían así. El servicio del núcleo ya no deja crear más, pero\n"
                "  éstas hay que corregirlas a mano con un evento de ajuste antes\n"
                "  de poder exigir la invariante en la base (`endurecer_invariantes`)."
            )
        else:
            self.stdout.write("  sin órdenes con contadores incoherentes")
