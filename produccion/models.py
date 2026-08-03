from django.db import models


ESTADOS = [
    "Espera de corte",
    "Corte",
    "Espera de armado",
    "Armado",
    "Espera de soldadura",
    "Soldadura",
    "Espera de pintura",
    "Pintura",
    "Terminado",
    "Enviado",
]


class Viga(models.Model):
    internal_id = models.AutoField(primary_key=True)
    codigo_viga = models.TextField()
    pieza_no = models.IntegerField()
    total_piezas = models.IntegerField()
    proyecto = models.TextField()
    descripcion = models.TextField(blank=True)
    fecha_compromiso = models.DateField()
    estado = models.TextField()
    observaciones = models.TextField(blank=True)
    prioridad = models.IntegerField()
    peso_kg = models.DecimalField(max_digits=15, decimal_places=3)
    fecha_creacion = models.DateTimeField()
    ultimo_cambio = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "vigas"

    def __str__(self) -> str:
        return f"{self.codigo_viga} ({self.pieza_no}/{self.total_piezas})"


class ProductionLog(models.Model):
    id = models.AutoField(primary_key=True)
    viga_internal = models.ForeignKey(
        Viga,
        db_column="viga_internal_id",
        on_delete=models.DO_NOTHING,
        related_name="logs",
    )
    fecha_operacion = models.DateField()
    estado_anterior = models.TextField()
    estado_nuevo = models.TextField()
    comentario = models.TextField(blank=True)
    timestamp = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "production_log"
