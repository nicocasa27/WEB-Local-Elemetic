"""Cuánto cuesta de verdad cada orden, y en qué se diferencia de lo previsto.

Hoy el sistema no sabe lo que cuesta nada. Sabe kilos y sabe fechas, pero no
hay ni una tarifa, ni un tiempo estándar, ni forma de responder «¿ganamos
dinero con esta orden?». Se decide por intuición y por el precio de la
competencia.

Este módulo lo calcula, y **no pide capturar nada nuevo al operador**. Las
tres fuentes ya existen:

- **El material** sale del lote consumido, con el costo que tenía ese lote.
- **Las horas** salen del historial del núcleo: el tiempo entre el evento que
  entra a una etapa y el que sale, descontando los paros de máquina y el
  tiempo fuera de jornada. Por eso el registro de eventos y el calendario
  laboral tenían que existir antes que esto: sin ellos, las horas habría que
  ficharlas aparte, y eso no lo sostiene nadie.
- **Quién trabajó** sale de las asignaciones.

Lo único que hay que capturar es la **tarifa**: cuánto cuesta una hora de cada
centro. Se captura una vez y se versiona.

Dos decisiones de diseño que conviene entender antes de leer el código:

**Las tarifas no se editan: se versionan.** Cambiar la tarifa de hoy no puede
cambiar lo que costó una orden del año pasado. Cada tarifa tiene una fecha
desde la que rige, y el cálculo busca la que estaba vigente el día que se
hizo el trabajo. Una tarifa guardada es inmutable.

**El costo declara cuánto de la orden pudo medir.** Si una etapa no tiene
asignado a nadie, sus horas de mano de obra no se pueden calcular, y este
módulo **no se inventa un operador**: pone cero y baja la cobertura. Un costo
que parece completo cuando en realidad midió la mitad es peor que no tener
costo, porque se usa para cotizar.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q


class CentroCosto(models.Model):
    """Dónde se consume el tiempo: una línea, una celda, un grupo de máquinas.

    Se empieza con uno por línea de negocio, que es la granularidad que el
    taller puede sostener hoy. Partirlo más adelante no rompe el histórico,
    porque las tarifas van con fecha.
    """

    codigo = models.SlugField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    linea = models.ForeignKey(
        "nucleo.LineaNegocio", on_delete=models.PROTECT, null=True, blank=True,
        related_name="centros_costo",
    )
    #: Tope de horas que se cobran por cada paso de una orden por una etapa.
    #:
    #: Hace falta porque el historial dice cuánto tiempo **pasó** una orden en
    #: una etapa, no cuánto se **trabajó** en ella. Son cosas distintas: una
    #: orden puede quedarse en pintura tres meses esperando material sin que
    #: nadie la toque. Sin tope, esa orden acumula todas las horas laborables
    #: de esos tres meses y sale costando lo que no costó: al probarlo con los
    #: datos del taller, una orden real daba 671 horas de pintura y 191.274
    #: pesos.
    #:
    #: El tope no mide nada: acota la ignorancia. Mientras no haya tiempos
    #: estándar capturados o una señal de inicio y fin, no se puede separar el
    #: trabajo de la espera, y lo honesto es poner un límite visible y decir
    #: cuántas etapas lo tocaron. Por omisión, una jornada.
    horas_max_por_visita = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("9.00")
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "centro de costo"
        verbose_name_plural = "centros de costo"

    def __str__(self) -> str:
        return self.nombre


class Tarifa(models.Model):
    """Cuánto cuesta una hora en un centro, a partir de una fecha.

    **Es inmutable.** Corregir una tarifa es crear otra con fecha nueva, no
    editar la anterior: si se pudiera editar, el costo de una orden cerrada
    cambiaría solo cada vez que sube el sueldo de alguien, y el histórico
    dejaría de servir para comparar.
    """

    centro = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, related_name="tarifas")
    vigente_desde = models.DateField(db_index=True)
    #: Costo de tener la máquina encendida una hora: energía, consumibles,
    #: depreciación, mantenimiento.
    costo_hora_maquina = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Tarifa de mano de obra que se usa cuando el colaborador no tiene una
    #: propia.
    costo_hora_mano_obra = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Gastos indirectos por hora-máquina: renta, supervisión, administración.
    #: Se prorratea por horas-máquina y no por toneladas porque una pieza
    #: pequeña y difícil ocupa la máquina igual que una grande y sencilla, y
    #: prorratear por peso se la regala al cliente equivocado.
    overhead_hora = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    moneda = models.CharField(max_length=3, default="MXN")
    notas = models.CharField(max_length=255, blank=True, default="")
    creado_por = models.CharField(max_length=150, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["centro", "-vigente_desde"]
        constraints = [
            models.UniqueConstraint(
                fields=["centro", "vigente_desde"], name="tarifa_unica_por_fecha"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.centro.codigo} desde {self.vigente_desde}"


class TarifaManoObra(models.Model):
    """Lo que cuesta una hora de una persona concreta, o de un rol.

    Con la persona se afina; con el rol basta para empezar. Si no hay ninguna
    de las dos, se usa la del centro.
    """

    colaborador = models.ForeignKey(
        "catalogos.Colaborador", on_delete=models.PROTECT, null=True, blank=True,
        related_name="tarifas_costeo",
    )
    rol = models.CharField(max_length=40, blank=True, default="", db_index=True)
    vigente_desde = models.DateField(db_index=True)
    costo_hora = models.DecimalField(max_digits=12, decimal_places=4)
    notas = models.CharField(max_length=255, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-vigente_desde"]
        constraints = [
            models.UniqueConstraint(
                fields=["colaborador", "vigente_desde"],
                condition=Q(colaborador__isnull=False),
                name="tarifa_persona_unica_por_fecha",
            ),
            models.UniqueConstraint(
                fields=["rol", "vigente_desde"],
                condition=Q(colaborador__isnull=True),
                name="tarifa_rol_unica_por_fecha",
            ),
        ]
        verbose_name = "tarifa de mano de obra"
        verbose_name_plural = "tarifas de mano de obra"

    def __str__(self) -> str:
        quien = self.colaborador or self.rol or "(general)"
        return f"{quien} desde {self.vigente_desde}"


class TiempoEstandar(models.Model):
    """Cuánto **debería** tardar una pieza en una etapa.

    Sin esto se puede saber lo que costó una orden, pero no si eso es mucho o
    poco, que es la pregunta útil. La varianza entre lo real y esto es el
    informe que dice dónde se pierde dinero.
    """

    pieza = models.ForeignKey(
        "nucleo.PiezaCatalogo", on_delete=models.CASCADE, related_name="tiempos_estandar"
    )
    etapa = models.ForeignKey(
        "nucleo.Etapa", on_delete=models.CASCADE, related_name="tiempos_estandar"
    )
    horas_por_pieza = models.DecimalField(max_digits=10, decimal_places=4)
    #: Cuántas personas se supone que trabajan a la vez en esa etapa.
    operadores = models.PositiveSmallIntegerField(default=1)
    vigente_desde = models.DateField(db_index=True)
    notas = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["pieza", "etapa__orden", "-vigente_desde"]
        constraints = [
            models.UniqueConstraint(
                fields=["pieza", "etapa", "vigente_desde"],
                name="tiempo_estandar_unico",
            ),
        ]
        verbose_name = "tiempo estándar"
        verbose_name_plural = "tiempos estándar"

    def __str__(self) -> str:
        return f"{self.pieza} · {self.etapa.codigo}: {self.horas_por_pieza} h"


class CostoOrden(models.Model):
    """El costo calculado de una orden. Se puede recalcular cuando se quiera.

    No es un asiento contable: es una foto derivada del historial, las tarifas
    y los consumos. Si mañana se corrige una tarifa vieja o aparece un consumo
    que faltaba, se vuelve a calcular y sale otro número, que además es el
    bueno.
    """

    class Metodo(models.TextChoices):
        ABSORCION = "absorcion", "Absorbente (incluye indirectos)"
        DIRECTO = "directo", "Directo (sólo material, obra y máquina)"

    orden = models.OneToOneField(
        "nucleo.OrdenProduccion", on_delete=models.CASCADE, related_name="costo"
    )
    metodo = models.CharField(
        max_length=12, choices=Metodo.choices, default=Metodo.ABSORCION
    )

    material = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    mano_obra = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    maquina = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    overhead = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    total = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))

    horas_maquina = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    horas_persona = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Tiempo de ciclo: lo que la orden tardó en atravesar el taller, sin
    #: topes. No se cobra, pero es la medida real del flujo y la que dice
    #: cuánto de ese tiempo fue espera.
    horas_transcurridas = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )

    #: Lo que debería haber costado, según los tiempos estándar.
    costo_estandar = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0")
    )
    horas_estandar = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )

    #: Qué parte de la orden se pudo medir de verdad, entre cero y uno. Baja
    #: cuando hay etapas sin nadie asignado, sin tarifa o sin recorrer. Es el
    #: número que dice cuánto hay que fiarse del resto.
    cobertura = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0")
    )

    #: Llega con la integración comercial. Mientras tanto se puede capturar a
    #: mano para poder mirar el margen.
    precio_venta = models.DecimalField(
        max_digits=16, decimal_places=4, null=True, blank=True
    )

    #: Por qué el número es el que es: etapas sin asignación, sin tarifa,
    #: tramos descontados por paro. Sin esto, un costo raro no se puede
    #: explicar y por tanto no se puede corregir.
    detalle = models.JSONField(default=dict, blank=True)

    calculado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-calculado_en"]
        verbose_name = "costo de orden"
        verbose_name_plural = "costos de orden"

    @property
    def costo_unitario(self):
        piezas = max(int(self.orden.cantidad_objetivo or 1), 1)
        return (self.total / piezas).quantize(Decimal("0.0001"))

    @property
    def varianza(self):
        """Lo real menos lo estándar. Positivo es que costó de más."""
        if not self.costo_estandar:
            return None
        return (self.total - self.costo_estandar).quantize(Decimal("0.0001"))

    @property
    def varianza_horas(self):
        if not self.horas_estandar:
            return None
        return (self.horas_persona - self.horas_estandar).quantize(Decimal("0.0001"))

    @property
    def margen(self):
        if self.precio_venta is None:
            return None
        return (self.precio_venta - self.total).quantize(Decimal("0.0001"))

    @property
    def margen_porcentaje(self):
        if not self.precio_venta:
            return None
        return ((self.margen / self.precio_venta) * 100).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.orden.folio}: {self.total}"


class CostoEtapa(models.Model):
    """El desglose por etapa. Es donde se ve en qué paso se va el dinero."""

    costo = models.ForeignKey(CostoOrden, on_delete=models.CASCADE, related_name="etapas")
    etapa = models.ForeignKey("nucleo.Etapa", on_delete=models.PROTECT, related_name="+")

    #: Horas de jornada que la orden **pasó** en esta etapa, descontados los
    #: paros. Es tiempo de ciclo, no tiempo de trabajo, y sirve para medir el
    #: flujo: cuánto tarda de verdad una orden en atravesar el taller.
    horas_transcurridas = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Horas que se **cobran**, ya con el tope del centro aplicado. Es lo que
    #: multiplica la tarifa.
    horas = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    horas_descontadas_por_paro = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Si hubo que aplicar el tope. Cuando está marcado, el costo de esta
    #: etapa es una cota y no una medición.
    topada = models.BooleanField(default=False)
    personas = models.PositiveSmallIntegerField(default=0)

    mano_obra = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    maquina = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    overhead = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))

    horas_estandar = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("0")
    )
    #: Qué faltó para poder calcular bien esta etapa.
    avisos = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["etapa__orden"]
        constraints = [
            models.UniqueConstraint(fields=["costo", "etapa"], name="costo_etapa_unico"),
        ]
        verbose_name = "costo por etapa"
        verbose_name_plural = "costos por etapa"

    @property
    def total(self):
        return self.mano_obra + self.maquina + self.overhead

    @property
    def varianza_horas(self):
        if not self.horas_estandar:
            return None
        return (self.horas - self.horas_estandar).quantize(Decimal("0.0001"))

    def __str__(self) -> str:
        return f"{self.etapa.codigo}: {self.horas} h"
