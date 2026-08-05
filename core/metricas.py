"""Cálculos del tablero que estaban mal.

Un indicador equivocado es peor que ninguno: no se nota que falla, se toman
decisiones con él y se pierde la confianza en todo el tablero cuando alguien
por fin lo descubre.

**Las toneladas semanales de Herrería salían siempre en cero.** Se calculaban
desde `HerrProduccion`, multiplicando la cantidad por el peso de la pieza del
renglón de la orden. En la base sólo hay una fila de esa tabla y tiene el
renglón vacío, así que el peso resuelve a cero y la suma también. Pero el
taller sí produce: el avance de herrería se lleva por contadores —soldadas,
pintadas, terminadas—, y cada cambio deja su rastro en `HerrAvanceCambio` con
el valor anterior y el nuevo. De ahí sale la producción de verdad.

El peso hay que repartirlo: `HerrOrdenProduccion.peso_kg` es el peso **total**
de la orden, no el de una pieza. La orden 20 son 70 piezas y 1.876 kg.
"""

from datetime import date

from core.estados import TERMINADO

BASE = "mes"


def _peso_unitario(orden):
    """Kilos por pieza de una orden de herrería.

    Devuelve 0 cuando la orden no tiene peso o no tiene piezas, en vez de
    dividir entre cero. Una orden sin peso capturado no aporta toneladas, que
    es justo lo que hay que enseñar para que se note que falta el dato.
    """
    piezas = int(getattr(orden, "total_piezas", 0) or 0)
    peso = float(getattr(orden, "peso_kg", 0.0) or 0.0)
    if piezas <= 0 or peso <= 0:
        return 0.0
    return peso / piezas


def produccion_de_herreria(desde: date, hasta: date):
    """Piezas terminadas y kilos por día, en el rango `[desde, hasta)`.

    Se cuentan las **terminadas**, que es lo que sale del taller. Contar
    también soldadas y pintadas mediría la misma pieza tres veces. Es la misma
    regla que sigue `toneladas_terminadas` para Estructuras: una pieza cuenta
    el día que se termina y no vuelve a contar nunca más.

    Se usa la diferencia entre el valor nuevo y el anterior, no el valor
    absoluto. Un cambio de 15 a 22 son siete piezas, no veintidós.
    """
    from catalogos.models import HerrAvanceCambio

    cambios = (
        HerrAvanceCambio.objects.using(BASE)
        .filter(fecha_operacion__gte=desde, fecha_operacion__lt=hasta)
        .select_related("orden")
        .order_by("fecha_operacion")
    )

    por_dia = {}
    for cambio in cambios:
        # Una corrección a la baja resta, que es lo correcto: si alguien
        # capturó de más y lo arregla, la producción del día baja.
        delta = int(cambio.terminadas_new or 0) - int(cambio.terminadas_prev or 0)
        if not delta:
            continue
        fila = por_dia.setdefault(cambio.fecha_operacion, {"piezas": 0, "kg": 0.0})
        fila["piezas"] += delta
        fila["kg"] += delta * _peso_unitario(cambio.orden)

    return por_dia


def toneladas_de_herreria(desde: date, hasta: date):
    return sum(f["kg"] for f in produccion_de_herreria(desde, hasta).values()) / 1000.0


def piezas_de_herreria(desde: date, hasta: date):
    return sum(f["piezas"] for f in produccion_de_herreria(desde, hasta).values())


# ------------------------------------------ producción terminada por persona
#
# El indicador estaba mal planteado, no mal calculado, que es peor: el número
# salía siempre y nadie tenía motivo para dudar de él.
#
# Se hacía `toneladas en estado Terminado / número de integrantes` y se
# comparaba contra una meta de **media tonelada por persona a la semana**.
#
# Lo de arriba es un inventario —lo que hay parado en el almacén de terminados
# ahora mismo— y lo de abajo es un flujo. Dividir uno entre otro no da nada.
# Peor: como el inventario sólo crece mientras no se envía, el indicador subía
# solo, y bajaba de golpe el día que salía un camión. Justo al revés de lo que
# significa producir.
#
# Aquí se mide lo que se terminó **en un rango de fechas**, que es lo mismo que
# mide la meta.


def toneladas_terminadas(desde: date, hasta: date):
    """Toneladas que pasaron a «Terminado» en `[desde, hasta)`.

    Se cuenta el paso, no el estado: una pieza cuenta el día que se terminó y
    no vuelve a contar nunca más. Y se cuenta una sola vez aunque tenga varios
    apuntes ese día, que los tiene cuando alguien corrige un movimiento.
    """
    from produccion.models import ProductionLog, Viga

    ids = set(
        ProductionLog.objects.using(BASE)
        .filter(
            estado_nuevo=TERMINADO,
            fecha_operacion__gte=desde,
            fecha_operacion__lt=hasta,
        )
        .values_list("viga_internal_id", flat=True)
    )
    if not ids:
        return 0.0

    from django.db.models import Sum

    kilos = (
        Viga.objects.using(BASE)
        .filter(internal_id__in=ids)
        .aggregate(total=Sum("peso_kg"))["total"]
        or 0
    )
    return float(kilos) / 1000.0


def toneladas_por_persona(desde: date, hasta: date, personas: int):
    """Lo que produjo cada persona en el rango, en toneladas.

    Cero personas devuelve cero en vez de reventar: pasa el primer día, antes
    de dar de alta a nadie.
    """
    if not personas:
        return 0.0
    return toneladas_terminadas(desde, hasta) / personas


# ------------------------------------------------------------- retrabajo
#
# El tablero medía el retrabajo de dos formas distintas **en la misma
# pantalla**: una buscaba la palabra «retrabajo» en cualquier parte del
# comentario y la otra la etiqueta `[MOTIVO=RETRABAJO]` que pone el
# formulario. La primera es más laxa y da falsos positivos evidentes: un
# comentario que diga «no hubo retrabajo» cuenta como retrabajo.
#
# Vale la estricta. El retrabajo es un dato que alguien declara, no algo que
# se adivine leyendo texto libre. Hoy las dos dan cero porque no se ha
# registrado ninguno, así que unificar no cambia ningún número: cambia que
# dejen de poder separarse.
#
# Cuando la línea corra sobre el motor unificado esto será una llave foránea
# a MotivoEvento y el problema desaparece de raíz.

ETIQUETA_RETRABAJO = "[MOTIVO=RETRABAJO]"


def filtro_de_retrabajo(campo="comentario"):
    """Condición que identifica un retrabajo declarado."""
    from django.db.models import Q

    return Q(**{f"{campo}__icontains": ETIQUETA_RETRABAJO})
