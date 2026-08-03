"""Inventario de materia prima, con trazabilidad por colada.

Hoy el sistema sabe qué se produce pero no con qué. Lo más parecido a un
catálogo de materiales es `LaserMaterialPlaca`: ciento trece placas dadas de
alta con su geometría y su peso, sin costo, sin proveedor, sin existencias y
sin ninguna forma de saber de qué colada salió una pieza que ya está en obra.
Cuando un cliente reclama, no hay a qué agarrarse.

Este módulo añade las cuatro cosas que faltan, y en este orden porque cada una
depende de la anterior:

1. **El material** como concepto propio, no como una placa de corte láser.
2. **El lote**, que es el corazón de todo esto. Un lote es una entrada
   concreta de material con su colada, su certificado y su costo. Sin lote no
   hay trazabilidad ni hay costeo: son la misma pieza de información.
3. **El movimiento**, un registro que sólo crece, igual que el del núcleo.
   Las existencias pasan a ser una caché reconstruible en vez de un número que
   alguien sube y baja.
4. **La lista de materiales**, que por ahora sólo *propone* el consumo.

Sobre ese último punto conviene ser explícito, porque es la decisión de diseño
que más se va a cuestionar: **el consumo se declara a mano y no se descuenta
solo.** Una lista de materiales incorrecta que descuenta automáticamente
destruye el inventario en una semana y nadie se entera hasta que hay que
comprar. Primero se poblan las listas y se comparan contra lo que de verdad se
consumió; automatizarlo es un interruptor que se enciende cuando los números
coincidan, no antes.

Aviso que no es técnico y es el que decide si esto sirve: **sin un inventario
físico inicial y sin una persona responsable de capturar las entradas, este
módulo no funciona.** No es un problema de código. Un inventario que nadie
alimenta da cifras peores que no tener inventario, porque además se creen.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

#: Acero al carbón, aluminio e inoxidable. Sale del cálculo de peso que hoy
#: está enterrado en `LaserOrdenProduccion.save()`, donde se decide la
#: densidad buscando trozos de texto en el nombre del material.
DENSIDAD_POR_DEFECTO = Decimal("7.850")


class Proveedor(models.Model):
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, unique=True, db_index=True)
    rfc = models.CharField(max_length=20, blank=True, default="")
    contacto = models.CharField(max_length=120, blank=True, default="")
    telefono = models.CharField(max_length=80, blank=True, default="")
    correo = models.CharField(max_length=180, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class Almacen(models.Model):
    """Dónde está físicamente el material.

    Se empieza con uno solo. Existe como tabla desde el principio porque
    añadirlo después obliga a repartir a mano todas las existencias entre
    ubicaciones que nadie apuntó, y eso ya no se puede reconstruir.
    """

    codigo = models.SlugField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    es_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-es_principal", "nombre"]
        verbose_name = "almacén"
        verbose_name_plural = "almacenes"
        constraints = [
            models.UniqueConstraint(
                fields=["es_principal"],
                condition=Q(es_principal=True),
                name="un_solo_almacen_principal",
            ),
        ]

    def __str__(self) -> str:
        return self.nombre


class Material(models.Model):
    """Qué se compra y se consume.

    Absorbe `LaserMaterialPlaca`, que hoy es puramente geométrica: sabe cuánto
    mide una placa y cuánto pesa, pero no cuánto cuesta ni cuántas hay.
    """

    class Unidad(models.TextChoices):
        PIEZA = "pza", "Pieza"
        KILOGRAMO = "kg", "Kilogramo"
        METRO = "m", "Metro"
        METRO_CUADRADO = "m2", "Metro cuadrado"

    codigo = models.CharField(max_length=40, unique=True, db_index=True)
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, db_index=True)
    categoria = models.CharField(max_length=60, blank=True, default="", db_index=True)
    tipo = models.CharField(max_length=120, blank=True, default="", db_index=True)
    calibre = models.CharField(max_length=40, blank=True, default="")
    unidad = models.CharField(max_length=4, choices=Unidad.choices, default=Unidad.PIEZA)

    # Geometría, para el material que viene en placa. Nula en lo que se
    # compra a granel.
    espesor_mm = models.DecimalField(
        max_digits=8, decimal_places=3, default=Decimal("0.000")
    )
    largo_mm = models.PositiveIntegerField(default=0)
    ancho_mm = models.PositiveIntegerField(default=0)
    #: Peso de una unidad. En placa es el peso de la placa entera.
    peso_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0.000")
    )
    #: Densidad en kg/dm³. Sirve para calcular el peso cuando no viene dado y
    #: para el aprovechamiento de placa.
    densidad = models.DecimalField(
        max_digits=6, decimal_places=3, default=DENSIDAD_POR_DEFECTO
    )

    #: Por debajo de esto hay que comprar. Cero significa que no se vigila.
    stock_minimo = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    activo = models.BooleanField(default=True)

    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "categoria", "tipo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="material_legacy_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["categoria", "tipo"], name="material_familia_idx"),
        ]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    @property
    def area_mm2(self):
        return int(self.largo_mm or 0) * int(self.ancho_mm or 0)

    def peso_calculado(self):
        """El peso de una placa a partir de su geometría y su densidad.

        Es el mismo cálculo que hoy vive dentro de `LaserOrdenProduccion.save()`,
        donde además decide la densidad buscando «ALUMIN» o «INOX» dentro del
        nombre del material. Aquí la densidad es un campo, así que dar de alta
        un material nuevo deja de depender de cómo se escriba su nombre.
        """
        if not (self.largo_mm and self.ancho_mm and self.espesor_mm):
            return Decimal("0.000")
        volumen_cm3 = (
            Decimal(self.largo_mm) * Decimal(self.ancho_mm) * self.espesor_mm
        ) / Decimal(1000)
        return ((volumen_cm3 * self.densidad) / Decimal(1000)).quantize(Decimal("0.001"))

    def __str__(self) -> str:
        return self.nombre


class LoteMaterial(models.Model):
    """Una entrada concreta de material: su colada, su certificado y su costo.

    Es la unidad de trazabilidad y el corazón del módulo. Sin lote no se puede
    responder «¿de qué colada salió esta pieza?» ni «¿cuánto costó de verdad
    esta orden?», que son la misma pregunta mirada desde dos sitios.

    El certificado se guarda como archivo porque es el documento que el
    cliente pide cuando reclama, y hoy vive en el correo de alguien.
    """

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="lotes")
    codigo = models.CharField(max_length=60, db_index=True)
    #: Número de colada del fabricante. Es lo que enlaza una pieza entregada
    #: con el certificado de la acería.
    colada = models.CharField(max_length=80, blank=True, default="", db_index=True)
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, null=True, blank=True, related_name="lotes"
    )
    orden_compra = models.ForeignKey(
        "OrdenCompra", on_delete=models.SET_NULL, null=True, blank=True, related_name="lotes"
    )
    certificado = models.FileField(
        upload_to="inventario/certificados/%Y/%m/", null=True, blank=True
    )
    #: Costo de una unidad del material en este lote. Es lo que hace posible
    #: valuar por lote en vez de por promedio, que es lo que pidió el taller.
    costo_unitario = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    moneda = models.CharField(max_length=3, default="MXN")
    recibido_en = models.DateField(db_index=True)
    observaciones = models.CharField(max_length=255, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Por fecha de recepción: es el orden en que se consume, y así la
        # consulta de salida por antigüedad no necesita ordenar nada aparte.
        ordering = ["recibido_en", "id"]
        constraints = [
            models.UniqueConstraint(fields=["material", "codigo"], name="lote_unico_por_material"),
        ]
        verbose_name = "lote de material"
        verbose_name_plural = "lotes de material"

    def __str__(self) -> str:
        return f"{self.material.codigo} · {self.codigo}"


class MovimientoMaterial(models.Model):
    """Todo lo que entra, sale o se corrige. Sólo se añade.

    Mismo patrón que `EventoProduccion`, y por las mismas razones: la cantidad
    es siempre un incremento con signo y nunca un total, hay clave de
    idempotencia para que un reenvío no cuente dos veces, y corregir es
    insertar el movimiento contrario en vez de editar el anterior.

    El costo unitario se copia aquí en el momento del movimiento. Es
    redundante respecto al lote a propósito: si mañana alguien corrige el costo
    de un lote, lo que ya se consumió tiene que seguir valiendo lo que valía,
    o el costo histórico de las órdenes cambiaría solo.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        CONSUMO = "consumo", "Consumo en producción"
        DEVOLUCION = "devolucion", "Devolución a almacén"
        MERMA = "merma", "Merma o desperdicio"
        AJUSTE = "ajuste", "Ajuste de inventario"
        TRASLADO_SALIDA = "traslado_salida", "Traslado: salida"
        TRASLADO_ENTRADA = "traslado_entrada", "Traslado: entrada"
        ANULACION = "anulacion", "Anulación de un movimiento"

    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="movimientos"
    )
    lote = models.ForeignKey(
        LoteMaterial, on_delete=models.PROTECT, null=True, blank=True,
        related_name="movimientos",
    )
    almacen = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="movimientos"
    )

    #: El incremento, con signo. Positivo entra, negativo sale.
    cantidad = models.DecimalField(max_digits=16, decimal_places=6)
    costo_unitario = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal("0")
    )

    #: A qué orden de producción se cargó. Es lo que permite responder
    #: «¿cuánto material lleva esta orden?» y, al revés, «¿en qué órdenes está
    #: la colada X?».
    orden = models.ForeignKey(
        "nucleo.OrdenProduccion", on_delete=models.PROTECT, null=True, blank=True,
        related_name="movimientos_material",
    )
    evento = models.ForeignKey(
        "nucleo.EventoProduccion", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="movimientos_material",
    )
    motivo = models.ForeignKey(
        "nucleo.MotivoEvento", on_delete=models.PROTECT, null=True, blank=True,
        related_name="movimientos_material",
    )

    comentario = models.CharField(max_length=255, blank=True, default="")
    actor_username = models.CharField(max_length=150, blank=True, default="", db_index=True)
    ocurrido_en = models.DateTimeField(db_index=True)
    registrado_en = models.DateTimeField(auto_now_add=True)

    clave_idempotencia = models.CharField(
        max_length=120, unique=True, null=True, blank=True
    )
    anula_a = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="anulado_por"
    )
    #: Para emparejar las dos mitades de un traslado.
    traslado = models.UUIDField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-ocurrido_en", "-id"]
        indexes = [
            models.Index(fields=["material", "ocurrido_en"], name="mov_material_fecha_idx"),
            models.Index(fields=["lote", "ocurrido_en"], name="mov_lote_fecha_idx"),
            models.Index(fields=["orden"], name="mov_orden_idx"),
        ]
        verbose_name = "movimiento de material"
        verbose_name_plural = "movimientos de material"

    @property
    def importe(self):
        return (self.cantidad * self.costo_unitario).quantize(Decimal("0.0001"))

    def __str__(self) -> str:
        return f"{self.tipo} {self.cantidad} {self.material.codigo}"


class Existencia(models.Model):
    """Cuánto hay de cada material, de cada lote y en cada almacén.

    Es **caché**: el valor bueno se obtiene sumando los movimientos.
    `verificar_existencias` comprueba que coincidan y `recalcular` la
    reconstruye. Existe porque preguntar «¿cuánto hay?» tiene que costar una
    consulta y no recorrer el historial entero.
    """

    material = models.ForeignKey(
        Material, on_delete=models.PROTECT, related_name="existencias"
    )
    lote = models.ForeignKey(
        LoteMaterial, on_delete=models.PROTECT, null=True, blank=True,
        related_name="existencias",
    )
    almacen = models.ForeignKey(
        Almacen, on_delete=models.PROTECT, related_name="existencias"
    )
    cantidad = models.DecimalField(max_digits=16, decimal_places=6, default=Decimal("0"))
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["material", "lote"]
        constraints = [
            models.UniqueConstraint(
                fields=["material", "lote", "almacen"],
                name="existencia_unica",
            ),
            models.UniqueConstraint(
                fields=["material", "almacen"],
                condition=Q(lote__isnull=True),
                name="existencia_sin_lote_unica",
            ),
            #: Nunca negativo. El servicio lo comprueba antes, pero esto es lo
            #: que garantiza que no haya ningún camino —ni un `update` en
            #: bloque, ni una consulta a mano— capaz de dejar el almacén
            #: debiendo material.
            models.CheckConstraint(
                condition=Q(cantidad__gte=Decimal("0")),
                name="existencia_no_negativa",
            ),
        ]
        verbose_name = "existencia"
        verbose_name_plural = "existencias"

    def __str__(self) -> str:
        return f"{self.material.codigo} · {self.cantidad}"


class ListaMateriales(models.Model):
    """Qué material lleva una pieza. Por ahora, sólo para proponer.

    Se versiona porque una lista cambia y el costo histórico de una orden
    tiene que poder calcularse con la lista que estaba vigente entonces, no
    con la de hoy.
    """

    pieza = models.ForeignKey(
        "nucleo.PiezaCatalogo", on_delete=models.PROTECT, related_name="listas_materiales"
    )
    version = models.PositiveIntegerField(default=1)
    vigente = models.BooleanField(default=True, db_index=True)
    notas = models.CharField(max_length=255, blank=True, default="")
    creado_por = models.CharField(max_length=150, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["pieza", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["pieza", "version"], name="lista_version_unica"),
            models.UniqueConstraint(
                fields=["pieza"],
                condition=Q(vigente=True),
                name="una_lista_vigente_por_pieza",
            ),
        ]
        verbose_name = "lista de materiales"
        verbose_name_plural = "listas de materiales"

    def __str__(self) -> str:
        return f"{self.pieza} v{self.version}"


class RenglonListaMateriales(models.Model):
    lista = models.ForeignKey(
        ListaMateriales, on_delete=models.CASCADE, related_name="renglones"
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="+")
    cantidad_por_pieza = models.DecimalField(max_digits=16, decimal_places=6)
    #: Porcentaje que se pierde en el corte. Separado de la cantidad para que
    #: se pueda comparar lo previsto con lo real y saber si la merma que se
    #: supone es la que de verdad hay.
    merma_porcentaje = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0")
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["lista", "material"], name="renglon_unico_por_lista"),
        ]
        verbose_name = "renglón de lista de materiales"
        verbose_name_plural = "renglones de lista de materiales"

    @property
    def cantidad_con_merma(self):
        factor = Decimal("1") + (self.merma_porcentaje / Decimal("100"))
        return (self.cantidad_por_pieza * factor).quantize(Decimal("0.000001"))

    def __str__(self) -> str:
        return f"{self.material.codigo} × {self.cantidad_por_pieza}"


class OrdenCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        ENVIADA = "enviada", "Enviada al proveedor"
        PARCIAL = "parcial", "Recibida en parte"
        RECIBIDA = "recibida", "Recibida"
        CANCELADA = "cancelada", "Cancelada"

    folio = models.CharField(max_length=30, unique=True, db_index=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="compras")
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.BORRADOR, db_index=True
    )
    moneda = models.CharField(max_length=3, default="MXN")
    fecha = models.DateField(db_index=True)
    fecha_promesa = models.DateField(null=True, blank=True)
    observaciones = models.CharField(max_length=255, blank=True, default="")
    creado_por = models.CharField(max_length=150, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "orden de compra"
        verbose_name_plural = "órdenes de compra"

    @property
    def importe(self):
        return sum((r.importe for r in self.renglones.all()), Decimal("0"))

    def __str__(self) -> str:
        return f"{self.folio} · {self.proveedor.nombre}"


class RenglonOrdenCompra(models.Model):
    orden = models.ForeignKey(OrdenCompra, on_delete=models.CASCADE, related_name="renglones")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="+")
    cantidad = models.DecimalField(max_digits=16, decimal_places=6)
    costo_unitario = models.DecimalField(max_digits=16, decimal_places=6)
    #: Se sube al registrar cada entrada. Es lo que distingue una compra
    #: recibida a medias de una recibida entera.
    cantidad_recibida = models.DecimalField(
        max_digits=16, decimal_places=6, default=Decimal("0")
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["orden", "material"], name="renglon_compra_unico"),
        ]
        verbose_name = "renglón de orden de compra"
        verbose_name_plural = "renglones de orden de compra"

    @property
    def importe(self):
        return (self.cantidad * self.costo_unitario).quantize(Decimal("0.0001"))

    @property
    def pendiente(self):
        return max(self.cantidad - self.cantidad_recibida, Decimal("0"))

    def __str__(self) -> str:
        return f"{self.material.codigo} × {self.cantidad}"
