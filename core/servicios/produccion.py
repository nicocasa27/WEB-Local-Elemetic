"""Las reglas de producción, escritas una sola vez.

Este módulo es el motivo de toda la fase. Hoy las mismas cuatro operaciones
—dar de alta, mover de etapa, registrar avance, cerrar y revertir— están
escritas cuatro veces dentro de vistas de doscientas a mil cuatrocientas
líneas, y ya divergieron. Aquí están una vez, sin `request`, sin HTML y sin
saber por qué línea de negocio les están llamando.

Lo que cambia respecto al comportamiento heredado, y por qué:

**El avance se pide en incrementos, no en totales.** Antes el navegador
mandaba «terminadas = 50» y el servidor restaba lo que había. Dos pestañas
abiertas mandaban las dos «50» y el almacén recibía el doble. Aquí se manda
«+5», y dos «+5» son diez, que es la respuesta correcta sin necesidad de
bloquear nada.

**Las reglas que vivían en el navegador viven aquí.** No avanzar con la
máquina parada, no pasarse del objetivo y justificar los retrocesos eran
comprobaciones de JavaScript: quien tuviera la dirección se las saltaba.

**Existe la invariante que no existía.** El sistema heredado admite sin
protestar «soldadas 0, pintadas 0, terminadas 50». Aquí no.

**Revertir un cierre deshace lo que el cierre hizo.** Antes no: el ingreso a
almacén y el acuse de entrega se quedaban. Era un fallo que costaba dinero.

Nada de esto se aplica a las tablas heredadas todavía. Mientras la línea esté
en escritura doble, la verdad sigue estando en ellas y esto se escribe en
paralelo para poder compararlo. Ver `core/banderas.py`.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.excepciones import (
    CantidadInvalida,
    ConflictoDeConcurrencia,
    MaquinaNoDisponible,
    MotivoRequerido,
    OperacionNoPermitida,
    OrdenBloqueada,
    TransicionInvalida,
)
from nucleo.models import (
    Asignacion,
    Etapa,
    EventoMaquina,
    EventoProduccion,
    MotivoEvento,
    OrdenProduccion,
    TransicionPermitida,
)
from core.bases import BASE  # noqa: F401

logger = logging.getLogger("mes.nucleo")


#: Orden en que se comprueban los contadores. Cada uno no puede pasar del
#: anterior: no se termina lo que no se pintó, ni se pinta lo que no se soldó.
CASCADA = [
    EventoProduccion.Contador.PRODUCIDA,
    EventoProduccion.Contador.PINTADA,
    EventoProduccion.Contador.TERMINADA,
]


def nombre_de(actor):
    """El nombre del actor, venga como venga.

    Se acepta un `User` o una cadena porque durante la convivencia hay
    llamadas desde vistas, desde comandos y desde tareas programadas, y no
    todas tienen un usuario detrás. Cuando las dos bases estén unificadas esto
    pasa a ser una clave foránea de verdad.
    """
    if actor is None:
        return "system"
    return getattr(actor, "username", None) or str(actor)


def _grupos_de(actor):
    if actor is None or not hasattr(actor, "groups"):
        return set()
    if getattr(actor, "is_superuser", False):
        return {"*"}
    return set(actor.groups.values_list("name", flat=True))


# ============================================================ consultas

def etapas_disponibles(orden, actor=None):
    """A qué etapas puede moverse esta orden, y quién puede hacerlo.

    Sirve para pintar los botones: si una transición no está aquí, el botón no
    se dibuja. Y como la misma tabla se comprueba al ejecutar, dibujar el
    botón y permitir la acción dejan de poder contradecirse, que es lo que
    pasa hoy.
    """
    grupos = _grupos_de(actor)
    transiciones = (
        TransicionPermitida.objects.using(BASE)
        .filter(linea=orden.linea, desde=orden.etapa_actual)
        .select_related("hasta")
        .order_by("hasta__orden")
    )
    permitidas = []
    for transicion in transiciones:
        if transicion.requiere_grupo and "*" not in grupos:
            if transicion.requiere_grupo not in grupos:
                continue
        permitidas.append(transicion)
    return permitidas


def recalcular_contadores(orden):
    """Reconstruye los contadores desde el historial y los guarda.

    Es lo que convierte los contadores en una caché de verdad: si alguna vez
    se separan del historial, esto los devuelve a su sitio y el historial
    gana. Sin una función así, «el registro es la fuente de verdad» es sólo
    una frase.
    """
    suma = {contador: 0 for contador in CASCADA}
    eventos = (
        EventoProduccion.objects.using(BASE)
        .filter(orden=orden)
        .exclude(contador="")
        .values_list("contador", "delta_cantidad")
    )
    for contador, delta in eventos:
        if contador in suma:
            suma[contador] += delta

    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        cantidad_producida=max(suma[EventoProduccion.Contador.PRODUCIDA], 0),
        cantidad_pintada=max(suma[EventoProduccion.Contador.PINTADA], 0),
        cantidad_terminada=max(suma[EventoProduccion.Contador.TERMINADA], 0),
    )
    orden.refresh_from_db(using=BASE)
    return suma


# ============================================================ comprobaciones

def _bloquear(orden):
    """Recupera la orden con la fila bloqueada, para leerla y escribirla.

    `of=("self",)` bloquea únicamente la fila de la orden. Sin eso, PostgreSQL
    rechaza la consulta —no admite `FOR UPDATE` sobre el lado nulable de un
    `LEFT JOIN`, y la etapa puede ser nula—, y de paso bloquear la etapa
    dejaría a todas las órdenes de la misma etapa esperando por nada.
    """
    return (
        OrdenProduccion.objects.using(BASE)
        .select_for_update(of=("self",))
        .select_related("linea", "etapa_actual")
        .get(pk=orden.pk)
    )


def _comprobar_version(orden, version):
    """Bloqueo optimista.

    Quien manda una versión distinta de la que hay está trabajando sobre una
    pantalla vieja. Antes eso se resolvía pisando lo del otro sin avisar.
    """
    if version is None:
        return
    if int(version) != int(orden.version):
        raise ConflictoDeConcurrencia(
            detalles={"version_enviada": int(version), "version_actual": int(orden.version)}
        )


def _comprobar_abierta(orden):
    if orden.estado == OrdenProduccion.Estado.CANCELADA:
        raise OrdenBloqueada("La orden está cancelada.")
    if orden.cierre_bloqueado_en is not None:
        raise OrdenBloqueada()


def _maquinas_paradas(orden):
    """Máquinas asignadas a la orden que tienen un paro o una falla abiertos.

    Se mira en las dos partes a propósito: en el núcleo y en las tablas
    heredadas. Mientras la línea no esté cortada, los paros se siguen
    registrando en `MaquinaParo` y `MaquinaFalla`, y una regla de seguridad
    que sólo mira la mitad de los datos no es una regla de seguridad.
    """
    from catalogos.models import MaquinaFalla, MaquinaParo

    identificadores = list(
        Asignacion.objects.using(BASE)
        .filter(orden=orden, vigente=True, maquina__isnull=False)
        .values_list("maquina_id", flat=True)
    )
    if not identificadores:
        return []

    paradas = set(
        EventoMaquina.objects.using(BASE)
        .filter(maquina_id__in=identificadores, fin__isnull=True)
        .values_list("maquina_id", flat=True)
    )
    for modelo in (MaquinaParo, MaquinaFalla):
        paradas |= set(
            modelo.objects.using(BASE)
            .filter(maquina_id__in=identificadores, fin__isnull=True)
            .values_list("maquina_id", flat=True)
        )
    return sorted(paradas)


def _transicion(orden, destino):
    transicion = (
        TransicionPermitida.objects.using(BASE)
        .filter(linea=orden.linea, desde=orden.etapa_actual, hasta=destino)
        .first()
    )
    if transicion is None:
        origen = orden.etapa_actual.nombre if orden.etapa_actual_id else "(sin etapa)"
        raise TransicionInvalida(
            f"No se puede pasar de «{origen}» a «{destino.nombre}» en {orden.linea.nombre}.",
            desde=origen,
            hasta=destino.nombre,
        )
    return transicion


def _evento_repetido(clave_idempotencia):
    """El mismo envío dos veces no debe hacer el trabajo dos veces.

    El celular del taller reenvía cuando la red se cae a media petición. Sin
    esto, cada reintento sumaría otra vez.
    """
    if not clave_idempotencia:
        return None
    return (
        EventoProduccion.objects.using(BASE)
        .filter(clave_idempotencia=clave_idempotencia)
        .first()
    )


# ============================================================ operaciones

@transaction.atomic(using=BASE)
def crear_orden(
    *,
    linea,
    actor,
    codigo="",
    nombre="",
    total_piezas=1,
    cantidad_objetivo=None,
    peso_kg_unitario=0,
    cliente=None,
    obra=None,
    pieza=None,
    fecha_compromiso=None,
    prioridad=3,
    descripcion="",
    observaciones="",
    atributos=None,
    clave_idempotencia=None,
):
    """Da de alta una orden con folio de secuencia y su evento de creación."""
    from core import folios

    repetido = _evento_repetido(clave_idempotencia)
    if repetido is not None:
        return repetido.orden

    inicial = (
        TransicionPermitida.objects.using(BASE)
        .filter(linea=linea, desde__isnull=True)
        .select_related("hasta")
        .first()
    )
    if inicial is None:
        raise TransicionInvalida(
            f"{linea.nombre} no tiene etapa inicial configurada. Ejecutar `sembrar_nucleo`."
        )

    ahora = timezone.now()
    total = max(int(total_piezas or 1), 1)
    orden = OrdenProduccion.objects.using(BASE).create(
        linea=linea,
        folio=folios.siguiente(linea),
        codigo=codigo,
        nombre=nombre,
        cliente=cliente,
        obra=obra,
        pieza=pieza,
        total_piezas=total,
        cantidad_objetivo=max(int(cantidad_objetivo or total), 1),
        peso_kg_unitario=peso_kg_unitario,
        fecha_compromiso=fecha_compromiso,
        prioridad=int(prioridad or 3),
        descripcion=descripcion,
        observaciones=observaciones,
        etapa_actual=inicial.hasta,
        atributos=atributos or {},
        creado_por=nombre_de(actor),
        creado_en=ahora,
        ultimo_cambio=ahora,
    )
    EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.CREACION,
        etapa=inicial.hasta,
        actor_username=nombre_de(actor),
        ocurrido_en=ahora,
        fecha_operacion=ahora.date(),
        clave_idempotencia=clave_idempotencia,
    )
    logger.info("orden creada %s en %s por %s", orden.folio, linea.codigo, nombre_de(actor))
    return orden


@transaction.atomic(using=BASE)
def cambiar_etapa(
    orden,
    *,
    destino,
    actor,
    motivo=None,
    comentario="",
    fecha_operacion=None,
    version=None,
    clave_idempotencia=None,
):
    """Mueve la orden de etapa comprobando que se pueda y que esté justificado."""
    repetido = _evento_repetido(clave_idempotencia)
    if repetido is not None:
        return repetido

    ahora = timezone.now()
    orden = _bloquear(orden)
    _comprobar_version(orden, version)
    _comprobar_abierta(orden)

    if isinstance(destino, str):
        destino = Etapa.objects.using(BASE).get(linea=orden.linea, codigo=destino)

    transicion = _transicion(orden, destino)

    if transicion.requiere_grupo:
        grupos = _grupos_de(actor)
        if "*" not in grupos and transicion.requiere_grupo not in grupos:
            raise OperacionNoPermitida(
                f"Este cambio lo tiene que hacer alguien de «{transicion.requiere_grupo}».",
                grupo=transicion.requiere_grupo,
            )

    if transicion.requiere_motivo and motivo is None:
        raise MotivoRequerido()

    if transicion.bloquea_si_maquina_en_paro:
        paradas = _maquinas_paradas(orden)
        if paradas:
            raise MaquinaNoDisponible(maquinas=paradas)

    anterior = orden.etapa_actual
    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.CAMBIO_ETAPA,
        etapa=destino,
        etapa_anterior=anterior,
        motivo=motivo,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
        fecha_operacion=fecha_operacion or ahora.date(),
        ocurrido_en=ahora,
        clave_idempotencia=clave_idempotencia,
    )
    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        etapa_actual=destino, ultimo_cambio=ahora, version=orden.version + 1
    )
    logger.info(
        "%s: %s → %s por %s",
        orden.folio,
        anterior.codigo if anterior else "(alta)",
        destino.codigo,
        nombre_de(actor),
    )
    return evento


@transaction.atomic(using=BASE)
def registrar_avance(
    orden,
    *,
    contador,
    delta,
    actor,
    fecha_operacion=None,
    comentario="",
    version=None,
    clave_idempotencia=None,
):
    """Suma o resta piezas a un contador. **Se pide la diferencia, no el total.**

    Ésta es la firma que arregla la duplicación de stock, y por eso no admite
    un valor absoluto ni aunque resulte cómodo: con un total, dos peticiones
    idénticas son ambiguas —¿son la misma dos veces o dos avances iguales?—
    y el sistema heredado resolvía esa ambigüedad de la forma equivocada.
    """
    repetido = _evento_repetido(clave_idempotencia)
    if repetido is not None:
        return repetido

    delta = int(delta or 0)
    if delta == 0:
        raise CantidadInvalida("Hay que indicar cuántas piezas se avanzan.")
    if contador not in CASCADA:
        raise CantidadInvalida(f"Contador desconocido: {contador!r}.")

    ahora = timezone.now()
    orden = _bloquear(orden)
    _comprobar_version(orden, version)
    _comprobar_abierta(orden)

    valores = {
        EventoProduccion.Contador.PRODUCIDA: orden.cantidad_producida,
        EventoProduccion.Contador.PINTADA: orden.cantidad_pintada,
        EventoProduccion.Contador.TERMINADA: orden.cantidad_terminada,
    }
    valores[contador] += delta
    _comprobar_cascada(orden, valores)

    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.AVANCE,
        etapa=orden.etapa_actual,
        contador=contador,
        delta_cantidad=delta,
        cantidad_resultante=valores[contador],
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
        fecha_operacion=fecha_operacion or ahora.date(),
        ocurrido_en=ahora,
        clave_idempotencia=clave_idempotencia,
    )
    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        cantidad_producida=valores[EventoProduccion.Contador.PRODUCIDA],
        cantidad_pintada=valores[EventoProduccion.Contador.PINTADA],
        cantidad_terminada=valores[EventoProduccion.Contador.TERMINADA],
        ultimo_cambio=ahora,
        version=orden.version + 1,
    )
    orden.refresh_from_db(using=BASE)

    if valores[EventoProduccion.Contador.TERMINADA] >= orden.cantidad_objetivo:
        _abrir_ventana_de_cierre(orden, actor, ahora)

    return evento


def _comprobar_cascada(orden, valores):
    """Ni negativos, ni por encima del objetivo, ni fuera de orden.

    Las tres cosas se pueden hacer hoy. La tercera es la más silenciosa: una
    orden con cincuenta terminadas y cero soldadas no da ningún error, sale en
    los informes y nadie sabe de dónde salieron esas piezas.
    """
    anterior = None
    for contador in CASCADA:
        valor = valores[contador]
        if valor < 0:
            raise CantidadInvalida(
                f"No se puede dejar el contador de {contador}s en {valor}.",
                contador=contador,
            )
        if valor > orden.cantidad_objetivo:
            raise CantidadInvalida(
                f"Se pasaría del objetivo: {valor} {contador}s sobre "
                f"{orden.cantidad_objetivo}.",
                contador=contador,
                objetivo=orden.cantidad_objetivo,
            )
        if anterior is not None and valor > valores[anterior]:
            raise CantidadInvalida(
                f"No puede haber más piezas {contador}s ({valor}) que "
                f"{anterior}s ({valores[anterior]}).",
                contador=contador,
                depende_de=anterior,
            )
        anterior = contador


def _abrir_ventana_de_cierre(orden, actor, ahora):
    """La orden llegó a su objetivo: empieza el plazo para deshacerlo.

    No se cierra en firme de inmediato para poder corregir un error de dedo.
    Quien la consolida pasado el plazo es la tarea programada, no la próxima
    persona que abra una pantalla.
    """
    etapa = (
        Etapa.objects.using(BASE)
        .filter(linea=orden.linea, es_cierre_pendiente=True)
        .first()
    )
    if etapa is None or orden.etapa_actual_id == etapa.pk:
        return None

    hasta = ahora + timedelta(minutes=int(orden.linea.ventana_cierre_minutos or 10))
    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.CIERRE_PENDIENTE,
        etapa=etapa,
        etapa_anterior=orden.etapa_actual,
        actor_username=nombre_de(actor),
        ocurrido_en=ahora,
        fecha_operacion=ahora.date(),
        comentario="objetivo alcanzado",
    )
    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        cierre_etapa_previa=orden.etapa_actual,
        etapa_actual=etapa,
        cierre_pendiente_en=ahora,
        cierre_pendiente_hasta=hasta,
        cierre_pendiente_por=nombre_de(actor),
        ultimo_cambio=ahora,
        version=orden.version + 1,
    )
    return evento


@transaction.atomic(using=BASE)
def consolidar_cierre(orden, ahora=None):
    """Pasado el plazo, el cierre se vuelve firme."""
    ahora = ahora or timezone.now()
    orden = _bloquear(orden)
    if orden.cierre_pendiente_hasta is None or orden.cierre_pendiente_hasta > ahora:
        return None

    # La etapa a la que se cierra es la siguiente al cierre pendiente en la
    # secuencia de la línea: «Terminado». Se busca por posición y no por
    # nombre porque el nombre es configurable y la posición no.
    terminal = None
    if orden.etapa_actual_id and orden.etapa_actual.es_cierre_pendiente:
        terminal = (
            Etapa.objects.using(BASE)
            .filter(linea=orden.linea, orden__gt=orden.etapa_actual.orden)
            .order_by("orden")
            .first()
        )

    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.CIERRE_FIRME,
        etapa=terminal or orden.etapa_actual,
        etapa_anterior=orden.etapa_actual,
        actor_username="system",
        ocurrido_en=ahora,
        fecha_operacion=ahora.date(),
        comentario="cierre automático al vencer el plazo",
    )
    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        etapa_actual=terminal or orden.etapa_actual,
        estado=OrdenProduccion.Estado.CERRADA,
        cierre_bloqueado_en=ahora,
        cierre_pendiente_hasta=None,
        ultimo_cambio=ahora,
        version=orden.version + 1,
    )
    return evento


@transaction.atomic(using=BASE)
def revertir_cierre(orden, *, actor, motivo, comentario=""):
    """Deshace un cierre **y lo que el cierre provocó**.

    En el sistema heredado, revertir devolvía la orden a su etapa anterior y
    ahí acababa: el ingreso a almacén se quedaba, y el acuse de entrega
    emitido también. La orden volvía a producción y las piezas seguían
    contadas como entregadas. Era un fallo que costaba dinero, y no se veía
    porque las dos mitades estaban en pantallas distintas.

    Aquí la reversión escribe los eventos contrarios de todo lo que el cierre
    escribió. No se borra nada: un documento firmado se anula, y quedan las
    dos cosas registradas.
    """
    if motivo is None:
        raise MotivoRequerido("Revertir un cierre exige indicar el motivo.")

    ahora = timezone.now()
    orden = _bloquear(orden)

    if orden.cierre_pendiente_en is None and orden.cierre_bloqueado_en is None:
        raise TransicionInvalida("Esta orden no tiene ningún cierre que revertir.")
    if orden.cierre_bloqueado_en is not None:
        raise OrdenBloqueada(
            "El cierre ya es firme: venció el plazo para revertirlo.",
            cerrada_en=orden.cierre_bloqueado_en,
        )
    if orden.cierre_pendiente_hasta and orden.cierre_pendiente_hasta <= ahora:
        raise OrdenBloqueada("Venció el plazo para revertir este cierre.")

    destino = orden.cierre_etapa_previa or orden.etapa_actual

    # Los eventos del cierre se anulan uno a uno con su contrario. Es más
    # trabajo que un `UPDATE`, y es la diferencia entre poder explicar qué
    # pasó y no poder.
    anulados = 0
    del_cierre = EventoProduccion.objects.using(BASE).filter(
        orden=orden,
        tipo=EventoProduccion.Tipo.CIERRE_PENDIENTE,
        ocurrido_en__gte=orden.cierre_pendiente_en,
        anulado_por__isnull=True,
    )
    for original in del_cierre:
        EventoProduccion.objects.using(BASE).create(
            orden=orden,
            tipo=EventoProduccion.Tipo.ANULACION,
            etapa=original.etapa_anterior,
            etapa_anterior=original.etapa,
            contador=original.contador,
            delta_cantidad=-original.delta_cantidad,
            motivo=motivo,
            actor_username=nombre_de(actor),
            ocurrido_en=ahora,
            fecha_operacion=ahora.date(),
            anula_a=original,
            comentario=f"anula el evento {original.pk}",
        )
        anulados += 1

    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.REVERSION_CIERRE,
        etapa=destino,
        etapa_anterior=orden.etapa_actual,
        motivo=motivo,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
        ocurrido_en=ahora,
        fecha_operacion=ahora.date(),
        metadata={"eventos_anulados": anulados},
    )
    OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
        etapa_actual=destino,
        estado=OrdenProduccion.Estado.ABIERTA,
        cierre_pendiente_en=None,
        cierre_pendiente_hasta=None,
        cierre_pendiente_por="",
        cierre_etapa_previa=None,
        cierre_revertido_en=ahora,
        cierre_revertido_por=nombre_de(actor),
        ultimo_cambio=ahora,
        version=orden.version + 1,
    )
    recalcular_contadores(orden)
    logger.info(
        "cierre revertido %s por %s (%s), %s evento(s) anulados",
        orden.folio,
        nombre_de(actor),
        motivo.codigo,
        anulados,
    )
    return evento


@transaction.atomic(using=BASE)
def ajustar(orden, *, contador, delta, actor, motivo, comentario=""):
    """Corrección explícita de un contador, con motivo obligatorio.

    Existe para poder arreglar las órdenes que vienen con los contadores
    incoherentes sin tocar la base a mano y sin dejar el arreglo fuera del
    historial.
    """
    if motivo is None:
        raise MotivoRequerido("Un ajuste de contadores exige indicar el motivo.")
    delta = int(delta or 0)
    if delta == 0:
        raise CantidadInvalida("Un ajuste de cero no ajusta nada.")

    ahora = timezone.now()
    orden = _bloquear(orden)
    valores = {
        EventoProduccion.Contador.PRODUCIDA: orden.cantidad_producida,
        EventoProduccion.Contador.PINTADA: orden.cantidad_pintada,
        EventoProduccion.Contador.TERMINADA: orden.cantidad_terminada,
    }
    valores[contador] += delta

    evento = EventoProduccion.objects.using(BASE).create(
        orden=orden,
        tipo=EventoProduccion.Tipo.AJUSTE,
        etapa=orden.etapa_actual,
        contador=contador,
        delta_cantidad=delta,
        cantidad_resultante=valores[contador],
        motivo=motivo,
        comentario=comentario[:255],
        actor_username=nombre_de(actor),
        ocurrido_en=ahora,
        fecha_operacion=ahora.date(),
    )
    recalcular_contadores(orden)
    return evento


def motivo(ambito, codigo):
    """Atajo para localizar un motivo sin repetir la consulta en cada sitio."""
    return (
        MotivoEvento.objects.using(BASE)
        .filter(ambito=ambito, codigo=codigo, activo=True)
        .first()
    )
