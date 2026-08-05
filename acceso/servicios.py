"""Las reglas del PIN, fuera de las vistas.

Aquí está lo que decide quién puede tener PIN, qué dígitos valen, y a quién
abre un PIN tecleado. Las vistas sólo leen el formulario y traducen el
resultado a una pantalla.
"""

import secrets

from django.conf import settings
from django.contrib.auth import get_user_model

from core import roles

Usuario = get_user_model()

#: Cuántos dígitos. Cuatro es lo que pidió el taller: se recuerdan sin
#: apuntarlos, que es la diferencia entre un PIN y una contraseña escrita en un
#: papel pegado a la tableta.
LARGO = 4

#: Cuántos intentos fallidos seguidos se admiten desde el mismo aparato antes
#: de hacerle esperar. No es una defensa contra un atacante decidido —no puede
#: serlo con cuatro dígitos— sino contra el caso real: alguien apoya la tableta
#: en la mesa y el teclado se dispara solo, o un script probando a ciegas deja
#: la pantalla inservible para el turno.
INTENTOS_ANTES_DE_ESPERAR = 8

#: Segundos de espera cuando se agotan los intentos.
SEGUNDOS_DE_ESPERA = 30

#: Minutos sin tocar nada antes de que la sesión de la tableta se cierre sola.
#: Quince: bastante para ir por una pieza y volver sin volver a teclear, y poco
#: para que no se quede abierta el turno entero. Se cambia con MES_PIN_MINUTOS.
MINUTOS_DE_INACTIVIDAD = 15


def minutos_de_inactividad():
    return int(getattr(settings, "MES_PIN_MINUTOS", MINUTOS_DE_INACTIVIDAD))


def normalizar(valor):
    """Deja sólo los dígitos de lo que se tecleó."""
    return "".join(c for c in (valor or "") if c.isdigit())


def revisar(digitos):
    """Devuelve el error de formato, o `None` si el PIN vale.

    No se rechaza el 1234 ni el 0000. Un PIN difícil de adivinar no compra
    nada aquí —no es un secreto, ver `models`— y sí cuesta: obligar a que sea
    raro es obligar a apuntarlo.
    """
    if len(digitos) != LARGO:
        return f"El PIN son {LARGO} dígitos exactos."
    return None


def puede_tener_pin(usuario):
    """Si esta cuenta se puede abrir con cuatro dígitos.

    **Sólo las del piso.** Cuatro dígitos son diez mil combinaciones, y eso no
    puede ser lo único que separe a cualquiera de la cuenta que da de alta
    usuarios, borra máquinas o cierra órdenes. Quien administra entra con su
    usuario y su contraseña, desde una PC, como hasta ahora.

    Una cuenta que además de ser del piso administra tampoco lleva PIN: manda
    el permiso más alto que tiene.
    """
    if usuario is None or not usuario.is_active:
        return False
    if usuario.is_superuser or usuario.is_staff:
        return False
    grupos = set(usuario.groups.values_list("name", flat=True))
    if grupos & roles.QUE_ADMINISTRAN:
        return False
    return bool(grupos & roles.DE_PISO)


def por_que_no_puede(usuario):
    """En castellano, por qué esta cuenta no lleva PIN. `None` si sí lleva."""
    if puede_tener_pin(usuario):
        return None
    if usuario is None or not usuario.is_active:
        return "La cuenta está apagada."
    if usuario.is_superuser or usuario.is_staff or (
        set(usuario.groups.values_list("name", flat=True)) & roles.QUE_ADMINISTRAN
    ):
        return (
            "Las cuentas que administran entran con usuario y contraseña. "
            "Cuatro dígitos no pueden ser lo único que proteja la "
            "administración del sistema."
        )
    return (
        "El PIN es para el piso. Esta cuenta no está en corte, soldadura, "
        "pintura, robótica, herrería ni Corta.mx."
    )


def de(usuario):
    """El PIN de esta cuenta, o cadena vacía."""
    from acceso.models import Pin

    fila = Pin.objects.filter(usuario=usuario).first()
    return fila.digitos if fila else ""


def ocupado_por(digitos, excepto=None):
    """Quién tiene ya estos dígitos, o `None`.

    Se cuentan también las cuentas apagadas: si a alguien se le apaga la cuenta
    y otro hereda su PIN, el trabajo del mes pasado y el de este mes quedan
    bajo el mismo número y ya no se pueden separar. Para liberarlo hay que
    quitárselo a mano, que es una decisión, no un descuido.
    """
    from acceso.models import Pin

    consulta = Pin.objects.filter(digitos=digitos)
    if excepto is not None:
        consulta = consulta.exclude(usuario=excepto)
    fila = consulta.select_related("usuario").first()
    return fila.usuario if fila else None


def libre():
    """Un PIN de cuatro dígitos que no tenga nadie.

    Sirve para proponerlo al dar de alta a alguien, que es cuando la pregunta
    «¿cuál le pongo?» detiene el alta. Devuelve cadena vacía si ya no queda
    ninguno libre, cosa que con diez mil combinaciones y un taller de decenas
    de personas no va a pasar, pero se contesta igual en vez de dar vueltas.
    """
    from acceso.models import Pin

    tomados = set(Pin.objects.values_list("digitos", flat=True))
    if len(tomados) >= 10**LARGO:
        return ""
    while True:
        propuesta = f"{secrets.randbelow(10 ** LARGO):0{LARGO}d}"
        if propuesta not in tomados:
            return propuesta


def asignar(usuario, digitos, quien=""):
    """Pone el PIN. Devuelve `(pin, error)`; el error es texto para la pantalla."""
    from acceso.models import Pin

    digitos = normalizar(digitos)
    problema = revisar(digitos)
    if problema:
        return None, problema

    motivo = por_que_no_puede(usuario)
    if motivo:
        return None, motivo

    otro = ocupado_por(digitos, excepto=usuario)
    if otro is not None:
        return None, (
            f"El PIN {digitos} ya es de {otro.get_full_name() or otro.get_username()}. "
            "Elige otro: dos personas con el mismo PIN harían que el trabajo "
            "quedara a nombre de cualquiera de las dos."
        )

    fila, _ = Pin.objects.update_or_create(
        usuario=usuario,
        defaults={"digitos": digitos, "actualizado_por": quien},
    )
    return fila, None


def quitar(usuario):
    """Le quita el PIN a una cuenta. No toca la cuenta ni su historial."""
    from acceso.models import Pin

    return Pin.objects.filter(usuario=usuario).delete()[0]


def quien_es(digitos):
    """A quién abre este PIN, o `None`.

    Vuelve a comprobar `puede_tener_pin` aquí y no sólo al asignarlo. Si a
    alguien se le pasa a administración o se le apaga la cuenta, su PIN deja de
    abrir en ese mismo momento sin que nadie tenga que acordarse de borrarlo.
    """
    from acceso.models import Pin

    digitos = normalizar(digitos)
    if revisar(digitos):
        return None
    fila = (
        Pin.objects.select_related("usuario")
        .filter(digitos=digitos)
        .first()
    )
    if fila is None:
        return None
    return fila.usuario if puede_tener_pin(fila.usuario) else None
