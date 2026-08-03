from django import template

register = template.Library()

def _to_float(value):
    try:
        return float(value)
    except Exception:
        return 0.0


@register.filter
def get_item(value, key):
    if isinstance(value, dict):
        return value.get(key, "")
    return ""


@register.filter
def hours_hm(value):
    h = _to_float(value)
    if h <= 0:
        return "0 min"
    total_minutes = int(round(h * 60.0))
    if total_minutes <= 0:
        return "0 min"
    hh = total_minutes // 60
    mm = total_minutes % 60
    if hh <= 0:
        return f"{mm} min"
    if mm <= 0:
        return f"{hh} h"
    return f"{hh} h {mm} min"


@register.filter
def estado_clase(valor):
    """Clase CSS del estado de una orden.

    El color venía en un `data-color` y lo aplicaba el JavaScript. Si el
    JavaScript no cargaba —y hasta la fase anterior venía de internet—, la
    etiqueta quedaba con texto blanco sobre fondo blanco y el estado de la
    orden desaparecía de la pantalla. Con esto lo pinta la hoja de estilos.
    """
    from core import estados

    return estados.clase(valor)


@register.simple_tag(takes_context=True)
def enlace_pagina(context, numero):
    """La dirección actual cambiando sólo el número de página.

    Conserva los filtros: perderlos al cambiar de página hace que la lista
    cambie de contenido sin motivo aparente.
    """
    from core.paginacion import enlace_de_pagina

    request = context.get("request")
    if request is None:
        return "#"
    return enlace_de_pagina(request, numero)
