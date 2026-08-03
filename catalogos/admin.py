from django.contrib import admin

from .models import EquipoTrabajo, Proyecto


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "creado_en")
    list_filter = ("activo",)
    search_fields = ("nombre", "nombre_normalizado")


@admin.register(EquipoTrabajo)
class EquipoTrabajoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "integrantes", "activo", "estados_texto")
    list_filter = ("activo",)
    search_fields = ("nombre",)
