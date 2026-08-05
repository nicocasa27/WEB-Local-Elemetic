"""Almacén de producto terminado: qué hay, de quién es y qué falta hacer.

El taller pidió «un registro del inventario disponible para entrega
inmediata». La primera versión de esta pantalla lo daba —una lista de
producto y cuánto hay— y con eso se contestaba el teléfono. No alcanzaba para
la conversación de verdad, que es ésta:

    — ¿Tienes cuarenta andamios?
    — Tengo treinta.
    — Dame esos treinta y fabrícame diez.

Para eso hay que ver cuatro números a la vez y por producto: lo que se puede
prometer, lo que ya tiene dueño, lo que se está fabricando y lo que hace
falta. Vivían en cuatro pantallas distintas y sumarlos era de cabeza.

Aquí se enseñan juntos. **No se crea una tabla nueva**: los números se
deducen de los almacenes, los pedidos y las órdenes abiertas, que siguen
siendo la fuente de verdad de su línea. Lo único que se guarda es el mínimo
de cada producto, porque eso no se puede deducir de ningún lado: es una
decisión.

Quién la ve: ventas y logística, que son quienes contestan el teléfono.
Fijar los mínimos es de quien decide qué conviene tener, y va aparte.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.servicios import almacen_terminado as servicio


def disponible_para_entrega(busqueda=""):
    """Lo que se puede entregar hoy mismo, sin agotados.

    Se mantiene por lo que significa —«¿qué puedo prometer ahora?»— que no es
    lo mismo que la lista completa: ahí un renglón en cero es información
    (hay que reponerlo) y aquí es ruido.
    """
    return servicio.foto(busqueda=busqueda, incluir_agotados=False)


def _puede_fijar_minimos(user):
    """Quién decide cuánto hay que tener siempre de algo.

    No es de quien despacha: es de quien conoce la demanda y lo que cuesta
    tener material parado. Un mínimo mal puesto llena el almacén o deja al
    taller vendiendo lo que no tiene.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(
        name__in={"admin_general", "pedidos_ventas", "herreria_supervision"}
    ).exists()


@login_required
def catalogo(request):
    busqueda = (request.GET.get("q") or "").strip()
    linea = (request.GET.get("linea") or "").strip()
    solo_alertas = request.GET.get("alertas") == "1"

    renglones = servicio.foto(busqueda=busqueda, linea=linea, solo_alertas=solo_alertas)
    # El contador de cada pestaña se calcula sobre la lista sin filtrar por
    # línea, para que no cambie al pulsarla.
    sin_filtro_de_linea = servicio.foto(busqueda=busqueda, solo_alertas=solo_alertas)

    return render(
        request,
        "catalogos/producto_terminado.html",
        {
            "filas": renglones,
            "resumen": servicio.resumen(renglones),
            "busqueda": busqueda,
            "linea": linea,
            "solo_alertas": solo_alertas,
            "lineas": servicio.NOMBRE_DE_LINEA,
            "conteo_por_linea": {
                clave: sum(1 for r in sin_filtro_de_linea if r.linea == clave)
                for clave in servicio.NOMBRE_DE_LINEA
            },
            "total_sin_filtrar": len(sin_filtro_de_linea),
            "puede_fijar_minimos": _puede_fijar_minimos(request.user),
        },
    )


@login_required
@user_passes_test(_puede_fijar_minimos, login_url="catalogos:producto_terminado")
def minimos(request):
    """Cuánto hay que tener siempre de cada producto.

    Se listan **todos** los productos conocidos, no sólo los que ya tienen
    mínimo: la pregunta útil es cuáles faltan por decidir, y una lista de lo
    ya decidido no la contesta.
    """
    busqueda = (request.GET.get("q") or "").strip()
    renglones = servicio.foto(busqueda=busqueda)
    renglones.sort(key=lambda r: (bool(r.minimo), r.linea, r.producto))
    return render(
        request,
        "catalogos/producto_terminado_minimos.html",
        {
            "filas": renglones,
            "busqueda": busqueda,
            "sin_decidir": sum(1 for r in renglones if not r.minimo),
        },
    )


@login_required
@user_passes_test(_puede_fijar_minimos, login_url="catalogos:producto_terminado")
@require_POST
def guardar_minimo(request):
    linea = (request.POST.get("linea") or "").strip()
    producto = (request.POST.get("producto") or "").strip()
    try:
        minimo = int(request.POST.get("minimo") or 0)
    except (TypeError, ValueError):
        minimo = -1
    crudo = (request.POST.get("objetivo") or "").strip()
    try:
        objetivo = int(crudo) if crudo else None
    except (TypeError, ValueError):
        objetivo = None

    if minimo < 0:
        messages.error(request, "El mínimo tiene que ser un número de cero para arriba.")
    elif objetivo is not None and objetivo < minimo:
        # Reponer hasta menos del mínimo dejaría el producto en alerta justo
        # después de fabricarlo. Es un error de dedo que vale la pena atajar.
        messages.error(
            request,
            "El objetivo de reposición no puede ser menor que el mínimo: "
            "el producto quedaría en alerta nada más fabricarlo.",
        )
    elif (
        servicio.fijar_minimo(
            linea,
            producto,
            minimo,
            objetivo=objetivo,
            nota=request.POST.get("nota") or "",
            quien=request.user.get_username(),
        )
        is None
    ):
        messages.error(request, "No se reconoce ese producto.")
    elif minimo:
        messages.success(
            request, f"«{producto}»: se avisa cuando el disponible baje de {minimo}."
        )
    else:
        messages.success(request, f"«{producto}»: sin aviso de existencias bajas.")

    destino = request.POST.get("next") or ""
    if destino.startswith("/"):
        return redirect(destino)
    return redirect("catalogos:producto_terminado_minimos")
