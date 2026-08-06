from django.urls import path

from . import views

app_name = "personal"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.alta, name="alta"),
    path("<int:pk>/", views.editar, name="editar"),
    path("<int:pk>/baja/", views.dar_de_baja, name="dar_de_baja"),
    path("organizacion/", views.organizacion, name="organizacion"),
]
