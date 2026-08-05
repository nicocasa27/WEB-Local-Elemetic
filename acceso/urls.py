from django.urls import path

from acceso import views

app_name = "acceso"

urlpatterns = [
    path("", views.teclado, name="teclado"),
    path("entrar/", views.entrar, name="entrar"),
    path("salir/", views.salir, name="salir"),
]
