"""Entregar y recibir una pieza entre áreas, con firma de los dos.

Aquí vive la regla de cuándo un cambio de etapa es un **traspaso** y cuándo es
sólo un paso más dentro de la misma área, que es lo único que hay que decidir
para que el mecanismo no estorbe.

Un traspaso ocurre cuando cambia el **centro de trabajo**, no la etapa:

    Corte → Espera de armado        corte pasa a soldadura   → traspaso
    Armado → Espera de soldadura    soldadura sigue en lo suyo → no
    Soldadura → Espera de pintura   soldadura pasa a pintura  → traspaso
    Pintura → Terminado             pintura entrega la pieza  → traspaso

Pedirle firma a un soldador para pasar de armado a soldadura sería pedirle que
se firme a sí mismo. Se usa `core.servicios.trabajo.CENTRO_DE_ETAPA`, que ya
existía para encontrar la cuadrilla, y así el mapa de áreas está escrito una
sola vez.

Sobre devolver una pieza
------------------------

Devolver **no es una falta**. Es lo contrario: es alguien haciendo la revisión
que se le pide. Si el indicador lo contara en contra, nadie devolvería nada y
en una semana todas las actas serían aceptaciones automáticas, que es lo mismo
que no tener actas. Por eso `rendimiento` cuenta las devoluciones a favor de
quien las detecta y en contra de quien entregó.
"""

from django.utils import timezone

from core.servicios.trabajo import CENTRO_DE_ETAPA, centro_de
from core.bases import BASE  # noqa: F401


#: Dónde acaba la pieza cuando sale de la última área. No es un centro de
#: trabajo: es el almacén, y no hay nadie que firme el recibo desde el celular.
#: El acta se registra igual —para saber quién dio la pieza por terminada— y
#: se queda esperando.
FUERA_DE_PRODUCCION = "Almacén"

#: Lo más largo que se admite en una firma. Un trazo de dedo en un lienzo de
#: 600×200 son unos 10 kB; el tope está muy por encima y sólo existe para que
#: una petición manipulada no meta un megabyte en una columna de texto.
FIRMA_MAXIMA = 400_000

_PREFIJO_FIRMA = "data:image/png;base64,"


def area_de(etapa):
    """El área que trabaja esta etapa. Vacío si la etapa no es de producción."""
    return centro_de(etapa)


def es_traspaso(etapa_anterior, etapa_nueva):
    """Si este cambio de etapa entrega la pieza a otra área.

    Devuelve `(area_origen, area_destino)`, o `(None, None)` si no lo es.
    """
    origen = area_de(etapa_anterior)
    if not origen:
        return None, None

    destino = area_de(etapa_nueva)
    if not destino:
        # La pieza sale de producción: terminado, enviado, lo que sea. Es una
        # entrega de verdad —alguien la dio por buena— aunque del otro lado no
        # haya un área que firme.
        if (etapa_nueva or "").strip() and etapa_nueva not in CENTRO_DE_ETAPA:
            return origen, FUERA_DE_PRODUCCION
        return None, None

    if destino == origen:
        return None, None
    return origen, destino


def limpiar_firma(dato):
    """Deja la firma si es un PNG en línea de tamaño razonable, o cadena vacía.

    No se intenta descifrar la imagen ni comprobar que el trazo sea de verdad
    un trazo. Lo que se comprueba es que sea del formato que manda el lienzo y
    que quepa: una firma en el taller vale por quién estaba delante de la
    tableta, y de eso responde la sesión, no el dibujo.
    """
    dato = (dato or "").strip()
    if not dato.startswith(_PREFIJO_FIRMA):
        return ""
    if len(dato) > FIRMA_MAXIMA:
        return ""
    return dato


# ------------------------------------------------------------------ consultas


def pendiente(legacy_modelo, legacy_id):
    """El acta que espera a que alguien reciba esta pieza, o `None`."""
    from nucleo.models import ActaDeEntrega

    return (
        ActaDeEntrega.objects.using(BASE)
        .filter(
            legacy_modelo=legacy_modelo,
            legacy_id=int(legacy_id),
            estado=ActaDeEntrega.Estado.PENDIENTE,
        )
        .first()
    )


def pendientes_de(legacy_modelo, identificadores):
    """Las actas pendientes de muchas piezas de una vez.

    En bloque porque la lista del celular enseña hasta veinte tarjetas y una
    consulta por tarjeta es lo que convierte una pantalla en una espera.
    """
    from nucleo.models import ActaDeEntrega

    identificadores = [int(x) for x in identificadores if x]
    if not identificadores:
        return {}
    filas = ActaDeEntrega.objects.using(BASE).filter(
        legacy_modelo=legacy_modelo,
        legacy_id__in=identificadores,
        estado=ActaDeEntrega.Estado.PENDIENTE,
    )
    return {int(f.legacy_id): f for f in filas}


def historial(legacy_modelo, legacy_id):
    """Todas las actas de una pieza, de la más antigua a la más reciente.

    Es la cadena de custodia: quién la entregó, quién la aceptó, y en qué
    escalón alguien dijo que no.
    """
    from nucleo.models import ActaDeEntrega

    return list(
        ActaDeEntrega.objects.using(BASE)
        .filter(legacy_modelo=legacy_modelo, legacy_id=int(legacy_id))
        .order_by("entregado_en")
    )


def quien_la_dio_por_buena(acta):
    """Quién aceptó esta pieza en el escalón anterior al de esta acta.

    Es la respuesta a «quién firmó que estaba correcta»: cuando una pieza se
    devuelve en pintura, el soldador que la entregó responde de su trabajo,
    y quien la aceptó viniendo de corte responde de haberla dado por buena.
    Devuelve cadena vacía si esta era la primera entrega de la pieza.
    """
    from nucleo.models import ActaDeEntrega

    anterior = (
        ActaDeEntrega.objects.using(BASE)
        .filter(
            legacy_modelo=acta.legacy_modelo,
            legacy_id=acta.legacy_id,
            entregado_en__lt=acta.entregado_en,
            estado=ActaDeEntrega.Estado.ACEPTADA,
        )
        .order_by("-entregado_en")
        .first()
    )
    return anterior.recibe_por if anterior else ""


# ------------------------------------------------------------------- escritura


def registrar(
    *,
    legacy_modelo,
    legacy_id,
    codigo,
    etapa_anterior,
    etapa_nueva,
    quien,
    firma="",
    momento=None,
):
    """Levanta el acta cuando una pieza cambia de área. Devuelve el acta o `None`.

    Devuelve `None` cuando el cambio no es un traspaso, que es el caso normal:
    la mayoría de los avances se quedan dentro de la misma área.

    **Nunca lanza.** Va dentro de la misma transacción que el cambio de estado,
    y si el acta fallara y arrastrara consigo el avance, el operador se
    quedaría sin poder mover la pieza por un fallo del mecanismo de medición.
    Un acta que falta se ve; una producción parada, también, pero cuesta el
    turno.
    """
    from nucleo.models import ActaDeEntrega

    origen, destino = es_traspaso(etapa_anterior, etapa_nueva)
    if not origen:
        return None

    momento = momento or timezone.now()

    # Si quedó una entrega abierta de un traspaso anterior —una pieza que se
    # devolvió y volvió a avanzar sin que nadie firmara el recibo— se cierra
    # aquí. La restricción de la base sólo admite una pendiente por pieza, y
    # la que vale es la última.
    (
        ActaDeEntrega.objects.using(BASE)
        .filter(
            legacy_modelo=legacy_modelo,
            legacy_id=int(legacy_id),
            estado=ActaDeEntrega.Estado.PENDIENTE,
        )
        .delete()
    )

    return ActaDeEntrega.objects.using(BASE).create(
        legacy_modelo=legacy_modelo,
        legacy_id=int(legacy_id),
        codigo=codigo or "",
        area_origen=origen,
        area_destino=destino,
        etapa_origen=etapa_anterior or "",
        etapa_destino=etapa_nueva or "",
        entrega_por=quien or "",
        entrega_firma=limpiar_firma(firma),
        entregado_en=momento,
    )


def aceptar(acta, *, quien, firma="", momento=None):
    """Quien recibe firma que lo que le entregaron está correcto."""
    from nucleo.models import ActaDeEntrega

    acta.recibe_por = quien or ""
    acta.recibe_firma = limpiar_firma(firma)
    acta.recibido_en = momento or timezone.now()
    acta.estado = ActaDeEntrega.Estado.ACEPTADA
    acta.save(
        using=BASE,
        update_fields=["recibe_por", "recibe_firma", "recibido_en", "estado"],
    )
    return acta


def rechazar(acta, *, quien, motivo, momento=None):
    """Quien recibe devuelve la pieza. Devuelve `(acta, error)`.

    El motivo es obligatorio. Una devolución sin motivo no le sirve a quien
    tiene que corregirla, y acaba en una llamada por teléfono que es justo lo
    que el sistema tenía que ahorrar.
    """
    from nucleo.models import ActaDeEntrega

    motivo = (motivo or "").strip()
    if not motivo:
        return None, "Di qué está mal, para que quien la hizo lo pueda corregir."

    acta.recibe_por = quien or ""
    acta.recibido_en = momento or timezone.now()
    acta.estado = ActaDeEntrega.Estado.RECHAZADA
    acta.motivo = motivo[:2000]
    acta.save(
        using=BASE,
        update_fields=["recibe_por", "recibido_en", "estado", "motivo"],
    )
    return acta, None
