"""El costeo en el administrador de Django.

Las tarifas se dan de alta pero **no se editan**: corregir una es capturar otra
con fecha nueva. Si se pudiera editar, el costo de una orden cerrada cambiaría
solo cada vez que sube el sueldo de alguien, y el histórico dejaría de servir
para comparar, que es para lo único que sirve un histórico.

Los costos calculados son de sólo lectura enteros: no son un dato que alguien
capture, son el resultado de aplicar las tarifas al historial. Si el número
está mal, lo que hay que arreglar es una tarifa, una asignación o un consumo,
y volver a calcular.
"""

from django.contrib import admin

from costeo.models import (
    CentroCosto,
    CostoEtapa,
    CostoOrden,
    Tarifa,
    TarifaManoObra,
    TiempoEstandar,
)


class TarifaEnLinea(admin.TabularInline):
    model = Tarifa
    extra = 0
    fields = (
        "vigente_desde", "costo_hora_maquina", "costo_hora_mano_obra",
        "overhead_hora", "notas",
    )

    def has_change_permission(self, request, obj=None):
        # Ver arriba: una tarifa guardada es inmutable.
        return False


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "linea", "tarifa_vigente", "activo")
    inlines = [TarifaEnLinea]

    @admin.display(description="tarifa vigente")
    def tarifa_vigente(self, obj):
        from django.utils import timezone

        from core.servicios import costeo

        tarifa = costeo.tarifa_vigente(obj, timezone.localdate())
        if tarifa is None:
            return "— sin capturar —"
        return (
            f"máq {tarifa.costo_hora_maquina} · obra {tarifa.costo_hora_mano_obra} · "
            f"ind. {tarifa.overhead_hora}"
        )


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = (
        "centro", "vigente_desde", "costo_hora_maquina",
        "costo_hora_mano_obra", "overhead_hora", "creado_por",
    )
    list_filter = ("centro",)
    date_hierarchy = "vigente_desde"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TarifaManoObra)
class TarifaManoObraAdmin(admin.ModelAdmin):
    list_display = ("__str__", "colaborador", "rol", "vigente_desde", "costo_hora")
    list_filter = ("rol",)
    date_hierarchy = "vigente_desde"

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TiempoEstandar)
class TiempoEstandarAdmin(admin.ModelAdmin):
    list_display = ("pieza", "etapa", "horas_por_pieza", "operadores", "vigente_desde")
    list_filter = ("etapa__linea", "etapa")
    search_fields = ("pieza__nombre_normalizado",)


class CostoEtapaEnLinea(admin.TabularInline):
    model = CostoEtapa
    extra = 0
    can_delete = False
    fields = (
        "etapa", "horas", "horas_descontadas_por_paro", "personas",
        "mano_obra", "maquina", "overhead", "horas_estandar", "avisos",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CostoOrden)
class CostoOrdenAdmin(admin.ModelAdmin):
    list_display = (
        "orden", "total", "material", "mano_obra", "maquina", "overhead",
        "costo_por_pieza", "cobertura_pct", "margen", "calculado_en",
    )
    list_filter = ("metodo", "orden__linea")
    search_fields = ("orden__folio", "orden__codigo_normalizado")
    inlines = [CostoEtapaEnLinea]
    # Lo único que se captura a mano hasta que llegue la integración
    # comercial: el precio al que se vendió.
    fields = ("orden", "metodo", "precio_venta", "detalle")
    readonly_fields = ("orden", "metodo", "detalle")

    @admin.display(description="por pieza")
    def costo_por_pieza(self, obj):
        return obj.costo_unitario

    @admin.display(description="cobertura")
    def cobertura_pct(self, obj):
        return f"{int(obj.cobertura * 100)} %"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
