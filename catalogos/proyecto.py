"""La pantalla de un proyecto: qué lleva y cómo va.

La pregunta de la obra es «¿cómo va Matilda?». La pantalla anterior enseñaba
una lista de hasta dos mil vigas con una barrita por pieza, y sólo de
Estructuras: un proyecto que además llevara herrería o corte láser se veía a
un tercio, y para saber cuánto faltaba había que contar las barritas.

Ahora enseña conceptos —«viga IPR: 27 pedidas, 9 hechas, faltan 18»— de las
cuatro líneas, y deja apuntar lo que el proyecto lleva antes de que exista
ninguna orden, que es lo que hacía imposible calcular el «faltan».
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalogos.models import Proyecto
from core.servicios import proyecto as servicio

BASE = "mes"


def _puede_planear(user):
    """Quién dice qué lleva un proyecto.

    Es de quien lo vendió y de quien lo dibuja, no del piso: apuntar aquí un
    requerimiento es decir qué se le prometió al cliente.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(
        name__in={"admin_general", "ingenieria_civil", "pedidos_ventas"}
    ).exists()


@login_required
def detalle(request, pk: int):
    el_proyecto = get_object_or_404(Proyecto.objects.using(BASE), pk=pk)
    lista = servicio.conceptos(el_proyecto)

    return render(
        request,
        "catalogos/proyecto_detalle.html",
        {
            "proyecto": el_proyecto,
            "conceptos": lista,
            "resumen": servicio.resumen(lista),
            "robotica": servicio.ordenes_de_robotica(el_proyecto),
            "puede_planear": _puede_planear(request.user),
        },
    )


@login_required
@user_passes_test(_puede_planear, login_url="catalogos:proyectos")
@require_POST
def requerimiento_crear(request, pk: int):
    from nucleo.models import RequerimientoProyecto

    el_proyecto = get_object_or_404(Proyecto.objects.using(BASE), pk=pk)
    descripcion = (request.POST.get("descripcion") or "").strip()
    codigo = (request.POST.get("codigo") or "").strip()
    try:
        cantidad = int(request.POST.get("cantidad") or 0)
    except (TypeError, ValueError):
        cantidad = 0

    if not descripcion:
        messages.error(request, "Falta decir qué es.")
    elif cantidad <= 0:
        messages.error(request, "La cantidad tiene que ser de uno para arriba.")
    elif (
        codigo
        and RequerimientoProyecto.objects.using(BASE)
        .filter(proyecto=el_proyecto, codigo_normalizado=codigo.upper())
        .exists()
    ):
        # Dos renglones con el mismo código se cruzarían los dos con la misma
        # producción y el avance saldría contado por duplicado.
        messages.error(
            request,
            f"Este proyecto ya lleva un renglón con el código «{codigo}». "
            "Cambia la cantidad de ése en vez de añadir otro.",
        )
    else:
        RequerimientoProyecto.objects.using(BASE).create(
            proyecto=el_proyecto,
            descripcion=descripcion,
            codigo=codigo,
            cantidad=cantidad,
            fecha_compromiso=request.POST.get("fecha_compromiso") or None,
            nota=(request.POST.get("nota") or "").strip()[:255],
            creado_por=request.user.get_username(),
        )
        if codigo:
            messages.success(
                request,
                f"{descripcion}: {cantidad}. Se cruza con lo que se produzca "
                f"con el código «{codigo}».",
            )
        else:
            messages.success(
                request,
                f"{descripcion}: {cantidad}. Sin código no se cruza con la "
                "producción todavía: queda como recordatorio hasta que se le "
                "ponga uno.",
            )

    return redirect("catalogos:proyecto_detalle", pk=el_proyecto.pk)


@login_required
@user_passes_test(_puede_planear, login_url="catalogos:proyectos")
@require_POST
def requerimiento_borrar(request, pk: int, requerimiento: int):
    from nucleo.models import RequerimientoProyecto

    el_proyecto = get_object_or_404(Proyecto.objects.using(BASE), pk=pk)
    fila = (
        RequerimientoProyecto.objects.using(BASE)
        .filter(pk=requerimiento, proyecto=el_proyecto)
        .first()
    )
    if fila is None:
        messages.error(request, "Ese renglón ya no está.")
    else:
        # Quitar el renglón quita lo planeado, no lo producido: lo que ya se
        # fabricó con ese código sigue apareciendo en la lista, y por eso se
        # dice, para que nadie crea que se borró trabajo.
        messages.success(
            request,
            f"Quitado «{fila.descripcion}» de lo planeado. Lo que ya se "
            "fabricó sigue en la lista.",
        )
        fila.delete()

    return redirect("catalogos:proyecto_detalle", pk=el_proyecto.pk)
