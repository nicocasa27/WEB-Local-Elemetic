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


@register.filter
def escala_etapas(valor, es_orden_grande=False):
    """Los tramos de la escala de etapas de una orden.

    La etiqueta dice «Espera de armado», pero no dice dónde cae eso en el
    proceso: para saber si una pieza va empezando o va terminando había que
    conocerse la secuencia de memoria. Esto devuelve la secuencia completa
    marcando por dónde va, y la plantilla la pinta como una escala.

    No inventa ningún dato. La secuencia ya estaba en `core/estados.py`; lo
    único que faltaba era enseñarla.

    Un estado desconocido —los hay, por las variantes ortográficas históricas—
    devuelve la escala en blanco en vez de marcar un tramo equivocado.
    """
    from core import estados

    secuencia = estados.SECUENCIA_ORDEN_GRANDE if es_orden_grande else estados.SECUENCIA
    actual = estados.normalizar(valor)
    try:
        posicion = secuencia.index(actual)
    except ValueError:
        posicion = -1

    return [
        {
            "pasada": posicion >= 0 and i < posicion,
            "actual": i == posicion,
            "nombre": nombre,
        }
        for i, nombre in enumerate(secuencia)
    ]


@register.filter
def desde_hoy(fecha):
    """«hace 3 meses», «en 5 días», «hoy».

    La lista enseñaba la fecha de compromiso en absoluto —«2026-05-04»—, que
    obliga a restar mentalmente contra el día de hoy para saber si una orden va
    tarde. En relativo el retraso se lee sin calcular.

    Cadena vacía si no hay fecha: mejor un hueco que un «hace 56 años».
    """
    if not fecha:
        return ""

    from django.utils import timezone

    dias = (fecha - timezone.localdate()).days
    if dias == 0:
        return "hoy"

    magnitud = abs(dias)
    if magnitud < 7:
        cantidad, unidad = magnitud, "día" if magnitud == 1 else "días"
    elif magnitud < 31:
        cantidad = magnitud // 7
        unidad = "semana" if cantidad == 1 else "semanas"
    elif magnitud < 365:
        cantidad = magnitud // 30
        unidad = "mes" if cantidad == 1 else "meses"
    else:
        cantidad = magnitud // 365
        unidad = "año" if cantidad == 1 else "años"

    return f"hace {cantidad} {unidad}" if dias < 0 else f"en {cantidad} {unidad}"


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
