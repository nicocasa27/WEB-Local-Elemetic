"""Cómo va un proyecto.

La pregunta de la obra es «¿cómo va Matilda?», y la respuesta útil es una
resta: «faltan dieciocho vigas, ayer se terminaron nueve». Hasta ahora el
sistema no podía darla por dos razones:

1. **Un proyecto era sólo un nombre.** No había en ningún lado cuánto había
   que fabricar, así que «faltan dieciocho» no se podía calcular: se veía lo
   que estaba en la línea y nada más. Eso lo resuelve
   `nucleo.RequerimientoProyecto`.

2. **La pantalla del proyecto sólo enseñaba Estructuras.** Un proyecto que
   además lleva herrería y corte láser se veía a un tercio, y las otras dos
   líneas había que buscarlas a mano en sus pantallas.

Aquí se juntan las dos mitades: lo que se prometió y lo que se ha hecho, de
las cuatro líneas, en una lista de conceptos.

Cómo se cruzan
--------------

Por el código. Un requerimiento que dice `V-118` se cruza con las piezas de
ese proyecto cuyo código es `V-118`. Lo que se produce sin requerimiento
aparece igual, con lo requerido igualado a lo que hay: es trabajo real y
esconderlo sería peor que no cuadrar.

Robótica se lista aparte y sin avance. Esa línea no registra producción por
orden —`RobotProduccion` no apunta a ninguna—, así que cualquier porcentaje
que se enseñara aquí estaría inventado.
"""

from dataclasses import dataclass

from django.db.models import Count, Sum
from django.db.models.functions import Upper

from core import estados

BASE = "mes"

#: Lo que ya no está en producción. Enviado incluido: una pieza en la obra
#: está hecha, y no contarla haría que un proyecto entregado se viera a
#: medias para siempre.
HECHAS = {estados.TERMINADO, estados.ENVIADO}


@dataclass
class Concepto:
    """Un renglón de lo que lleva el proyecto."""

    codigo: str
    descripcion: str = ""
    linea: str = ""
    #: Cuánto hay que entregar. Del requerimiento si lo hay; si no, lo que se
    #: dio de alta en producción.
    requerido: int = 0
    hechas: int = 0
    en_produccion: int = 0
    peso_kg: float = 0.0
    fecha_compromiso = None
    nota: str = ""
    #: Si alguien apuntó este concepto como parte del proyecto, o si sólo
    #: apareció porque hay producción con ese código. Se dice: un proyecto
    #: donde todo es «apareció solo» es un proyecto que nadie planeó.
    planeado: bool = False

    @property
    def faltan(self):
        return max(0, self.requerido - self.hechas)

    @property
    def avance(self):
        if not self.requerido:
            return 0
        return min(100, round(self.hechas / self.requerido * 100))

    @property
    def completo(self):
        return bool(self.requerido) and self.hechas >= self.requerido


def _de_estructuras(proyecto):
    """Una fila por código de pieza, con sus piezas contadas por etapa.

    Estructuras lleva una fila por pieza física, así que aquí el requerido no
    hay que inventarlo: veintisiete vigas del código V-118 en este proyecto
    son veintisiete filas.
    """
    from produccion.models import Viga

    hechas_escritas = []
    for etapa in HECHAS:
        hechas_escritas.extend(estados.variantes(etapa))

    filas = {}
    consulta = (
        Viga.objects.using(BASE)
        .annotate(proyecto_norm=Upper("proyecto"))
        .filter(proyecto_norm=proyecto.nombre_normalizado)
        .values("codigo_viga", "descripcion", "estado")
        .annotate(cuantas=Count("internal_id"), kilos=Sum("peso_kg"))
    )
    for fila in consulta:
        codigo = (fila["codigo_viga"] or "").strip()
        concepto = filas.get(codigo.upper())
        if concepto is None:
            filas[codigo.upper()] = concepto = Concepto(
                codigo=codigo,
                descripcion=fila["descripcion"] or "",
                linea="Estructuras",
            )
        cuantas = int(fila["cuantas"] or 0)
        concepto.requerido += cuantas
        concepto.peso_kg += float(fila["kilos"] or 0)
        if estados.normalizar(fila["estado"]) in HECHAS:
            concepto.hechas += cuantas
        else:
            concepto.en_produccion += cuantas
    return filas


def _de_las_ordenes(proyecto):
    """Herrería y Corta.mx, que llevan una fila por orden y contadores dentro."""
    from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion

    filas = {}
    fuentes = (
        ("Herrería", HerrOrdenProduccion),
        ("Corta.mx", LaserOrdenProduccion),
    )
    for nombre_linea, modelo in fuentes:
        consulta = (
            modelo.objects.using(BASE)
            .filter(proyecto=proyecto)
            .exclude(estado="Cancelada")
            .values("codigo", "nombre", "descripcion")
            .annotate(
                objetivo=Sum("cantidad_objetivo"),
                terminadas=Sum("cantidad_terminada"),
                kilos=Sum("peso_kg"),
            )
        )
        for fila in consulta:
            codigo = (fila["codigo"] or fila["nombre"] or "").strip()
            if not codigo:
                continue
            objetivo = int(fila["objetivo"] or 0)
            terminadas = min(int(fila["terminadas"] or 0), objetivo)
            clave = codigo.upper()
            concepto = filas.get(clave)
            if concepto is None:
                filas[clave] = concepto = Concepto(
                    codigo=codigo,
                    descripcion=fila["descripcion"] or fila["nombre"] or "",
                    linea=nombre_linea,
                )
            concepto.requerido += objetivo
            concepto.hechas += terminadas
            concepto.en_produccion += max(0, objetivo - terminadas)
            concepto.peso_kg += float(fila["kilos"] or 0)
    return filas


def _requerimientos(proyecto):
    from nucleo.models import RequerimientoProyecto

    return list(
        RequerimientoProyecto.objects.using(BASE)
        .filter(proyecto=proyecto)
        .order_by("descripcion")
    )


def conceptos(proyecto):
    """Lo que lleva el proyecto y cómo va cada cosa.

    Se parte de lo producido y se le encima lo planeado. Al revés —partir de
    los requerimientos— escondería el trabajo que se hizo sin haberse
    apuntado, que es la mayoría mientras nadie use todavía esta pantalla.
    """
    filas = {**_de_estructuras(proyecto), **_de_las_ordenes(proyecto)}

    for requerimiento in _requerimientos(proyecto):
        clave = requerimiento.codigo_normalizado
        concepto = filas.get(clave) if clave else None
        if concepto is None:
            # Un requerimiento sin producción todavía. Es el caso normal el
            # día que se da de alta el proyecto, y es justo lo que antes no
            # se podía ver.
            concepto = Concepto(
                codigo=requerimiento.codigo,
                descripcion=requerimiento.descripcion,
                linea="",
            )
            filas[clave or f"sin-codigo-{requerimiento.pk}"] = concepto
        else:
            # Manda lo que alguien planeó: si se vendieron veintisiete y en el
            # sistema hay veinte dadas de alta, faltan siete por dar de alta y
            # el proyecto tiene que decirlo.
            concepto.descripcion = requerimiento.descripcion or concepto.descripcion
        concepto.requerido = max(concepto.requerido, requerimiento.cantidad)
        concepto.fecha_compromiso = requerimiento.fecha_compromiso
        concepto.nota = requerimiento.nota
        concepto.planeado = True

    orden = sorted(
        filas.values(),
        # Lo que falta primero, y dentro de eso lo que más falta. Un proyecto
        # se mira para saber qué queda, no para leer lo ya entregado.
        key=lambda c: (c.completo, -c.faltan, c.codigo),
    )
    return orden


def resumen(lista):
    """Los totales del proyecto, calculados sobre lo que se está viendo."""
    requerido = sum(c.requerido for c in lista)
    hechas = sum(c.hechas for c in lista)
    return {
        "conceptos": len(lista),
        "requerido": requerido,
        "hechas": hechas,
        "faltan": sum(c.faltan for c in lista),
        "en_produccion": sum(c.en_produccion for c in lista),
        "avance": round(hechas / requerido * 100) if requerido else 0,
        "toneladas": round(sum(c.peso_kg for c in lista) / 1000, 3),
        "completos": sum(1 for c in lista if c.completo),
        #: Cuántos renglones nadie apuntó como parte del proyecto. Un proyecto
        #: donde todo apareció solo es un proyecto que nadie planeó, y el
        #: «faltan N» de arriba entonces sólo cuenta lo ya dado de alta.
        "sin_planear": sum(1 for c in lista if not c.planeado),
    }


def ordenes_de_robotica(proyecto):
    """Las órdenes de robótica del proyecto, sin avance.

    Esa línea no registra producción por orden —`RobotProduccion` no apunta a
    ninguna— así que enseñar aquí un porcentaje sería inventarlo. Se listan
    para que no desaparezcan del proyecto, y se dice que no se miden.
    """
    from catalogos.models import RobotOrdenProduccion

    return list(
        RobotOrdenProduccion.objects.using(BASE)
        .filter(proyecto=proyecto)
        .exclude(estado="Cancelada")
        .order_by("-creado_en")
    )
