"""«Mi trabajo»: la pantalla del operador en el celular.

Hasta ahora, un soldador que quería apuntar que terminó una pieza tenía que
abrir la lista completa del taller —trescientas órdenes—, encontrar la suya,
rellenar una fecha, abrir un diálogo y guardar. Cinco a siete toques, en un
teléfono, con guantes, a pleno sol. En la práctica no se hacía en el momento:
se apuntaba en un papel y alguien lo capturaba por la tarde, que es
exactamente por lo que el sistema iba siempre por detrás de la realidad.

Esta pantalla enseña **sólo lo que esa persona tiene asignado y sigue
abierto**, y el avance se registra con un toque.

Dos cosas que hacen falta para que funcione y que antes no existían:

- **Saber quién es quien entra.** No había ninguna relación entre la cuenta
  con la que se inicia sesión y la ficha del colaborador al que se asigna el
  trabajo. Se resuelve con `Colaborador.usuario`, que se captura desde el
  administrador. Mientras no esté capturado se intenta adivinar por el
  nombre, y si no se acierta la pantalla lo dice en lugar de salir vacía.

- **La fecha de operación.** Desaparece del formulario: se usa la de hoy. Era
  un campo obligatorio que el operador no tiene por qué pensar, y era la
  causa del defecto de que la lista se comportara distinto en el celular y en
  la PC.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from core import estados

BASE = "mes"

#: Etapas en las que una persona está trabajando de verdad. Las de espera no
#: son trabajo de nadie: son la orden esperando a que alguien la tome.
ETAPAS_DE_TRABAJO = {estados.CORTE, estados.ARMADO, estados.SOLDADURA, estados.PINTURA}


def colaborador_de(usuario):
    """La ficha de colaborador de quien ha iniciado sesión, o `None`.

    Primero por la cuenta enlazada, que es el camino bueno. Si nadie la ha
    capturado todavía, se prueba por el nombre: no es de fiar para nada
    importante, pero aquí sólo decide qué órdenes se enseñan, y acertar el
    primer día sin configurar nada vale más que la exactitud.
    """
    from catalogos.models import Colaborador

    nombre_de_cuenta = (getattr(usuario, "username", "") or "").strip()
    if not nombre_de_cuenta:
        return None

    activos = Colaborador.objects.using(BASE).filter(activo=True)

    enlazado = activos.filter(usuario__iexact=nombre_de_cuenta).first()
    if enlazado:
        return enlazado

    completo = (usuario.get_full_name() or "").strip()
    por_nombre = Q(nombre__iexact=nombre_de_cuenta)
    if completo:
        por_nombre |= Q(nombre__iexact=completo)
    return activos.filter(por_nombre).first()


#: Qué etapas puede mover cada grupo. Es la misma regla que aplica el
#: servidor en `viga_change_status_json`; aquí se consulta para no enseñar un
#: botón que va a ser rechazado. Un botón que falla sin explicar por qué, en
#: el piso, hace que la gente deje de usar la pantalla.
ETAPAS_POR_GRUPO = {
    "corte": {estados.CORTE},
    "soldadura": {estados.ARMADO, estados.SOLDADURA, estados.PINTURA},
}


def etapas_que_puede_mover(usuario):
    if getattr(usuario, "is_superuser", False):
        return set(ETAPAS_DE_TRABAJO)
    grupos = set(usuario.groups.values_list("name", flat=True))
    if grupos & {"admin_general", "ingenieria_civil"}:
        return set(ETAPAS_DE_TRABAJO)
    permitidas = set()
    for grupo, etapas in ETAPAS_POR_GRUPO.items():
        if grupo in grupos:
            permitidas |= etapas
    return permitidas


def _piezas_asignadas(colaborador, movibles):
    """Piezas de Estructuras metálicas asignadas y todavía en producción."""
    from catalogos.models import VigaAsignacion
    from produccion.models import Viga

    identificadores = list(
        VigaAsignacion.objects.using(BASE)
        .filter(colaborador=colaborador, vigente=True)
        .values_list("viga_internal_id", flat=True)
        .distinct()
    )
    if not identificadores:
        return []

    piezas = list(
        Viga.objects.using(BASE)
        .filter(internal_id__in=identificadores)
        .order_by("prioridad", "fecha_compromiso", "codigo_viga")
    )

    trabajos = []
    for pieza in piezas:
        etapa = estados.normalizar(pieza.estado)
        if etapa not in ETAPAS_DE_TRABAJO:
            # Terminada, enviada o esperando a otra área: no es trabajo de
            # esta persona ahora mismo, y enseñarla sólo añade ruido.
            continue
        posicion = estados.posicion(etapa)
        siguiente = (
            estados.SECUENCIA[posicion + 1]
            if posicion is not None and posicion + 1 < len(estados.SECUENCIA)
            else ""
        )
        trabajos.append(
            {
                "id": pieza.internal_id,
                "codigo": pieza.codigo_viga,
                "detalle": f"{pieza.pieza_no}/{pieza.total_piezas} · {pieza.proyecto}",
                "descripcion": pieza.descripcion,
                "etapa": etapa,
                "clase_etapa": estados.clase(etapa),
                "siguiente": siguiente if etapa in movibles else "",
                "puede_mover": etapa in movibles,
                "peso_kg": pieza.peso_kg,
                "prioridad": pieza.prioridad,
                "fecha_compromiso": pieza.fecha_compromiso,
            }
        )
    return trabajos


@login_required
def mi_trabajo(request):
    from catalogos.models import MaquinaParoMotivo

    colaborador = colaborador_de(request.user)
    movibles = etapas_que_puede_mover(request.user)
    trabajos = _piezas_asignadas(colaborador, movibles) if colaborador else []

    return render(
        request,
        "produccion/movil.html",
        {
            "colaborador": colaborador,
            "trabajos": trabajos,
            "puede_mover_algo": bool(movibles),
            "motivos_de_paro": list(
                MaquinaParoMotivo.objects.using(BASE).filter(activo=True).order_by("nombre")
            ),
        },
    )
