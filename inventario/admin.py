"""El inventario en el administrador de Django.

Los movimientos son de sólo lectura, igual que el historial de producción y
por la misma razón: un registro que se puede editar deja de ser un registro, y
con él se va la única razón para fiarse de las existencias. Para corregir está
el movimiento contrario, que es una operación del servicio.

Las existencias tampoco se editan a mano. Son una caché; el número bueno sale
de sumar los movimientos, y `verificar_inventario --corregir` la reconstruye.
Dejar que alguien escriba ahí un número es exactamente la forma de que el
almacén deje de cuadrar sin que quede rastro de quién lo hizo.
"""

from django.contrib import admin

from inventario.models import (
    Almacen,
    Existencia,
    ListaMateriales,
    LoteMaterial,
    Material,
    MovimientoMaterial,
    OrdenCompra,
    Proveedor,
    RenglonListaMateriales,
    RenglonOrdenCompra,
)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "rfc", "contacto", "telefono", "activo")
    search_fields = ("nombre_normalizado", "rfc")


@admin.register(Almacen)
class AlmacenAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "es_principal", "activo")


class LoteEnLinea(admin.TabularInline):
    model = LoteMaterial
    extra = 0
    fields = ("codigo", "colada", "proveedor", "costo_unitario", "recibido_en", "certificado")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "codigo", "nombre", "categoria", "unidad", "peso_kg",
        "stock_minimo", "existencia_total", "activo",
    )
    list_filter = ("categoria", "unidad", "activo")
    search_fields = ("codigo", "nombre_normalizado", "tipo", "calibre")
    readonly_fields = ("legacy_modelo", "legacy_id", "peso_calculado")
    inlines = [LoteEnLinea]

    @admin.display(description="existencia")
    def existencia_total(self, obj):
        from core.servicios import inventario

        return inventario.existencia(obj)

    @admin.display(description="peso calculado por geometría")
    def peso_calculado(self, obj):
        return obj.peso_calculado()


@admin.register(LoteMaterial)
class LoteAdmin(admin.ModelAdmin):
    list_display = (
        "codigo", "material", "colada", "proveedor",
        "costo_unitario", "recibido_en", "tiene_certificado",
    )
    list_filter = ("proveedor", "recibido_en")
    search_fields = ("codigo", "colada", "material__codigo", "material__nombre_normalizado")
    date_hierarchy = "recibido_en"

    @admin.display(boolean=True, description="certificado")
    def tiene_certificado(self, obj):
        return bool(obj.certificado)


@admin.register(MovimientoMaterial)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = (
        "ocurrido_en", "tipo", "material", "lote", "cantidad",
        "costo_unitario", "orden", "actor_username",
    )
    list_filter = ("tipo", "almacen", "material__categoria")
    search_fields = ("material__codigo", "lote__colada", "orden__folio", "actor_username")
    date_hierarchy = "ocurrido_en"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Existencia)
class ExistenciaAdmin(admin.ModelAdmin):
    list_display = ("material", "lote", "almacen", "cantidad", "actualizado_en")
    list_filter = ("almacen", "material__categoria")
    search_fields = ("material__codigo", "lote__codigo")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class RenglonListaEnLinea(admin.TabularInline):
    model = RenglonListaMateriales
    extra = 1


@admin.register(ListaMateriales)
class ListaMaterialesAdmin(admin.ModelAdmin):
    list_display = ("pieza", "version", "vigente", "creado_por", "creado_en")
    list_filter = ("vigente",)
    inlines = [RenglonListaEnLinea]


class RenglonCompraEnLinea(admin.TabularInline):
    model = RenglonOrdenCompra
    extra = 1
    readonly_fields = ("cantidad_recibida",)


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = ("folio", "proveedor", "estado", "fecha", "fecha_promesa", "importe")
    list_filter = ("estado", "proveedor")
    date_hierarchy = "fecha"
    inlines = [RenglonCompraEnLinea]
