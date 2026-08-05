"""Qué hay de cada producto terminado, y en qué situación está.

El taller vende de almacén. Un cliente pide cuarenta andamios, hay treinta, y
la respuesta se da por teléfono en ese momento: «te doy treinta hoy y te
fabrico diez». Para eso hace falta ver, de un vistazo y por producto, cuatro
números distintos que hasta ahora vivían en cuatro sitios:

    ┌─ en almacén ─────────────────────────────┐
    │  disponible          apartado            │   en producción      pedido
    │  (se puede           (ya tiene           │   (se está           (falta por
    │   prometer)           dueño)             │    fabricando)        cubrir)
    └──────────────────────────────────────────┘

- **Disponible** salía de `LogisticaStock`, que es lo único que la pantalla
  de producto terminado enseñaba.
- **Apartado** vivía repartido por las líneas de pedido y sólo se veía pedido
  a pedido, en la pantalla de Logística.
- **En producción** no se veía en ninguna parte junto al almacén: había que
  irse a Control de producción y sumar a ojo.
- **Lo pedido y no cubierto** tampoco.

Nada de esto se copia a una tabla nueva. Se deduce de las que ya existen,
igual que el catálogo de producto terminado: mantener un quinto número para
lo mismo garantiza que algún día uno de ellos mienta y nadie sepa cuál.

Un aviso sobre el significado de `LogisticaStock.stock`
-------------------------------------------------------

**Baja al apartar.** Es decir, es el *disponible*, no lo que hay en el
estante. Lo físico es `disponible + apartado`. Es la convención contraria a
la del almacén de materia prima (`inventario.Existencia`, donde `cantidad` es
lo físico y `comprometido` va aparte), y confundirlas hace que el almacenista
cuente el estante y encuentre más de lo que dice el sistema. Aquí se calculan
las dos y se enseñan con su nombre.
"""

from dataclasses import dataclass, field

from django.db.models import Sum

BASE = "mes"

HERRERIA = "herreria"
CORTA = "corta"

NOMBRE_DE_LINEA = {HERRERIA: "Herrería", CORTA: "Corta.mx"}


@dataclass
class Renglon:
    """Un producto y todo lo que se sabe de él."""

    linea: str
    producto: str
    #: Lo que se le puede prometer a un cliente nuevo, ahora mismo.
    disponible: int = 0
    #: Lo que sigue en el estante pero ya tiene dueño.
    apartado: int = 0
    #: Lo que se está fabricando y todavía no ha entrado al almacén.
    en_produccion: int = 0
    #: Lo que hay pedido y no está ni apartado ni enviado.
    pedido_pendiente: int = 0
    #: Lo que ya salió al cliente. Histórico, para saber qué se mueve.
    enviado: int = 0
    minimo: int = 0
    objetivo: int | None = None
    peso_kg: float | None = None
    actualizado = None
    nota: str = ""

    @property
    def linea_nombre(self):
        return NOMBRE_DE_LINEA.get(self.linea, self.linea)

    @property
    def en_almacen(self):
        """Lo que hay físicamente, prometido o no.

        Es el número que tiene que cuadrar cuando alguien cuenta el estante.
        """
        return self.disponible + self.apartado

    @property
    def bajo_minimo(self):
        """Si hay que reponer. Sin mínimo fijado no se avisa de nada.

        Se compara contra lo **disponible** y no contra lo que hay en el
        estante: lo apartado ya tiene dueño y no sirve para el siguiente
        cliente. Avisar sobre el físico haría que la alerta llegara cuando ya
        no queda nada que prometer.
        """
        return bool(self.minimo) and self.disponible < self.minimo

    @property
    def falta_por_fabricar(self):
        """Cuánto habría que hacer para cubrir lo pedido y el mínimo.

        Cuenta lo que ya está en producción: mandar a fabricar diez cuando ya
        hay diez en la línea es hacer veinte y quedarse con diez parados.
        """
        para_pedidos = self.pedido_pendiente - self.disponible - self.en_produccion
        objetivo = self.objetivo if self.objetivo is not None else self.minimo
        para_el_minimo = objetivo - self.disponible - self.en_produccion
        return max(0, para_pedidos, para_el_minimo if self.minimo else 0)


def _clave(texto):
    return (texto or "").strip().upper()


# ------------------------------------------------------------------ fuentes
#
# Cada función devuelve un diccionario {(línea, producto normalizado): número}.
# Se juntan al final. Partirlo así es lo que permite añadir una fuente —lo
# que Corta tenga apartado, mañana lo que devuelva un cliente— sin tocar el
# resto.


def _existencias():
    """Lo disponible en los dos almacenes, y de paso el nombre y el peso."""
    from catalogos.models import LogisticaStock, LogisticaStockCorta

    filas = {}
    for fila in (
        LogisticaStock.objects.using(BASE).select_related("producto").all()
    ):
        nombre = getattr(fila.producto, "nombre", "") or "—"
        filas[(HERRERIA, _clave(nombre))] = {
            "producto": nombre,
            "disponible": int(fila.stock or 0),
            "peso_kg": float(getattr(fila.producto, "peso_kg", 0) or 0),
            "actualizado": fila.actualizado_en,
        }
    for fila in LogisticaStockCorta.objects.using(BASE).all():
        filas[(CORTA, fila.producto_normalizado)] = {
            "producto": fila.producto,
            "disponible": int(fila.stock or 0),
            # Corta guarda el producto como texto libre, sin ficha, así que no
            # hay peso. Vacío y no cero: cero es un dato, vacío dice que no se
            # sabe.
            "peso_kg": None,
            "actualizado": fila.actualizado_en,
        }
    return filas


def _del_catalogo():
    """Los productos que el taller fabrica, hayan pasado por almacén o no.

    Sin esto, un producto del catálogo que nunca se ha fabricado no existe
    para esta pantalla, y por tanto **no se le puede fijar un mínimo**: habría
    que esperar a que se agote una vez para poder pedir que avise de que se
    agota. Devuelve sólo el nombre; los números salen de las otras fuentes.
    """
    from catalogos.models import CortaPiezaCatalogo, HerrPiezaCatalogo

    nombres = {}
    for linea, modelo in ((HERRERIA, HerrPiezaCatalogo), (CORTA, CortaPiezaCatalogo)):
        for nombre in modelo.objects.using(BASE).filter(activo=True).values_list(
            "nombre", flat=True
        ):
            if nombre:
                nombres[(linea, _clave(nombre))] = nombre
    return nombres


def _de_los_pedidos():
    """Lo apartado, lo enviado y lo pedido sin cubrir, por producto.

    Sólo de pedidos vivos. Un pedido cancelado que dejó material apartado es
    un problema de ese pedido, no una reserva que deba seguir descontando del
    disponible de todo el taller.
    """
    from catalogos.models import PedidoProduccionItem

    apartado, enviado, pendiente, nombres = {}, {}, {}, {}
    filas = (
        PedidoProduccionItem.objects.using(BASE)
        .filter(pedido__estado="Activa")
        .exclude(estado_herreria="Cancelado")
        .select_related("producto")
        .values("producto__nombre")
        .annotate(
            total=Sum("cantidad_total"),
            reservado=Sum("apartado"),
            despachado=Sum("enviado"),
        )
    )
    for fila in filas:
        nombre = fila["producto__nombre"] or ""
        clave = (HERRERIA, _clave(nombre))
        reservado = int(fila["reservado"] or 0)
        despachado = int(fila["despachado"] or 0)
        nombres[clave] = nombre
        apartado[clave] = reservado
        enviado[clave] = despachado
        pendiente[clave] = max(0, int(fila["total"] or 0) - reservado - despachado)
    return apartado, enviado, pendiente, nombres


def _de_corta():
    """Lo mismo, del lado de Corta, que lleva los contadores en la orden."""
    from catalogos.models import LaserOrdenProduccion

    apartado, enviado, nombres = {}, {}, {}
    filas = (
        LaserOrdenProduccion.objects.using(BASE)
        .exclude(estado="Cancelada")
        .values("nombre", "nombre_normalizado")
        .annotate(reservado=Sum("apartado"), despachado=Sum("enviado"))
    )
    for fila in filas:
        clave = (CORTA, fila["nombre_normalizado"] or "")
        if not clave[1]:
            continue
        nombres[clave] = fila["nombre"] or ""
        apartado[clave] = apartado.get(clave, 0) + int(fila["reservado"] or 0)
        enviado[clave] = enviado.get(clave, 0) + int(fila["despachado"] or 0)
    return apartado, enviado, nombres


def _en_produccion():
    """Lo que está en la línea y todavía no ha entrado al almacén.

    Se mide como objetivo menos terminado, no como total de piezas: una orden
    de cincuenta con treinta ya terminadas aporta veinte, no cincuenta. Las
    treinta ya están contadas en el almacén.
    """
    from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion

    en_curso, nombres = {}, {}
    fuentes = (
        (HERRERIA, HerrOrdenProduccion),
        (CORTA, LaserOrdenProduccion),
    )
    for linea, modelo in fuentes:
        for fila in (
            modelo.objects.using(BASE)
            .filter(estado="Abierta")
            .values(
                "nombre", "nombre_normalizado", "cantidad_objetivo", "cantidad_terminada"
            )
        ):
            clave = (linea, fila["nombre_normalizado"] or "")
            if not clave[1]:
                continue
            nombres[clave] = fila["nombre"] or ""
            falta = int(fila["cantidad_objetivo"] or 0) - int(
                fila["cantidad_terminada"] or 0
            )
            if falta > 0:
                en_curso[clave] = en_curso.get(clave, 0) + falta
    return en_curso, nombres


def _minimos():
    from nucleo.models import NivelMinimo

    return {
        (fila.linea, fila.producto_normalizado): fila
        for fila in NivelMinimo.objects.using(BASE).all()
    }


# -------------------------------------------------------------------- vista


def foto(busqueda="", linea="", solo_alertas=False, incluir_agotados=True):
    """La situación de cada producto terminado, en una lista.

    `incluir_agotados` existe porque la pantalla anterior filtraba por
    `stock > 0` y por tanto **escondía justo lo que se acabó**, que es lo que
    hay que reponer. Se puede apagar para el catálogo de «qué puedo entregar
    hoy», donde un renglón en cero no es información.
    """
    existencias = _existencias()
    apartado_h, enviado_h, pendiente_h, nombres_h = _de_los_pedidos()
    apartado_c, enviado_c, nombres_c = _de_corta()
    en_curso, nombres_o = _en_produccion()
    minimos = _minimos()

    apartado = {**apartado_h, **apartado_c}
    enviado = {**enviado_h, **enviado_c}

    # Cómo se escribe cada producto. La clave es el nombre en mayúsculas
    # porque es lo único que las dos líneas comparten, pero enseñar la clave
    # sería enseñar «ANDAMIO ESTÁNDAR» a gritos en toda la tabla. Se prefiere
    # el nombre del catálogo, que es el que alguien escribió con cuidado.
    del_catalogo = _del_catalogo()
    nombres = {
        **nombres_o,
        **nombres_c,
        **nombres_h,
        **{c: d["producto"] for c, d in existencias.items()},
        **del_catalogo,
    }

    # Qué cuenta como producto de almacén.
    #
    # Todo aquello de lo que se sepa algo entra, aunque no tenga fila de
    # existencias: algo pedido que nunca se ha fabricado tiene que verse, y
    # con el filtro anterior era invisible.
    #
    # Lo que **no** entra es una orden suelta. Herrería no guarda de qué pieza
    # del catálogo sale una orden: copia el nombre, y cuando alguien da de
    # alta un trabajo único escribiendo el código del pedido en el nombre, ese
    # código acabaría en esta lista como si fuera un producto que se tiene en
    # existencia. Un trabajo que se hace una vez no es almacén: vive en
    # Control de producción.
    claves = (
        set(existencias)
        | set(apartado)
        | set(enviado)
        | set(pendiente_h)
        | set(minimos)
        | set(del_catalogo)
    )

    renglones = []
    for clave in claves:
        codigo_linea, normalizado = clave
        datos = existencias.get(clave, {})
        minimo = minimos.get(clave)
        renglon = Renglon(
            linea=codigo_linea,
            producto=(
                nombres.get(clave)
                or (minimo.producto if minimo else "")
                or normalizado
            ),
            disponible=int(datos.get("disponible", 0)),
            apartado=apartado.get(clave, 0),
            en_produccion=en_curso.get(clave, 0),
            pedido_pendiente=pendiente_h.get(clave, 0),
            enviado=enviado.get(clave, 0),
            minimo=minimo.minimo if minimo else 0,
            objetivo=minimo.objetivo if minimo else None,
            peso_kg=datos.get("peso_kg"),
            nota=minimo.nota if minimo else "",
        )
        renglon.actualizado = datos.get("actualizado")
        renglones.append(renglon)

    if linea:
        renglones = [r for r in renglones if r.linea == linea]
    if busqueda:
        agujas = _clave(busqueda)
        renglones = [r for r in renglones if agujas in _clave(r.producto)]
    if solo_alertas:
        renglones = [r for r in renglones if r.bajo_minimo or r.falta_por_fabricar]
    if not incluir_agotados:
        renglones = [r for r in renglones if r.disponible > 0]

    # Lo que hay que atender primero: lo que está bajo mínimo, y dentro de
    # eso lo que más falta. Ordenar por nombre dejaría la alerta escondida en
    # la letra ese.
    renglones.sort(
        key=lambda r: (
            not r.bajo_minimo,
            -r.falta_por_fabricar,
            -r.disponible,
            r.producto,
        )
    )
    return renglones


def resumen(renglones):
    """Los totales de lo que se está viendo, no de otra consulta aparte.

    Un contador que dice diez sobre una lista de ocho es peor que no tener
    contador.
    """
    con_peso = [r for r in renglones if r.peso_kg is not None]
    return {
        "productos": len(renglones),
        "disponible": sum(r.disponible for r in renglones),
        "apartado": sum(r.apartado for r in renglones),
        "en_produccion": sum(r.en_produccion for r in renglones),
        "bajo_minimo": sum(1 for r in renglones if r.bajo_minimo),
        "por_fabricar": sum(r.falta_por_fabricar for r in renglones),
        "kilos": sum((r.peso_kg or 0) * r.en_almacen for r in con_peso),
        #: Cuántos renglones no pueden decir su peso. Sin el aviso, el total
        #: de kilos parece completo cuando no lo es.
        "sin_peso": len(renglones) - len(con_peso),
    }


def alertas():
    """Los productos bajo mínimo. Para la portada y para el aviso diario."""
    return [r for r in foto() if r.bajo_minimo]


def fijar_minimo(linea, producto, minimo, objetivo=None, nota="", quien=""):
    """Deja fijado cuánto hay que tener siempre de un producto.

    Un mínimo de cero se guarda igual, no se borra la fila: es la diferencia
    entre «alguien lo pensó y decidió que no hace falta avisar» y «nadie lo ha
    mirado nunca», y la segunda es la que hay que poder encontrar.
    """
    from nucleo.models import NivelMinimo

    producto = (producto or "").strip()
    if not producto or linea not in NOMBRE_DE_LINEA:
        return None
    fila, _ = NivelMinimo.objects.using(BASE).update_or_create(
        linea=linea,
        producto_normalizado=_clave(producto),
        defaults={
            "producto": producto,
            "minimo": max(0, int(minimo or 0)),
            "objetivo": max(0, int(objetivo)) if objetivo not in (None, "") else None,
            "nota": (nota or "").strip()[:200],
            "actualizado_por": (quien or "")[:120],
        },
    )
    return fila
