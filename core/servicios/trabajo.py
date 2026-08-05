"""Quién y con qué se hizo cada avance.

La bitácora heredada guarda el cambio de estado y nada más. Este servicio
escribe, junto a ella, el equipo concreto y la cuadrilla del turno, que es lo
que hace falta para medir por máquina y para saber quién estuvo el día que
algo salió mal.

Dos decisiones que conviene tener presentes:

**La cuadrilla se deduce del momento, no se pide.** Nadie va a escribir en qué
cuadrilla está cada vez que avanza una pieza; si hubiera que capturarlo, el
campo quedaría vacío y el dato no serviría. Se busca la cuadrilla armada para
ese día, ese turno y ese centro, que es exactamente lo que la pantalla de
«Armar cuadrilla» existe para dejar dicho una vez por la mañana.

**Anotar nunca impide avanzar.** Si no hay cuadrilla armada, el apunte se
escribe igual, sin ella. Un taller que no puede mover una pieza porque falta
un dato de medición deja de usar el sistema, y entonces no se mide nada.
"""

import logging

from django.utils import timezone

from catalogos.models import ApunteDeTrabajo, Cuadrilla, Maquina, SeguimientoDespacho

logger = logging.getLogger(__name__)

BASE = "mes"

#: Qué centro de trabajo corresponde a cada etapa. Es lo que permite encontrar
#: la cuadrilla sin preguntárselo a nadie.
CENTRO_DE_ETAPA = {
    "Espera de corte": "Corte",
    "Corte": "Corte",
    "Espera de armado": "Soldadura",
    "Armado": "Soldadura",
    "Espera de soldadura": "Soldadura",
    "Soldadura": "Soldadura",
    "Espera de pintura": "Pintura",
    "Pintura": "Pintura",
}

#: Las etapas que no se pueden empezar sin decir en qué equipo. Corte tiene
#: seis y la producción de cada uno es una pregunta que el taller hace; sin
#: obligar aquí, el dato llega vacío el 90% de las veces y el indicador por
#: máquina no existe.
ETAPAS_QUE_EXIGEN_MAQUINA = {"Corte"}


def centro_de(etapa):
    return CENTRO_DE_ETAPA.get((etapa or "").strip(), "")


def exige_maquina(etapa):
    return (etapa or "").strip() in ETAPAS_QUE_EXIGEN_MAQUINA


def turnos_que_cubren(momento):
    """Los turnos válidos a esa hora.

    La jornada completa siempre cuenta. El matutino cubre hasta las 13:30 y el
    vespertino a partir de ahí, que es como parte el día el taller.
    """
    hora = timezone.localtime(momento).time()
    if hora < timezone.datetime(2000, 1, 1, 13, 30).time():
        return [Cuadrilla.Turno.COMPLETO, Cuadrilla.Turno.MATUTINO]
    return [Cuadrilla.Turno.COMPLETO, Cuadrilla.Turno.VESPERTINO]


def cuadrilla_vigente(*, centro, momento=None, maquina=None):
    """La cuadrilla armada para ese día, turno y centro.

    Si hay una pegada al equipo concreto gana sobre la del área: una cuadrilla
    de «la cortadora 3» dice más que una de «corte».
    """
    if not centro:
        return None

    momento = momento or timezone.now()
    dia = timezone.localdate(momento)
    turnos = turnos_que_cubren(momento)

    base = Cuadrilla.objects.using(BASE).filter(
        fecha=dia, centro=centro, turno__in=turnos
    )
    if maquina is not None:
        pegada = base.filter(maquina=maquina).first()
        if pegada is not None:
            return pegada
    return base.filter(maquina__isnull=True).first() or base.first()


def integrantes_de(cuadrilla):
    if cuadrilla is None:
        return ""
    ids = cuadrilla.integrantes.values_list("colaborador_id", flat=True)
    return ",".join(str(int(i)) for i in sorted(ids))


def maquinas_disponibles(etapa):
    """Los equipos del área en los que se puede trabajar ahora mismo.

    Las elige el propio operador, no un supervisor desde la oficina. En el
    piso la asignación de escritorio se quedaba vieja en cuanto la máquina
    estaba ocupada por otro, o el ayudante iba a la de al lado, y entonces el
    apunte decía que la pieza se cortó en un equipo en el que no se cortó.

    Fuera quedan las que están en paro o con falla abierta. No se enseñan
    apagadas: se quitan. Una lista donde la mitad de las opciones no se pueden
    elegir es una lista que hay que leer entera para descartar, y esto se usa
    con guantes.
    """
    from catalogos.models import MaquinaFalla, MaquinaParo

    centro = centro_de(etapa)
    if not centro:
        return []

    detenidas = set(
        MaquinaParo.objects.using(BASE)
        .filter(fin__isnull=True)
        .values_list("maquina_id", flat=True)
    ) | set(
        MaquinaFalla.objects.using(BASE)
        .filter(fin__isnull=True)
        .values_list("maquina_id", flat=True)
    )
    return list(
        Maquina.objects.using(BASE)
        .filter(activo=True, tipo=centro, es_robot=False)
        .exclude(id__in=detenidas)
        .order_by("nombre")
    )


def maquina_valida(identificador, *, etapa):
    """La máquina que se pidió, si existe, está activa y es del área.

    Devuelve `(maquina, error)`. Que sea del área importa: sin comprobarlo se
    podría anotar que una viga se cortó en la cabina de pintura.
    """
    texto = str(identificador or "").strip()
    if not texto:
        return None, ""
    if not texto.isdigit():
        return None, "Equipo inválido."

    centro = centro_de(etapa)
    maquina = (
        Maquina.objects.using(BASE)
        .filter(id=int(texto), activo=True)
        .first()
    )
    if maquina is None:
        return None, "Ese equipo no existe o está dado de baja."
    if centro and maquina.tipo != centro:
        return None, f"Ese equipo no es de {centro}."
    return maquina, ""


def anotar(
    *,
    linea,
    referencia,
    etapa,
    codigo="",
    etapa_anterior="",
    maquina=None,
    actor="",
    ocurrido_en=None,
):
    """Deja constancia de con qué y con quién se hizo un avance.

    Se llama dentro de la misma transacción que el cambio de estado: o quedan
    los dos apuntes o no queda ninguno. Un apunte sin su cambio de estado sería
    peor que no tenerlo, porque mediría trabajo que no pasó.
    """
    if linea not in SeguimientoDespacho.Linea.values:
        raise ValueError(f"Línea desconocida: {linea!r}")

    ocurrido_en = ocurrido_en or timezone.now()
    cuadrilla = cuadrilla_vigente(
        centro=centro_de(etapa), momento=ocurrido_en, maquina=maquina
    )
    if cuadrilla is None:
        logger.info(
            "apunte sin cuadrilla: %s %s etapa %s", linea, referencia, etapa
        )

    return ApunteDeTrabajo.objects.using(BASE).create(
        linea=linea,
        referencia=int(referencia),
        codigo=(codigo or "")[:120],
        etapa=(etapa or "")[:40],
        etapa_anterior=(etapa_anterior or "")[:40],
        maquina=maquina,
        cuadrilla=cuadrilla,
        integrantes=integrantes_de(cuadrilla)[:255],
        actor=(actor or "")[:150],
        ocurrido_en=ocurrido_en,
    )
