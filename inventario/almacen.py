"""«Por surtir»: la pantalla del almacenista.

Es el segundo factor que pidió el taller. La orden aparta el material, pero el
inventario **no baja** hasta que una persona con el material en la mano
confirma que lo entregó. Quien produce no puede hacerlo: sería el operador
diciendo que recibió lo que él mismo pidió, y entonces la confirmación no
comprueba nada.

Tres cosas se ven aquí y en ningún otro sitio:

- **Lo apartado que todavía no se ha entregado**, agrupado por orden. Es la
  cola de trabajo del almacén.
- **Lo que hay que comprar**: los materiales en o por debajo de su mínimo. Sale
  al entregar, que es el único momento en que el físico baja.
- **La diferencia entre lo que hay y lo que se puede prometer**, que es la
  distinción que hace que el inventario sea creíble.
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import roles
from core.excepciones import ErrorDeDominio
from core.servicios import inventario as servicio
from inventario.models import Existencia, Material, MovimientoMaterial

BASE = "mes"
CERO = Decimal("0")

solo_almacen = user_passes_test(roles.puede_entregar_material, login_url="login")


def _pendientes():
    """Lo apartado que todavía no se entregó, por material.

    Se lee de las existencias y no de los movimientos porque lo que interesa
    es el saldo vivo: una reserva de diez con seis ya entregadas son cuatro
    pendientes, no dos apuntes que hay que restar a mano.
    """
    filas = (
        Existencia.objects.using(BASE)
        .filter(comprometido__gt=CERO)
        .select_related("material", "lote", "almacen")
        .order_by("material__nombre", "lote__recibido_en")
    )

    por_material = {}
    for fila in filas:
        entrada = por_material.setdefault(fila.material_id, {
            "material": fila.material,
            "apartado": CERO,
            "fisico": CERO,
            "lotes": [],
        })
        entrada["apartado"] += fila.comprometido
        entrada["lotes"].append(fila)

    # El físico se cuenta aparte porque incluye los lotes que no tienen nada
    # apartado: si se sumara sólo lo de arriba, un material con reserva en un
    # lote y existencia libre en otro parecería tenerlo todo comprometido.
    for material_id, entrada in por_material.items():
        entrada["fisico"] = (
            Existencia.objects.using(BASE)
            .filter(material_id=material_id)
            .aggregate(total=Sum("cantidad"))["total"] or CERO
        )
        entrada["disponible"] = entrada["fisico"] - entrada["apartado"]

    return sorted(por_material.values(), key=lambda e: e["material"].nombre)


@login_required
@solo_almacen
def por_surtir(request):
    pendientes = _pendientes()
    faltantes = servicio.bajo_minimo()

    entregas = (
        MovimientoMaterial.objects.using(BASE)
        .filter(tipo=MovimientoMaterial.Tipo.CONSUMO)
        .select_related("material", "lote", "orden")
        .order_by("-ocurrido_en")[:15]
    )

    return render(request, "inventario/por_surtir.html", {
        "pendientes": pendientes,
        "faltantes": faltantes,
        "entregas": entregas,
        "total_apartado": sum((p["apartado"] for p in pendientes), CERO),
    })


@login_required
@solo_almacen
@require_POST
def entregar(request):
    """Confirma que el material salió del almacén. Aquí baja el inventario."""
    try:
        material = Material.objects.using(BASE).get(pk=request.POST.get("material"))
    except (Material.DoesNotExist, ValueError, TypeError):
        messages.error(request, "No se encontró ese material.")
        return redirect("inventario:por_surtir")

    try:
        cantidad = Decimal(str(request.POST.get("cantidad") or "0"))
    except Exception:
        messages.error(request, "La cantidad no es un número.")
        return redirect("inventario:por_surtir")

    try:
        _movimientos, faltantes = servicio.entregar(
            material=material,
            cantidad=cantidad,
            actor=request.user,
            comentario=(request.POST.get("comentario") or "")[:255],
            # El navegador manda la misma clave si el operador pulsa dos veces
            # o si la red del taller reintenta. Sin esto, el material se
            # descuenta dos veces.
            clave_idempotencia=request.POST.get("clave") or None,
        )
    except ErrorDeDominio as error:
        messages.error(request, str(error))
        return redirect("inventario:por_surtir")

    messages.success(
        request, f"Entregado: {cantidad} de {material.nombre}."
    )
    for faltante, queda, comprar in faltantes:
        # El aviso de reorden va como mensaje y no como un contador escondido
        # en una pantalla de compras: si no se ve aquí, se ve cuando ya no hay.
        messages.warning(
            request,
            f"Comprar {faltante.nombre}: quedan {queda} y el mínimo es "
            f"{faltante.stock_minimo} (faltan {comprar}).",
        )
    return redirect("inventario:por_surtir")


@login_required
@solo_almacen
@require_POST
def liberar(request):
    """Suelta una reserva sin entregar nada. La orden se canceló o se recortó."""
    try:
        material = Material.objects.using(BASE).get(pk=request.POST.get("material"))
        cantidad = Decimal(str(request.POST.get("cantidad") or "0"))
    except Exception:
        messages.error(request, "Datos incompletos.")
        return redirect("inventario:por_surtir")

    try:
        servicio.liberar(
            material=material,
            cantidad=cantidad,
            actor=request.user,
            comentario=(request.POST.get("comentario") or "")[:255],
        )
    except ErrorDeDominio as error:
        messages.error(request, str(error))
        return redirect("inventario:por_surtir")

    messages.success(request, f"Liberado: {cantidad} de {material.nombre}.")
    return redirect("inventario:por_surtir")


@login_required
def existencias(request):
    """Lo que hay, lo apartado y lo disponible.

    De sólo lectura y sin exigir el grupo de almacén a propósito: ventas y
    logística necesitan ver las existencias en tiempo real para saber qué
    pueden prometer, y no poder verlas es lo que lleva a prometer material que
    no hay.
    """
    filas = []
    for material in (
        Material.objects.using(BASE).filter(activo=True, inventariable=True)
        .order_by("categoria", "nombre")
    ):
        totales = (
            Existencia.objects.using(BASE)
            .filter(material=material)
            .aggregate(fisico=Sum("cantidad"), apartado=Sum("comprometido"))
        )
        fisico = totales["fisico"] or CERO
        apartado = totales["apartado"] or CERO
        filas.append({
            "material": material,
            "fisico": fisico,
            "apartado": apartado,
            "disponible": fisico - apartado,
            "bajo_minimo": material.stock_minimo > CERO and fisico <= material.stock_minimo,
        })

    return render(request, "inventario/existencias.html", {
        "filas": filas,
        "puede_entregar": roles.puede_entregar_material(request.user),
    })
