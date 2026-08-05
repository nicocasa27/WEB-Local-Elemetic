"""El motor de producción, una sola vez.

Hoy hay cuatro: vigas, herrería, corte láser y robótica son la misma máquina
de estados copiada y pegada. `HerrOrdenProduccion` y `LaserOrdenProduccion`
comparten veintiocho campos con el mismo nombre; hay unos veinticinco pares de
funciones con más del setenta por ciento de código idéntico. Y ya divergieron:
los pares que menos se parecen son justamente los que se arreglaron de un lado
y no del otro, que es de donde salen los fallos asimétricos.

La causa no es descuido. Es que la lógica vive dentro de las vistas, así que
la única forma de añadir una línea era copiar la anterior. Mientras eso siga
así, cada módulo nuevo cuesta el cuádruple y nace con los mismos fallos.

Este paquete es el destino común. Tres ideas lo sostienen:

**La máquina de estados pasa de código a datos.** `LineaNegocio`, `Etapa` y
`TransicionPermitida` sustituyen a unos ciento cuarenta literales repartidos
por `catalogos/views.py` y a media docena de listas repetidas. Añadir un
granallado, un turno o una línea entera pasa de ser un refactor a ser un
`INSERT`.

**El historial es la fuente de verdad, no los contadores.**
`EventoProduccion` es un registro que sólo crece: nunca se actualiza ni se
borra. Los contadores de la orden pasan a ser una caché que se puede
recalcular y verificar. Si caché e historial no coinciden, gana el historial.

**Nada se pierde.** Cada fila apunta a la fila heredada de la que salió
(`legacy_modelo`, `legacy_id`), así que la migración es idempotente y
verificable en los dos sentidos. Las tablas viejas no se tocan.

Sobre la identidad: aquí no hay `ForeignKey` a `User` porque `auth` todavía
vive en SQLite y el negocio en PostgreSQL, y Django no admite claves foráneas
entre bases. Se guarda `actor_username`, igual que hace el sistema heredado.
El día que se unifiquen las bases (tarea pendiente de la fase anterior, ver
DESPLIEGUE.md) se añade la columna `actor` y se rellena desde ésta: por eso el
campo está aislado en un solo sitio de cada modelo y no repartido por catorce.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


# =========================================================== configuración
#
# Estas cuatro tablas son la máquina de estados. No contienen operación: se
# siembran una vez con `sembrar_nucleo` y se editan desde el admin.


class LineaNegocio(models.Model):
    """Una línea de producción: vigas, herrería, corte láser, robótica.

    Lo que de verdad las distingue son un puñado de opciones, no el código.
    Ponerlas aquí es lo que permite que las cuatro compartan motor.
    """

    codigo = models.SlugField(max_length=30, unique=True)
    nombre = models.CharField(max_length=80)
    prefijo_folio = models.CharField(
        max_length=6,
        help_text="Letra del folio: H para herrería, L para corte láser…",
    )
    #: Si las piezas terminadas entran a almacén o se entregan directamente.
    #: Ésta es la opción que hace explícita la diferencia entre herrería (que
    #: sí genera stock) y corte láser (que hoy rechaza las órdenes de una
    #: pieza sin decir por qué), en vez de dejarla escondida en un `if`.
    usa_almacen = models.BooleanField(default=True)
    #: Si la entrega genera acuse firmado. Un acuse emitido no se borra nunca:
    #: se anula.
    usa_acuse = models.BooleanField(default=True)
    #: Minutos que una orden permanece en cierre pendiente antes de volverse
    #: firme, para poder deshacer un error de dedo.
    ventana_cierre_minutos = models.PositiveIntegerField(default=10)
    #: A partir de cuántas piezas la orden deja de llevarse por etapas y pasa
    #: a llevarse por contadores.
    piezas_minimas_orden_grande = models.PositiveIntegerField(default=2)
    activa = models.BooleanField(default=True)
    orden_visual = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden_visual", "nombre"]
        verbose_name = "línea de negocio"
        verbose_name_plural = "líneas de negocio"

    def __str__(self) -> str:
        return self.nombre


class Etapa(models.Model):
    """Un paso del proceso dentro de una línea.

    El código es estable y en minúsculas (`espera_corte`); el nombre es lo que
    se enseña. Hoy el valor guardado *es* la etiqueta, y por eso «Espera
    Armado» y «Espera de armado» son dos estados distintos para la base
    aunque sean el mismo para una persona. Separarlos corta esa clase de fallo
    de raíz.
    """

    linea = models.ForeignKey(LineaNegocio, on_delete=models.PROTECT, related_name="etapas")
    codigo = models.SlugField(max_length=40)
    nombre = models.CharField(max_length=60)
    orden = models.PositiveSmallIntegerField()
    #: Las etapas de espera no consumen tiempo de máquina: cuentan como cola.
    #: Separarlas es prerrequisito del cálculo de tiempos de la fase 4.
    es_espera = models.BooleanField(default=False)
    #: Una orden en etapa terminal ya no avanza más.
    es_terminal = models.BooleanField(default=False)
    #: Etapa intermedia del cierre, con ventana de reversión. Existía en el
    #: sistema heredado pero no figuraba en ninguna de las listas de estados,
    #: así que la comprobación de retroceso quedaba desactivada para las
    #: órdenes que la tenían: desde ahí se podía saltar a cualquier estado sin
    #: justificar nada.
    es_cierre_pendiente = models.BooleanField(default=False)
    requiere_asignacion = models.BooleanField(default=False)
    requiere_maquina = models.BooleanField(default=False)
    #: Gancho para el módulo de calidad: la orden no sale de aquí si queda una
    #: inspección obligatoria pendiente. Vive en datos y no en código a
    #: propósito.
    requiere_inspeccion_aprobada = models.BooleanField(default=False)
    color = models.CharField(max_length=9, blank=True, default="")

    class Meta:
        ordering = ["linea", "orden"]
        constraints = [
            models.UniqueConstraint(fields=["linea", "codigo"], name="etapa_unica_por_linea"),
            models.UniqueConstraint(fields=["linea", "orden"], name="etapa_orden_unico_por_linea"),
        ]

    def __str__(self) -> str:
        return f"{self.linea.codigo}:{self.codigo}"


class EtapaAlias(models.Model):
    """Cada forma en que una etapa se ha escrito alguna vez.

    Tabla aparte y no una lista dentro de `Etapa` porque durante la
    convivencia hay que poder buscar por el valor heredado, y eso quiere un
    índice. Cuando las tablas viejas se retiren, esto se queda como
    documentación de lo que hubo.
    """

    etapa = models.ForeignKey(Etapa, on_delete=models.CASCADE, related_name="alias")
    valor = models.CharField(max_length=60)
    #: Minúsculas, sin acentos, sin espacios de más. Es la clave de búsqueda.
    valor_normalizado = models.CharField(max_length=60, db_index=True)

    class Meta:
        ordering = ["etapa", "valor"]
        constraints = [
            models.UniqueConstraint(
                fields=["etapa", "valor_normalizado"], name="alias_unico_por_etapa"
            ),
        ]
        verbose_name_plural = "alias de etapa"

    def __str__(self) -> str:
        return self.valor


class TransicionPermitida(models.Model):
    """Qué movimiento es legal, quién puede hacerlo y qué debe justificar.

    Las tres reglas que hoy sólo viven en el navegador —no avanzar con la
    máquina parada, no pasar del objetivo, motivo obligatorio al retroceder—
    dejan de ser JavaScript y pasan a ser filas. Cualquiera con la URL podía
    saltárselas.
    """

    linea = models.ForeignKey(
        LineaNegocio, on_delete=models.CASCADE, related_name="transiciones"
    )
    #: Nulo significa «desde el alta»: la etapa en que nace una orden.
    desde = models.ForeignKey(
        Etapa, on_delete=models.CASCADE, related_name="salidas", null=True, blank=True
    )
    hasta = models.ForeignKey(Etapa, on_delete=models.CASCADE, related_name="entradas")
    requiere_motivo = models.BooleanField(default=False)
    #: Grupo de Django exigido, vacío si no se exige ninguno.
    requiere_grupo = models.CharField(max_length=60, blank=True, default="")
    bloquea_si_maquina_en_paro = models.BooleanField(default=False)
    #: Se calcula al sembrar comparando el orden de las dos etapas. Se guarda
    #: para poder consultarlo sin recorrer la secuencia.
    es_retroceso = models.BooleanField(default=False)

    class Meta:
        ordering = ["linea", "desde__orden", "hasta__orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "desde", "hasta"],
                name="transicion_unica",
            ),
            models.UniqueConstraint(
                fields=["linea", "hasta"],
                condition=Q(desde__isnull=True),
                name="transicion_inicial_unica",
            ),
        ]
        verbose_name = "transición permitida"
        verbose_name_plural = "transiciones permitidas"

    def __str__(self) -> str:
        origen = self.desde.codigo if self.desde_id else "(alta)"
        return f"{self.linea.codigo}: {origen} → {self.hasta.codigo}"


class MotivoEvento(models.Model):
    """Un solo catálogo de motivos donde había cuatro.

    Hoy los motivos de paro y los tipos de falla son dos tablas gemelas, y los
    motivos de retroceso y de retrabajo son texto libre dentro de un
    comentario. Por eso el tablero tiene dos definiciones incompatibles de
    «retrabajo» en la misma pantalla: una busca la palabra en el comentario y
    otra una etiqueta `[MOTIVO=RETRABAJO]`. Con una clave foránea la
    definición es una sola y se puede contar.
    """

    class Ambito(models.TextChoices):
        PARO = "paro", "Paro de máquina"
        FALLA = "falla", "Falla de máquina"
        RETROCESO = "retroceso", "Retroceso de etapa"
        RETRABAJO = "retrabajo", "Retrabajo"
        AJUSTE = "ajuste", "Ajuste de contadores"
        CANCELACION = "cancelacion", "Cancelación"
        REVERSION = "reversion", "Reversión de cierre"

    ambito = models.CharField(max_length=20, choices=Ambito.choices, db_index=True)
    codigo = models.SlugField(max_length=40)
    nombre = models.CharField(max_length=120)
    activo = models.BooleanField(default=True)
    #: Los del sistema no se pueden borrar desde la interfaz: hay lógica que
    #: depende de ellos.
    es_sistema = models.BooleanField(default=False)
    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["ambito", "-activo", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["ambito", "codigo"], name="motivo_unico_por_ambito"),
        ]
        verbose_name = "motivo"
        verbose_name_plural = "motivos"

    def __str__(self) -> str:
        return self.nombre


# ================================================================ clientes
#
# Hoy hay tres conceptos sin ninguna relación entre sí —`Proyecto`,
# `HerrCliente` y `CortaClienteProyecto`— más un campo de texto libre en
# vigas. Sin un cliente único no hay integración comercial posible, ni costeo
# por cliente, ni forma de responder «cuánto le hemos entregado a este».
#
# La fusión no se automatiza. Dos nombres parecidos pueden ser dos empresas
# distintas, y unirlas mal contamina la facturación: `fusionar_clientes`
# propone en un CSV y sólo aplica lo aprobado por una persona.


class Cliente(models.Model):
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, unique=True, db_index=True)
    rfc = models.CharField(max_length=20, blank=True, default="")
    correo = models.CharField(max_length=180, blank=True, default="")
    telefono = models.CharField(max_length=80, blank=True, default="")
    activo = models.BooleanField(default=True)
    #: De dónde salió al migrar, para poder auditar la fusión después.
    origen = models.CharField(max_length=40, blank=True, default="")
    #: Identificador en el sistema comercial, cuando se conecte (fase 4).
    referencia_externa = models.CharField(max_length=80, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class Obra(models.Model):
    """El proyecto concreto de un cliente. Lo que hoy es `Proyecto`, suelto."""

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="obras")
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, db_index=True)
    activo = models.BooleanField(default=True)
    referencia_externa = models.CharField(max_length=80, blank=True, default="")
    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-activo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "nombre_normalizado"], name="obra_unica_por_cliente"
            ),
        ]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.cliente.nombre} · {self.nombre}"


class PiezaCatalogo(models.Model):
    """Un catálogo de piezas donde hay tres: robótica, herrería y corta.

    `linea` nulo significa que la pieza sirve para todas.
    """

    linea = models.ForeignKey(
        LineaNegocio, on_delete=models.PROTECT, related_name="piezas", null=True, blank=True
    )
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, db_index=True)
    #: Decimal y no coma flotante: esto acaba multiplicado por toneladas y
    #: por pesos. En el sistema heredado es `FloatField` y los kilos no
    #: cuadran al sumar.
    peso_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0.000"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    pdf = models.FileField(upload_to="nucleo/catalogo/pdf/%Y/%m/", null=True, blank=True)
    dxf = models.FileField(upload_to="nucleo/catalogo/dxf/%Y/%m/", null=True, blank=True)
    activo = models.BooleanField(default=True)
    #: Por qué etapas pasa esta pieza **siempre**. Lista de códigos de etapa,
    #: igual que `OrdenProduccion.ruta`.
    #:
    #: Hay piezas que se hacen una vez y piezas que se hacen todas las
    #: semanas. Un andamio tipo A no se pinta nunca: sin esto, alguien tiene
    #: que acordarse de quitarle pintura a mano en cada pedido, y el día que
    #: se le olvide, el andamio se forma en una cola de pintura por la que no
    #: va a pasar. Con esto se dice una vez y las órdenes nuevas nacen bien.
    #:
    #: Vacía significa «nadie lo ha dicho»: la orden nace con la ruta
    #: completa, que es lo que hacía el sistema.
    ruta = models.JSONField(default=list, blank=True)
    #: Cómo se hace esta pieza, para las órdenes nuevas. Mismo motivo que la
    #: ruta: lo que se fabrica todas las semanas se describe una vez, no en
    #: cada pedido. Ver `EspecificacionOrden`, que es donde acaba copiado.
    especificaciones = models.TextField(blank=True, default="")
    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "nombre_normalizado"],
                name="pieza_unica_por_linea",
            ),
            models.UniqueConstraint(
                fields=["nombre_normalizado"],
                condition=Q(linea__isnull=True),
                name="pieza_comun_unica",
            ),
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="pieza_legacy_unica",
            ),
        ]
        verbose_name = "pieza de catálogo"
        verbose_name_plural = "piezas de catálogo"

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


# ================================================================== núcleo


class OrdenProduccion(models.Model):
    """La orden, una sola vez para las cuatro líneas.

    Lo que difiere entre motores son exactamente tres cosas: a qué cliente
    apunta, unos pocos atributos propios de la línea y cómo se calcula el
    peso. Todo lo demás —folio, etapas, contadores, cierre, reversión— es
    idéntico y estaba cuadruplicado.

    Los atributos propios van a `atributos`, no a columnas. Los siete campos
    de geometría del corte láser estarían vacíos en tres de cada cuatro filas,
    y la alternativa ortodoxa (herencia con tabla por modelo) reintroduce un
    `JOIN` por consulta y, peor, devuelve el `isinstance` a los servicios, que
    es justo el problema que se está resolviendo.

    La regla para decidir: **si se filtra o se agrega, es columna; si sólo se
    muestra, es JSON.** Por eso `material` acabará siendo columna real cuando
    llegue el inventario, y `logo_ancho_mm` no.
    """

    class Estado(models.TextChoices):
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"
        CANCELADA = "cancelada", "Cancelada"

    linea = models.ForeignKey(LineaNegocio, on_delete=models.PROTECT, related_name="ordenes")
    #: Sale de una secuencia de PostgreSQL, no de «el último más uno». El
    #: sistema heredado calculaba el folio contando filas, así que dos
    #: usuarios a la vez obtenían el mismo, y tras purgar una orden se
    #: reutilizaban folios que ya estaban impresos y firmados en un acuse.
    folio = models.CharField(max_length=30, unique=True, db_index=True)
    codigo = models.CharField(max_length=60, blank=True, default="")
    codigo_normalizado = models.CharField(max_length=60, blank=True, default="", db_index=True)

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, null=True, blank=True, related_name="ordenes"
    )
    obra = models.ForeignKey(
        Obra, on_delete=models.PROTECT, null=True, blank=True, related_name="ordenes"
    )
    pieza = models.ForeignKey(
        PiezaCatalogo, on_delete=models.PROTECT, null=True, blank=True, related_name="ordenes"
    )

    nombre = models.CharField(max_length=180, blank=True, default="")
    descripcion = models.CharField(max_length=255, blank=True, default="")
    observaciones = models.CharField(max_length=255, blank=True, default="")

    total_piezas = models.PositiveIntegerField(default=1)
    cantidad_objetivo = models.PositiveIntegerField(default=1)

    #: Contadores. A partir de aquí son **caché**: el valor bueno se obtiene
    #: sumando los eventos. `recalcular_contadores` los reconstruye y
    #: `verificar_backfill` comprueba que coincidan.
    cantidad_producida = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_pintada = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_terminada = models.PositiveIntegerField(default=0, db_index=True)

    #: Seis decimales, no tres. El sistema heredado guarda el peso **de la
    #: orden**; aquí se guarda el de una pieza, y dividir a tres decimales
    #: pierde gramos que reaparecen multiplicados por el número de piezas: una
    #: orden de cuatro piezas de 6.518 kg volvía a salir como 6.520. Sobre
    #: toneladas eso es dinero, y `verificar_backfill` lo detectó antes de que
    #: nadie lo viera en un informe.
    peso_kg_unitario = models.DecimalField(
        max_digits=15, decimal_places=6, default=Decimal("0.000000")
    )

    fecha_compromiso = models.DateField(null=True, blank=True, db_index=True)
    prioridad = models.PositiveSmallIntegerField(default=3, db_index=True)

    etapa_actual = models.ForeignKey(
        Etapa, on_delete=models.PROTECT, null=True, blank=True, related_name="ordenes"
    )
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.ABIERTA, db_index=True
    )

    cierre_pendiente_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_hasta = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_por = models.CharField(max_length=150, blank=True, default="")
    cierre_etapa_previa = models.ForeignKey(
        Etapa, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cierre_bloqueado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_revertido_en = models.DateTimeField(null=True, blank=True)
    cierre_revertido_por = models.CharField(max_length=150, blank=True, default="")

    #: Bloqueo optimista. Sube en cada escritura del servicio; quien manda una
    #: versión vieja recibe un conflicto en vez de pisar el trabajo de otro.
    version = models.PositiveIntegerField(default=0)

    atributos = models.JSONField(default=dict, blank=True)

    #: Por qué etapas pasa **esta** orden. Lista de códigos de `Etapa`.
    #:
    #: Vacía significa «las de su línea, todas», que es lo que hacía el
    #: sistema y sigue siendo lo normal. Ponerla es decir «esta orden no lleva
    #: pintura»: se corta, se suelda y se entrega.
    #:
    #: Hasta ahora la secuencia estaba configurada **por línea**, así que
    #: todas las órdenes recorrían las mismas etapas. Cuando una no llevaba
    #: pintura, en el taller se la pasaba por pintura igual y se declaraba sin
    #: pintar nada: el sistema registraba una etapa que no ocurrió, y todo lo
    #: que se calcula encima —tiempos, coste, quién hizo qué, cuánto le
    #: falta— quedaba contaminado por un dato falso.
    #:
    #: Va aquí y no en `atributos` porque se filtra y se recorre: es la
    #: diferencia entre una columna y un cajón de sastre.
    ruta = models.JSONField(default=list, blank=True)

    #: De qué fila heredada salió. Es lo que hace la migración idempotente y
    #: reversible: se puede volver a correr sin duplicar, y se puede comparar
    #: fila a fila contra el original mientras convivan las dos.
    legacy_modelo = models.CharField(max_length=40, blank=True, default="", db_index=True)
    legacy_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    #: Cuándo se retiró, porque la fila heredada de la que salió ya no existe.
    #:
    #: En el sistema heredado una pieza se puede borrar, y cuando eso pasa su
    #: copia aquí queda sin origen. La reconciliación lo notaba —«heredado
    #: ausente, núcleo presente»— pero no tenía forma de arreglarlo: volver a
    #: reflejar una fila que ya no está no hace nada, así que la diferencia se
    #: repetía todos los días y la racha de siete jornadas limpias que exige
    #: el corte no llegaba nunca.
    #:
    #: Se marca en vez de borrar. La orden ya no se compara ni sale en
    #: producción, pero su historial se queda: para eso es un registro que
    #: sólo crece. Si la fila heredada reaparece, el reflejo vuelve a poner
    #: esto en nulo y la orden revive.
    retirada_en = models.DateTimeField(null=True, blank=True, db_index=True)

    creado_por = models.CharField(max_length=150, blank=True, default="")
    ultimo_cambio = models.DateTimeField(null=True, blank=True, db_index=True)
    creado_en = models.DateTimeField(db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="orden_legacy_unica",
            ),
        ]
        indexes = [
            models.Index(fields=["linea", "estado", "etapa_actual"], name="orden_tablero_idx"),
            models.Index(fields=["linea", "codigo_normalizado"], name="orden_codigo_idx"),
        ]
        verbose_name = "orden de producción"
        verbose_name_plural = "órdenes de producción"

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or "").strip()
        self.codigo_normalizado = self.codigo.upper()
        self.nombre = (self.nombre or "").strip()
        if int(self.total_piezas or 0) <= 0:
            self.total_piezas = 1
        if int(self.cantidad_objetivo or 0) <= 0:
            self.cantidad_objetivo = int(self.total_piezas)
        super().save(*args, **kwargs)

    @property
    def es_orden_grande(self) -> bool:
        """Si se lleva por contadores en vez de por etapas."""
        return int(self.total_piezas or 1) >= int(self.linea.piezas_minimas_orden_grande)

    @property
    def peso_kg_total(self) -> Decimal:
        return (self.peso_kg_unitario or Decimal("0")) * int(self.total_piezas or 1)

    @property
    def contadores_coherentes(self) -> bool:
        """¿Se cumple terminadas ≤ pintadas ≤ producidas ≤ objetivo?

        En el sistema heredado no existe esta comprobación en ningún sitio, ni
        en el navegador ni en el servidor ni en la base, así que se puede
        guardar «soldadas 0, pintadas 0, terminadas 50». El servicio la exige
        para lo nuevo; esta propiedad sirve para medir lo que ya había.
        """
        return (
            self.cantidad_terminada <= self.cantidad_pintada <= self.cantidad_producida
            and self.cantidad_producida <= self.cantidad_objetivo
        )

    def __str__(self) -> str:
        return f"{self.folio} · {self.codigo or self.nombre}"


class EventoProduccion(models.Model):
    """El historial. Sólo se añade: nunca se actualiza y nunca se borra.

    Cuatro propiedades, cada una resuelve un fallo concreto del sistema
    heredado:

    **Se guarda el incremento, no el total.** Hoy el navegador manda
    `terminadas=50` y el servidor calcula la diferencia contra lo que había.
    Dos pestañas abiertas mandan las dos el mismo total y el stock se duplica.
    Con incrementos, dos «+5» son +10, que es lo correcto, y no hace falta
    ningún bloqueo para que lo sea.

    **`clave_idempotencia`.** El celular del taller reenvía cuando la red
    falla; con la clave, el reintento no hace nada. Es también lo que permite
    encolar los avances sin señal y sincronizarlos después.

    **Corregir es insertar el evento contrario**, no editar el anterior. Un
    acuse firmado no desaparece del historial: se anula, y queda constancia de
    las dos cosas.

    **Los contadores se derivan de aquí.** Pasan a ser caché verificable.
    """

    class Tipo(models.TextChoices):
        CREACION = "creacion", "Alta de la orden"
        CAMBIO_ETAPA = "cambio_etapa", "Cambio de etapa"
        AVANCE = "avance", "Avance de piezas"
        CIERRE_PENDIENTE = "cierre_pendiente", "Cierre pendiente"
        CIERRE_FIRME = "cierre_firme", "Cierre en firme"
        REVERSION_CIERRE = "reversion_cierre", "Reversión de cierre"
        AJUSTE = "ajuste", "Ajuste"
        CANCELACION = "cancelacion", "Cancelación"
        ANULACION = "anulacion", "Anulación de un evento"

    class Contador(models.TextChoices):
        NINGUNO = "", "—"
        PRODUCIDA = "producida", "Producidas"
        PINTADA = "pintada", "Pintadas"
        TERMINADA = "terminada", "Terminadas"

    orden = models.ForeignKey(
        OrdenProduccion, on_delete=models.PROTECT, related_name="eventos"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)

    etapa = models.ForeignKey(
        Etapa, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    etapa_anterior = models.ForeignKey(
        Etapa, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    #: Cuál de los tres contadores mueve este evento. Vacío si no mueve
    #: ninguno.
    contador = models.CharField(
        max_length=12, choices=Contador.choices, blank=True, default="", db_index=True
    )
    #: El incremento, con signo. Nunca un total absoluto.
    delta_cantidad = models.IntegerField(default=0)
    #: Cuánto quedó después. Redundante a propósito: permite detectar una
    #: divergencia entre el historial y la caché sin recorrer toda la serie.
    cantidad_resultante = models.IntegerField(null=True, blank=True)

    motivo = models.ForeignKey(
        MotivoEvento, on_delete=models.PROTECT, null=True, blank=True, related_name="eventos"
    )
    comentario = models.CharField(max_length=255, blank=True, default="")

    actor_username = models.CharField(max_length=150, blank=True, default="", db_index=True)
    #: La fecha que declara el operador, que no siempre es la de hoy.
    fecha_operacion = models.DateField(null=True, blank=True, db_index=True)
    #: Cuándo ocurrió de verdad. En los eventos reconstruidos es la fecha del
    #: registro heredado.
    ocurrido_en = models.DateTimeField(db_index=True)
    #: Cuándo se escribió esta fila. En los reconstruidos es la fecha de la
    #: migración, y por eso son dos campos y no uno.
    registrado_en = models.DateTimeField(auto_now_add=True)

    clave_idempotencia = models.CharField(
        max_length=120, unique=True, null=True, blank=True
    )
    anula_a = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="anulado_por"
    )
    #: Marca honesta: este evento se dedujo porque no había historial que
    #: reconstruir. Inventar fechas y autores plausibles destruiría
    #: exactamente la trazabilidad que justifica todo esto.
    sin_historico = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict, blank=True)

    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["orden", "ocurrido_en", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="evento_legacy_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["orden", "ocurrido_en"], name="evento_orden_fecha_idx"),
            models.Index(fields=["tipo", "ocurrido_en"], name="evento_tipo_fecha_idx"),
        ]
        verbose_name = "evento de producción"
        verbose_name_plural = "eventos de producción"

    def __str__(self) -> str:
        return f"{self.orden.folio} · {self.tipo} · {self.ocurrido_en:%Y-%m-%d %H:%M}"


class Asignacion(models.Model):
    """Quién y con qué máquina, una sola tabla donde había cinco.

    `HerrAsignacion`, `HerrOrdenAsignacion`, `LaserAsignacion`,
    `LaserOrdenAsignacion`, `RobotOrdenAsignacion` y `VigaAsignacion` son la
    misma idea seis veces.

    `fraccion_peso` es nueva y arregla un error del tablero: hoy a cada
    colaborador de una viga se le apunta el peso completo de la pieza, así que
    la misma tonelada se cuenta tantas veces como personas la tocaron. En
    herrería y robótica sí se divide. Con una fracción explícita deja de
    depender de la línea.
    """

    orden = models.ForeignKey(
        OrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones"
    )
    etapa = models.ForeignKey(
        Etapa, on_delete=models.PROTECT, null=True, blank=True, related_name="asignaciones"
    )
    rol = models.CharField(max_length=30, blank=True, default="", db_index=True)
    colaborador = models.ForeignKey(
        "catalogos.Colaborador", on_delete=models.PROTECT, null=True, blank=True,
        related_name="asignaciones_nucleo",
    )
    maquina = models.ForeignKey(
        "catalogos.Maquina", on_delete=models.PROTECT, null=True, blank=True,
        related_name="asignaciones_nucleo",
    )
    fraccion_peso = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("1.0000")
    )
    vigente = models.BooleanField(default=True, db_index=True)
    asignado_por = models.CharField(max_length=150, blank=True, default="")
    asignado_en = models.DateTimeField()
    retirado_en = models.DateTimeField(null=True, blank=True)

    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-asignado_en", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="asignacion_legacy_unica",
            ),
        ]
        # No se pone aquí una restricción de «una asignación vigente por
        # persona, orden y etapa» aunque sea deseable: las seis tablas
        # heredadas se solapan y hay duplicados reales. Imponerla durante el
        # volcado sería cambiar los datos escondiéndolo en una migración. La
        # exige el servicio para lo que se escriba a partir de ahora, y
        # `verificar_backfill` cuenta lo que ya había.
        indexes = [
            models.Index(
                fields=["colaborador", "vigente"], name="asignacion_persona_idx"
            ),
        ]
        verbose_name = "asignación"
        verbose_name_plural = "asignaciones"

    def __str__(self) -> str:
        return f"{self.orden.folio} · {self.etapa_id and self.etapa.codigo} · {self.colaborador}"


class EventoMaquina(models.Model):
    """Paros y fallas en una sola tabla.

    `MaquinaParo` y `MaquinaFalla` son campo por campo el mismo modelo con
    otro nombre, y cada uno tiene su propio catálogo de motivos, su propia
    vista y su propia consulta en el tablero.
    """

    class Clase(models.TextChoices):
        PARO = "paro", "Paro"
        FALLA = "falla", "Falla"

    maquina = models.ForeignKey(
        "catalogos.Maquina", on_delete=models.PROTECT, related_name="eventos_nucleo"
    )
    clase = models.CharField(max_length=10, choices=Clase.choices, db_index=True)
    motivo = models.ForeignKey(
        MotivoEvento, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField(null=True, blank=True, db_index=True)
    comentario = models.CharField(max_length=255, blank=True, default="")
    registrado_por = models.CharField(max_length=150, blank=True, default="")
    evento_planta = models.ForeignKey(
        "catalogos.PlantaEvento", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos_nucleo",
    )

    legacy_modelo = models.CharField(max_length=40, blank=True, default="")
    legacy_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-inicio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(legacy_id__isnull=False),
                name="eventomaquina_legacy_unico",
            ),
            #: Una máquina no puede tener dos paros abiertos a la vez. El
            #: sistema heredado lo garantiza con la misma restricción, y hay
            #: que conservarla: sin ella, arreglar el fallo del registro de
            #: paros habría permitido que dos operadores abrieran dos.
            models.UniqueConstraint(
                fields=["maquina", "clase"],
                condition=Q(fin__isnull=True),
                name="eventomaquina_uno_abierto_por_maquina",
            ),
        ]
        verbose_name = "evento de máquina"
        verbose_name_plural = "eventos de máquina"

    def __str__(self) -> str:
        return f"{self.maquina} · {self.clase} · {self.inicio:%Y-%m-%d %H:%M}"


class DivergenciaReconciliacion(models.Model):
    """Lo que la reconciliación en sombra encontró distinto.

    Durante la convivencia, un trabajo diario compara cada orden heredada con
    su copia del núcleo campo por campo. No se avanza al corte de una línea
    hasta que esta tabla lleve siete días seguidos vacía para ella. Este
    control es lo que convierte la migración en algo aburrido en vez de
    heroico.
    """

    detectada_en = models.DateTimeField(auto_now_add=True, db_index=True)
    linea = models.ForeignKey(LineaNegocio, on_delete=models.CASCADE, related_name="+")
    legacy_modelo = models.CharField(max_length=40)
    legacy_id = models.PositiveIntegerField()
    orden = models.ForeignKey(
        OrdenProduccion, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    campo = models.CharField(max_length=60)
    valor_heredado = models.CharField(max_length=255, blank=True, default="")
    valor_nucleo = models.CharField(max_length=255, blank=True, default="")
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detectada_en", "id"]
        indexes = [
            models.Index(fields=["linea", "detectada_en"], name="divergencia_linea_idx"),
        ]
        verbose_name = "divergencia"
        verbose_name_plural = "divergencias"

    def __str__(self) -> str:
        return f"{self.legacy_modelo}#{self.legacy_id}.{self.campo}"


class EspecificacionOrden(models.Model):
    """Cómo se hace esta orden, escrito para quien la va a hacer.

    En el celular, un soldador veía «V-118 · 3/50 · Obra Norte». Eso dice
    cuál es la pieza, no cómo es. Lo que hace falta en la mano es el detalle:
    «vigas de 70 cm con un corte a los 30 cm a noventa grados». Hoy eso viaja
    en un plano impreso, o de boca en boca, y por eso se rehacen piezas.

    Va en una tabla aparte y no como columna de la orden por dos razones:

    - `vigas` es una tabla heredada declarada `managed = False`. Este sistema
      no le añade columnas a las tablas del legado: la regla es que revertir
      el código deje la base en pie sin tocarla.
    - La única columna larga que existe en el legado es `descripcion`, que ya
      se usa para otra cosa —el nombre de la pieza— y en herrería son 255
      caracteres. No caben unas instrucciones.

    Y no cuelga de `OrdenProduccion` a propósito, aunque la ruta sí lo haga.
    La ruta es configuración: si el motor unificado todavía no está encendido
    en ese servidor, la orden recorre las etapas de siempre y no se pierde
    nada. Esto es contenido que alguien escribió, y tiene que poder
    escribirse y leerse desde el primer día, con el motor encendido o
    apagado. Por eso se apunta a la fila heredada directamente.
    """

    legacy_modelo = models.CharField(max_length=40)
    legacy_id = models.PositiveIntegerField()
    texto = models.TextField(blank=True, default="")
    actualizado_por = models.CharField(max_length=120, blank=True, default="")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["legacy_modelo", "legacy_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                name="especificacion_unica_por_orden",
            ),
        ]
        verbose_name = "especificación de la orden"
        verbose_name_plural = "especificaciones de las órdenes"

    def __str__(self) -> str:
        return f"{self.legacy_modelo}#{self.legacy_id}"


class NivelMinimo(models.Model):
    """Cuánto hay que tener siempre de un producto terminado.

    El taller vende de almacén: un cliente pide cuarenta andamios, hay
    treinta, y la respuesta tiene que darse en el momento. Hasta ahora nadie
    podía saber que quedaban pocos hasta que se acababan, porque el almacén de
    producto terminado guarda un solo número por producto y ese número no se
    compara con nada.

    Aquí se guarda con qué compararlo. Debajo del mínimo, el producto sale
    marcado en la lista y en el aviso de la portada.

    **Tabla propia y no una columna del catálogo de piezas.** El almacén de
    Corta guarda el producto como texto libre y no siempre tiene ficha de
    catálogo; el de herrería sí. Colgar el mínimo del catálogo dejaría media
    planta sin poder fijarlo. La clave es la que las dos líneas comparten de
    verdad: la línea y el nombre normalizado del producto.
    """

    #: `herreria` o `corta`. Cadena y no clave foránea a `LineaNegocio` para
    #: que esto funcione en un servidor donde el motor unificado todavía no se
    #: ha sembrado: un mínimo de almacén no tiene por qué esperar a eso.
    linea = models.SlugField(max_length=30)
    producto = models.CharField(max_length=180)
    #: En mayúsculas y sin espacios de sobra, igual que en los dos almacenes.
    producto_normalizado = models.CharField(max_length=180, db_index=True)
    #: Por debajo de esto, el producto se marca. Cero significa «no avisar»,
    #: que es distinto de no tener fila: una fila en cero es alguien que lo
    #: pensó y decidió que no hace falta.
    minimo = models.PositiveIntegerField(default=0)
    #: Cuánto conviene tener cuando se manda a fabricar. Vacío significa que
    #: nadie lo dijo y la sugerencia se limita a reponer hasta el mínimo.
    objetivo = models.PositiveIntegerField(null=True, blank=True)
    nota = models.CharField(max_length=200, blank=True, default="")
    actualizado_por = models.CharField(max_length=120, blank=True, default="")
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["linea", "producto"]
        constraints = [
            models.UniqueConstraint(
                fields=["linea", "producto_normalizado"],
                name="minimo_unico_por_producto",
            ),
        ]
        verbose_name = "nivel mínimo de almacén"
        verbose_name_plural = "niveles mínimos de almacén"

    def save(self, *args, **kwargs):
        self.producto = (self.producto or "").strip()
        self.producto_normalizado = self.producto.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.producto}: mínimo {self.minimo}"


class RequerimientoProyecto(models.Model):
    """Qué lleva un proyecto, dicho antes de que exista ninguna orden.

    Hoy un proyecto es un nombre y nada más. Lo que se sabe de él se deduce de
    las órdenes que alguien escribió con ese nombre encima, así que la
    pregunta que se hace en la obra —«¿cómo va Matilda?»— sólo se puede
    contestar a medias: se ve lo que se está fabricando, pero no lo que falta,
    porque nadie apuntó nunca cuánto había que fabricar.

    Aquí se apunta. «Matilda lleva 27 vigas IPR y 40 placas base.» A partir de
    eso, el avance es una resta: lo requerido menos lo terminado.

    **Lo requerido no se convierte en órdenes.** Es a propósito: quien recibe
    el proyecto sabe qué se vendió, y quien programa la producción decide
    cuándo y en qué lotes se hace. Convertirlo automáticamente pondría en el
    piso trabajo que nadie ha planeado.

    El cruce con la producción se hace por el código. Si el requerimiento dice
    `V-118` y en el proyecto hay veintisiete vigas con ese código, ésas son
    las suyas. Sin código, el renglón se queda solo y sirve de recordatorio:
    es mejor que fingir un avance que nadie ha comprobado.
    """

    proyecto = models.ForeignKey(
        "catalogos.Proyecto", on_delete=models.CASCADE, related_name="requerimientos"
    )
    #: Qué es, en las palabras de quien lo vendió.
    descripcion = models.CharField(max_length=180)
    #: Con qué se cruza contra la producción. Vacío significa que todavía no
    #: se sabe cómo se va a codificar, y entonces no se cruza con nada.
    codigo = models.CharField(max_length=60, blank=True, default="")
    codigo_normalizado = models.CharField(max_length=60, blank=True, default="", db_index=True)
    cantidad = models.PositiveIntegerField(default=1)
    fecha_compromiso = models.DateField(null=True, blank=True)
    nota = models.CharField(max_length=255, blank=True, default="")
    creado_por = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["proyecto", "descripcion"]
        constraints = [
            #: Dos renglones con el mismo código en el mismo proyecto se
            #: cruzarían los dos con la misma producción y el avance saldría
            #: contado por duplicado.
            models.UniqueConstraint(
                fields=["proyecto", "codigo_normalizado"],
                condition=~Q(codigo_normalizado=""),
                name="requerimiento_codigo_unico_por_proyecto",
            ),
        ]
        verbose_name = "requerimiento del proyecto"
        verbose_name_plural = "requerimientos del proyecto"

    def save(self, *args, **kwargs):
        from core.constantes import clave_de_codigo

        self.descripcion = (self.descripcion or "").strip()
        self.codigo = (self.codigo or "").strip()
        # Sin guiones ni espacios: en el taller el mismo perfil se escribe
        # «V-118», «V118» y «v 118» según quién lo teclee, y con la
        # comparación literal el requerimiento no encontraba su producción.
        self.codigo_normalizado = clave_de_codigo(self.codigo)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.proyecto}: {self.descripcion} x{self.cantidad}"


# ======================================================== entrega entre áreas
#
# Quién entregó, quién recibió, y quién firmó que estaba bien.


class ActaDeEntrega(models.Model):
    """El traspaso de una pieza de un área a la siguiente, firmado por los dos.

    El problema que resuelve es de responsabilidad, no de registro. Hoy, si
    llegan a pintura dos vigas que debían medir un metro y miden noventa
    centímetros, el sistema sabe que la pieza pasó por corte y por soldadura,
    pero no sabe **quién dijo que estaba bien**. Y en un taller esa es la
    pregunta que importa: no «dónde se rompió», sino «quién lo revisó y lo dio
    por bueno».

    Así que el traspaso deja de ser un cambio de estado y pasa a ser un acto
    con dos partes:

    - **Quien entrega** dice que revisó que la pieza quedó como se pidió, y lo
      firma con el dedo.
    - **Quien recibe** ve qué le entregan y quién lo firmó, y decide: la acepta
      —y la firma, y entonces es suya— o la devuelve diciendo qué está mal.

    De ahí salen las tres cosas que el taller pidió poder contestar:

    1. Quién entregó mal: el `entrega_por` de las actas rechazadas.
    2. Quién aceptó lo que estaba mal: el `recibe_por` del acta anterior de esa
       misma pieza, que firmó que estaba bien y no lo estaba. Es el «que la
       cobren entre los dos».
    3. Quién revisa de verdad: el `rechazada_por`. **Devolver una pieza mala no
       es una falta, es el trabajo bien hecho**, y el indicador lo cuenta a
       favor. Si contara en contra, nadie devolvería nada y todo el mecanismo
       se apagaría en una semana.

    Sobre guardar la firma como texto
    ---------------------------------

    El trazo se guarda como imagen PNG en línea (`data:image/png;base64,...`)
    dentro de una columna de texto, no como archivo en disco. Una firma de
    dedo son unos pocos kilobytes; a este taller le salen del orden de dos por
    pieza y etapa, que en un año no llegan a los cientos de megas. A cambio, la
    firma viaja en el mismo respaldo que el resto —un acta cuya imagen se
    quedó en un disco que nadie respaldó no prueba nada—, no hay archivos
    huérfanos que limpiar, y no hay una URL adivinable con la firma de nadie.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Esperando a que la reciban"
        ACEPTADA = "aceptada", "Recibida y firmada"
        RECHAZADA = "rechazada", "Devuelta"

    #: A qué fila apunta, con el mismo par que usa el resto del núcleo.
    legacy_modelo = models.CharField(max_length=40)
    legacy_id = models.PositiveIntegerField()
    #: El código visible, copiado. Un acta se lee años después, cuando la fila
    #: de origen puede haberse renombrado.
    codigo = models.CharField(max_length=120, blank=True, default="")

    #: Las áreas, no las etapas: el traspaso es de corte a soldadura, y da
    #: igual si por dentro se llamó «Espera de armado».
    area_origen = models.CharField(max_length=40)
    area_destino = models.CharField(max_length=40)
    etapa_origen = models.CharField(max_length=40, blank=True, default="")
    etapa_destino = models.CharField(max_length=40, blank=True, default="")

    entrega_por = models.CharField(max_length=150, db_index=True)
    entrega_firma = models.TextField(blank=True, default="")
    entregado_en = models.DateTimeField(db_index=True)

    recibe_por = models.CharField(max_length=150, blank=True, default="", db_index=True)
    recibe_firma = models.TextField(blank=True, default="")
    recibido_en = models.DateTimeField(null=True, blank=True)

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True
    )
    #: Qué está mal, en palabras de quien lo devolvió. Obligatorio al rechazar:
    #: una devolución sin motivo no le sirve a quien tiene que corregirla.
    motivo = models.TextField(blank=True, default="")

    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-entregado_en"]
        indexes = [
            models.Index(fields=["legacy_modelo", "legacy_id", "entregado_en"]),
            models.Index(fields=["estado", "entregado_en"]),
        ]
        constraints = [
            # Una pieza no puede tener dos entregas esperando a la vez. Sin
            # esto, dos avances seguidos dejarían dos actas abiertas y quien
            # recibiera firmaría una cualquiera de las dos.
            models.UniqueConstraint(
                fields=["legacy_modelo", "legacy_id"],
                condition=Q(estado="pendiente"),
                name="una_entrega_pendiente_por_pieza",
            ),
        ]
        verbose_name = "acta de entrega"
        verbose_name_plural = "actas de entrega"

    def __str__(self) -> str:
        return f"{self.codigo or self.legacy_id}: {self.area_origen} → {self.area_destino}"

    @property
    def esta_pendiente(self):
        return self.estado == self.Estado.PENDIENTE

    @property
    def fue_devuelta(self):
        return self.estado == self.Estado.RECHAZADA

    @property
    def espera_desde_hace(self):
        """Cuánto lleva esperando a que alguien la reciba, en segundos."""
        if not self.esta_pendiente:
            return None
        from django.utils import timezone

        return (timezone.now() - self.entregado_en).total_seconds()
