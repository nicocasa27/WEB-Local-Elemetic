"""Rutas del almacén.

Se separan de `catalogos` porque el almacén es su propio ámbito: quien surte
material no es quien produce, y tenerlo aparte hace evidente qué protege el
grupo de almacén.
"""

from django.urls import path

from . import almacen

app_name = "inventario"

urlpatterns = [
    path("existencias/", almacen.existencias, name="existencias"),
    path("por-surtir/", almacen.por_surtir, name="por_surtir"),
    path("entregar/", almacen.entregar, name="entregar"),
    path("liberar/", almacen.liberar, name="liberar"),
]
