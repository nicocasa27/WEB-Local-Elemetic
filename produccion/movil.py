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
from core.servicios import especificaciones as servicio_especificaciones
from core.servicios import ruta as servicio_ruta
from core.servicios import trabajo as servicio_trabajo

BASE = "mes"

#: Las etapas que salen en la cola de un área.
#:
#: Incluye las de espera **a propósito**, y esto es el corazón del cambio.
#: Mientras la pantalla enseñaba sólo lo asignado, «Espera de corte» no era
#: trabajo de nadie: era la pieza esperando a que un supervisor la repartiera.
#: Ahora que la cola es del área, «Espera de corte» es exactamente lo que el
#: área tiene que hacer: hay un marco que pintar y está en «Espera de
#: pintura».
#:
#: Dejarlas fuera vaciaba la pantalla justo cuando había más trabajo. Con los
#: datos de hoy: doce piezas esperando corte, once esperando armado, y la
#: pantalla decía «no hay nada pendiente en tu área».
ETAPAS_DE_TRABAJO = {
    estados.ESPERA_CORTE,
    estados.CORTE,
    estados.ESPERA_ARMADO,
    estados.ARMADO,
    estados.ESPERA_SOLDADURA,
    estados.SOLDADURA,
    estados.ESPERA_PINTURA,
    estados.PINTURA,
}

#: Las etapas en las que alguien ya está trabajando. Se distinguen de las de
#: espera sólo para el texto del botón: «Empezar corte» no es lo mismo que
#: «Terminé corte», y en el piso esa palabra es toda la instrucción.
ETAPAS_EN_CURSO = {estados.CORTE, estados.ARMADO, estados.SOLDADURA, estados.PINTURA}


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


def etapas_que_puede_mover(usuario):
    """Las etapas que esta cuenta puede mover, y por tanto su cola.

    **No se decide aquí.** La regla la pone el servidor, en
    `produccion.views.ETAPAS_POR_GRUPO`, y aquí se consulta. Cuando estaban
    escritas dos veces, la pantalla ofrecía botones que el servidor rechazaba
    con un «Sin permiso» que en el piso no dice nada.

    Lo propio de esta pantalla es quedarse sólo con las etapas desde las que
    esta persona puede **completar** el paso, no las que simplemente puede
    tocar. Son cosas distintas y confundirlas ofrece botones que fallan:

    El servidor exige que la etapa de origen y la de destino estén las dos
    permitidas. Las etapas de espera están a caballo entre dos áreas a
    propósito —«Espera de armado» la pueden tocar corte y soldadura, porque es
    el punto de entrega— pero sólo soldadura puede pasarla a «Armado». Sin
    este filtro, a un cortador le salía un botón «Empezar armado» que el
    servidor contestaba con «Sin permiso».
    """
    from produccion.views import _etapas_permitidas

    if getattr(usuario, "is_superuser", False):
        return set(ETAPAS_DE_TRABAJO)
    grupos = set(usuario.groups.values_list("name", flat=True))
    if grupos & {"admin_general", "ingenieria_civil"}:
        return set(ETAPAS_DE_TRABAJO)

    permitidas = {estados.normalizar(etapa) for etapa in _etapas_permitidas(usuario)}
    utiles = set()
    for etapa in permitidas & ETAPAS_DE_TRABAJO:
        posicion = estados.posicion(etapa)
        if posicion is None or posicion + 1 >= len(estados.SECUENCIA):
            continue
        if estados.SECUENCIA[posicion + 1] in permitidas:
            utiles.add(etapa)
    return utiles


#: Cuántas piezas se enseñan como mucho. Es una pantalla de teléfono: pasar
#: de esto no es información, es desplazamiento. Lo que se corta se dice.
TOPE = 40


def _texto_del_boton(etapa, siguiente):
    """Lo que dice el botón. En el piso, esa palabra es la instrucción.

    Una pieza en espera se **toma**; una que ya está en curso se **termina**.
    Es la misma acción para el servidor —un cambio de etapa— pero no es la
    misma para quien la pulsa, y llamar «Terminé corte» a empezar a cortar es
    pedir que se registre una mentira.
    """
    if not siguiente:
        return ""
    if etapa in ETAPAS_EN_CURSO:
        return f"Terminé {etapa.lower()}"
    return f"Empezar {siguiente.lower()}"


# --------------------------------------------------------------- las líneas
#
# Estructuras metálicas, Herrería y Corta.mx. Hasta ahora esta pantalla sólo
# cubría la primera, así que la gente de Herrería y de Corta entraba y leía
# «tu cuenta no tiene un área de producción». Media planta sin pantalla de
# celular, que es justo la mitad que más órdenes mueve al día.
#
# Las tres son la misma máquina de estados con distinta tabla —es la
# duplicación de la que vive todo este sistema— así que aquí se recorren con
# un solo bloque de código en vez de copiarlo tres veces. Lo único que
# cambia por línea está en esta tabla.


class Linea:
    def __init__(self, clave, titulo, grupos, ruta_avance, ruta_control, legacy_modelo):
        self.clave = clave
        self.titulo = titulo
        self.grupos = set(grupos)
        self.ruta_avance = ruta_avance
        self.ruta_control = ruta_control
        #: Cómo se llama esta tabla en el núcleo, que es donde vive la ruta.
        self.legacy_modelo = legacy_modelo

    def la_ve(self, grupos_del_usuario, es_admin):
        return bool(es_admin or (self.grupos & grupos_del_usuario))


LINEAS = [
    Linea(
        "herreria",
        "Herrería",
        {"herreria", "herreria_supervision"},
        "catalogos:herreria_change_status_json",
        "catalogos:herreria_control",
        "HerrOrdenProduccion",
    ),
    Linea(
        "corta",
        "Corta.mx",
        {"corte_laser", "corte_laser_supervision"},
        "catalogos:corte_laser_change_status_json",
        "catalogos:corte_laser_control",
        "LaserOrdenProduccion",
    ),
]

#: Las etapas a las que el servidor deja pasar una orden grande. Una orden de
#: varias piezas no avanza por etapas después de soldadura: se lleva por
#: contadores y se cierra. Está copiado de `herreria_change_status_json`
#: a propósito —enseñar un botón que el servidor va a rechazar con un 409 es
#: peor que no enseñarlo— y por eso hay una prueba que compara las dos.
ETAPAS_QUE_ACEPTA_UNA_ORDEN_GRANDE = {
    estados.ESPERA_CORTE,
    estados.CORTE,
    estados.SOLDADURA,
}


def es_orden_grande(orden):
    """La misma regla que aplica el servidor: dos piezas o más.

    Se calcula, no se lee de la columna `es_op`. Las dos conviven en los
    datos y no siempre coinciden; la que decide si el avance se acepta es
    ésta.
    """
    return int(getattr(orden, "total_piezas", 0) or 0) >= 2


def _siguiente_de_una_orden(orden, etapa, legacy_modelo=""):
    """A qué etapa pasa, o cadena vacía si desde aquí ya no se avanza así.

    Una orden de varias piezas sigue su propia secuencia corta: de soldadura
    salta al cierre porque el avance se lleva por contadores. Ésa no se
    recorta, porque no hay etapas que recortar.

    Una orden de una sola pieza sí respeta su ruta: puede no llevar pintura,
    igual que una pieza de estructuras.
    """
    grande = es_orden_grande(orden)
    if grande:
        secuencia = estados.SECUENCIA_ORDEN_GRANDE
        posicion = estados.posicion(etapa, secuencia)
        if posicion is None or posicion + 1 >= len(secuencia):
            return ""
        siguiente = secuencia[posicion + 1]
        return siguiente if siguiente in ETAPAS_QUE_ACEPTA_UNA_ORDEN_GRANDE else ""

    siguiente = servicio_ruta.siguiente(legacy_modelo, orden.pk, etapa)
    if siguiente == estados.ENVIADO:
        # Enviar es de logística, no del piso.
        return ""
    return siguiente


def _cola_de_una_linea(linea, modelo, movibles):
    """Órdenes abiertas de una línea, en etapa de trabajo."""
    from django.urls import reverse

    escrituras = []
    for etapa in movibles:
        escrituras.extend(estados.variantes(etapa))

    consulta = (
        modelo.objects.using(BASE)
        .filter(estado="Abierta", estado_etapa__in=escrituras)
        .order_by("prioridad", "fecha_compromiso", "codigo")
    )
    total = consulta.count()

    trabajos = []
    for orden in consulta[: TOPE * 2]:
        etapa = estados.normalizar(orden.estado_etapa)
        if etapa not in ETAPAS_DE_TRABAJO:
            continue
        siguiente = _siguiente_de_una_orden(orden, etapa, linea.legacy_modelo)
        trabajos.append(
            {
                "id": orden.pk,
                "linea": linea.clave,
                "linea_titulo": linea.titulo,
                "codigo": orden.codigo,
                "detalle": f"{orden.total_piezas} pza{'s' if orden.total_piezas != 1 else ''} · {orden.proyecto or ''}".strip(" ·"),
                "descripcion": orden.descripcion or orden.nombre or "",
                "etapa": etapa,
                "clase_etapa": estados.clase(etapa),
                "en_curso": etapa in ETAPAS_EN_CURSO,
                "accion": _texto_del_boton(etapa, siguiente),
                "siguiente": siguiente,
                "puede_mover": bool(siguiente),
                "por_cantidades": es_orden_grande(orden) and not siguiente,
                "cuantas": 1,
                "url_avance": reverse(linea.ruta_avance, args=[orden.pk]),
                "url_control": reverse(linea.ruta_control),
                "peso_kg": orden.peso_kg,
                "prioridad": orden.prioridad,
                "fecha_compromiso": orden.fecha_compromiso,
                "mia": False,
            }
        )
    return trabajos, total


def _colas_de_las_otras_lineas(usuario):
    """Herrería y Corta.mx, según los grupos de la cuenta.

    Aquí no se reparte por etapa como en Estructuras. El permiso de estas dos
    líneas es de línea entera —`_can_herreria`, `_can_corte_laser`— y no mira
    la etapa, así que restringirla en la pantalla escondería trabajo que el
    servidor sí deja registrar.
    """
    from catalogos.models import HerrOrdenProduccion, LaserOrdenProduccion

    modelos = {"herreria": HerrOrdenProduccion, "corta": LaserOrdenProduccion}
    grupos = set(usuario.groups.values_list("name", flat=True))
    es_admin = bool(
        getattr(usuario, "is_superuser", False)
        or grupos & {"admin_general", "ingenieria_civil"}
    )

    trabajos = []
    total = 0
    for linea in LINEAS:
        if not linea.la_ve(grupos, es_admin):
            continue
        de_la_linea, cuantas = _cola_de_una_linea(
            linea, modelos[linea.clave], ETAPAS_DE_TRABAJO
        )
        trabajos.extend(de_la_linea)
        total += cuantas
    return trabajos, total


def puede_ver_alguna_linea(usuario):
    """Si la cuenta tiene área en alguna de las tres líneas.

    Es lo que decide entre enseñar «no hay nada pendiente» y «tu cuenta no
    tiene área». Son mensajes distintos y confundirlos manda a la persona a
    pedir un permiso que ya tiene, o al revés.
    """
    if etapas_que_puede_mover(usuario):
        return True
    grupos = set(usuario.groups.values_list("name", flat=True))
    es_admin = bool(
        getattr(usuario, "is_superuser", False)
        or grupos & {"admin_general", "ingenieria_civil"}
    )
    return any(linea.la_ve(grupos, es_admin) for linea in LINEAS)


def _cola_de_mi_area(movibles, asignadas):
    """Lo pendiente en las etapas que esta persona puede mover.

    El filtro se hace en la base con todas las variantes de escritura de cada
    etapa —«Espera de armado» y «Espera Armado» conviven en los datos—, no
    trayendo la tabla entera para descartarla en Python.

    Lo asignado a esa persona sube arriba del todo. Sigue siendo su trabajo
    de forma explícita; lo que cambia es que ya no es lo *único* que ve.
    """
    from django.urls import reverse

    from produccion.models import Viga

    if not movibles:
        return [], 0

    escrituras = []
    for etapa in movibles:
        escrituras.extend(estados.variantes(etapa))

    consulta = Viga.objects.using(BASE).filter(estado__in=escrituras)
    total = consulta.count()

    # Los grupos se eligen **en la base**, no recortando piezas y agrupando
    # después. Con un recorte de piezas, el último grupo se parte por la
    # mitad: la tarjeta diría «2 de 3» habiendo tres, y la tercera no se
    # podría avanzar desde ahí. Se piden los grupos más urgentes y luego sus
    # piezas, que son dos consultas y ningún grupo cortado.
    from django.db.models import Count, Min

    claves = list(
        consulta.values("codigo_viga", "proyecto", "estado")
        .annotate(
            cuantas=Count("internal_id"),
            urgencia=Min("prioridad"),
            compromiso=Min("fecha_compromiso"),
        )
        .order_by("urgencia", "compromiso", "codigo_viga")[:TOPE]
    )
    if not claves:
        return [], total

    piezas = list(
        consulta.filter(
            codigo_viga__in={c["codigo_viga"] for c in claves},
            proyecto__in={c["proyecto"] for c in claves},
            estado__in={c["estado"] for c in claves},
        ).order_by("prioridad", "fecha_compromiso", "codigo_viga", "pieza_no")
    )
    de_los_grupos = {(c["codigo_viga"], c["proyecto"], c["estado"]) for c in claves}
    piezas = [
        p for p in piezas if (p.codigo_viga, p.proyecto, p.estado) in de_los_grupos
    ]

    # Las piezas iguales van juntas.
    #
    # Una orden de cincuenta vigas son cincuenta renglones, uno por pieza.
    # Sin agrupar, un soldador que hizo cuarenta tenía que dar cuarenta toques
    # con guantes en un teléfono, y en la práctica se apuntaba en papel y
    # alguien lo capturaba por la tarde. Agrupadas es una tarjeta y un número.
    #
    # Se agrupa por código, obra y etapa: dos piezas del mismo código que van
    # por distinta etapa son dos trabajos distintos y no se pueden sumar.
    grupos = {}
    for pieza in piezas:
        etapa = estados.normalizar(pieza.estado)
        if etapa not in ETAPAS_DE_TRABAJO:
            # Terminada, enviada o en cierre pendiente: ya no es de piso.
            continue
        clave = (pieza.codigo_viga, pieza.proyecto, etapa)
        grupo = grupos.get(clave)
        if grupo is None:
            grupos[clave] = grupo = {"piezas": [], "etapa": etapa}
        grupo["piezas"].append(pieza)

    trabajos = []
    for (codigo, proyecto, etapa), grupo in grupos.items():
        integrantes = grupo["piezas"]
        primera = integrantes[0]
        cuantas = len(integrantes)
        # La siguiente etapa sale de la ruta de **esta** pieza, no de la
        # secuencia general. En una que no lleva pintura, «terminé soldadura»
        # tiene que llevar a Terminado y no a una cola de pintura por la que
        # no va a pasar nunca.
        siguiente = servicio_ruta.siguiente("Viga", primera.internal_id, etapa)
        if siguiente == estados.ENVIADO:
            # Enviar a obra es de logística, no del piso.
            siguiente = ""
        detalle = (
            f"{cuantas} de {primera.total_piezas} · {proyecto}"
            if cuantas > 1
            else f"{primera.pieza_no}/{primera.total_piezas} · {proyecto}"
        )
        trabajos.append(
            {
                "id": primera.internal_id,
                "linea": "estructuras",
                "linea_titulo": "Estructuras",
                "codigo": codigo,
                #: Va al formulario de avance en lote junto con el código: dos
                #: pedidos distintos pueden usar el mismo código en obras
                #: distintas, y el servidor tiene que saber cuál es cuál.
                "proyecto": proyecto,
                "detalle": detalle,
                "descripcion": primera.descripcion,
                "etapa": etapa,
                "clase_etapa": estados.clase(etapa),
                "en_curso": etapa in ETAPAS_EN_CURSO,
                "accion": _texto_del_boton(etapa, siguiente),
                "siguiente": siguiente,
                "puede_mover": bool(siguiente),
                "por_cantidades": False,
                #: Cuántas piezas iguales hay en esta etapa. Con más de una, la
                #: tarjeta pide el número en vez de avanzarlas todas a ciegas:
                #: casi nunca se terminan las cincuenta de un tirón.
                "cuantas": cuantas,
                "url_avance": (
                    reverse("produccion:viga_avanzar_grupo")
                    if cuantas > 1
                    else reverse(
                        "produccion:viga_change_status_json", args=[primera.internal_id]
                    )
                ),
                "url_control": reverse("produccion:viga_list"),
                "peso_kg": primera.peso_kg,
                "prioridad": primera.prioridad,
                "fecha_compromiso": primera.fecha_compromiso,
                "mia": any(p.internal_id in asignadas for p in integrantes),
            }
        )

    return trabajos, total


#: De qué tabla heredada sale cada línea de esta pantalla. Es la clave con la
#: que se guardan las especificaciones.
LEGACY_DE = {
    "estructuras": "Viga",
    "herreria": "HerrOrdenProduccion",
    "corta": "LaserOrdenProduccion",
}


def _poner_las_especificaciones(trabajos):
    """Cuelga de cada tarjeta el detalle de cómo se hace su pieza.

    «V-118 · 3/50 · Obra Norte» dice cuál es la pieza, no cómo es. Lo que
    hace falta en la mano es «vigas de 70 cm con un corte a los 30 cm a
    noventa grados», y hasta ahora eso viajaba en un plano impreso o de boca
    en boca.

    Se piden en bloque, una consulta por línea y no una por tarjeta. Con
    cuarenta tarjetas, lo segundo son cuarenta consultas más para enseñar un
    párrafo, que es el defecto que este sistema tiene repartido por todas
    partes.
    """
    por_linea = {}
    for trabajo in trabajos:
        por_linea.setdefault(trabajo["linea"], []).append(trabajo["id"])

    textos = {}
    for linea, identificadores in por_linea.items():
        etiqueta = LEGACY_DE.get(linea)
        if not etiqueta:
            continue
        for identificador, texto in servicio_especificaciones.de_muchas(
            etiqueta, identificadores
        ).items():
            textos[(linea, identificador)] = texto

    for trabajo in trabajos:
        trabajo["especificaciones"] = textos.get((trabajo["linea"], trabajo["id"]), "")
    return trabajos


def _poner_los_equipos(trabajos):
    """Cuelga de cada tarjeta los equipos entre los que puede elegir.

    Sólo donde hace falta: hoy, las etapas de corte. El servidor ya exigía
    decir en qué equipo se trabaja —sin eso la producción de los seis se
    queda en un montón y no se sabe cuál va saturado— pero la pantalla del
    piso no ofrecía ninguno, así que el cortador recibía un «elige en qué
    equipo» sin nada que elegir.

    **Lo elige él, no la oficina.** La asignación de escritorio se queda vieja
    en cuanto la máquina está ocupada por otro o el ayudante se pasa a la de
    al lado, y entonces el apunte dice que la pieza se cortó donde no se
    cortó. Quien está delante sabe cuál está libre.

    Se consultan una vez por etapa y no una por tarjeta: con quince piezas
    esperando corte, lo segundo son quince consultas para pintar la misma
    lista.
    """
    por_etapa = {}
    for trabajo in trabajos:
        siguiente = trabajo.get("siguiente") or ""
        # Sólo en Estructuras: es la única línea cuyo servidor exige el
        # equipo. Poner el selector en las otras dos ofrecería un campo
        # obligatorio que nadie va a leer del otro lado.
        exige = trabajo.get("linea") == "estructuras" and servicio_trabajo.exige_maquina(
            siguiente
        )
        trabajo["exige_equipo"] = exige
        if not exige:
            trabajo["equipos"] = []
            continue
        if siguiente not in por_etapa:
            por_etapa[siguiente] = servicio_trabajo.maquinas_disponibles(siguiente)
        trabajo["equipos"] = por_etapa[siguiente]
    return trabajos


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
    trabajos, total = _cola_de_mi_area(movibles, _asignadas_a(colaborador))
    otras, total_otras = _colas_de_las_otras_lineas(request.user)
    trabajos.extend(otras)
    total += total_otras

    # Lo asignado a esta persona, primero; después lo urgente. `sort` de
    # Python es estable, así que el orden por prioridad y fecha que trae cada
    # cola se respeta dentro de cada bloque.
    trabajos.sort(key=lambda t: (not t["mia"], t["prioridad"], t["fecha_compromiso"]))
    visibles = _poner_los_equipos(_poner_las_especificaciones(trabajos[:TOPE]))
    # Se cuentan **piezas**, no tarjetas: una tarjeta puede llevar cincuenta.
    # Decir «hay 3 piezas más» cuando en realidad hay ciento cincuenta sería
    # peor que no decir nada.
    piezas_visibles = sum(int(t.get("cuantas") or 1) for t in visibles)

    return render(
        request,
        "produccion/movil.html",
        {
            "colaborador": colaborador,
            "trabajos": visibles,
            "de_mas": max(0, total - piezas_visibles),
            "varias_lineas": len({t["linea"] for t in visibles}) > 1,
            "puede_mover_algo": puede_ver_alguna_linea(request.user),
            "motivos_de_paro": list(
                MaquinaParoMotivo.objects.using(BASE).filter(activo=True).order_by("nombre")
            ),
        },
    )
