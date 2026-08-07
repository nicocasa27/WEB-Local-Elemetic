"""Qué se hizo, con qué equipo y con quién.

Tres preguntas que el taller hacía y el sistema no podía responder:

- **«¿Cuánto sacó la cortadora 3 esta semana?»** Antes toda la producción de
  corte iba a un mismo montón, así que no se podía saber cuál de los seis
  equipos va saturado ni cuál lleva días parado.
- **«¿Quién estaba el día que salió mal esa pieza?»** La bitácora guardaba el
  cambio de estado y nada más.
- **«¿Por dónde pasó esta pieza?»** Se podía leer del historial, pero sin
  decir en qué equipo ni con qué cuadrilla.

Se responden leyendo los apuntes de trabajo. La pantalla no calcula nada que
no esté escrito: si un apunte salió sin cuadrilla, aquí se ve sin cuadrilla, no
se rellena con una suposición.
"""

from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from catalogos.models import ApunteDeTrabajo, Colaborador, Cuadrilla, Maquina
from core.bases import BASE  # noqa: F401


#: Ventana por defecto. Una semana es lo que dura la conversación de «cómo
#: fuimos»; un mes obliga a esperar y a filtrar.
DIAS = 7


def _rango(request):
    hoy = timezone.localdate()
    try:
        hasta = datetime.strptime(request.GET.get("hasta", ""), "%Y-%m-%d").date()
    except ValueError:
        hasta = hoy
    try:
        desde = datetime.strptime(request.GET.get("desde", ""), "%Y-%m-%d").date()
    except ValueError:
        desde = hasta - timedelta(days=DIAS)
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


def _apuntes(desde, hasta):
    return (
        ApunteDeTrabajo.objects.using(BASE)
        .filter(ocurrido_en__date__gte=desde, ocurrido_en__date__lte=hasta)
        .select_related("maquina", "cuadrilla")
    )


def por_maquina(desde, hasta):
    """Cuántos avances hizo cada equipo en la ventana.

    Se cuentan avances y no toneladas porque el peso vive en cuatro tablas
    distintas y traerlo aquí duplicaría la lógica de conteo que ya está en
    métricas. Los avances contestan la pregunta que se hace en el piso: cuál
    va cargado y cuál no se está usando.
    """
    conteos = dict(
        _apuntes(desde, hasta)
        .filter(maquina__isnull=False)
        .values_list("maquina_id")
        .annotate(cuantos=Count("id"))
    )

    filas = []
    for maquina in Maquina.objects.using(BASE).filter(activo=True).order_by("tipo", "nombre"):
        filas.append({
            "maquina": maquina,
            "avances": conteos.get(maquina.id, 0),
        })
    # Sin actividad primero no: lo que interesa arriba es lo que más se movió.
    # Pero los ceros se quedan en la lista a propósito — un equipo que no
    # aparece se confunde con uno que no existe.
    return sorted(filas, key=lambda f: -f["avances"])


def sin_equipo(desde, hasta):
    """Avances de etapas que exigen equipo y salieron sin él.

    Debería ser cero. Si no lo es, hay un camino del código que todavía
    escribe sin pasar por el selector, y el indicador por máquina está
    contando de menos sin avisar.
    """
    from core.servicios.trabajo import ETAPAS_QUE_EXIGEN_MAQUINA

    return (
        _apuntes(desde, hasta)
        .filter(etapa__in=ETAPAS_QUE_EXIGEN_MAQUINA, maquina__isnull=True)
        .count()
    )


def por_persona(desde, hasta):
    """En cuántos avances participó cada quien.

    Sale de los integrantes copiados en el apunte, no de la cuadrilla actual.
    Por eso corregir una cuadrilla hoy no cambia este número de la semana
    pasada, que es justo lo que hace que se pueda comprobar.
    """
    cuenta = {}
    # Sólo la columna de integrantes: son miles de filas y no hace falta
    # instanciar el apunte entero para contar.
    copiados = (
        ApunteDeTrabajo.objects.using(BASE)
        .filter(ocurrido_en__date__gte=desde, ocurrido_en__date__lte=hasta)
        .values_list("integrantes", flat=True)
    )
    for texto in copiados:
        for parte in (texto or "").split(","):
            if parte.strip().isdigit():
                identificador = int(parte)
                cuenta[identificador] = cuenta.get(identificador, 0) + 1

    if not cuenta:
        return []

    gente = {
        c.id: c
        for c in Colaborador.objects.using(BASE).filter(id__in=cuenta)
    }
    filas = [
        {"colaborador": gente[i], "avances": n}
        for i, n in cuenta.items()
        if i in gente
    ]
    return sorted(filas, key=lambda f: -f["avances"])


def historia_de(linea, referencia):
    """Por dónde pasó una pieza, con equipo y cuadrilla en cada paso."""
    return list(
        ApunteDeTrabajo.objects.using(BASE)
        .filter(linea=linea, referencia=int(referencia))
        .select_related("maquina", "cuadrilla")
        .order_by("ocurrido_en")
    )


@login_required
def tablero(request):
    desde, hasta = _rango(request)

    codigo = (request.GET.get("codigo") or "").strip()
    seguimiento = []
    if codigo:
        # Se busca por código y no por identificador: en el piso la pieza se
        # llama por lo que lleva pintado, no por su número de fila.
        seguimiento = list(
            ApunteDeTrabajo.objects.using(BASE)
            .filter(codigo__icontains=codigo)
            .select_related("maquina", "cuadrilla")
            .order_by("ocurrido_en")[:200]
        )

    return render(request, "catalogos/trazabilidad.html", {
        "desde": desde,
        "hasta": hasta,
        "maquinas": por_maquina(desde, hasta),
        "personas": por_persona(desde, hasta),
        "sin_equipo": sin_equipo(desde, hasta),
        "codigo": codigo,
        "seguimiento": seguimiento,
        "total": _apuntes(desde, hasta).count(),
        "cuadrillas": Cuadrilla.objects.using(BASE).filter(
            fecha__gte=desde, fecha__lte=hasta
        ).count(),
    })
