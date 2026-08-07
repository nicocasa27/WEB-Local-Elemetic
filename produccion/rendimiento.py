"""«¿Quién está rindiendo y dónde se para el material?»

El tablero de Reportes contesta cuánto se produjo. No contestaba nada de lo
que este taller pregunta a diario: cuánto tarda cada quien en su parte, dónde
se queda el material parado esperando a que alguien lo tome, y quién entrega
piezas que hay que rehacer.

Se enseña por rango de fechas, con los últimos treinta días por defecto: menos
que eso y las medianas se apoyan en cuatro muestras, más y se mezclan meses
con gente distinta.
"""

from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.utils import timezone

from core import roles
from core.servicios import rendimiento as servicio
from core.bases import BASE  # noqa: F401


#: Cuántos días se miran si nadie dice otra cosa.
DIAS_POR_DEFECTO = 30

#: Por debajo de esto, una mediana no significa nada y la pantalla lo dice en
#: vez de enseñar un número que alguien va a usar para juzgar a una persona.
#: Es la diferencia entre un indicador y un rumor con formato de tabla.
MUESTRAS_MINIMAS = 5


def puede_ver(user):
    """Quién ve el rendimiento de las personas.

    No es una pantalla de piso. Enseña el nombre de cada quien con su tiempo al
    lado, y eso lo mira quien dirige, no el compañero de al lado. La supervisión
    de cada línea entra porque es quien tiene que actuar con lo que dice.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(
        name__in=set(roles.QUE_ADMINISTRAN)
        | {"herreria_supervision", "corte_laser_supervision"}
    ).exists()


def _rango(request):
    """El rango que se está mirando, y sus dos fechas para el formulario."""
    hoy = timezone.localdate()
    try:
        hasta = datetime.strptime(request.GET.get("hasta", ""), "%Y-%m-%d").date()
    except ValueError:
        hasta = hoy
    try:
        desde = datetime.strptime(request.GET.get("desde", ""), "%Y-%m-%d").date()
    except ValueError:
        desde = hasta - timedelta(days=DIAS_POR_DEFECTO)
    if desde > hasta:
        desde, hasta = hasta, desde

    huso = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(desde, datetime.min.time()), huso),
        # Hasta el final del día elegido: si no, pedir «del 1 al 5» dejaría
        # fuera todo el día 5, que es el fallo clásico de estos formularios.
        timezone.make_aware(
            datetime.combine(hasta + timedelta(days=1), datetime.min.time()), huso
        ),
        desde,
        hasta,
    )


@login_required
@user_passes_test(puede_ver, login_url="produccion:dashboard")
def rendimiento(request):
    desde, hasta, desde_dia, hasta_dia = _rango(request)

    personas = servicio.por_persona(desde, hasta)
    return render(request, "produccion/rendimiento.html", {
        "desde": desde_dia,
        "hasta": hasta_dia,
        "personas": personas,
        "esperas": servicio.esperas(desde, hasta),
        "parado": servicio.parado_ahora(),
        "calidad": servicio.calidad(desde, hasta),
        "muestras_minimas": MUESTRAS_MINIMAS,
        # Sin apuntes no hay nada que medir, y la pantalla vacía se lee como
        # «nadie trabajó». Se distingue una cosa de la otra.
        "hay_datos": bool(personas),
    })
