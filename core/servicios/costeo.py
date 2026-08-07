"""Convierte el historial de producción en horas, y las horas en dinero.

Toda la gracia del módulo está en una idea: **las horas no se fichan, se
deducen**. El registro de eventos ya dice cuándo entró una orden a soldadura y
cuándo salió. Restando el tiempo fuera de jornada y los paros de máquina de
por medio, sale el tiempo real de esa etapa. Nadie tiene que apuntar nada más.

Eso es exactamente por lo que el registro de eventos y el calendario laboral
tenían que existir antes que este módulo. Con contadores en vez de historial,
la única alternativa sería un reloj checador, y eso no lo sostiene un taller.

Tres reglas que gobiernan el cálculo:

**La tarifa que manda es la que estaba vigente el día del trabajo.** No la de
hoy. Si mañana suben los sueldos, lo que costó una orden del año pasado tiene
que seguir siendo lo mismo, o el histórico deja de servir para comparar.

**Lo que no se puede medir no se inventa.** Una etapa sin nadie asignado
aporta cero horas de mano de obra, no «una persona por defecto». En su lugar
baja la *cobertura*, que es el número que dice qué parte de la orden se midió
de verdad. Un costo que parece completo cuando midió la mitad es peor que no
tener costo, porque se usa para cotizar.

**Los paros se descuentan.** Una orden parada tres horas porque la máquina se
cayó no costó tres horas de máquina. Si no se descuentan, el costo castiga a
la orden que tuvo mala suerte y el informe de varianza deja de significar
nada.

Y una advertencia que apareció al probar esto contra los datos del taller, no
al escribirlo:

**El tiempo que una orden pasa en una etapa no es el tiempo que se trabajó en
ella.** El historial dice cuándo entró y cuándo salió; entre medias puede
haber estado tres meses esperando material sin que nadie la tocara. La primera
versión de este módulo cobraba todo ese tiempo: una orden real de herrería dio
671 horas de pintura y 191.274 pesos.

Mientras no haya tiempos estándar capturados ni una señal de inicio y fin, esa
diferencia no se puede medir. Lo que se hace es acotarla: cada centro de costo
tiene un tope de horas por paso, las etapas que lo superan se cobran al tope,
se marcan como topadas y **no cuentan como cobertura**, porque están estimadas
y no medidas. El tiempo transcurrido se guarda igual, aparte, porque es la
medida real del flujo y dice cuánto de todo eso fue espera.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core import jornada
from costeo.models import (
    CentroCosto,
    CostoEtapa,
    CostoOrden,
    Tarifa,
    TarifaManoObra,
    TiempoEstandar,
)
from nucleo.models import Asignacion, EventoProduccion
from core.bases import BASE  # noqa: F401

logger = logging.getLogger("mes.costeo")

CERO = Decimal("0")
CUATRO = Decimal("0.0001")

#: Tipos de evento que mueven la orden de etapa. Son los que marcan los
#: cortes del tiempo: entre uno y el siguiente, la orden estuvo en una etapa.
EVENTOS_DE_TRANSITO = [
    EventoProduccion.Tipo.CREACION,
    EventoProduccion.Tipo.CAMBIO_ETAPA,
    EventoProduccion.Tipo.CIERRE_PENDIENTE,
    EventoProduccion.Tipo.CIERRE_FIRME,
    EventoProduccion.Tipo.REVERSION_CIERRE,
]


def a_decimal(valor):
    return Decimal(str(valor)).quantize(CUATRO)


# ============================================================== tarifas

def centro_de(linea):
    """El centro de costo de una línea, o el general si no tiene uno propio."""
    propio = CentroCosto.objects.using(BASE).filter(linea=linea, activo=True).first()
    if propio is not None:
        return propio
    return CentroCosto.objects.using(BASE).filter(linea__isnull=True, activo=True).first()


def tarifa_vigente(centro, fecha):
    """La tarifa que regía ese día. `None` si no había ninguna todavía."""
    if centro is None:
        return None
    return (
        Tarifa.objects.using(BASE)
        .filter(centro=centro, vigente_desde__lte=fecha)
        .order_by("-vigente_desde")
        .first()
    )


def tarifa_de_persona(colaborador, rol, fecha, tarifa_centro):
    """Cuánto cuesta una hora de esta persona ese día.

    Se busca de lo específico a lo general: primero la tarifa de la persona,
    luego la de su rol, y al final la del centro. Devuelve también de dónde
    salió, porque un costo que no se puede explicar no se puede corregir.
    """
    if colaborador is not None:
        propia = (
            TarifaManoObra.objects.using(BASE)
            .filter(colaborador=colaborador, vigente_desde__lte=fecha)
            .order_by("-vigente_desde")
            .first()
        )
        if propia is not None:
            return propia.costo_hora, "persona"

    if rol:
        del_rol = (
            TarifaManoObra.objects.using(BASE)
            .filter(colaborador__isnull=True, rol=rol, vigente_desde__lte=fecha)
            .order_by("-vigente_desde")
            .first()
        )
        if del_rol is not None:
            return del_rol.costo_hora, "rol"

    if tarifa_centro is not None:
        return tarifa_centro.costo_hora_mano_obra, "centro"
    return CERO, "sin tarifa"


# ================================================== el tiempo de cada etapa

def tramos_por_etapa(orden, hasta=None):
    """En qué etapa estuvo la orden y entre qué instantes.

    Sale de recorrer el historial: cada evento que la mueve de etapa cierra el
    tramo anterior y abre el siguiente. Devuelve una lista de
    (etapa, desde, hasta).

    El último tramo se cierra con el cierre de la orden si lo hay, y si no con
    el momento actual: una orden abierta lleva tiempo acumulándose, y ese
    tiempo es real.
    """
    eventos = list(
        EventoProduccion.objects.using(BASE)
        .filter(orden=orden, tipo__in=EVENTOS_DE_TRANSITO)
        .select_related("etapa")
        .order_by("ocurrido_en", "id")
    )
    if not eventos:
        return []

    hasta = hasta or orden.cierre_bloqueado_en or timezone.now()
    tramos = []
    for indice, evento in enumerate(eventos):
        if evento.etapa_id is None:
            continue
        fin = eventos[indice + 1].ocurrido_en if indice + 1 < len(eventos) else hasta
        if fin > evento.ocurrido_en:
            tramos.append((evento.etapa, evento.ocurrido_en, fin))
    return tramos


def horas_de_paro(orden, desde, hasta):
    """Horas de jornada en que una máquina de la orden estuvo parada.

    Se miran las dos fuentes —el núcleo y las tablas heredadas— porque
    mientras una línea no esté cortada los paros se siguen registrando en
    `MaquinaParo` y `MaquinaFalla`, y un costeo que mira la mitad de los paros
    es un costeo equivocado.
    """
    from catalogos.models import MaquinaFalla, MaquinaParo
    from nucleo.models import EventoMaquina

    maquinas = list(
        Asignacion.objects.using(BASE)
        .filter(orden=orden, maquina__isnull=False)
        .values_list("maquina_id", flat=True)
    )
    if not maquinas:
        return CERO

    segundos = 0
    consultas = [
        EventoMaquina.objects.using(BASE).filter(maquina_id__in=maquinas),
        MaquinaParo.objects.using(BASE).filter(maquina_id__in=maquinas),
        MaquinaFalla.objects.using(BASE).filter(maquina_id__in=maquinas),
    ]
    for consulta in consultas:
        for paro in consulta.filter(
            Q(fin__isnull=True) | Q(fin__gte=desde), inicio__lte=hasta
        ):
            segundos += jornada.solape_laboral(
                max(paro.inicio, desde), min(paro.fin or hasta, hasta)
            )
    return a_decimal(segundos / 3600)


def personas_de(orden, etapa):
    """Quién estaba asignado a esa etapa. Sin nadie, no se inventa nadie."""
    return list(
        Asignacion.objects.using(BASE)
        .filter(orden=orden, etapa=etapa, colaborador__isnull=False)
        .select_related("colaborador")
    )


def horas_estandar_de(orden, etapa, fecha):
    estandar = (
        TiempoEstandar.objects.using(BASE)
        .filter(pieza=orden.pieza, etapa=etapa, vigente_desde__lte=fecha)
        .order_by("-vigente_desde")
        .first()
        if orden.pieza_id
        else None
    )
    if estandar is None:
        return CERO, None
    return (
        a_decimal(estandar.horas_por_pieza * orden.cantidad_objetivo * estandar.operadores),
        estandar,
    )


# ================================================================ cálculo

@transaction.atomic(using=BASE)
def calcular(orden, metodo=CostoOrden.Metodo.ABSORCION):
    """Calcula el costo de una orden y guarda el desglose.

    Se puede volver a llamar tantas veces como se quiera: no es un asiento,
    es una foto derivada. Si mañana aparece un consumo que faltaba o se
    corrige una tarifa, se recalcula y sale el número bueno.
    """
    from core.servicios import inventario

    centro = centro_de(orden.linea)
    tramos = tramos_por_etapa(orden)

    costo, _ = CostoOrden.objects.using(BASE).get_or_create(orden=orden)
    costo.etapas.all().delete()

    total_mano_obra = total_maquina = total_overhead = CERO
    total_horas_maquina = total_horas_persona = total_horas_estandar = CERO
    total_transcurridas = total_estandar_dinero = CERO
    etapas_medidas = etapas_totales = etapas_topadas = 0
    avisos_generales = []

    # Ver `CentroCosto.horas_max_por_visita`: el historial dice cuánto tiempo
    # pasó la orden en una etapa, no cuánto se trabajó en ella.
    tope = centro.horas_max_por_visita if centro else None

    # Varios tramos pueden ser de la misma etapa (una orden que va y vuelve),
    # así que se acumulan antes de guardar: una fila por etapa, no por visita.
    acumulado = {}

    for etapa, desde, hasta in tramos:
        etapas_totales += 1
        fecha = timezone.localtime(desde).date()
        tarifa = tarifa_vigente(centro, fecha)
        avisos = []

        brutas = a_decimal(jornada.horas_laborales(desde, hasta))
        paradas = horas_de_paro(orden, desde, hasta)
        transcurridas = max(brutas - paradas, CERO)

        horas = transcurridas
        topada = False
        if tope is not None and transcurridas > tope:
            horas = a_decimal(tope)
            topada = True
            etapas_topadas += 1
            avisos.append(
                f"{transcurridas} h en la etapa: se cobran {horas} h por el tope del "
                "centro. El historial no distingue el trabajo de la espera, así que "
                "esto es una cota, no una medición."
            )

        personas = personas_de(orden, etapa)
        if not personas:
            # Deliberado: no se supone un operador. Baja la cobertura y se
            # dice por qué.
            avisos.append("sin colaborador asignado: no se puede costear la mano de obra")
        if tarifa is None:
            avisos.append(f"sin tarifa vigente al {fecha}")
        else:
            # Una etapa cuenta como medida sólo si tuvo gente asignada, tarifa
            # vigente y no hizo falta acotarla. Las tres condiciones a la vez:
            # con cualquiera de ellas fallando, el número es una estimación.
            etapas_medidas += int(bool(personas) and not topada)

        mano_obra = CERO
        for asignacion in personas:
            por_hora, origen = tarifa_de_persona(
                asignacion.colaborador, asignacion.rol, fecha, tarifa
            )
            if por_hora <= CERO:
                avisos.append(f"{asignacion.colaborador} sin tarifa ({origen})")
            mano_obra += horas * por_hora

        usa_maquina = etapa.requiere_maquina or bool(
            Asignacion.objects.using(BASE)
            .filter(orden=orden, etapa=etapa, maquina__isnull=False)
            .exists()
        )
        horas_maquina = horas if usa_maquina else CERO
        maquina = horas_maquina * (tarifa.costo_hora_maquina if tarifa else CERO)
        overhead = (
            horas_maquina * tarifa.overhead_hora
            if tarifa and metodo == CostoOrden.Metodo.ABSORCION
            else CERO
        )

        estandar, _ = horas_estandar_de(orden, etapa, fecha)

        fila = acumulado.setdefault(
            etapa.pk,
            {
                "etapa": etapa, "horas": CERO, "transcurridas": CERO, "paro": CERO,
                "personas": 0, "topada": False,
                "mano_obra": CERO, "maquina": CERO, "overhead": CERO,
                "estandar": CERO, "avisos": [],
            },
        )
        fila["horas"] += horas
        fila["transcurridas"] += transcurridas
        fila["topada"] = fila["topada"] or topada
        fila["paro"] += paradas
        fila["personas"] = max(fila["personas"], len(personas))
        fila["mano_obra"] += mano_obra
        fila["maquina"] += maquina
        fila["overhead"] += overhead
        # El estándar es por orden y etapa, no por visita: sumarlo en cada
        # vuelta multiplicaría el objetivo por el número de retrocesos.
        fila["estandar"] = estandar
        fila["avisos"].extend(a for a in avisos if a not in fila["avisos"])

        total_mano_obra += mano_obra
        total_maquina += maquina
        total_overhead += overhead
        total_horas_maquina += horas_maquina
        total_horas_persona += horas * len(personas)
        total_transcurridas += transcurridas

    for fila in acumulado.values():
        CostoEtapa.objects.using(BASE).create(
            costo=costo,
            etapa=fila["etapa"],
            horas=fila["horas"],
            horas_transcurridas=fila["transcurridas"],
            topada=fila["topada"],
            horas_descontadas_por_paro=fila["paro"],
            personas=fila["personas"],
            mano_obra=fila["mano_obra"].quantize(CUATRO),
            maquina=fila["maquina"].quantize(CUATRO),
            overhead=fila["overhead"].quantize(CUATRO),
            horas_estandar=fila["estandar"],
            avisos=fila["avisos"],
        )
        total_horas_estandar += fila["estandar"]

    material = inventario.costo_material_de(orden)
    if material <= CERO:
        avisos_generales.append(
            "sin consumo de material registrado: el costo no incluye materia prima"
        )

    if total_horas_estandar > CERO:
        tarifa_hoy = tarifa_vigente(centro, timezone.localdate())
        if tarifa_hoy is not None:
            total_estandar_dinero = material + total_horas_estandar * (
                tarifa_hoy.costo_hora_mano_obra
                + tarifa_hoy.costo_hora_maquina
                + (
                    tarifa_hoy.overhead_hora
                    if metodo == CostoOrden.Metodo.ABSORCION
                    else CERO
                )
            )
    else:
        avisos_generales.append("sin tiempo estándar: no se puede calcular la varianza")

    if etapas_topadas:
        avisos_generales.append(
            f"{etapas_topadas} etapa(s) superaron el tope de horas del centro: la "
            "orden estuvo parada más de lo que se trabajó en ella. El costo de esas "
            "etapas es una cota superior. Se corrige capturando tiempos estándar o "
            "acotando el tope en el centro de costo."
        )

    # Aparentar que se midió lo que se acotó es exactamente lo que produce un
    # costo que nadie puede defender, así que las etapas topadas ya quedaron
    # fuera de `etapas_medidas` arriba.
    cobertura = (
        Decimal(etapas_medidas) / Decimal(etapas_totales) if etapas_totales else CERO
    )

    costo.metodo = metodo
    costo.material = material
    costo.mano_obra = total_mano_obra.quantize(CUATRO)
    costo.maquina = total_maquina.quantize(CUATRO)
    costo.overhead = total_overhead.quantize(CUATRO)
    costo.total = (material + total_mano_obra + total_maquina + total_overhead).quantize(
        CUATRO
    )
    costo.horas_maquina = total_horas_maquina
    costo.horas_persona = total_horas_persona
    costo.horas_transcurridas = total_transcurridas
    costo.horas_estandar = total_horas_estandar
    costo.costo_estandar = total_estandar_dinero.quantize(CUATRO)
    costo.cobertura = cobertura.quantize(Decimal("0.0001"))
    costo.detalle = {
        "centro": centro.codigo if centro else None,
        "tramos": len(tramos),
        "etapas_medidas": etapas_medidas,
        "etapas_topadas": etapas_topadas,
        "etapas_recorridas": etapas_totales,
        "avisos": avisos_generales,
    }
    costo.save(using=BASE)

    logger.info(
        "costo de %s: %s (cobertura %s%%)",
        orden.folio, costo.total, int(cobertura * 100),
    )
    return costo


def calcular_muchas(ordenes, metodo=CostoOrden.Metodo.ABSORCION):
    return [calcular(orden, metodo) for orden in ordenes]


# =============================================================== informes

def varianza(orden):
    """Lo real frente a lo estándar, etapa por etapa.

    Es el informe más valioso del sistema: no dice cuánto cuesta algo, dice
    **dónde se está perdiendo dinero**. Un costo absoluto sin nada con qué
    compararlo no acciona ninguna decisión.
    """
    costo = CostoOrden.objects.using(BASE).filter(orden=orden).first()
    if costo is None:
        return None

    filas = []
    for etapa in costo.etapas.select_related("etapa"):
        if not etapa.horas_estandar:
            continue
        filas.append(
            {
                "etapa": etapa.etapa,
                "horas_reales": etapa.horas,
                "horas_estandar": etapa.horas_estandar,
                "diferencia": etapa.varianza_horas,
                "porcentaje": (
                    ((etapa.horas - etapa.horas_estandar) / etapa.horas_estandar * 100)
                    .quantize(Decimal("0.01"))
                ),
                "paro": etapa.horas_descontadas_por_paro,
            }
        )
    return {"costo": costo, "etapas": filas}


def resumen_por_linea(desde=None, hasta=None):
    """Costo, varianza y cobertura agregados. Para el tablero."""
    consulta = CostoOrden.objects.using(BASE).select_related("orden", "orden__linea")
    if desde:
        consulta = consulta.filter(orden__creado_en__date__gte=desde)
    if hasta:
        consulta = consulta.filter(orden__creado_en__date__lte=hasta)

    por_linea = {}
    for costo in consulta:
        clave = costo.orden.linea
        fila = por_linea.setdefault(
            clave,
            {
                "linea": clave, "ordenes": 0, "total": CERO, "material": CERO,
                "mano_obra": CERO, "maquina": CERO, "overhead": CERO,
                "estandar": CERO, "cobertura": CERO,
            },
        )
        fila["ordenes"] += 1
        fila["total"] += costo.total
        fila["material"] += costo.material
        fila["mano_obra"] += costo.mano_obra
        fila["maquina"] += costo.maquina
        fila["overhead"] += costo.overhead
        fila["estandar"] += costo.costo_estandar
        fila["cobertura"] += costo.cobertura

    for fila in por_linea.values():
        fila["cobertura"] = (fila["cobertura"] / fila["ordenes"]).quantize(
            Decimal("0.0001")
        )
        fila["varianza"] = (
            (fila["total"] - fila["estandar"]).quantize(CUATRO)
            if fila["estandar"]
            else None
        )
    return sorted(por_linea.values(), key=lambda f: f["linea"].orden_visual)


def sin_tarifa():
    """Centros de costo sin ninguna tarifa capturada.

    Mientras esto no esté vacío, todos los costos salen incompletos y no hay
    que creérselos.
    """
    return [
        centro
        for centro in CentroCosto.objects.using(BASE).filter(activo=True)
        if not Tarifa.objects.using(BASE).filter(centro=centro).exists()
    ]
