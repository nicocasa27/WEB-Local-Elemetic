"""Los papeles que puede tener una persona en el sistema, en un solo sitio.

Hasta ahora los grupos eran cadenas sueltas repartidas por
`produccion/context_processors.py` y por las plantillas. Nadie podía contestar
«¿qué roles existen?» sin leer el código, y dar de alta a alguien significaba
entrar al admin de Django y adivinar qué grupo tocaba.

Aquí están los once que ya existían, con lo que hace cada uno en castellano, y
uno nuevo: **almacén**.

Sobre el almacén, que es lo que pidió el taller: quien produce no puede
confirmar que se entregó material. Si el operador pudiera, la confirmación no
valdría de nada — sería él diciendo que recibió lo que él mismo pidió, y el
inventario volvería a ser un número que nadie contrastó. Por eso es un grupo
aparte y por eso la pantalla de «Por surtir» lo exige.
"""

#: Los grupos, en el orden en que tiene sentido enseñarlos.
#:
#: `clave` es el nombre del grupo de Django, que ya está en la base y no se
#: puede cambiar sin romper los permisos de los once usuarios que existen.
ROLES = [
    {
        "clave": "admin_general",
        "nombre": "Administración general",
        "descripcion": "Ve y modifica todo, incluidos usuarios y configuración de planta.",
        "administra": True,
    },
    {
        "clave": "ingenieria_civil",
        "nombre": "Ingeniería",
        "descripcion": "Como administración general. Pensado para quien planea la obra.",
        "administra": True,
    },
    {
        "clave": "corte",
        "nombre": "Corte",
        "descripcion": "Mueve piezas de espera de corte a corte y a espera de armado.",
        "administra": False,
    },
    {
        "clave": "soldadura",
        "nombre": "Soldadura",
        "descripcion": "Armado, soldadura, pintura y terminado de estructuras.",
        "administra": False,
    },
    {
        "clave": "robotica",
        "nombre": "Robótica",
        "descripcion": "Órdenes de la celda robótica.",
        "administra": False,
    },
    {
        "clave": "herreria",
        "nombre": "Herrería",
        "descripcion": "Captura el avance de las órdenes de herrería.",
        "administra": False,
    },
    {
        "clave": "herreria_supervision",
        "nombre": "Herrería · supervisión",
        "descripcion": "Además cierra órdenes y corrige avances.",
        "administra": False,
    },
    {
        "clave": "corte_laser",
        "nombre": "Corta.mx",
        "descripcion": "Captura el avance de las órdenes de corte láser.",
        "administra": False,
    },
    {
        "clave": "corte_laser_supervision",
        "nombre": "Corta.mx · supervisión",
        "descripcion": "Además cierra órdenes y corrige avances.",
        "administra": False,
    },
    {
        "clave": "pedidos_ventas",
        "nombre": "Pedidos y ventas",
        "descripcion": "Levanta pedidos y sigue la logística de entrega.",
        "administra": False,
    },
    {
        "clave": "almacen",
        "nombre": "Almacén",
        "descripcion": (
            "Confirma la entrega de material y ajusta existencias. "
            "Quien produce no puede hacerlo."
        ),
        "administra": False,
    },
    {
        "clave": "configuracion",
        "nombre": "Configuración",
        "descripcion": "Catálogos de planta: equipos, máquinas y proyectos.",
        "administra": False,
    },
]

#: Los grupos cuyos miembros pueden administrar usuarios.
QUE_ADMINISTRAN = {r["clave"] for r in ROLES if r["administra"]}

#: El grupo que puede confirmar entregas de material.
ALMACEN = "almacen"

#: Los del piso. Son los que necesitan cuenta para usar «Mi trabajo» desde el
#: celular, y hasta ahora ninguno la tenía: los once usuarios del sistema son
#: todos de oficina.
DE_PISO = {"corte", "soldadura", "robotica", "herreria", "corte_laser"}


def por_clave(clave):
    for rol in ROLES:
        if rol["clave"] == clave:
            return rol
    return None


def puede_administrar_usuarios(user):
    """Quién puede dar de alta y modificar a los demás.

    El superusuario siempre, para que nunca se pueda quedar el sistema sin
    nadie capaz de entrar.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in=QUE_ADMINISTRAN).exists()


def puede_entregar_material(user):
    """Quién puede confirmar que el material salió del almacén."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name__in={ALMACEN} | QUE_ADMINISTRAN).exists()


def asegurar_grupos():
    """Crea los grupos que falten. Idempotente.

    No borra ninguno: si alguien creó un grupo a mano en el admin de Django,
    se queda. Devuelve los que se crearon.
    """
    from django.contrib.auth.models import Group

    creados = []
    for rol in ROLES:
        _, nuevo = Group.objects.get_or_create(name=rol["clave"])
        if nuevo:
            creados.append(rol["clave"])
    return creados
