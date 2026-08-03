"""Errores de dominio.

Los servicios que se extraigan de las vistas no reciben `request` ni devuelven
respuestas HTTP: reciben datos y lanzan estas excepciones. Es la vista la que
traduce cada una a un mensaje para el usuario y a un código de estado.

Esa separación es lo que permite probar una regla de negocio sin montar una
petición, y reutilizar la misma regla desde un comando de gestión, desde una
tarea programada o desde una API.
"""


class ErrorDeDominio(Exception):
    """Raíz de todos los errores de negocio.

    Permite a una vista capturar cualquiera de ellos de una vez, sin tragarse
    de paso los errores de programación.
    """

    mensaje_por_defecto = "No se pudo completar la operación."

    def __init__(self, mensaje=None, **detalles):
        self.mensaje = mensaje or self.mensaje_por_defecto
        self.detalles = detalles
        super().__init__(self.mensaje)


class TransicionInvalida(ErrorDeDominio):
    """El cambio de estado pedido no está permitido."""

    mensaje_por_defecto = "Ese cambio de estado no está permitido."


class MotivoRequerido(ErrorDeDominio):
    """Un retroceso de estado sin justificación."""

    mensaje_por_defecto = "Hay que indicar el motivo para regresar a una etapa anterior."


class OrdenBloqueada(ErrorDeDominio):
    """La orden ya cerró y venció su ventana de reversión."""

    mensaje_por_defecto = "La orden está cerrada: venció el plazo para modificarla."


class MaquinaNoDisponible(ErrorDeDominio):
    """La máquina tiene un paro o una falla abiertos.

    Hasta ahora esta regla sólo existía en el navegador, de modo que bastaba
    con desactivar el JavaScript para saltársela.
    """

    mensaje_por_defecto = "La máquina tiene un paro o una falla sin resolver."


class StockInsuficiente(ErrorDeDominio):
    """No hay material disponible para lo que se pide."""

    mensaje_por_defecto = "No hay suficiente material disponible."


class CantidadInvalida(ErrorDeDominio):
    """Una cantidad negativa, mayor que el objetivo o incoherente.

    Cubre también la invariante que hoy no comprueba nadie: no se puede haber
    terminado más piezas de las que se pintaron, ni pintado más de las
    soldadas.
    """

    mensaje_por_defecto = "La cantidad indicada no es válida."


class ConflictoDeConcurrencia(ErrorDeDominio):
    """Otra persona modificó la orden mientras se editaba.

    Hoy el avance manda la cantidad total en vez de la diferencia, así que dos
    pestañas abiertas a la vez se pisan sin que nadie se entere y el stock
    puede acabar contando el doble.
    """

    mensaje_por_defecto = "Otra persona actualizó esta orden. Recarga la página y vuelve a intentarlo."


class OperacionNoPermitida(ErrorDeDominio):
    """El usuario no tiene permiso para esta operación concreta."""

    mensaje_por_defecto = "No tienes permiso para hacer esto."
