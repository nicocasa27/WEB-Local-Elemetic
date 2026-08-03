"""Datos que necesitan todas las plantillas.

`user_access` resuelve qué puede ver cada quien; `navegacion` resuelve dónde
está.
"""

# ---------------------------------------------------------------- secciones
#
# Cada sección tiene su color de acento en produccion/static/css/mes.css. El
# reparto se hace por el nombre de la ruta, que ya viene con un prefijo
# limpio, en vez de enumerarlas una por una.
#
# Antes esto era una cadena de seis `{% elif %}` dentro de la plantilla, así
# que unas cuarenta pantallas se quedaban sin acento y navegar de Herrería
# (verde) a «Órdenes de herrería» cambiaba el color de la aplicación sin que
# hubiera pasado nada.

#: Rutas concretas, cuando el prefijo no basta.
SECCION_POR_RUTA = {
    "area_corte": "corte",
    "area_soldadura": "soldadura",
    "solo_lectura_robotica": "robotica",
    "solo_lectura_herreria": "herreria",
    "solo_lectura_corte_laser": "corta",
    "solo_lectura_produccion": "estructuras",
    "logistica_corta": "corta",
    "proyectos": "configuracion",
    "proyecto_detalle": "configuracion",
    "equipos": "configuracion",
    "maquinas": "configuracion",
}

#: Prefijos del nombre de la ruta, del más específico al más general. El orden
#: importa: "corte_laser_" tiene que mirarse antes que "corte".
SECCION_POR_PREFIJO = [
    ("corte_laser", "corta"),
    ("corta_", "corta"),
    ("herreria", "herreria"),
    ("robotica", "robotica"),
    ("robot_", "robotica"),
    ("viga", "estructuras"),
    ("export_vigas", "estructuras"),
    ("pedidos_", "pedidos"),
    ("dashboard", "reportes"),
    ("paros", "paros"),
    ("equipo_", "configuracion"),
    ("colaborador_", "configuracion"),
    ("maquina_", "configuracion"),
    ("configuracion", "configuracion"),
]


def seccion_de(nombre_ruta):
    """Sección a la que pertenece una ruta, o cadena vacía."""
    nombre = (nombre_ruta or "").strip()
    if not nombre:
        return ""
    if nombre in SECCION_POR_RUTA:
        return SECCION_POR_RUTA[nombre]
    for prefijo, seccion in SECCION_POR_PREFIJO:
        if nombre.startswith(prefijo):
            return seccion
    return ""


#: Nombre y pantalla principal de cada sección, para las migas de pan.
#:
#: Hasta ahora no había ninguna: desde una pantalla de detalle no se sabía de
#: dónde se venía, y para volver al menú había que adivinar que el logotipo
#: era un enlace. Lo que había en su lugar eran treinta variantes artesanales
#: de «Volver», cada una con un destino escrito a mano, que muchas veces te
#: sacaban de donde estabas.
INICIO_DE_SECCION = {
    "estructuras": ("Estructuras metálicas", "produccion:viga_list"),
    "corta": ("Corta.mx", "catalogos:corte_laser_control"),
    "corte": ("Corte", "produccion:area_corte"),
    "soldadura": ("Soldadura", "produccion:area_soldadura"),
    "robotica": ("Robótica", "catalogos:robotica"),
    "herreria": ("Herrería", "catalogos:herreria_control"),
    "pedidos": ("Pedidos", "catalogos:pedidos_ordenes"),
    "paros": ("Paros", "catalogos:paros"),
    "reportes": ("Reportes", "produccion:dashboard"),
    "configuracion": ("Configuración de planta", "nucleo:configuracion"),
}

#: Pantallas que ya son la portada de su sección: repetirlas en las migas
#: sería decir «Herrería › Herrería».
SIN_MIGAS = {"home", "menu", "movil"}


def navegacion(request):
    from django.urls import NoReverseMatch, reverse

    resuelta = getattr(request, "resolver_match", None)
    nombre = getattr(resuelta, "url_name", "") or ""
    seccion = seccion_de(nombre)

    migas = []
    if nombre not in SIN_MIGAS:
        migas.append({"texto": "Menú", "url": reverse("produccion:home")})
        titulo, ruta = INICIO_DE_SECCION.get(seccion, (None, None))
        if titulo:
            try:
                destino = reverse(ruta)
            except NoReverseMatch:
                destino = ""
            # La portada de la sección no se enlaza a sí misma.
            migas.append({"texto": titulo, "url": "" if destino == request.path else destino})

    return {"seccion": seccion, "migas": migas}


def user_access(request):
    user = getattr(request, "user", None)
    is_auth = bool(user and getattr(user, "is_authenticated", False))
    is_admin = False
    can_pedidos = False
    can_logistica_corta = False
    role = ""
    can_corte = False
    can_soldadura = False
    can_robotica = False
    can_herreria = False
    can_corte_laser = False
    try:
        if is_auth:
            can_corte = bool(user.groups.filter(name="corte").exists())
            can_soldadura = bool(user.groups.filter(name="soldadura").exists())
            can_robotica = bool(user.groups.filter(name="robotica").exists())
            can_herreria = bool(
                user.groups.filter(name__in=["herreria", "herreria_supervision"]).exists()
            )
            can_corte_laser = bool(
                user.groups.filter(name__in=["corte_laser", "corte_laser_supervision"]).exists()
            )
            is_admin = bool(
                getattr(user, "is_superuser", False)
                or getattr(user, "is_staff", False)
                or user.groups.filter(name__in=["admin_general", "ingenieria_civil"]).exists()
            )
            can_pedidos = bool(
                getattr(user, "is_superuser", False)
                or user.groups.filter(name__in=["admin_general", "ingenieria_civil", "pedidos_ventas"]).exists()
            )
            can_logistica_corta = bool(can_corte_laser or can_pedidos or is_admin)
            if is_admin:
                role = "admin"
            elif can_corte:
                role = "corte"
            elif can_soldadura:
                role = "soldadura"
            elif can_robotica:
                role = "robotica"
            elif can_herreria:
                role = "herreria"
            elif can_corte_laser:
                role = "corte_laser"
    except Exception:
        is_admin = False
        can_pedidos = False
        can_logistica_corta = False
        role = ""
        can_corte = False
        can_soldadura = False
        can_robotica = False
        can_herreria = False
        can_corte_laser = False
    return {
        "is_admin": is_admin,
        "can_pedidos": can_pedidos,
        "can_logistica_corta": can_logistica_corta,
        "user_role": role,
        "can_corte": can_corte or is_admin,
        "can_soldadura": can_soldadura or is_admin,
        "can_robotica": can_robotica or is_admin,
        "can_herreria": can_herreria or is_admin,
        "can_corte_laser": can_corte_laser or is_admin,
    }
