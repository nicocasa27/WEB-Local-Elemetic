"""Rutas del almacén.

Se separan de `catalogos` porque el almacén es su propio ámbito: quien surte
material no es quien produce, y tenerlo aparte hace evidente qué protege el
grupo de almacén.
"""

from django.urls import path

from . import almacen, carga_inicial, compras, opus_import

app_name = "inventario"

urlpatterns = [
    path("existencias/", almacen.existencias, name="existencias"),
    path("por-surtir/", almacen.por_surtir, name="por_surtir"),
    path("entregar/", almacen.entregar, name="entregar"),
    path("liberar/", almacen.liberar, name="liberar"),

    # Despacho global: la obra completa en un viaje. La manufactura por
    # proyectos no descuenta pieza a pieza.
    path("por-proyecto/", almacen.por_proyecto, name="por_proyecto"),
    path("por-proyecto/entregar/", almacen.entregar_proyecto, name="entregar_proyecto"),

    # Qué hay que comprar. Se deduce del mínimo, no de un aviso disparado.
    path("compras/", compras.bandeja, name="compras"),
    path("compras/marcar/", compras.marcar, name="compras_marcar"),

    path("importar-opus/", opus_import.importar, name="opus_importar"),
    # El catálogo entra por OPUS; las cantidades del día uno, por aquí.
    path("carga-inicial/", carga_inicial.importar, name="carga_inicial"),
]
