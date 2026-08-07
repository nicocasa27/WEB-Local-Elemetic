"""Qué hay que comprar.

El taller pidió que al bajar del mínimo se avisara a Compras. Está hecho, pero
**no con un aviso disparado**, por el mismo motivo que la bandeja de despacho:
el físico baja por entregas, por ajustes, por devoluciones y por correcciones a
mano, y cualquier camino que se olvide de disparar deja un material agotado del
que nadie se entera. Y ese fallo no se ve: la lista sale vacía y se confunde
con «no hay nada que comprar».

Aquí la lista se **deduce**: es lo que está en o por debajo de su mínimo, ahora
mismo. Cuando el material vuelve a subir desaparece solo, sin que nadie tenga
que acordarse de cerrar nada. Lo que se guarda es la respuesta: que ya se pidió,
a quién, cuánto y para cuándo.

Hasta ahora el aviso sólo se veía en el momento de entregar, así que quien no
estuviera surtiendo en ese instante no se enteraba nunca.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import roles
from core.servicios import inventario as servicio
from inventario.models import Material, Proveedor, SeguimientoCompra
from core.bases import BASE  # noqa: F401

CERO = Decimal("0")


def _seguimientos():
    return {
        s.material_id: s
        for s in SeguimientoCompra.objects.using(BASE).select_related("proveedor")
    }


def por_comprar(almacen=None):
    """Lo que está en o por debajo de su mínimo, con lo que ya se hizo.

    Se calcula cada vez. Es más lento que leer una tabla de avisos y es lo que
    garantiza que no se quede fuera un material que bajó por un camino que
    nadie previó.
    """
    atendidos = _seguimientos()
    filas = []
    for material, hay, falta in servicio.bajo_minimo(almacen=almacen):
        seguimiento = atendidos.get(material.id)
        filas.append({
            "material": material,
            "fisico": hay,
            "faltan": falta,
            # Lo disponible importa tanto como lo físico: material que está en
            # el estante pero comprometido con una orden no cubre la
            # siguiente, y comprar mirando sólo el físico llega tarde.
            "disponible": servicio.disponible(material, almacen=almacen),
            "seguimiento": seguimiento,
            "estado": (
                seguimiento.estado if seguimiento
                else SeguimientoCompra.Estado.PENDIENTE
            ),
        })
    # Lo más urgente arriba: lo que falta en proporción a su mínimo, no en
    # valor absoluto. Faltar dos de un mínimo de tres aprieta más que faltar
    # veinte de un mínimo de mil.
    return sorted(
        filas,
        key=lambda f: -(f["faltan"] / f["material"].stock_minimo)
        if f["material"].stock_minimo else 0,
    )


def cuantos_hay_que_comprar():
    """Para el contador del menú. Sólo lo que nadie ha atendido todavía."""
    return sum(
        1 for f in por_comprar()
        if f["estado"] == SeguimientoCompra.Estado.PENDIENTE
    )


@login_required
def bandeja(request):
    filas = por_comprar()
    return render(request, "inventario/compras.html", {
        "filas": filas,
        "total": len(filas),
        "pendientes": sum(
            1 for f in filas
            if f["estado"] == SeguimientoCompra.Estado.PENDIENTE
        ),
        "estados": SeguimientoCompra.Estado.choices,
        "proveedores": Proveedor.objects.using(BASE).filter(activo=True).order_by("nombre"),
        "puede_marcar": roles.puede_entregar_material(request.user),
    })


def _cantidad(texto):
    texto = (texto or "").strip().replace(",", "")
    if not texto:
        return CERO
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    return valor if valor >= CERO else None


@login_required
@require_POST
def marcar(request):
    """Anota qué hizo Compras con un renglón de la lista."""
    if not roles.puede_entregar_material(request.user):
        messages.error(request, "No tienes permiso para mover compras.")
        return redirect("inventario:compras")

    estado = (request.POST.get("estado") or "").strip()
    if estado not in SeguimientoCompra.Estado.values:
        messages.error(request, "Estado desconocido.")
        return redirect("inventario:compras")

    pedido = (request.POST.get("material") or "").strip()
    material = None
    if pedido.isdigit():
        material = Material.objects.using(BASE).filter(id=int(pedido)).first()
    if material is None:
        messages.error(request, "Ese material no existe.")
        return redirect("inventario:compras")

    cantidad = _cantidad(request.POST.get("cantidad_pedida"))
    if cantidad is None:
        messages.error(request, "La cantidad pedida tiene que ser un número.")
        return redirect("inventario:compras")

    proveedor = None
    identificador = (request.POST.get("proveedor") or "").strip()
    if identificador.isdigit():
        proveedor = Proveedor.objects.using(BASE).filter(id=int(identificador)).first()

    promesa = None
    texto = (request.POST.get("promesa") or "").strip()
    if texto:
        try:
            promesa = datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "La fecha de promesa no se entiende.")
            return redirect("inventario:compras")

    SeguimientoCompra.objects.using(BASE).update_or_create(
        material=material,
        defaults={
            "estado": estado,
            "proveedor": proveedor,
            "cantidad_pedida": cantidad,
            "promesa": promesa,
            "notas": (request.POST.get("notas") or "")[:255],
            "actor": request.user.get_username(),
        },
    )
    messages.success(request, f"{material.codigo}: {dict(SeguimientoCompra.Estado.choices)[estado]}.")
    return redirect("inventario:compras")
