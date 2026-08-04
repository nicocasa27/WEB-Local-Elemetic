"""Catálogo de producto terminado: qué se puede entregar hoy mismo.

El taller pidió «un registro del inventario disponible para entrega inmediata:
andamios, anclas, placas base, registros». Ese registro ya existía, pero
partido en dos tablas que nadie mira juntas —`LogisticaStock` para herrería y
`LogisticaStockCorta` para Corta— con estructuras distintas: una apunta al
catálogo de piezas y la otra guarda el nombre como texto.

Aquí se leen las dos y se enseñan como una sola lista. **No se crea una tercera
tabla.** Copiar los saldos a un catálogo nuevo significaría mantener tres
números para lo mismo, y el día que uno se desincronice —que es cuando, no si—
nadie sabría cuál es el bueno. La lista se deduce; las dos tablas siguen siendo
la fuente de verdad de su línea.

Quién la ve: Ventas y Logística, en lectura. Es la pregunta que hacen veinte
veces al día por teléfono —«¿tienes andamios?»— y hasta ahora había que
levantarse a mirar.
"""

from django.contrib.auth.decorators import login_required

from django.shortcuts import render

from catalogos.models import (
    LogisticaStock,
    LogisticaStockCorta,
    SeguimientoDespacho,
)

BASE = "mes"


def _de_herreria(busqueda=""):
    filas = (
        LogisticaStock.objects.using(BASE)
        .select_related("producto")
        .filter(stock__gt=0)
    )
    if busqueda:
        filas = filas.filter(producto__nombre__icontains=busqueda)
    for fila in filas:
        yield {
            "linea": SeguimientoDespacho.Linea.HERRERIA,
            "linea_nombre": "Herrería",
            "producto": getattr(fila.producto, "nombre", "") or "—",
            "disponible": int(fila.stock or 0),
            "peso_kg": float(getattr(fila.producto, "peso_kg", 0) or 0),
            "actualizado": fila.actualizado_en,
        }


def _de_corta(busqueda=""):
    filas = LogisticaStockCorta.objects.using(BASE).filter(stock__gt=0)
    if busqueda:
        filas = filas.filter(producto__icontains=busqueda)
    for fila in filas:
        yield {
            "linea": SeguimientoDespacho.Linea.CORTA,
            "linea_nombre": "Corta.mx",
            "producto": fila.producto,
            "disponible": int(fila.stock or 0),
            # Corta guarda el producto como texto libre, sin ficha, así que no
            # hay peso. Se enseña vacío en vez de cero: cero es un dato, vacío
            # dice que no se sabe.
            "peso_kg": None,
            "actualizado": fila.actualizado_en,
        }


def disponible_para_entrega(busqueda=""):
    """Todo lo que hay listo, de las dos líneas, sin agotados."""
    filas = list(_de_herreria(busqueda)) + list(_de_corta(busqueda))
    return sorted(filas, key=lambda f: (-f["disponible"], f["producto"]))


@login_required
def catalogo(request):
    busqueda = (request.GET.get("q") or "").strip()
    filas = disponible_para_entrega(busqueda)

    return render(request, "catalogos/producto_terminado.html", {
        "filas": filas,
        "busqueda": busqueda,
        "renglones": len(filas),
        "piezas": sum(f["disponible"] for f in filas),
        "kilos": sum(
            (f["peso_kg"] or 0) * f["disponible"] for f in filas
        ),
        # Cuántos renglones no pueden decir su peso. Es honesto enseñarlo: sin
        # el aviso, el total de kilos parece completo cuando no lo es.
        "sin_peso": sum(1 for f in filas if f["peso_kg"] is None),
    })
