"""Recursos humanos: cómo está organizada la gente del taller.

Hasta ahora la única ficha de una persona era `catalogos.Colaborador`, con tres
datos: nombre, equipo y un `rol` elegido de una lista de cuatro escrita en el
código. Para dar de alta a alguien había que entrar por la pantalla de Equipos,
y no había forma de contestar cuánta gente hay, en qué departamento está, ni
cuánto suma la nómina.

Aquí van las dos piezas que faltaban —el departamento y el puesto— y en
`catalogos.Colaborador` se añaden los datos de la persona. **La ficha sigue
siendo una sola**: si la mitad de una persona viviera aquí y la otra mitad
allá, tarde o temprano habría dos personas.

Los cuatro roles de siempre —Soldador, Auxiliar, Pintor, Operador— se siembran
como puestos con `sembrar_personal`, así que nada de lo que ya funciona cambia
de sitio.
"""

from django.db import models


def normalizar(texto: str) -> str:
    return (texto or "").strip().upper()


class Departamento(models.Model):
    """Corte, Soldadura, Pintura, Administración… lo que el taller decida.

    No se siembra ninguno a la fuerza: cómo se divide este taller lo sabe el
    taller, no yo. La pantalla de organización los crea.
    """

    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, db_index=True)
    descripcion = models.CharField(max_length=250, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "nombre"]
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = normalizar(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.nombre


class Puesto(models.Model):
    """Lo que hace una persona. Lo que el taller llama «su rol».

    Antes eran cuatro cadenas escritas en el código de `Colaborador`, así que
    añadir «Pailero» o «Ayudante general» era tocar el programa.

    `rol_de_produccion` es lo que hace que esto no rompa nada. El sistema
    reparte el trabajo por los cuatro papeles de siempre; un puesto nuevo dice
    a cuál de ellos se parece, y la asignación sigue funcionando. Vacío
    significa que esa persona no entra en el reparto de producción, que es lo
    normal en administración o en almacén.
    """

    ROLES_DE_PRODUCCION = [
        ("Soldador", "Soldador"),
        ("Auxiliar", "Auxiliar"),
        ("Pintor", "Pintor"),
        ("Operador", "Operador"),
    ]

    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, db_index=True)
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="puestos",
    )
    rol_de_produccion = models.CharField(
        max_length=20, choices=ROLES_DE_PRODUCCION, blank=True, default=""
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "departamento__nombre", "nombre"]
        verbose_name = "puesto"
        verbose_name_plural = "puestos"
        constraints = [
            models.UniqueConstraint(
                fields=["nombre_normalizado", "departamento"],
                name="uniq_puesto_por_departamento",
            )
        ]

    def save(self, *args, **kwargs):
        self.nombre = (self.nombre or "").strip()
        self.nombre_normalizado = normalizar(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.departamento_id:
            return f"{self.nombre} · {self.departamento.nombre}"
        return self.nombre
