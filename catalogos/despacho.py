"""Bandeja de despacho: qué está listo para salir del taller.

El taller pidió «un disparador automático que avise a Logística al marcar una
orden como Terminado». Está hecho, pero **no con un disparador**, y conviene
saber por qué.

Un disparador crea el aviso cuando alguien cambia el estado. En este sistema el
estado se cambia desde cuatro motores distintos y desde decenas de sitios del
código, así que cualquier camino que se olvide de disparar deja una orden
terminada de la que Logística nunca se entera. Y ese fallo no se ve: la bandeja
sale vacía y parece que no hay nada que despachar. Es la peor clase de error,
porque se confunde con «hoy no hubo trabajo».

Aquí la bandeja se **deduce**: es lo que está terminado y todavía no ha salido.
No puede desactualizarse porque no hay nada que actualizar, y una orden aparece
sola aunque se haya terminado por un camino que nadie previó. Lo que sí se
guarda es la respuesta —quién la vio, quién la apartó para el camión—, que es
lo que una lista sin memoria no puede dar.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogos.models import (
    HerrOrdenProduccion,
    LaserOrdenProduccion,
    LogisticaEnvioCorta,
    SeguimientoDespacho,
)
from core import estados as est
from produccion.models import Viga
from core.bases import BASE  # noqa: F401


#: Los estados que significan «ya salió». Lo que esté en uno de ellos no
#: aparece en la bandeja.
YA_SALIO = {est.ENVIADO}


def _seguimientos():
    """Lo que ya se atendió, indexado para cruzarlo con lo deducido."""
    return {
        (s.linea, s.referencia): s
        for s in SeguimientoDespacho.objects.using(BASE).all()
    }


def _de_estructuras():
    piezas = (
        Viga.objects.using(BASE)
        .filter(estado=est.TERMINADO)
        .order_by("proyecto", "codigo_viga", "pieza_no")
    )
    for pieza in piezas:
        yield {
            "linea": SeguimientoDespacho.Linea.VIGAS,
            "referencia": pieza.internal_id,
            "codigo": pieza.codigo_viga,
            "detalle": f"{pieza.pieza_no}/{pieza.total_piezas} · {pieza.descripcion}",
            "cliente": pieza.proyecto,
            "peso_kg": float(pieza.peso_kg or 0),
            "cantidad": 1,
            "desde": pieza.ultimo_cambio,
            "compromiso": pieza.fecha_compromiso,
        }


def _de_herreria():
    ordenes = (
        HerrOrdenProduccion.objects.using(BASE)
        .filter(estado_etapa=est.TERMINADO)
        .exclude(estado__in=YA_SALIO)
        .select_related("cliente_herreria", "proyecto")
        .order_by("codigo")
    )
    for orden in ordenes:
        cliente = getattr(orden.cliente_herreria, "nombre", "") or getattr(
            orden.proyecto, "nombre", ""
        )
        yield {
            "linea": SeguimientoDespacho.Linea.HERRERIA,
            "referencia": orden.id,
            "codigo": orden.codigo,
            "detalle": orden.nombre or orden.descripcion,
            "cliente": cliente or "—",
            "peso_kg": float(orden.peso_kg or 0),
            "cantidad": int(orden.total_piezas or 0),
            "desde": orden.ultimo_cambio,
            "compromiso": orden.fecha_compromiso,
        }


def _de_corta():
    # Las de Corta que ya tienen envío registrado no se vuelven a ofrecer.
    enviadas = set(
        LogisticaEnvioCorta.objects.using(BASE).values_list("orden_id", flat=True)
    )
    ordenes = (
        LaserOrdenProduccion.objects.using(BASE)
        .filter(estado_etapa=est.TERMINADO)
        .exclude(id__in=enviadas)
        .select_related("corta_cliente_proyecto")
        .order_by("folio_externo", "codigo")
    )
    for orden in ordenes:
        yield {
            "linea": SeguimientoDespacho.Linea.CORTA,
            "referencia": orden.id,
            "codigo": orden.folio_externo or orden.codigo,
            "detalle": orden.descripcion or orden.nombre,
            "cliente": getattr(orden.corta_cliente_proyecto, "nombre", "") or "—",
            "peso_kg": float(orden.peso_kg or 0),
            "cantidad": int(orden.total_piezas or 0),
            "desde": orden.ultimo_cambio,
            "compromiso": orden.fecha_compromiso,
        }


def listos_para_salir():
    """Todo lo terminado que todavía no ha salido, de las tres líneas.

    Se calcula cada vez. Es más lento que leer una tabla de avisos y es lo que
    garantiza que nada se quede fuera por un camino no previsto.
    """
    atendidos = _seguimientos()
    filas = []
    for origen in (_de_estructuras, _de_herreria, _de_corta):
        for fila in origen():
            seguimiento = atendidos.get((fila["linea"], fila["referencia"]))
            fila["seguimiento"] = seguimiento
            fila["estado"] = (
                seguimiento.estado if seguimiento
                else SeguimientoDespacho.Estado.PENDIENTE
            )
            filas.append(fila)
    return filas


def _por_cliente(filas):
    """Agrupado por cliente, que es como se carga un camión.

    Una lista plana obliga a leerla entera para saber qué va junto. Agrupada,
    se ve de un vistazo que hay tres cosas para el mismo cliente y salen en el
    mismo viaje.
    """
    grupos = {}
    for fila in filas:
        grupo = grupos.setdefault(fila["cliente"], {
            "cliente": fila["cliente"],
            "filas": [],
            "peso_kg": 0.0,
            "piezas": 0,
            "pendientes": 0,
        })
        grupo["filas"].append(fila)
        grupo["peso_kg"] += fila["peso_kg"]
        grupo["piezas"] += fila["cantidad"]
        if fila["estado"] == SeguimientoDespacho.Estado.PENDIENTE:
            grupo["pendientes"] += 1
    return sorted(grupos.values(), key=lambda g: -g["peso_kg"])


@login_required
def bandeja(request):
    filas = listos_para_salir()
    pendientes = [f for f in filas if f["estado"] == SeguimientoDespacho.Estado.PENDIENTE]

    return render(request, "catalogos/despacho.html", {
        "grupos": _por_cliente(filas),
        "total": len(filas),
        "pendientes": len(pendientes),
        "peso_total": sum(f["peso_kg"] for f in filas),
        "estados": SeguimientoDespacho.Estado.choices,
    })


@login_required
@require_POST
def marcar(request):
    """Anota qué hizo Logística con un renglón de la bandeja."""
    linea = request.POST.get("linea") or ""
    estado = request.POST.get("estado") or ""

    if linea not in SeguimientoDespacho.Linea.values:
        messages.error(request, "Línea desconocida.")
        return redirect("catalogos:despacho")
    if estado not in SeguimientoDespacho.Estado.values:
        messages.error(request, "Estado desconocido.")
        return redirect("catalogos:despacho")

    try:
        referencia = int(request.POST.get("referencia"))
    except (TypeError, ValueError):
        messages.error(request, "Falta la referencia.")
        return redirect("catalogos:despacho")

    ahora = timezone.now()
    seguimiento, _ = SeguimientoDespacho.objects.using(BASE).update_or_create(
        linea=linea,
        referencia=referencia,
        defaults={
            "estado": estado,
            "notas": (request.POST.get("notas") or "")[:255],
            "actor": request.user.get_username(),
            "visto_en": ahora,
            # Se sella cuándo salió, no sólo que salió: sin la fecha no se
            # puede responder cuánto tardó el taller en entregar.
            "despachado_en": (
                ahora if estado == SeguimientoDespacho.Estado.DESPACHADO else None
            ),
        },
    )
    messages.success(
        request, f"Marcado como «{seguimiento.get_estado_display()}»."
    )
    return redirect("catalogos:despacho")


def cuantos_esperan_despacho():
    """Para el contador de la barra de navegación.

    Cuenta sólo lo pendiente: si contara todo, el número no bajaría nunca al
    trabajar y dejaría de significar algo.
    """
    atendidos = {
        (s.linea, s.referencia)
        for s in SeguimientoDespacho.objects.using(BASE).filter(
            ~Q(estado=SeguimientoDespacho.Estado.PENDIENTE)
        )
    }
    return sum(
        1 for f in listos_para_salir()
        if (f["linea"], f["referencia"]) not in atendidos
    )
