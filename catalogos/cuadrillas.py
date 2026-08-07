"""Armar la cuadrilla del día: quién trabaja, dónde y en qué turno.

`EquipoTrabajo` ya existía, pero es una plantilla fija —«Cuadrilla A de
soldadura, cuatro integrantes»— y en el piso no se cumple ningún día: falta
uno, otro se pasa a pintura por la tarde. La producción se acababa atribuyendo
a la plantilla y no a quien estuvo.

Esta pantalla se abre una vez por la mañana y deja dicho quién vino. A partir
de ahí, cada avance que se registre en esa área se anota solo con esa
cuadrilla; nadie tiene que escribirla otra vez. Ese es el trato: se captura una
vez al día en lugar de una vez por pieza.

**El pasado no se edita.** Una cuadrilla de la semana pasada es un hecho, y es
lo que sostiene el indicador de producción por persona. Si se pudiera corregir,
cualquier número histórico dejaría de ser comprobable. Lo que sí se puede es
armar la de mañana por adelantado.
"""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogos.models import (
    Colaborador,
    Cuadrilla,
    CuadrillaIntegrante,
    EquipoTrabajo,
    Maquina,
)
from core.bases import BASE  # noqa: F401


#: Cuántos días atrás se enseñan en la lista. Más que eso es historia, y para
#: eso está la pantalla de trazabilidad.
DIAS_VISIBLES = 14


def _editable(cuadrilla):
    """Sólo se toca la de hoy o la de un día futuro.

    Se compara contra la fecha de la cuadrilla y no contra cuándo se creó: lo
    que hace que un día sea pasado es el trabajo que ya se hizo, no cuándo se
    capturó.
    """
    return cuadrilla.fecha >= timezone.localdate()


def _colaboradores():
    return list(
        Colaborador.objects.using(BASE)
        .filter(activo=True)
        .select_related("equipo")
        .order_by("nombre")
    )


def _fraccion(texto):
    """Qué parte de la jornada estuvo. Vacío es la jornada entera."""
    texto = (texto or "").strip().replace(",", ".")
    if not texto:
        return Decimal("1.00")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    if valor <= Decimal("0") or valor > Decimal("1"):
        return None
    return valor.quantize(Decimal("0.01"))


@login_required
def lista(request):
    desde = timezone.localdate() - timedelta(days=DIAS_VISIBLES)
    cuadrillas = (
        Cuadrilla.objects.using(BASE)
        .filter(fecha__gte=desde)
        .select_related("maquina", "plantilla")
        .prefetch_related("integrantes__colaborador")
        .order_by("-fecha", "centro", "turno")
    )

    filas = []
    for cuadrilla in cuadrillas:
        filas.append({
            "cuadrilla": cuadrilla,
            "gente": [i.colaborador.nombre for i in cuadrilla.integrantes.all()],
            "editable": _editable(cuadrilla),
        })

    hoy = timezone.localdate()
    return render(request, "catalogos/cuadrillas.html", {
        "filas": filas,
        "hoy": hoy,
        # Cuántas áreas se quedaron sin cuadrilla hoy. Es el aviso que hace
        # útil abrir esta pantalla por la mañana: sin él, olvidarse no se
        # nota hasta que los indicadores salen vacíos a fin de mes.
        "sin_armar": _areas_sin_cuadrilla(hoy),
        "dias": DIAS_VISIBLES,
    })


def _areas_sin_cuadrilla(dia):
    armadas = set(
        Cuadrilla.objects.using(BASE).filter(fecha=dia).values_list("centro", flat=True)
    )
    return [
        etiqueta
        for clave, etiqueta in Maquina.TIPO_CHOICES
        if clave not in armadas
    ]


@login_required
def armar(request, pk=None):
    cuadrilla = None
    if pk is not None:
        cuadrilla = get_object_or_404(Cuadrilla.objects.using(BASE), pk=pk)
        if not _editable(cuadrilla):
            messages.error(
                request,
                "Esa cuadrilla ya es historia y no se cambia. "
                "Es lo que sostiene la producción por persona de ese día.",
            )
            return redirect("catalogos:cuadrillas")

    if request.method == "POST":
        return _guardar(request, cuadrilla)

    elegidos = {}
    if cuadrilla is not None:
        elegidos = {
            i.colaborador_id: i for i in cuadrilla.integrantes.select_related("colaborador")
        }

    # Las filas se arman aquí y no en la plantilla: un `{% if %}` no puede
    # buscar por clave en un diccionario, y sin esto los papeles y las
    # jornadas ya capturadas saldrían en blanco al volver a abrir.
    filas = []
    for persona in _colaboradores():
        anterior = elegidos.get(persona.id)
        filas.append({
            "persona": persona,
            "elegido": anterior is not None,
            "papel": getattr(anterior, "papel", ""),
            "fraccion": getattr(anterior, "fraccion", None),
        })

    return render(request, "catalogos/cuadrilla_armar.html", {
        "cuadrilla": cuadrilla,
        "gente": filas,
        "turnos": Cuadrilla.Turno.choices,
        "centros": Maquina.TIPO_CHOICES,
        "papeles": Colaborador.ROL_CHOICES,
        "maquinas": Maquina.objects.using(BASE).filter(activo=True).order_by("tipo", "nombre"),
        "plantillas": EquipoTrabajo.objects.using(BASE).filter(activo=True).order_by("nombre"),
        "hoy": timezone.localdate().isoformat(),
    })


def _guardar(request, cuadrilla):
    fecha = (request.POST.get("fecha") or "").strip()
    turno = (request.POST.get("turno") or "").strip()
    centro = (request.POST.get("centro") or "").strip()
    maquina_id = (request.POST.get("maquina") or "").strip()
    plantilla_id = (request.POST.get("plantilla") or "").strip()
    seleccionados = request.POST.getlist("integrante")

    if turno not in Cuadrilla.Turno.values:
        messages.error(request, "Turno desconocido.")
        return redirect("catalogos:cuadrilla_armar")
    if centro not in {clave for clave, _ in Maquina.TIPO_CHOICES}:
        messages.error(request, "Centro de trabajo desconocido.")
        return redirect("catalogos:cuadrilla_armar")

    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Falta la fecha.")
        return redirect("catalogos:cuadrilla_armar")

    if dia < timezone.localdate():
        messages.error(
            request, "No se arma una cuadrilla para un día que ya pasó."
        )
        return redirect("catalogos:cuadrilla_armar")

    if not seleccionados:
        # Una cuadrilla vacía es peor que ninguna: aparece armada y no
        # atribuye el trabajo a nadie.
        messages.error(request, "Elige al menos a una persona.")
        return redirect("catalogos:cuadrilla_armar")

    validos = {
        c.id for c in Colaborador.objects.using(BASE).filter(activo=True)
    }
    ids = []
    for texto in seleccionados:
        if str(texto).isdigit() and int(texto) in validos:
            ids.append(int(texto))
    if not ids:
        messages.error(request, "Ninguna de esas personas está activa.")
        return redirect("catalogos:cuadrilla_armar")

    # Las fracciones se validan antes de abrir la transacción: descubrir un
    # dato malo a mitad de la escritura obliga a deshacerla, y el usuario ve
    # un error de sistema en vez del suyo.
    fracciones = {}
    for persona in ids:
        fraccion = _fraccion(request.POST.get(f"fraccion_{persona}"))
        if fraccion is None:
            messages.error(
                request,
                "La fracción de jornada va entre 0 y 1. "
                "Media jornada se escribe 0.5.",
            )
            return redirect("catalogos:cuadrilla_armar")
        fracciones[persona] = fraccion

    maquina = None
    if maquina_id.isdigit():
        maquina = Maquina.objects.using(BASE).filter(
            id=int(maquina_id), activo=True
        ).first()
    plantilla = None
    if plantilla_id.isdigit():
        plantilla = EquipoTrabajo.objects.using(BASE).filter(
            id=int(plantilla_id)
        ).first()

    with transaction.atomic(using=BASE):
        if cuadrilla is None:
            # Armar dos veces el mismo turno en el mismo sitio no crea una
            # segunda cuadrilla: actualiza la que ya estaba. Sin esto, la
            # restricción de la base lanzaría un error que el usuario leería
            # como «el sistema falló» cuando lo que quiso fue corregir.
            cuadrilla, _ = Cuadrilla.objects.using(BASE).get_or_create(
                fecha=dia, turno=turno, centro=centro, maquina=maquina,
                defaults={"armada_por": request.user.get_username()},
            )
        cuadrilla.fecha = dia
        cuadrilla.turno = turno
        cuadrilla.centro = centro
        cuadrilla.maquina = maquina
        cuadrilla.plantilla = plantilla
        cuadrilla.comentario = (request.POST.get("comentario") or "")[:255]
        cuadrilla.armada_por = request.user.get_username()
        cuadrilla.save(using=BASE)

        CuadrillaIntegrante.objects.using(BASE).filter(
            cuadrilla=cuadrilla
        ).exclude(colaborador_id__in=ids).delete()

        for persona in ids:
            CuadrillaIntegrante.objects.using(BASE).update_or_create(
                cuadrilla=cuadrilla,
                colaborador_id=persona,
                defaults={
                    "papel": (request.POST.get(f"papel_{persona}") or "")[:20],
                    "fraccion": fracciones[persona],
                },
            )

    messages.success(
        request, f"Cuadrilla de {cuadrilla.get_centro_display()} armada con {len(ids)} personas."
    )
    return redirect("catalogos:cuadrillas")


@login_required
@require_POST
def deshacer(request, pk):
    """Borra una cuadrilla del día, para cuando se armó equivocada.

    Sólo la de hoy o la de mañana, por lo mismo que no se editan las viejas.
    Los apuntes de trabajo que ya la citaban conservan a su gente, porque los
    integrantes se copiaron al anotarlos.
    """
    cuadrilla = get_object_or_404(Cuadrilla.objects.using(BASE), pk=pk)
    if not _editable(cuadrilla):
        messages.error(request, "Esa cuadrilla ya es historia y no se borra.")
        return redirect("catalogos:cuadrillas")

    etiqueta = f"{cuadrilla.get_centro_display()} del {cuadrilla.fecha:%d/%m}"
    with transaction.atomic(using=BASE):
        CuadrillaIntegrante.objects.using(BASE).filter(cuadrilla=cuadrilla).delete()
        cuadrilla.delete(using=BASE)

    messages.success(request, f"Se quitó la cuadrilla de {etiqueta}.")
    return redirect("catalogos:cuadrillas")
