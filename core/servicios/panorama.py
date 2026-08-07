"""Todo lo que el taller está haciendo ahora mismo, en una sola lista.

El taller lo pidió así: «mando a hacer treinta andamios y quiero verlo junto
con lo demás, en general». Hasta ahora no había ninguna pantalla que
contestara «¿qué se está produciendo?». Había cuatro, una por línea, y para
responder había que abrir las cuatro y sumar de cabeza.

Cuatro porque el sistema tiene el mismo motor copiado cuatro veces, cada uno
con su tabla. Aquí se leen las cuatro y se enseñan como una. **No se crea una
tabla nueva ni se copia nada**: es el mismo trato que ya tienen «Listo para
salir» y «Producto terminado». Una lista que se deduce no se puede
desincronizar; una que se copia, sí, y el día que pase nadie sabrá cuál de
las dos es la buena.

Las dos formas de trabajar que conviven
---------------------------------------

**A medida.** Una pieza única de una obra. Avanza etapa por etapa: espera de
corte, corte, armado, soldadura, pintura. El avance *es* la etapa.

**En serie.** Una orden de treinta andamios. Avanza por cantidades: veinte
soldados, doce pintados, cinco terminados. La etapa dice poco; lo que importa
es cuánto lleva.

Enseñarlas en la misma tabla obliga a decidir qué es «avance» para las dos.
La respuesta que se da aquí: **la fracción terminada**. Para una orden en
serie son las piezas terminadas entre el objetivo. Para una pieza única es lo
que lleva recorrido de su secuencia de etapas. No son la misma medida y no se
suman entre sí, pero las dos contestan «¿cuánto le falta?», que es lo que se
mira en una lista de control.

Robótica va aparte en un detalle: no tiene máquina de estados ni fecha de
compromiso. Se enseña con lo que sí tiene y el resto va vacío, en vez de
inventarle una etapa para que la columna no quede en blanco.
"""

from decimal import Decimal

from django.db.models import F, FloatField, Sum
from django.db.models.functions import Coalesce

from core import estados
from core.servicios import ruta as servicio_ruta
from core.bases import BASE  # noqa: F401


#: Las etapas en las que una pieza está viva. Terminado y Enviado ya no son
#: producción: son almacén y logística, y tienen sus propias pantallas.
EN_PRODUCCION = {
    estados.ESPERA_CORTE,
    estados.CORTE,
    estados.ESPERA_ARMADO,
    estados.ARMADO,
    estados.ESPERA_SOLDADURA,
    estados.SOLDADURA,
    estados.ESPERA_PINTURA,
    estados.PINTURA,
}

#: Cómo se llama cada línea en la pantalla, y a qué pantalla se va desde un
#: renglón para trabajar en él. El panorama es de lectura: enseña qué hay y
#: manda al sitio donde se hace.
LINEAS = {
    "estructuras": ("Estructuras", "produccion:viga_list"),
    "herreria": ("Herrería", "catalogos:herreria_control"),
    "corta": ("Corta.mx", "catalogos:corte_laser_control"),
    "robotica": ("Robótica", "catalogos:robotica"),
}


def _avance_de_etapa(etapa, legacy_modelo="", legacy_id=None):
    """Cuánto lleva recorrido una pieza única, de 0 a 100.

    Se mide sobre **su ruta**, no sobre la secuencia general: una pieza que no
    lleva pintura está al cien por cien cuando sale de soldadura. Medirla
    contra la secuencia completa la dejaría en 75 % para siempre, y una lista
    de control llena de órdenes que nunca llegan al final deja de leerse.

    Sin ruta configurada, la ruta *es* la secuencia completa, así que esto no
    cambia ningún número de los que ya había.
    """
    if legacy_modelo and legacy_id:
        return servicio_ruta.avance(legacy_modelo, legacy_id, etapa)
    secuencia = servicio_ruta.secuencia_completa()
    posicion = estados.posicion(etapa, secuencia)
    if posicion is None or len(secuencia) < 2:
        return 0
    return round(posicion / (len(secuencia) - 1) * 100)


def _renglon(**campos):
    """Un renglón con todas las columnas, para que ninguna falte por línea."""
    base = {
        "linea": "",
        "linea_nombre": "",
        "url_linea": "",
        "id": None,
        "ruta_recortada": False,
        "codigo": "",
        "descripcion": "",
        "cliente": "",
        "etapa": "",
        "clase_etapa": "",
        "en_serie": False,
        "piezas": 0,
        "hechas": 0,
        "avance": 0,
        "peso_kg": Decimal("0"),
        "fecha_compromiso": None,
        "prioridad": 3,
        "ultimo_cambio": None,
    }
    base.update(campos)
    base["linea_nombre"], base["url_linea"] = LINEAS.get(base["linea"], ("", ""))
    return base


def _de_estructuras(busqueda=""):
    from produccion.models import Viga

    escrituras = []
    for etapa in EN_PRODUCCION:
        escrituras.extend(estados.variantes(etapa))

    piezas = Viga.objects.using(BASE).filter(estado__in=escrituras)
    if busqueda:
        piezas = piezas.filter(codigo_viga__icontains=busqueda)

    renglones = []
    for pieza in piezas:
        etapa = estados.normalizar(pieza.estado)
        renglones.append(
            _renglon(
                linea="estructuras",
                codigo=pieza.codigo_viga,
                descripcion=pieza.descripcion or "",
                cliente=pieza.proyecto or "",
                etapa=etapa,
                clase_etapa=estados.clase(etapa),
                en_serie=False,
                piezas=pieza.total_piezas or 1,
                id=pieza.internal_id,
                ruta_recortada=servicio_ruta.de("Viga", pieza.internal_id)
                != servicio_ruta.secuencia_completa(),
                avance=_avance_de_etapa(etapa, "Viga", pieza.internal_id),
                peso_kg=pieza.peso_kg or 0,
                fecha_compromiso=pieza.fecha_compromiso,
                prioridad=pieza.prioridad or 3,
                ultimo_cambio=pieza.ultimo_cambio,
            )
        )
    return renglones


def _de_una_linea_en_serie(modelo, clave, cliente_de, busqueda="", legacy_modelo=""):
    """Herrería y Corta.mx, que son la misma tabla con distinto nombre."""
    ordenes = modelo.objects.using(BASE).filter(estado="Abierta")
    if busqueda:
        ordenes = ordenes.filter(codigo__icontains=busqueda)

    renglones = []
    for orden in ordenes.select_related("proyecto"):
        etapa = estados.normalizar(orden.estado_etapa)
        if etapa not in EN_PRODUCCION:
            continue
        objetivo = int(orden.cantidad_objetivo or orden.total_piezas or 0)
        hechas = int(orden.cantidad_terminada or 0)
        renglones.append(
            _renglon(
                linea=clave,
                id=orden.pk,
                ruta_recortada=(
                    int(orden.total_piezas or 0) < 2
                    and servicio_ruta.de(legacy_modelo, orden.pk)
                    != servicio_ruta.secuencia_completa()
                ),
                codigo=orden.codigo,
                descripcion=orden.descripcion or orden.nombre or "",
                cliente=cliente_de(orden),
                etapa=etapa,
                clase_etapa=estados.clase(etapa),
                # La misma regla que aplica el servidor para aceptar un
                # avance: dos piezas o más se llevan por cantidades.
                en_serie=int(orden.total_piezas or 0) >= 2,
                piezas=objetivo,
                hechas=hechas,
                avance=round(hechas / objetivo * 100) if objetivo else 0,
                peso_kg=orden.peso_kg or 0,
                fecha_compromiso=orden.fecha_compromiso,
                prioridad=orden.prioridad or 3,
                ultimo_cambio=orden.ultimo_cambio,
            )
        )
    return renglones


def _de_robotica(busqueda=""):
    """La celda robótica, que no lleva etapas ni fecha de compromiso.

    Se enseña con lo que tiene. Inventarle una etapa para rellenar la columna
    sería más cómodo de programar y mentira en la pantalla.
    """
    from catalogos.models import RobotOrdenItem, RobotOrdenProduccion

    ordenes = RobotOrdenProduccion.objects.using(BASE).filter(estado="Abierta")
    if busqueda:
        ordenes = ordenes.filter(nombre__icontains=busqueda)
    ordenes = list(ordenes.select_related("proyecto"))
    if not ordenes:
        return []

    kilos = {
        fila["orden_id"]: float(fila["kg"] or 0.0)
        for fila in (
            RobotOrdenItem.objects.using(BASE)
            .filter(orden__in=ordenes)
            .values("orden_id")
            .annotate(
                kg=Sum(
                    F("cantidad_requerida")
                    * Coalesce(F("pieza__peso_kg"), F("pieza_custom_peso_kg"), 0.0),
                    output_field=FloatField(),
                )
            )
        )
    }

    return [
        _renglon(
            linea="robotica",
            codigo=orden.nombre or orden.producto or f"#{orden.pk}",
            descripcion=orden.producto or "",
            cliente=orden.proyecto.nombre if orden.proyecto_id else "",
            en_serie=True,
            piezas=int(orden.cantidad_objetivo or 0),
            peso_kg=Decimal(str(round(kilos.get(orden.pk, 0.0), 3))),
            ultimo_cambio=orden.actualizado_en,
        )
        for orden in ordenes
    ]


def lo_que_se_esta_haciendo(busqueda="", linea=""):
    """Todo lo que está en producción, ordenado por urgencia.

    `linea` vacío son las cuatro. Lo que no tiene fecha de compromiso —las
    órdenes de robótica— va al final: no es que no corra prisa, es que nadie
    ha dicho para cuándo, y colarlo entre lo urgente sería inventarse un dato.
    """
    from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion

    fuentes = {
        "estructuras": lambda: _de_estructuras(busqueda),
        "herreria": lambda: _de_una_linea_en_serie(
            HerrOrdenProduccion,
            "herreria",
            lambda o: (
                o.cliente_herreria.nombre if o.cliente_herreria_id else ""
            )
            or (o.proyecto.nombre if o.proyecto_id else ""),
            busqueda,
            "HerrOrdenProduccion",
        ),
        "corta": lambda: _de_una_linea_en_serie(
            LaserOrdenProduccion,
            "corta",
            lambda o: (
                o.corta_cliente_proyecto.nombre if o.corta_cliente_proyecto_id else ""
            )
            or (o.proyecto.nombre if o.proyecto_id else ""),
            busqueda,
            "LaserOrdenProduccion",
        ),
        "robotica": lambda: _de_robotica(busqueda),
    }

    if linea and linea in fuentes:
        renglones = fuentes[linea]()
    else:
        renglones = [r for traer in fuentes.values() for r in traer()]

    from datetime import date

    renglones.sort(
        key=lambda r: (
            r["fecha_compromiso"] or date.max,
            r["prioridad"],
            r["codigo"],
        )
    )
    return renglones


def resumen(renglones):
    """Los totales de la cabecera, calculados sobre lo que se está viendo.

    Se calculan del mismo conjunto que se enseña, no con consultas aparte: un
    contador que dice diez sobre una lista de ocho es peor que no tener
    contador.
    """
    from datetime import date

    hoy = date.today()
    return {
        "renglones": len(renglones),
        "piezas": sum(int(r["piezas"] or 0) for r in renglones),
        # Al kilo. En un indicador de cabecera, el gramo es ruido: «35.31605»
        # se lee peor que «35.316» y no dice nada más.
        "toneladas": (
            sum(Decimal(str(r["peso_kg"] or 0)) for r in renglones) / Decimal("1000")
        ).quantize(Decimal("0.001")),
        "vencidas": sum(
            1
            for r in renglones
            if r["fecha_compromiso"] and r["fecha_compromiso"] < hoy
        ),
        "por_linea": {
            clave: sum(1 for r in renglones if r["linea"] == clave)
            for clave in LINEAS
        },
    }
