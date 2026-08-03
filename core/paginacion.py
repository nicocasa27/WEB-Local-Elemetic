"""Paginación de las listas de producción.

Las listas traían `qs[:2000]` y la pantalla decía «Mostrando hasta 2000
registros». Eso tiene dos problemas: en el celular son miles de filas que el
navegador tiene que dibujar antes de enseñar nada, y sobre todo **es un
recorte silencioso**: el día que el taller pase de dos mil piezas, las que
sobren no aparecerán y nadie recibirá aviso.

Con un paginador el corte deja de ser silencioso: se ve cuántas hay en total
y se puede llegar a todas.
"""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

#: Cuántas filas por página. Cincuenta entran de sobra en una pantalla de
#: oficina con desplazamiento y no ahogan a un celular.
POR_PAGINA = 50

#: Tope de lo que se puede pedir a mano por la dirección, para que un
#: `?por_pagina=100000` no tumbe el servidor.
MAXIMO_POR_PAGINA = 200


def tamano_de_pagina(request):
    try:
        pedido = int(request.GET.get("por_pagina") or POR_PAGINA)
    except (TypeError, ValueError):
        return POR_PAGINA
    return max(1, min(pedido, MAXIMO_POR_PAGINA))


def paginar(request, consulta, por_pagina=None):
    """Devuelve la página pedida de una consulta.

    Una página fuera de rango devuelve la última en vez de un error: quien
    llega ahí suele venir de un enlace viejo, y una lista vacía sin
    explicación parece que se borraron los datos.
    """
    paginador = Paginator(consulta, por_pagina or tamano_de_pagina(request))
    numero = request.GET.get("pagina") or 1
    try:
        return paginador.page(numero)
    except PageNotAnInteger:
        return paginador.page(1)
    except EmptyPage:
        return paginador.page(paginador.num_pages)


def enlace_de_pagina(request, numero):
    """La dirección actual cambiando sólo el número de página.

    Conserva los filtros. Perderlos al cambiar de página es de los errores que
    más desconciertan: la lista cambia de contenido sin motivo aparente.
    """
    parametros = request.GET.copy()
    parametros["pagina"] = numero
    return f"{request.path}?{parametros.urlencode()}"
