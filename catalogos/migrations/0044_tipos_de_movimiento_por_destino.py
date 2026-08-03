"""Distingue las reversiones que devuelven al almacén de las que devuelven al apartado.

Hasta ahora las dos escribían el mismo tipo `revertir`, así que era imposible
saber, mirando un movimiento, si esa cantidad había vuelto al stock disponible
o a la reserva del pedido. Como consecuencia, el stock no se podía reconstruir
a partir de su propio historial.

Sólo cambian los `choices`, que Django no traduce a ninguna restricción en
PostgreSQL: la migración no toca datos ni bloquea las tablas. Los registros
anteriores conservan el valor `revertir`, que se mantiene en la lista para
poder leerlos, marcado como histórico.

Se dejaron fuera a propósito las operaciones sobre las restricciones de
LogisticaExpediente que `makemigrations` propone de paso. Son consecuencia de
que Django 6 renombra `CheckConstraint.check` a `condition`, no de este
cambio, y suponen un DROP y un CREATE sobre tablas vivas. Van en su propia
migración.
"""

from django.db import migrations, models

CHOICES = [
    ("stock_in", "stock_in"),
    ("ajuste", "ajuste"),
    ("apartar", "apartar"),
    ("enviar", "enviar"),
    ("revertir_a_stock", "revertir a stock"),
    ("revertir_a_apartado", "revertir a apartado"),
    ("revertir", "revertir (histórico, ambiguo)"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0043_logisticaacuseentrega"),
    ]

    operations = [
        migrations.AlterField(
            model_name="logisticamovimiento",
            name="tipo",
            field=models.CharField(choices=CHOICES, db_index=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="logisticamovimientocorta",
            name="tipo",
            field=models.CharField(choices=CHOICES, db_index=True, max_length=20),
        ),
    ]
