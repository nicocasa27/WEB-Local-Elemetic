import json
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone


class Proyecto(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = self.nombre.upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class EquipoTrabajo(models.Model):
    nombre = models.CharField(max_length=120)
    area = models.CharField(max_length=120)
    sub_area = models.CharField(max_length=120, blank=True)
    estados_json = models.TextField(default="[]")
    integrantes = models.PositiveIntegerField()
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["area", "sub_area", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.area = (self.area or "").strip()
        self.sub_area = (self.sub_area or "").strip()
        if not self.estados_json:
            self.estados_json = "[]"
        super().save(*args, **kwargs)

    @property
    def estados(self):
        try:
            value = json.loads(self.estados_json or "[]")
        except Exception:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        return []

    @property
    def estados_texto(self) -> str:
        return ", ".join(self.estados)

    def __str__(self) -> str:
        return self.nombre


class PdfExtractionTemplate(models.Model):
    nombre = models.CharField(max_length=120)
    proyecto_normalizado = models.CharField(max_length=120, blank=True, db_index=True)
    config_json = models.TextField(default="{}")
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def __str__(self) -> str:
        return self.nombre


class VigaPlano(models.Model):
    viga_internal_id = models.PositiveIntegerField(unique=True, db_index=True)
    archivo_pdf = models.FileField(upload_to="planos_vigas/%Y/%m/%d")
    nombre_original = models.CharField(max_length=255, blank=True)
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-subido_en"]

    def __str__(self) -> str:
        return f"Viga {self.viga_internal_id}"


class WeeklyReportSnapshot(models.Model):
    week_start = models.DateField(unique=True, db_index=True)
    week_end = models.DateField(db_index=True)
    integrantes_total = models.PositiveIntegerField(default=0)
    payload_json = models.TextField(default="{}")
    generado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start"]

    def __str__(self) -> str:
        return f"{self.week_start} a {self.week_end}"


class Colaborador(models.Model):
    ROL_CHOICES = [
        ("Soldador", "Soldador"),
        ("Auxiliar", "Auxiliar"),
        ("Pintor", "Pintor"),
        ("Operador", "Operador"),
    ]

    nombre = models.CharField(max_length=120)
    rol = models.CharField(max_length=20, choices=ROL_CHOICES)
    equipo = models.ForeignKey(EquipoTrabajo, on_delete=models.PROTECT, related_name="colaboradores")
    activo = models.BooleanField(default=True)

    #: Cuenta con la que entra esta persona al sistema.
    #:
    #: Hasta ahora no había ninguna relación entre quien inicia sesión y la
    #: ficha del colaborador al que se le asigna el trabajo, así que el
    #: sistema no podía responder a «qué me toca a mí»: sólo sabía enseñar
    #: las trescientas órdenes del taller y que cada quien buscara la suya.
    #:
    #: No es una llave foránea porque los usuarios viven en otra base
    #: mientras no se unifiquen; se guarda el nombre de usuario. Vacío
    #: significa que esa persona todavía no tiene cuenta enlazada, que es lo
    #: normal el primer día.
    usuario = models.CharField(max_length=150, blank=True, db_index=True)

    # --- Recursos humanos -------------------------------------------------
    #
    # La ficha de la persona vive aquí y no en una tabla aparte a propósito.
    # Media persona en un sitio y media en otro acaba siendo dos personas: se
    # da de alta por un lado a quien ya estaba por el otro, y a partir de ahí
    # nadie sabe cuánta gente hay.
    #
    # Todo es opcional. Los colaboradores que ya existen no tienen ninguno de
    # estos datos, y el sistema tiene que seguir funcionando igual mientras
    # alguien los va completando.

    SEXO_CHOICES = [
        ("M", "Hombre"),
        ("F", "Mujer"),
        ("X", "Prefiere no decirlo"),
    ]

    sexo = models.CharField(max_length=1, choices=SEXO_CHOICES, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    fecha_ingreso = models.DateField(null=True, blank=True)
    telefono = models.CharField(max_length=40, blank=True, default="")
    departamento = models.ForeignKey(
        "personal.Departamento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="colaboradores",
    )
    puesto = models.ForeignKey(
        "personal.Puesto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="colaboradores",
    )
    #: Sueldo mensual bruto. `Decimal` y no `float`: es dinero, y en coma
    #: flotante 0.1 + 0.2 no da 0.3. Cero significa «sin capturar», que es lo
    #: que hay hoy para todo el mundo.
    sueldo_mensual = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["equipo__nombre", "rol", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class Maquina(models.Model):
    """Un equipo del piso. Es el «centro de trabajo» del que habla el taller.

    Faltaba Pintura. Corte y Soldadura estaban porque son las dos áreas que
    tienen máquina con nombre propio, pero pintura también es una estación por
    la que pasa la orden y en la que se registra quién trabajó: sin estar aquí,
    el avance de pintura no se podía atribuir a ningún sitio.
    """

    TIPO_CHOICES = [
        ("Corte", "Corte"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    nombre = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)

    #: Qué sabe hacer este equipo y hasta dónde llega.
    #:
    #: Los seis equipos de corte no son intercambiables: el plasma no corta lo
    #: que corta la láser, y la cinta tiene un grueso máximo. Sin este dato,
    #: elegir equipo al lanzar una orden es una lista de seis nombres sin
    #: criterio, y quien la llena tiene que acordarse de memoria de cuál
    #: aguanta la placa de 3/8.
    funcion = models.CharField(
        max_length=180, blank=True, default="",
        help_text="Qué corta o suelda este equipo. Ej.: «Placa hasta 25 mm»",
    )

    #: Cuánto rinde por hora, en la unidad que tenga sentido para el equipo.
    #: Cero es «no medido»: sirve para no inventar una capacidad que nadie
    #: cronometró.
    capacidad_hora = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Piezas, metros o kilos por hora. Cero si no se ha medido.",
    )
    capacidad_unidad = models.CharField(
        max_length=20, blank=True, default="",
        help_text="La unidad de la capacidad: pza/h, m/h, kg/h…",
    )
    es_robot = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tipo", "-es_robot", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class Cuadrilla(models.Model):
    """Quién trabaja hoy, dónde y en qué turno.

    `EquipoTrabajo` ya existía, pero es una plantilla fija: «Cuadrilla A de
    soldadura, cuatro integrantes». En el piso eso no se cumple ningún día —
    falta uno, otro se pasa a pintura por la tarde—, así que la producción se
    acababa atribuyendo a la plantilla y no a las personas que estuvieron.

    Esto es lo que de verdad pasó: se arma por turno y por centro de trabajo,
    con la gente que se presentó. La plantilla se queda como punto de partida
    para no capturar veinte nombres a mano cada mañana.

    Es una entidad transaccional: hay una fila por día, turno y centro. No se
    edita el pasado — una cuadrilla de la semana anterior es un hecho, y es lo
    que sostiene el indicador de producción por persona.
    """

    class Turno(models.TextChoices):
        MATUTINO = "matutino", "Matutino"
        VESPERTINO = "vespertino", "Vespertino"
        COMPLETO = "completo", "Jornada completa"

    fecha = models.DateField(db_index=True)
    turno = models.CharField(
        max_length=12, choices=Turno.choices, default=Turno.COMPLETO, db_index=True
    )

    #: El área: Corte, Soldadura o Pintura. Se guarda el texto y no una llave
    #: a `Maquina` porque una cuadrilla es de un área, no de un equipo: dentro
    #: de corte pueden rotar entre los seis.
    centro = models.CharField(max_length=20, choices=Maquina.TIPO_CHOICES, db_index=True)

    #: El equipo concreto, cuando la cuadrilla está pegada a uno. En corte es
    #: lo normal; en soldadura y pintura casi nunca.
    maquina = models.ForeignKey(
        Maquina, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cuadrillas",
    )

    #: De qué plantilla se partió, si se partió de alguna. Sólo informativo.
    plantilla = models.ForeignKey(
        EquipoTrabajo, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cuadrillas",
    )

    comentario = models.CharField(max_length=255, blank=True, default="")
    armada_por = models.CharField(max_length=150, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "centro", "turno"]
        constraints = [
            #: Una sola cuadrilla por día, turno, centro y equipo. Dos
            #: cuadrillas del mismo turno en el mismo sitio son un error de
            #: captura, y si se admiten la producción se cuenta dos veces.
            models.UniqueConstraint(
                fields=["fecha", "turno", "centro", "maquina"],
                name="cuadrilla_unica_con_maquina",
            ),
            models.UniqueConstraint(
                fields=["fecha", "turno", "centro"],
                condition=Q(maquina__isnull=True),
                name="cuadrilla_unica_sin_maquina",
            ),
        ]
        verbose_name = "cuadrilla"
        verbose_name_plural = "cuadrillas"

    def __str__(self):
        donde = self.maquina.nombre if self.maquina else self.centro
        return f"{self.fecha} · {self.get_turno_display()} · {donde}"


class CuadrillaIntegrante(models.Model):
    """Una persona en una cuadrilla, con el papel que hizo ese día.

    El papel se guarda aparte del rol del colaborador a propósito: un auxiliar
    puede estar soldando un martes porque falta un soldador, y para el costo de
    mano de obra importa lo que hizo, no lo que dice su ficha.
    """

    cuadrilla = models.ForeignKey(
        Cuadrilla, on_delete=models.CASCADE, related_name="integrantes"
    )
    colaborador = models.ForeignKey(
        Colaborador, on_delete=models.PROTECT, related_name="participaciones"
    )
    papel = models.CharField(
        max_length=20, choices=Colaborador.ROL_CHOICES, blank=True, default=""
    )

    #: Qué parte de la jornada estuvo. Uno es el turno entero. Sirve para
    #: repartir las horas cuando alguien entra a media mañana.
    fraccion = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00")
    )

    class Meta:
        ordering = ["colaborador__nombre"]
        constraints = [
            #: Nadie dos veces en la misma cuadrilla: sus horas se contarían
            #: dobles.
            models.UniqueConstraint(
                fields=["cuadrilla", "colaborador"], name="integrante_unico"
            ),
            models.CheckConstraint(
                condition=Q(fraccion__gt=Decimal("0")) & Q(fraccion__lte=Decimal("1")),
                name="fraccion_de_jornada_valida",
            ),
        ]
        verbose_name = "integrante de cuadrilla"
        verbose_name_plural = "integrantes de cuadrilla"

    def __str__(self):
        return f"{self.colaborador.nombre} · {self.cuadrilla}"


class SeguimientoDespacho(models.Model):
    """Lo que Logística ya atendió de la bandeja de despacho.

    **Aquí no se guarda el aviso, sino la respuesta al aviso.** La distinción
    importa y es la decisión de diseño de esta pantalla.

    Lo natural sería crear una fila cada vez que una orden pasa a Terminado —un
    disparador— y que la bandeja enseñara esas filas. En este sistema eso falla:
    el estado se cambia desde cuatro motores distintos y desde decenas de sitios
    del código, así que **cualquier camino que se olvide de disparar deja una
    orden terminada de la que Logística nunca se entera**. Y ese fallo es
    invisible: la bandeja se ve vacía y parece que no hay nada que despachar.

    Por eso la bandeja se **deduce** de los datos: lo que está terminado y
    todavía no ha salido. No se puede quedar desactualizada porque no hay nada
    que actualizar, y una orden nueva aparece sola aunque se haya terminado por
    un camino que nadie previó.

    Esta tabla sólo recuerda lo que una persona hizo con cada renglón: si ya lo
    vio, si lo apartó para el camión, o si lo dejó anotado. Sin ella la bandeja
    sería una lista sin memoria.
    """

    class Linea(models.TextChoices):
        VIGAS = "vigas", "Estructuras metálicas"
        HERRERIA = "herreria", "Herrería"
        CORTA = "corta", "Corta.mx"
        ROBOTICA = "robotica", "Robótica"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        PREPARANDO = "preparando", "Preparando para salir"
        DESPACHADO = "despachado", "Despachado"

    linea = models.CharField(max_length=12, choices=Linea.choices, db_index=True)

    #: El identificador del renglón en su tabla de origen. No es una llave
    #: foránea porque apunta a cuatro tablas distintas y una de ellas —`vigas`—
    #: es heredada y no la maneja Django.
    referencia = models.PositiveIntegerField(db_index=True)

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True
    )
    notas = models.CharField(max_length=255, blank=True, default="")
    actor = models.CharField(max_length=150, blank=True, default="")
    visto_en = models.DateTimeField(null=True, blank=True)
    despachado_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizado_en"]
        constraints = [
            #: Un renglón, un seguimiento. Dos filas para lo mismo harían que
            #: la bandeja enseñara la orden dos veces con estados distintos.
            models.UniqueConstraint(
                fields=["linea", "referencia"], name="seguimiento_despacho_unico"
            ),
        ]
        verbose_name = "seguimiento de despacho"
        verbose_name_plural = "seguimientos de despacho"

    def __str__(self):
        return f"{self.get_linea_display()} #{self.referencia} · {self.get_estado_display()}"


class ApunteDeTrabajo(models.Model):
    """Con qué equipo y con qué cuadrilla se hizo cada avance.

    La bitácora heredada (`production_log`) guarda que una pieza pasó de Corte
    a Espera de armado, y nada más. No dice en cuál de los seis equipos de
    corte se hizo ni quién estaba. Sin eso no se puede responder «cuánto
    produjo la cortadora 3 esta semana» ni «qué se hizo el día que salió mal»,
    que es la mitad de para qué sirve medir.

    No se le añaden columnas a `production_log` porque es una tabla heredada
    que Django no maneja: tocarla es tocar el esquema vivo. Esto va aparte y se
    escribe en la misma transacción que el cambio de estado, así que o quedan
    los dos apuntes o no queda ninguno.

    **Los integrantes se copian, no se consultan.** Una cuadrilla es un
    registro vivo: mañana alguien la corrige y quita a quien no vino. Si el
    apunte sólo guardara la llave, esa corrección reescribiría quién cortó la
    pieza la semana pasada. Aquí se guarda a quién había en ese momento, y ya
    no cambia.
    """

    #: Mismo vocabulario que la bandeja de despacho: son las mismas cuatro
    #: líneas y no deben poder divergir.
    linea = models.CharField(
        max_length=12, choices=SeguimientoDespacho.Linea.choices, db_index=True
    )

    #: El identificador en su tabla de origen. No es llave foránea por lo
    #: mismo que en `SeguimientoDespacho`: apunta a cuatro tablas y una es
    #: heredada.
    referencia = models.PositiveIntegerField(db_index=True)

    #: El código visible de la pieza u orden. Se copia para que el histórico
    #: se pueda leer aunque el renglón de origen se renombre o se borre.
    codigo = models.CharField(max_length=120, blank=True, default="")

    etapa = models.CharField(max_length=40, db_index=True)
    etapa_anterior = models.CharField(max_length=40, blank=True, default="")

    maquina = models.ForeignKey(
        Maquina, on_delete=models.PROTECT, null=True, blank=True,
        related_name="apuntes",
    )
    cuadrilla = models.ForeignKey(
        Cuadrilla, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="apuntes",
    )

    #: Los identificadores de quienes estaban en la cuadrilla en ese momento,
    #: separados por comas. Es una copia deliberada: ver la explicación de
    #: arriba.
    integrantes = models.CharField(max_length=255, blank=True, default="")

    actor = models.CharField(max_length=150, blank=True, default="")
    ocurrido_en = models.DateTimeField(db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-ocurrido_en"]
        indexes = [
            models.Index(fields=["maquina", "ocurrido_en"]),
            models.Index(fields=["linea", "referencia"]),
        ]
        verbose_name = "apunte de trabajo"
        verbose_name_plural = "apuntes de trabajo"

    def __str__(self):
        return f"{self.codigo or self.referencia} · {self.etapa}"

    @property
    def integrantes_ids(self):
        return [int(x) for x in self.integrantes.split(",") if x.strip().isdigit()]


class MaquinaParoMotivo(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    activo = models.BooleanField(default=True)
    es_sistema = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class MaquinaFallaTipo(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    activo = models.BooleanField(default=True)
    es_sistema = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class PlantaEvento(models.Model):
    TIPO_CHOICES = [
        ("Energia", "Corte de energía"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField(null=True, blank=True, db_index=True)
    comentario = models.CharField(max_length=255, blank=True)
    registrado_por = models.CharField(max_length=120, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inicio", "-id"]

    def __str__(self) -> str:
        return f"{self.tipo} {self.inicio}"


class MaquinaParo(models.Model):
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, related_name="paros")
    motivo = models.ForeignKey(MaquinaParoMotivo, on_delete=models.PROTECT, null=True, blank=True)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField(null=True, blank=True, db_index=True)
    comentario = models.CharField(max_length=255, blank=True)
    registrado_por = models.CharField(max_length=120, blank=True)
    evento_planta = models.ForeignKey(PlantaEvento, on_delete=models.SET_NULL, null=True, blank=True, related_name="paros_maquina")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inicio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["maquina"],
                condition=Q(fin__isnull=True),
                name="maquinaparo_unique_open_per_machine",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.maquina} - paro {self.inicio}"


class MaquinaFalla(models.Model):
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, related_name="fallas")
    tipo = models.ForeignKey(MaquinaFallaTipo, on_delete=models.PROTECT, null=True, blank=True)
    inicio = models.DateTimeField(db_index=True)
    fin = models.DateTimeField(null=True, blank=True, db_index=True)
    comentario = models.CharField(max_length=255, blank=True)
    registrado_por = models.CharField(max_length=120, blank=True)
    paro = models.ForeignKey(MaquinaParo, on_delete=models.SET_NULL, null=True, blank=True, related_name="fallas")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-inicio", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["maquina"],
                condition=Q(fin__isnull=True),
                name="maquinafalla_unique_open_per_machine",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.maquina} - falla {self.inicio}"


class RobotPiezaCatalogo(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    peso_kg = models.FloatField(default=0.0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class RobotOrdenProduccion(models.Model):
    ESTADO_CHOICES = [
        ("Abierta", "Abierta"),
        ("Cerrada", "Cerrada"),
        ("Cancelada", "Cancelada"),
    ]

    proyecto = models.ForeignKey("Proyecto", on_delete=models.PROTECT, null=True, blank=True)
    nombre = models.CharField(max_length=120, blank=True, default="")
    nombre_normalizado = models.CharField(max_length=120, db_index=True, blank=True, default="")
    producto = models.CharField(max_length=120, blank=True, default="")
    producto_normalizado = models.CharField(max_length=120, db_index=True, blank=True, default="")
    cantidad_objetivo = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="Abierta", db_index=True)
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        self.producto = (self.producto or "").strip()
        self.producto_normalizado = (self.producto or "").upper()
        super().save(*args, **kwargs)

    @property
    def folio(self) -> str:
        return f"OP-{int(self.id or 0):05d}"

    def __str__(self) -> str:
        base = self.nombre or self.producto or ""
        return f"{self.folio} - {base} x{self.cantidad_objetivo}"


class RobotOrdenItem(models.Model):
    orden = models.ForeignKey(RobotOrdenProduccion, on_delete=models.CASCADE, related_name="items")
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, default="Corte", db_index=True)
    pieza = models.ForeignKey(RobotPiezaCatalogo, on_delete=models.PROTECT, null=True, blank=True)
    pieza_custom_nombre = models.CharField(max_length=120, blank=True, default="")
    pieza_custom_peso_kg = models.FloatField(default=0.0)
    cantidad_requerida = models.PositiveIntegerField(default=1)
    robot_sugerido = models.ForeignKey(Maquina, on_delete=models.PROTECT, null=True, blank=True, related_name="robot_orden_items")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden", "pieza"],
                condition=Q(pieza__isnull=False),
                name="robotordenitem_orden_pieza_unique",
            ),
        ]

    @property
    def pieza_nombre(self) -> str:
        return (self.pieza.nombre if self.pieza_id else "") or (self.pieza_custom_nombre or "").strip()

    @property
    def pieza_peso_kg(self) -> float:
        if self.pieza_id:
            return float(self.pieza.peso_kg or 0.0)
        return float(self.pieza_custom_peso_kg or 0.0)

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.pieza_nombre} x{self.cantidad_requerida}"


class RobotOrdenAsignacion(models.Model):
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    orden = models.ForeignKey(RobotOrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones")
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]
        constraints = [
            models.UniqueConstraint(fields=["orden", "etapa", "colaborador"], name="robot_asig_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.etapa} - {self.colaborador}"


class RobotProduccion(models.Model):
    fecha = models.DateField(db_index=True)
    pieza = models.ForeignKey(RobotPiezaCatalogo, on_delete=models.PROTECT, null=True, blank=True)
    pieza_custom_nombre = models.CharField(max_length=120, blank=True, default="")
    pieza_custom_peso_kg = models.FloatField(default=0.0)
    cantidad = models.PositiveIntegerField(default=1)
    robot = models.ForeignKey(Maquina, on_delete=models.PROTECT, related_name="robot_produccion")
    operador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name="robot_operaciones")
    orden_item = models.ForeignKey(
        RobotOrdenItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="producciones",
    )
    corte_maquina = models.ForeignKey(
        Maquina,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="robot_cortes",
    )
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def total_kg(self) -> float:
        if self.orden_item_id:
            return float(self.orden_item.pieza_peso_kg or 0.0) * int(self.cantidad or 0)
        if self.pieza_id:
            return float(self.pieza.peso_kg or 0.0) * int(self.cantidad or 0)
        return float(self.pieza_custom_peso_kg or 0.0) * int(self.cantidad or 0)

    @property
    def total_ton(self) -> float:
        return self.total_kg / 1000.0

    def __str__(self) -> str:
        label = ""
        if self.orden_item_id:
            label = self.orden_item.pieza_nombre
        elif self.pieza_id:
            label = str(self.pieza)
        else:
            label = (self.pieza_custom_nombre or "").strip()
        return f"{self.fecha} - {label} x{self.cantidad}"


class HerrPiezaCatalogo(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    peso_kg = models.FloatField(default=0.0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class HerrCliente(models.Model):
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, unique=True, db_index=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class HerrOrdenProduccion(models.Model):
    ESTADO_CHOICES = [
        ("Abierta", "Abierta"),
        ("Cerrada", "Cerrada"),
        ("Cancelada", "Cancelada"),
    ]

    proyecto = models.ForeignKey("Proyecto", on_delete=models.PROTECT, null=True, blank=True)
    cliente_herreria = models.ForeignKey(HerrCliente, on_delete=models.PROTECT, null=True, blank=True)
    codigo = models.CharField(max_length=60, blank=True, default="")
    codigo_normalizado = models.CharField(max_length=60, unique=True, db_index=True, null=True, blank=True)
    pieza_no = models.PositiveIntegerField(default=1)
    total_piezas = models.PositiveIntegerField(default=1)
    nombre = models.CharField(max_length=120, blank=True, default="")
    nombre_normalizado = models.CharField(max_length=120, db_index=True, blank=True, default="")
    descripcion = models.CharField(max_length=255, blank=True, default="")
    plano_pdf = models.FileField(upload_to="herreria/planos/", null=True, blank=True)
    fecha_compromiso = models.DateField(null=True, blank=True, db_index=True)
    prioridad = models.PositiveSmallIntegerField(default=3, db_index=True)
    peso_kg = models.FloatField(default=0.0)
    ultimo_cambio = models.DateTimeField(null=True, blank=True, db_index=True)
    estado_etapa = models.CharField(max_length=30, default="Espera de corte", db_index=True)
    es_individual = models.BooleanField(default=False, db_index=True)
    es_op = models.BooleanField(default=False, db_index=True)
    cantidad_objetivo = models.PositiveIntegerField(default=1)
    cantidad_producida = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_pintada = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_terminada = models.PositiveIntegerField(default=0, db_index=True)
    cierre_pendiente_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_hasta = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_por = models.CharField(max_length=120, blank=True, default="")
    cierre_estado_previo = models.CharField(max_length=30, blank=True, default="")
    cierre_bloqueado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_revertido_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_revertido_por = models.CharField(max_length=120, blank=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="Abierta", db_index=True)
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        self.descripcion = (self.descripcion or "").strip()
        self.codigo = (self.codigo or "").strip()
        self.codigo_normalizado = (self.codigo or "").upper() or None
        if int(self.total_piezas or 0) <= 0:
            self.total_piezas = 1
        if int(self.cantidad_objetivo or 0) <= 0:
            self.cantidad_objetivo = int(self.total_piezas or 1)
        is_op = int(self.total_piezas or 0) >= 2
        self.es_op = bool(is_op)
        self.es_individual = bool(not is_op)
        super().save(*args, **kwargs)

    @property
    def folio(self) -> str:
        return f"H-{int(self.id or 0):05d}"

    def __str__(self) -> str:
        return f"{self.folio} - {self.codigo} x{self.total_piezas}"


class HerrSolicitudProduccion(models.Model):
    ESTADO_CHOICES = [
        ("Pendiente", "Pendiente"),
        ("Aceptada", "Aceptada"),
        ("Rechazada", "Rechazada"),
        ("Cancelada", "Cancelada"),
    ]

    producto = models.ForeignKey(HerrPiezaCatalogo, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    cliente = models.ForeignKey(HerrCliente, on_delete=models.PROTECT, null=True, blank=True)
    fecha_compromiso = models.DateField(null=True, blank=True, db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="Pendiente", db_index=True)
    orden_creada = models.ForeignKey(HerrOrdenProduccion, on_delete=models.SET_NULL, null=True, blank=True)
    creado_por = models.CharField(max_length=120, blank=True, default="")
    aceptado_por = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    aceptado_en = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

class HerrEstadoCambio(models.Model):
    orden = models.ForeignKey(
        HerrOrdenProduccion,
        on_delete=models.CASCADE,
        related_name="cambios_estado",
    )
    estado_anterior = models.CharField(max_length=30, blank=True, default="")
    estado_nuevo = models.CharField(max_length=30, blank=True, default="")
    fecha_operacion = models.DateField(null=True, blank=True, db_index=True)
    actor_username = models.CharField(max_length=120, blank=True, default="")
    motivo_retroceso = models.CharField(max_length=255, blank=True, default="")
    comentario = models.CharField(max_length=255, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class HerrAvanceCambio(models.Model):
    orden = models.ForeignKey(HerrOrdenProduccion, on_delete=models.CASCADE, related_name="cambios_avance")
    fecha_operacion = models.DateField(db_index=True)
    soldadas_prev = models.PositiveIntegerField(default=0)
    soldadas_new = models.PositiveIntegerField(default=0)
    pintadas_prev = models.PositiveIntegerField(default=0)
    pintadas_new = models.PositiveIntegerField(default=0)
    terminadas_prev = models.PositiveIntegerField(default=0)
    terminadas_new = models.PositiveIntegerField(default=0)
    actor_username = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class HerrAsignacion(models.Model):
    orden = models.ForeignKey(HerrOrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones_v2")
    etapa = models.CharField(max_length=30, db_index=True)
    rol = models.CharField(max_length=20, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, null=True, blank=True)
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, null=True, blank=True)
    vigente = models.BooleanField(default=True, db_index=True)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]


class HerrOrdenAsignacion(models.Model):
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    orden = models.ForeignKey(HerrOrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones")
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]
        constraints = [
            models.UniqueConstraint(fields=["orden", "etapa", "colaborador"], name="herr_asig_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.etapa} - {self.colaborador}"


class HerrOrdenItem(models.Model):
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    orden = models.ForeignKey(HerrOrdenProduccion, on_delete=models.CASCADE, related_name="items")
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, default="Corte", db_index=True)
    pieza = models.ForeignKey(HerrPiezaCatalogo, on_delete=models.PROTECT, null=True, blank=True)
    pieza_custom_nombre = models.CharField(max_length=120, blank=True, default="")
    pieza_custom_peso_kg = models.FloatField(default=0.0)
    cantidad_requerida = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["orden", "pieza"],
                condition=Q(pieza__isnull=False),
                name="herrordenitem_orden_pieza_unique",
            ),
        ]

    @property
    def pieza_nombre(self) -> str:
        return (self.pieza.nombre if self.pieza_id else "") or (self.pieza_custom_nombre or "").strip()

    @property
    def pieza_peso_kg(self) -> float:
        if self.pieza_id:
            return float(self.pieza.peso_kg or 0.0)
        return float(self.pieza_custom_peso_kg or 0.0)

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.pieza_nombre} x{self.cantidad_requerida}"


class HerrProduccion(models.Model):
    fecha = models.DateField(db_index=True)
    orden_item = models.ForeignKey(HerrOrdenItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="producciones")
    cantidad = models.PositiveIntegerField(default=1)
    operador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name="herr_operaciones")
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def total_kg(self) -> float:
        if not self.orden_item_id:
            return 0.0
        return float(self.orden_item.pieza_peso_kg or 0.0) * int(self.cantidad or 0)

    @property
    def total_ton(self) -> float:
        return self.total_kg / 1000.0

    def __str__(self) -> str:
        return f"{self.fecha} - {self.orden_item_id or ''} x{self.cantidad}"


class PedidoProduccion(models.Model):
    ESTADO_CHOICES = [
        ("Activa", "Activa"),
        ("Terminada", "Terminada"),
        ("Cancelada", "Cancelada"),
    ]

    folio = models.CharField(max_length=40, unique=True, db_index=True)
    cliente = models.CharField(max_length=180, db_index=True)
    telefono = models.CharField(max_length=80, blank=True, default="")
    fecha_compromiso = models.DateField(db_index=True)
    comentarios = models.TextField(blank=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="Activa", db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return self.folio


class PedidoProduccionItem(models.Model):
    ESTADO_HERRERIA_CHOICES = [
        ("Pendiente", "Pendiente"),
        ("Espera de material", "Espera de material"),
        ("En producción", "En producción"),
        ("Cancelado", "Cancelado"),
    ]

    pedido = models.ForeignKey(PedidoProduccion, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey(HerrPiezaCatalogo, on_delete=models.PROTECT)
    cantidad_total = models.PositiveIntegerField(default=1)
    apartado = models.PositiveIntegerField(default=0)
    enviado = models.PositiveIntegerField(default=0)

    estado_herreria = models.CharField(max_length=30, choices=ESTADO_HERRERIA_CHOICES, default="Pendiente", db_index=True)
    orden_herreria = models.ForeignKey(HerrOrdenProduccion, on_delete=models.SET_NULL, null=True, blank=True)
    aceptado_por = models.CharField(max_length=120, blank=True, default="")
    aceptado_en = models.DateTimeField(null=True, blank=True, db_index=True)

    espera_material_entrada_en = models.DateTimeField(null=True, blank=True, db_index=True)
    espera_material_salida_en = models.DateTimeField(null=True, blank=True, db_index=True)

    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    @property
    def saldo(self) -> int:
        total = int(self.cantidad_total or 0)
        apartado = int(self.apartado or 0)
        enviado = int(self.enviado or 0)
        return max(0, total - apartado - enviado)

    def __str__(self) -> str:
        return f"{self.pedido.folio} - {self.producto.nombre} x{self.cantidad_total}"


class LogisticaStock(models.Model):
    producto = models.OneToOneField(HerrPiezaCatalogo, on_delete=models.PROTECT)
    stock = models.PositiveIntegerField(default=0)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["producto__nombre"]

    def __str__(self) -> str:
        return f"{self.producto.nombre} - {self.stock}"


class LogisticaMovimiento(models.Model):
    # El material pasa por tres estados: disponible, apartado y enviado. Cada
    # tipo de movimiento es un salto entre dos de ellos, y de ahí depende si
    # afecta o no al stock disponible:
    #
    #   stock_in             producción entrega        -> aumenta disponible
    #   apartar              se reserva para un pedido -> baja disponible
    #   enviar               sale del apartado         -> no toca disponible
    #   revertir_a_stock     vuelve al almacén         -> aumenta disponible
    #   revertir_a_apartado  vuelve a la reserva       -> no toca disponible
    #   ajuste               corrección manual         -> afecta disponible
    #
    # "revertir" es histórico y ambiguo: se escribía igual tanto si el
    # material volvía al almacén como si volvía al apartado, de modo que los
    # registros anteriores a esta corrección no permiten distinguir un caso
    # del otro. Se conserva para poder leerlos, pero no debe escribirse.
    TIPO_CHOICES = [
        ("stock_in", "stock_in"),
        ("ajuste", "ajuste"),
        ("apartar", "apartar"),
        ("enviar", "enviar"),
        ("revertir_a_stock", "revertir a stock"),
        ("revertir_a_apartado", "revertir a apartado"),
        ("revertir", "revertir (histórico, ambiguo)"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    producto = models.ForeignKey(HerrPiezaCatalogo, on_delete=models.PROTECT)
    pedido_item = models.ForeignKey(PedidoProduccionItem, on_delete=models.SET_NULL, null=True, blank=True)
    cantidad = models.IntegerField(default=0)
    actor = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class LogisticaEnvio(models.Model):
    pedido = models.ForeignKey(PedidoProduccion, on_delete=models.CASCADE, related_name="envios")
    fecha = models.DateField(db_index=True)
    comprobante_pdf = models.FileField(upload_to="logistica/envios/%Y/%m/%d", null=True, blank=True)
    actor = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class LogisticaEnvioItem(models.Model):
    envio = models.ForeignKey(LogisticaEnvio, on_delete=models.CASCADE, related_name="items")
    pedido_item = models.ForeignKey(PedidoProduccionItem, on_delete=models.PROTECT, related_name="envio_items")
    producto = models.ForeignKey(HerrPiezaCatalogo, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    revertido = models.PositiveIntegerField(default=0)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class LogisticaAcuseEntrega(models.Model):
    pedido_item = models.ForeignKey(PedidoProduccionItem, on_delete=models.PROTECT, related_name="acuses_logistica")
    cantidad = models.PositiveIntegerField(default=1)
    fecha = models.DateField(db_index=True)
    entregado_por = models.CharField(max_length=120, blank=True, default="")
    recibido_por = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self) -> str:
        return f"Acuse #{int(self.id or 0)} - {self.fecha} - {int(self.cantidad or 0)}"


class LogisticaExpediente(models.Model):
    pedido = models.OneToOneField(PedidoProduccion, on_delete=models.CASCADE, related_name="expediente", null=True, blank=True)
    orden_corta = models.OneToOneField(
        "LaserOrdenProduccion",
        on_delete=models.CASCADE,
        related_name="expediente_logistica",
        null=True,
        blank=True,
    )
    generado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    generado_por = models.CharField(max_length=120, blank=True, default="")
    descargas_count = models.PositiveIntegerField(default=0)
    primera_descarga_en = models.DateTimeField(null=True, blank=True, db_index=True)
    primera_descarga_por = models.CharField(max_length=120, blank=True, default="")
    ultima_descarga_en = models.DateTimeField(null=True, blank=True, db_index=True)
    ultima_descarga_por = models.CharField(max_length=120, blank=True, default="")

    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(pedido__isnull=False) & models.Q(orden_corta__isnull=True))
                    | (models.Q(pedido__isnull=True) & models.Q(orden_corta__isnull=False))
                ),
                name="logisticaexpediente_exactly_one_target",
            )
        ]


class LogisticaExpedienteDescarga(models.Model):
    expediente = models.ForeignKey(LogisticaExpediente, on_delete=models.CASCADE, related_name="descargas")
    pedido = models.ForeignKey(
        PedidoProduccion, on_delete=models.CASCADE, related_name="expediente_descargas", null=True, blank=True
    )
    orden_corta = models.ForeignKey(
        "LaserOrdenProduccion",
        on_delete=models.CASCADE,
        related_name="expediente_descargas",
        null=True,
        blank=True,
    )
    descargado_en = models.DateTimeField(db_index=True)
    usuario = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        ordering = ["-descargado_en"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(pedido__isnull=False) & models.Q(orden_corta__isnull=True))
                    | (models.Q(pedido__isnull=True) & models.Q(orden_corta__isnull=False))
                ),
                name="logisticaexpdescarga_exactly_one_target",
            )
        ]


class LogisticaStockCorta(models.Model):
    producto = models.CharField(max_length=180)
    producto_normalizado = models.CharField(max_length=180, unique=True, db_index=True)
    stock = models.PositiveIntegerField(default=0)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["producto"]

    def save(self, *args, **kwargs):
        self.producto = (self.producto or "").strip()
        self.producto_normalizado = (self.producto or "").upper()
        self.stock = int(self.stock or 0)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.producto} - {self.stock}"


class LogisticaMovimientoCorta(models.Model):
    # El material pasa por tres estados: disponible, apartado y enviado. Cada
    # tipo de movimiento es un salto entre dos de ellos, y de ahí depende si
    # afecta o no al stock disponible:
    #
    #   stock_in             producción entrega        -> aumenta disponible
    #   apartar              se reserva para un pedido -> baja disponible
    #   enviar               sale del apartado         -> no toca disponible
    #   revertir_a_stock     vuelve al almacén         -> aumenta disponible
    #   revertir_a_apartado  vuelve a la reserva       -> no toca disponible
    #   ajuste               corrección manual         -> afecta disponible
    #
    # "revertir" es histórico y ambiguo: se escribía igual tanto si el
    # material volvía al almacén como si volvía al apartado, de modo que los
    # registros anteriores a esta corrección no permiten distinguir un caso
    # del otro. Se conserva para poder leerlos, pero no debe escribirse.
    TIPO_CHOICES = [
        ("stock_in", "stock_in"),
        ("ajuste", "ajuste"),
        ("apartar", "apartar"),
        ("enviar", "enviar"),
        ("revertir_a_stock", "revertir a stock"),
        ("revertir_a_apartado", "revertir a apartado"),
        ("revertir", "revertir (histórico, ambiguo)"),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    producto = models.CharField(max_length=180)
    producto_normalizado = models.CharField(max_length=180, db_index=True)
    orden = models.ForeignKey("LaserOrdenProduccion", on_delete=models.SET_NULL, null=True, blank=True, related_name="logistica_movimientos")
    cantidad = models.IntegerField(default=0)
    actor = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        self.producto = (self.producto or "").strip()
        self.producto_normalizado = (self.producto or "").upper()
        self.cantidad = int(self.cantidad or 0)
        super().save(*args, **kwargs)


class LogisticaEnvioCorta(models.Model):
    orden = models.ForeignKey("LaserOrdenProduccion", on_delete=models.PROTECT, related_name="logistica_envios")
    fecha = models.DateField(db_index=True)
    comprobante_pdf = models.FileField(upload_to="logistica/envios_corta/%Y/%m/%d", null=True, blank=True)
    producto = models.CharField(max_length=180)
    producto_normalizado = models.CharField(max_length=180, db_index=True)
    cantidad = models.PositiveIntegerField(default=1)
    revertido = models.PositiveIntegerField(default=0)
    actor = models.CharField(max_length=120, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        self.producto = (self.producto or "").strip()
        self.producto_normalizado = (self.producto or "").upper()
        self.cantidad = int(self.cantidad or 0)
        self.revertido = int(self.revertido or 0)
        super().save(*args, **kwargs)

class LaserMaterialPlaca(models.Model):
    categoria_material = models.CharField(max_length=60, blank=True, default="", db_index=True)
    tipo_material = models.CharField(max_length=120, blank=True, default="", db_index=True)
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, db_index=True)
    calibre = models.CharField(max_length=40, blank=True, default="")
    espesor_mm = models.FloatField(default=0.0)
    largo_mm = models.PositiveIntegerField(default=0)
    ancho_mm = models.PositiveIntegerField(default=0)
    peso_kg = models.FloatField(default=0.0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "categoria_material", "tipo_material", "nombre", "calibre", "espesor_mm", "largo_mm", "ancho_mm", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["categoria_material", "tipo_material", "nombre_normalizado", "calibre", "espesor_mm", "largo_mm", "ancho_mm"],
                name="uniq_lasermaterialplaca_signature",
            )
        ]

    def save(self, *args, **kwargs):
        self.categoria_material = (self.categoria_material or "").strip()
        self.tipo_material = (self.tipo_material or "").strip()
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        self.calibre = (self.calibre or "").strip()
        try:
            self.espesor_mm = float(self.espesor_mm or 0.0)
        except Exception:
            self.espesor_mm = 0.0
        self.largo_mm = int(self.largo_mm or 0)
        self.ancho_mm = int(self.ancho_mm or 0)
        try:
            self.peso_kg = float(self.peso_kg or 0.0)
        except Exception:
            self.peso_kg = 0.0
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class CortaClienteProyecto(models.Model):
    TIPO_CHOICES = [
        ("cliente", "Cliente"),
        ("proyecto", "Proyecto"),
        ("mixto", "Cliente/Proyecto"),
    ]

    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES, default="mixto", db_index=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class CortaPiezaCatalogo(models.Model):
    nombre = models.CharField(max_length=180)
    nombre_normalizado = models.CharField(max_length=180, unique=True, db_index=True)
    pdf = models.FileField(upload_to="corta/catalogo/pdf/%Y/%m/%d", null=True, blank=True)
    dxf = models.FileField(upload_to="corta/catalogo/dxf/%Y/%m/%d", null=True, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class LaserOrdenProduccion(models.Model):
    ESTADO_CHOICES = [
        ("Abierta", "Abierta"),
        ("Cerrada", "Cerrada"),
        ("Cancelada", "Cancelada"),
    ]

    proyecto = models.ForeignKey("Proyecto", on_delete=models.PROTECT, null=True, blank=True)
    corta_cliente_proyecto = models.ForeignKey(CortaClienteProyecto, on_delete=models.PROTECT, null=True, blank=True)
    folio_externo = models.CharField(max_length=80, blank=True, default="")
    folio_externo_normalizado = models.CharField(max_length=80, unique=True, db_index=True, null=True, blank=True)
    codigo = models.CharField(max_length=60, blank=True, default="")
    codigo_normalizado = models.CharField(max_length=60, db_index=True, null=True, blank=True)
    corta_pieza = models.ForeignKey(CortaPiezaCatalogo, on_delete=models.PROTECT, null=True, blank=True)
    correo = models.CharField(max_length=180, blank=True, default="")
    telefono = models.CharField(max_length=80, blank=True, default="")
    pieza_no = models.PositiveIntegerField(default=1)
    total_piezas = models.PositiveIntegerField(default=1)
    nombre = models.CharField(max_length=120, blank=True, default="")
    nombre_normalizado = models.CharField(max_length=120, db_index=True, blank=True, default="")
    descripcion = models.CharField(max_length=255, blank=True, default="")
    archivo = models.FileField(upload_to="corte_laser/archivos/", null=True, blank=True)
    archivo_dxf = models.FileField(upload_to="corte_laser/dxf/", null=True, blank=True)
    fecha_compromiso = models.DateField(null=True, blank=True, db_index=True)
    prioridad = models.PositiveSmallIntegerField(default=3, db_index=True)
    material = models.ForeignKey(LaserMaterialPlaca, on_delete=models.PROTECT, null=True, blank=True)
    # El espesor y la cédula **de este pedido**, que normalmente son los de la
    # placa y por eso se copian solos al elegirla. Se guardan aparte porque a
    # veces no coinciden: la placa que había en el taller no era exactamente la
    # del catálogo, y eso hay que poder anotarlo sin ensuciar el catálogo, que
    # es de todos. Vacío o cero significa «los de la placa».
    espesor_mm = models.FloatField(default=0.0)
    calibre = models.CharField(max_length=40, blank=True, default="")
    pieza_ancho_mm = models.PositiveIntegerField(default=0)
    pieza_alto_mm = models.PositiveIntegerField(default=0)
    logo_ancho_mm = models.PositiveIntegerField(default=0)
    logo_alto_mm = models.PositiveIntegerField(default=0)
    peso_kg = models.FloatField(default=0.0)
    ultimo_cambio = models.DateTimeField(null=True, blank=True, db_index=True)
    estado_etapa = models.CharField(max_length=30, default="Espera de corte", db_index=True)
    es_individual = models.BooleanField(default=False, db_index=True)
    es_op = models.BooleanField(default=False, db_index=True)
    cantidad_objetivo = models.PositiveIntegerField(default=1)
    cantidad_producida = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_pintada = models.PositiveIntegerField(default=0, db_index=True)
    cantidad_terminada = models.PositiveIntegerField(default=0, db_index=True)
    cierre_pendiente_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_hasta = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_pendiente_por = models.CharField(max_length=120, blank=True, default="")
    cierre_estado_previo = models.CharField(max_length=30, blank=True, default="")
    cierre_bloqueado_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_revertido_en = models.DateTimeField(null=True, blank=True, db_index=True)
    cierre_revertido_por = models.CharField(max_length=120, blank=True, default="")
    apartado = models.PositiveIntegerField(default=0)
    enviado = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default="Abierta", db_index=True)
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = (self.nombre or "").upper()
        self.descripcion = (self.descripcion or "").strip()
        self.codigo = (self.codigo or "").strip()
        self.codigo_normalizado = (self.codigo or "").upper() or None
        self.folio_externo = (self.folio_externo or "").strip()
        self.folio_externo_normalizado = (self.folio_externo or "").upper() or None
        self.correo = (self.correo or "").strip()
        self.telefono = (self.telefono or "").strip()
        if int(self.total_piezas or 0) <= 0:
            self.total_piezas = 1
        if int(self.cantidad_objetivo or 0) <= 0:
            self.cantidad_objetivo = int(self.total_piezas or 1)
        is_op = int(self.total_piezas or 0) >= 2
        self.es_op = bool(is_op)
        self.es_individual = bool(not is_op)
        self.apartado = int(self.apartado or 0)
        self.enviado = int(self.enviado or 0)

        self.pieza_ancho_mm = int(self.pieza_ancho_mm or 0)
        self.pieza_alto_mm = int(self.pieza_alto_mm or 0)
        self.logo_ancho_mm = int(self.logo_ancho_mm or 0)
        self.logo_alto_mm = int(self.logo_alto_mm or 0)

        if not self.ultimo_cambio:
            self.ultimo_cambio = timezone.now()

        calc_ancho_mm = int(self.pieza_ancho_mm or 0)
        calc_alto_mm = int(self.pieza_alto_mm or 0)
        if calc_ancho_mm <= 0 or calc_alto_mm <= 0:
            calc_ancho_mm = int(self.logo_ancho_mm or 0)
            calc_alto_mm = int(self.logo_alto_mm or 0)

        if self.material_id and calc_ancho_mm > 0 and calc_alto_mm > 0:
            m = self.material
            plate_area = float(int(getattr(m, "largo_mm", 0) or 0)) * float(int(getattr(m, "ancho_mm", 0) or 0))
            if plate_area > 0:
                margin = 30.0
                rect_area = (float(calc_ancho_mm) + (2.0 * margin)) * (float(calc_alto_mm) + (2.0 * margin))
                peso_placa = float(getattr(m, "peso_kg", 0.0) or 0.0)
                if not (peso_placa > 0):
                    esp = float(getattr(m, "espesor_mm", 0.0) or 0.0)
                    largo = float(int(getattr(m, "largo_mm", 0) or 0))
                    ancho = float(int(getattr(m, "ancho_mm", 0) or 0))
                    if esp > 0 and largo > 0 and ancho > 0:
                        cat = (getattr(m, "categoria_material", "") or "").upper()
                        tip = (getattr(m, "tipo_material", "") or "").upper()
                        dens = 7.85
                        if ("ALUMIN" in cat) or ("ALUMIN" in tip):
                            dens = 2.7
                        elif ("INOX" in cat) or ("INOXID" in cat) or ("INOX" in tip) or ("INOXID" in tip):
                            dens = 8.0
                        vol_mm3 = largo * ancho * esp
                        vol_cm3 = vol_mm3 / 1000.0
                        peso_placa = (vol_cm3 * dens) / 1000.0
                if peso_placa > 0:
                    per_piece = (rect_area / plate_area) * peso_placa
                    total = max(per_piece * float(int(self.total_piezas or 1)), 0.0)
                    self.peso_kg = float(round(total, 3))

        try:
            self.peso_kg = float(self.peso_kg or 0.0)
        except Exception:
            self.peso_kg = 0.0

        super().save(*args, **kwargs)

    @property
    def folio(self) -> str:
        return f"L-{int(self.id or 0):05d}"

    def __str__(self) -> str:
        return f"{self.folio} - {self.codigo} x{self.total_piezas}"


class LaserEstadoCambio(models.Model):
    orden = models.ForeignKey(
        LaserOrdenProduccion,
        on_delete=models.CASCADE,
        related_name="cambios_estado",
    )
    estado_anterior = models.CharField(max_length=30, blank=True, default="")
    estado_nuevo = models.CharField(max_length=30, blank=True, default="")
    fecha_operacion = models.DateField(null=True, blank=True, db_index=True)
    actor_username = models.CharField(max_length=120, blank=True, default="")
    motivo_retroceso = models.CharField(max_length=255, blank=True, default="")
    comentario = models.CharField(max_length=255, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-creado_en"]


class LaserAsignacion(models.Model):
    orden = models.ForeignKey(LaserOrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones_v2")
    etapa = models.CharField(max_length=30, db_index=True)
    rol = models.CharField(max_length=20, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, null=True, blank=True)
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, null=True, blank=True)
    vigente = models.BooleanField(default=True, db_index=True)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]


class LaserOrdenAsignacion(models.Model):
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    orden = models.ForeignKey(LaserOrdenProduccion, on_delete=models.CASCADE, related_name="asignaciones")
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]
        constraints = [
            models.UniqueConstraint(fields=["orden", "etapa", "colaborador"], name="laser_asig_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.etapa} - {self.colaborador}"


class LaserOrdenItem(models.Model):
    ETAPA_CHOICES = [
        ("Corte", "Corte"),
        ("Armado", "Armado"),
        ("Soldadura", "Soldadura"),
        ("Pintura", "Pintura"),
    ]

    orden = models.ForeignKey(LaserOrdenProduccion, on_delete=models.CASCADE, related_name="items")
    etapa = models.CharField(max_length=20, choices=ETAPA_CHOICES, default="Corte", db_index=True)
    item_nombre = models.CharField(max_length=120, blank=True, default="")
    item_peso_kg = models.FloatField(default=0.0)
    cantidad_requerida = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["id"]

    @property
    def pieza_nombre(self) -> str:
        return (self.item_nombre or "").strip()

    @property
    def pieza_peso_kg(self) -> float:
        return float(self.item_peso_kg or 0.0)

    def __str__(self) -> str:
        return f"{self.orden.folio} - {self.pieza_nombre} x{self.cantidad_requerida}"


class LaserProduccion(models.Model):
    fecha = models.DateField(db_index=True)
    orden_item = models.ForeignKey(
        LaserOrdenItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="producciones",
    )
    cantidad = models.PositiveIntegerField(default=1)
    operador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, related_name="laser_operaciones")
    observaciones = models.CharField(max_length=255, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def total_kg(self) -> float:
        if not self.orden_item_id:
            return 0.0
        return float(self.orden_item.pieza_peso_kg or 0.0) * int(self.cantidad or 0)

    @property
    def total_ton(self) -> float:
        return self.total_kg / 1000.0

    def __str__(self) -> str:
        return f"{self.fecha} - {self.orden_item_id or ''} x{self.cantidad}"


class VigaAsignacion(models.Model):
    viga_internal_id = models.PositiveIntegerField(db_index=True)
    etapa = models.CharField(max_length=30, db_index=True)
    rol = models.CharField(max_length=20, db_index=True)
    colaborador = models.ForeignKey(Colaborador, on_delete=models.PROTECT, null=True, blank=True)
    maquina = models.ForeignKey(Maquina, on_delete=models.PROTECT, null=True, blank=True)
    vigente = models.BooleanField(default=True, db_index=True)
    asignado_por = models.CharField(max_length=120, blank=True)
    asignado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-asignado_en"]
        indexes = [
            models.Index(fields=["viga_internal_id", "etapa", "rol", "vigente"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(colaborador__isnull=False, maquina__isnull=True)
                    | models.Q(colaborador__isnull=True, maquina__isnull=False)
                ),
                name="vigaasignacion_persona_o_maquina",
            )
        ]

    def __str__(self) -> str:
        return f"Viga {self.viga_internal_id} - {self.etapa} - {self.rol}"
