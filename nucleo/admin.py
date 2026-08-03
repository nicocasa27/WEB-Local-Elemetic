"""El núcleo en el administrador de Django.

Sirve para dos cosas mientras dure la convivencia: poder mirar el historial de
una orden sin escribir SQL, y poder editar la máquina de estados —etapas y
transiciones— sin tocar código, que es justamente lo que la fase venía a
conseguir.

Los eventos son de sólo lectura a propósito. Un registro que sólo crece deja
de serlo en cuanto alguien puede corregirlo desde una pantalla, y con él se va
la única razón para fiarse de los números. Para corregir está el evento
contrario, que es una operación del servicio, no un formulario.
"""

from django.contrib import admin

from nucleo.models import (
    Asignacion,
    Cliente,
    DivergenciaReconciliacion,
    Etapa,
    EtapaAlias,
    EventoMaquina,
    EventoProduccion,
    LineaNegocio,
    MotivoEvento,
    Obra,
    OrdenProduccion,
    PiezaCatalogo,
    TransicionPermitida,
)


class EtapaEnLinea(admin.TabularInline):
    model = Etapa
    extra = 0
    fields = ("orden", "codigo", "nombre", "es_espera", "es_cierre_pendiente", "es_terminal")


@admin.register(LineaNegocio)
class LineaNegocioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "prefijo_folio", "usa_almacen", "usa_acuse", "activa")
    inlines = [EtapaEnLinea]


class AliasEnLinea(admin.TabularInline):
    model = EtapaAlias
    extra = 0


@admin.register(Etapa)
class EtapaAdmin(admin.ModelAdmin):
    list_display = ("linea", "orden", "codigo", "nombre", "es_espera", "es_cierre_pendiente")
    list_filter = ("linea", "es_espera", "es_terminal")
    inlines = [AliasEnLinea]


@admin.register(TransicionPermitida)
class TransicionAdmin(admin.ModelAdmin):
    list_display = (
        "linea", "desde", "hasta", "es_retroceso", "requiere_motivo",
        "requiere_grupo", "bloquea_si_maquina_en_paro",
    )
    list_filter = ("linea", "es_retroceso", "bloquea_si_maquina_en_paro")
    list_editable = ("requiere_motivo", "requiere_grupo", "bloquea_si_maquina_en_paro")


@admin.register(MotivoEvento)
class MotivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ambito", "codigo", "activo", "es_sistema")
    list_filter = ("ambito", "activo")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "rfc", "activo", "origen")
    search_fields = ("nombre_normalizado", "rfc")


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cliente", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre_normalizado",)


@admin.register(PiezaCatalogo)
class PiezaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "linea", "peso_kg", "activo")
    list_filter = ("linea", "activo")
    search_fields = ("nombre_normalizado",)


class EventoEnLinea(admin.TabularInline):
    model = EventoProduccion
    extra = 0
    can_delete = False
    fields = (
        "ocurrido_en", "tipo", "etapa_anterior", "etapa", "contador",
        "delta_cantidad", "cantidad_resultante", "motivo", "actor_username",
        "sin_historico",
    )
    readonly_fields = fields
    ordering = ("ocurrido_en", "id")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdenProduccion)
class OrdenAdmin(admin.ModelAdmin):
    list_display = (
        "folio", "linea", "codigo", "etapa_actual", "estado",
        "cantidad_terminada", "cantidad_objetivo", "fecha_compromiso",
    )
    list_filter = ("linea", "estado", "etapa_actual")
    search_fields = ("folio", "codigo_normalizado", "nombre")
    readonly_fields = ("folio", "version", "legacy_modelo", "legacy_id", "creado_en")
    inlines = [EventoEnLinea]


@admin.register(EventoProduccion)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "ocurrido_en", "orden", "tipo", "contador", "delta_cantidad",
        "actor_username", "sin_historico",
    )
    list_filter = ("tipo", "contador", "sin_historico", "orden__linea")
    search_fields = ("orden__folio", "actor_username")
    date_hierarchy = "ocurrido_en"

    # Sólo lectura. Ver la explicación de arriba: un registro que se puede
    # editar deja de ser un registro.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = ("orden", "etapa", "rol", "colaborador", "maquina", "fraccion_peso", "vigente")
    list_filter = ("vigente", "orden__linea")


@admin.register(EventoMaquina)
class EventoMaquinaAdmin(admin.ModelAdmin):
    list_display = ("maquina", "clase", "motivo", "inicio", "fin")
    list_filter = ("clase", "maquina")


@admin.register(DivergenciaReconciliacion)
class DivergenciaAdmin(admin.ModelAdmin):
    list_display = (
        "detectada_en", "linea", "legacy_modelo", "legacy_id",
        "campo", "valor_heredado", "valor_nucleo",
    )
    list_filter = ("linea", "campo")
    date_hierarchy = "detectada_en"
