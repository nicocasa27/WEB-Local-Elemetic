"""El menú, en un solo sitio.

Estaba escrito tres veces —la barra de escritorio, el panel del celular y el
muro de mosaicos de la portada— y nada obligaba a que coincidieran. No
coincidían: Almacén, Usuarios y «Listo para salir» sólo existían en una de las
tres. Cada pantalla nueva había que acordarse de añadirla en tres sitios, y
olvidarse no se notaba: la pantalla existía, simplemente no se podía llegar.

Aquí se declara una vez y las tres formas de enseñarlo leen de esto. Añadir una
pantalla es añadir un renglón.

**Por qué barra lateral y no desplegables.** Con desplegables, cada destino
cuesta tres gestos: abrir el menú, buscar dentro, pulsar. Y como la portada era
otro menú distinto, había que aprender dos navegaciones. Con la barra fija todo
está a un clic y siempre se ve dónde estás, que es la mitad de saber moverse.
"""


class Item:
    """Un destino del menú.

    `visible` recibe los permisos ya calculados por el procesador de contexto y
    decide si esta persona lo ve. Se guarda como función y no como cadena de
    condiciones en la plantilla porque una condición en una plantilla no se
    puede probar sola.
    """

    def __init__(self, nombre, url, icono, *, visible=None, consulta="", nota=""):
        self.nombre = nombre
        self.url = url
        self.icono = icono
        self.nota = nota
        self.consulta = consulta
        self._visible = visible or (lambda acceso: True)

    def se_ve(self, acceso):
        return bool(self._visible(acceso))


class Grupo:
    def __init__(self, titulo, items, *, visible=None):
        self.titulo = titulo
        self.items = items
        self._visible = visible or (lambda acceso: True)

    def se_ve(self, acceso):
        return bool(self._visible(acceso))


def _si(clave):
    """Se ve si ese permiso está puesto."""
    return lambda acceso: bool(acceso.get(clave))


def _cualquiera(*claves):
    return lambda acceso: any(acceso.get(c) for c in claves)


def _solo_area(clave):
    """Para quien trabaja en un área concreta y no es administrador.

    El administrador ve las cuatro líneas; quien corta ve corte, y soldadura
    sólo si además está en soldadura. Enseñar áreas donde alguien no puede
    hacer nada llena el menú de callejones sin salida.
    """
    return lambda acceso: bool(acceso.get("is_admin") or acceso.get(clave))


#: El menú entero. El orden es el de un día de trabajo: primero dónde estoy,
#: luego lo que produzco, luego lo que sale, y al final lo que se configura una
#: vez cada mucho.
MENU = [
    Grupo("Principal", [
        Item("Inicio", "produccion:home", "bi-house"),
        Item("Mi trabajo", "produccion:movil", "bi-phone", nota="Piso"),
    ]),

    Grupo("Producción", [
        # El taller pidió este orden y estos nombres. «Control de producción»
        # va primero porque es la pantalla desde la que se dirige el día.
        Item("Control de producción", "catalogos:herreria_control", "bi-hammer",
             visible=_solo_area("can_herreria")),
        Item("Corte", "produccion:area_corte", "bi-scissors",
             consulta="?src=nav", visible=_solo_area("can_corte")),
        Item("Herrería", "produccion:area_soldadura", "bi-fire",
             consulta="?src=nav", visible=_solo_area("can_soldadura")),
        Item("Estructuras", "produccion:viga_list", "bi-list-task",
             visible=_si("is_admin")),
        Item("Robótica", "catalogos:robotica", "bi-robot",
             visible=_solo_area("can_robotica")),
        Item("Corta.mx", "catalogos:corte_laser_control", "bi-layers",
             visible=_solo_area("can_corte_laser")),
        Item("Solo lectura", "produccion:solo_lectura_produccion", "bi-eye",
             # Sólo para quien no puede operar ninguna línea: es su única
             # forma de ver el taller.
             visible=lambda a: not (
                 a.get("is_admin") or a.get("can_corte") or a.get("can_soldadura")
             )),
        Item("Paros", "catalogos:paros", "bi-exclamation-octagon"),
    ]),

    Grupo("Almacén", [
        Item("Existencias", "inventario:existencias", "bi-clipboard-data"),
        Item("Por surtir", "inventario:por_surtir", "bi-box-arrow-right"),
        Item("Por proyecto", "inventario:por_proyecto", "bi-buildings"),
        Item("Por comprar", "inventario:compras", "bi-cart-plus"),
        Item("Producto terminado", "catalogos:producto_terminado", "bi-box2-heart"),
    ]),

    Grupo("Pedidos", [
        Item("Órdenes de producción", "catalogos:pedidos_ordenes", "bi-receipt",
             visible=_si("can_pedidos")),
        Item("Logística", "catalogos:pedidos_logistica", "bi-truck",
             visible=_si("can_pedidos")),
        Item("Logística", "catalogos:logistica_corta", "bi-truck",
             visible=lambda a: a.get("can_logistica_corta") and not a.get("can_pedidos")),
        Item("Listo para salir", "catalogos:despacho", "bi-box-seam",
             visible=_si("can_pedidos")),
    ], visible=_cualquiera("can_pedidos", "can_logistica_corta")),

    Grupo("Análisis", [
        Item("Reportes", "produccion:dashboard", "bi-bar-chart-line"),
        Item("Trazabilidad", "catalogos:trazabilidad", "bi-diagram-3"),
    ]),

    Grupo("Configuración", [
        Item("Proyectos", "catalogos:proyectos", "bi-folder2-open"),
        Item("Equipos", "catalogos:equipos", "bi-people"),
        Item("Maquinaria", "catalogos:maquinas", "bi-cpu"),
        Item("Cuadrillas", "catalogos:cuadrillas", "bi-people-fill"),
        Item("Usuarios", "catalogos:usuarios", "bi-person-badge"),
        Item("Importar de OPUS", "inventario:opus_importar", "bi-filetype-csv"),
        Item("Carga inicial", "inventario:carga_inicial", "bi-upload"),
    ], visible=_si("is_admin")),
]


def para(acceso):
    """El menú que le toca a esta persona, ya filtrado.

    Los grupos que se quedan sin ningún destino no se devuelven: un título de
    grupo vacío parece un fallo de carga.
    """
    grupos = []
    for grupo in MENU:
        if not grupo.se_ve(acceso):
            continue
        items = [i for i in grupo.items if i.se_ve(acceso)]
        if items:
            grupos.append({"titulo": grupo.titulo, "items": items})
    return grupos
