"""«Mi trabajo»: la pantalla del operador en el celular.

Hasta ahora, un soldador que quería apuntar que terminó una pieza tenía que
abrir la lista completa del taller —trescientas órdenes—, encontrar la suya,
rellenar una fecha, abrir un diálogo y guardar. Cinco a siete toques, en un
teléfono, con guantes, a pleno sol. En la práctica no se hacía en el momento:
se apuntaba en un papel y alguien lo capturaba por la tarde, que es
exactamente por lo que el sistema iba siempre por detrás de la realidad.

Esta pantalla enseña **lo que está pendiente en el área de esa persona**, y
el avance se registra con un toque.

Sobre por qué el área y no la asignación personal
-------------------------------------------------

La primera versión enseñaba sólo las piezas que alguien le había asignado a
esa persona una por una, desde el diálogo «Asignaciones por etapa». En un
taller eso no se sostiene: significa que un marco no se pinta hasta que un
supervisor entra a la PC y escribe quién lo va a pintar. El trabajo se para
esperando a que alguien lo reparta.

Así que se invierte. Hay un marco que pintar: **cualquiera del área de
pintura lo ve pendiente y lo toma**. Quien lo toma queda firmado
automáticamente —por eso cada quien necesita su propia cuenta— en el apunte
de trabajo, junto con la cuadrilla del día. El registro de quién hizo qué
sale de quién lo hizo, no de quién dijo por adelantado que lo iba a hacer.

La asignación nominal sigue existiendo para el caso en que de verdad haga
falta («esta pieza la hace Omar porque conoce el plano»), pero deja de ser
un requisito para que el trabajo aparezca.

Dos cosas que hacen falta para que funcione y que antes no existían:

- **Saber quién es quien entra.** No había ninguna relación entre la cuenta
  con la que se inicia sesión y la ficha del colaborador. Se resuelve con
  `Colaborador.usuario`, que se captura desde la pantalla de usuarios.
  Mientras no esté capturado se intenta adivinar por el nombre. Ya no es
  imprescindible para ver el trabajo —el área basta—, pero sí para que el
  apunte diga quién fue.

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


#: Cuántas piezas se enseñan como mucho. Es una pantalla de teléfono: pasar
#: de esto no es información, es desplazamiento. Lo que se corta se dice.
TOPE = 40


def _cola_de_mi_area(movibles, asignadas):
    """Lo pendiente en las etapas que esta persona puede mover.

    El filtro se hace en la base con todas las variantes de escritura de cada
    etapa —«Espera de armado» y «Espera Armado» conviven en los datos—, no
    trayendo la tabla entera para descartarla en Python.

    Lo asignado a esa persona sube arriba del todo. Sigue siendo su trabajo
    de forma explícita; lo que cambia es que ya no es lo *único* que ve.
    """
    from produccion.models import Viga

    if not movibles:
        return [], 0

    escrituras = []
    for etapa in movibles:
        escrituras.extend(estados.variantes(etapa))

    consulta = (
        Viga.objects.using(BASE)
        .filter(estado__in=escrituras)
        .order_by("prioridad", "fecha_compromiso", "codigo_viga")
    )
    total = consulta.count()
    piezas = list(consulta[: TOPE * 2])

    trabajos = []
    for pieza in piezas:
        etapa = estados.normalizar(pieza.estado)
        if etapa not in ETAPAS_DE_TRABAJO:
            # `variantes` puede traer una escritura que normaliza a una etapa
            # de espera. No es trabajo de nadie: es la orden esperando.
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
                "mia": pieza.internal_id in asignadas,
            }
        )

    # Lo asignado a esta persona, primero. `sort` de Python es estable, así
    # que dentro de cada bloque se respeta el orden por prioridad y fecha.
    trabajos.sort(key=lambda t: not t["mia"])
    return trabajos[:TOPE], max(0, total - len(trabajos[:TOPE]))


def _asignadas_a(colaborador):
    """Identificadores de las piezas asignadas nominalmente a esta persona."""
    if colaborador is None:
        return set()
    from catalogos.models import VigaAsignacion

    return set(
        VigaAsignacion.objects.using(BASE)
        .filter(colaborador=colaborador, vigente=True)
        .values_list("viga_internal_id", flat=True)
    )


@login_required
def mi_trabajo(request):
    from catalogos.models import MaquinaParoMotivo

    colaborador = colaborador_de(request.user)
    movibles = etapas_que_puede_mover(request.user)
    # Sin ficha también se ve la cola: el área la da el grupo de la cuenta,
    # no la ficha. Lo que falta sin ficha es la firma del apunte, y de eso
    # avisa la propia pantalla.
    trabajos, de_mas = _cola_de_mi_area(movibles, _asignadas_a(colaborador))

    return render(
        request,
        "produccion/movil.html",
        {
            "colaborador": colaborador,
            "trabajos": trabajos,
            "de_mas": de_mas,
            "puede_mover_algo": bool(movibles),
            "motivos_de_paro": list(
                MaquinaParoMotivo.objects.using(BASE).filter(activo=True).order_by("nombre")
            ),
        },
    )
