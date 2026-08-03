from django.urls import path

from nucleo import views

app_name = "nucleo"

urlpatterns = [
    path("", views.configuracion, name="configuracion"),
]
