"""Stock comprometido: apalabrar material sin sacarlo del estante.

Sólo agrega. Ningún `RemoveField`, ningún `DeleteModel`, ningún `DROP`.
Revertir el código deja el sistema funcionando sin tocar la base: las dos
columnas nuevas se quedan ahí con su valor por defecto y nadie las lee.

Las dos restricciones se pueden crear directamente, sin `NOT VALID`, porque
`existencia` está vacía: el almacén está construido pero todavía no se usa.
El día que tenga filas habría que crearlas sin validar, corregir lo que
violen y validar después.
"""

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0001_creacion_del_inventario'),
    ]

    operations = [
        migrations.AddField(
            model_name='existencia',
            name='comprometido',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), max_digits=16),
        ),
        migrations.AddField(
            model_name='material',
            name='inventariable',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name='movimientomaterial',
            name='tipo',
            field=models.CharField(choices=[('entrada', 'Entrada'), ('reserva', 'Reserva para una orden'), ('liberacion', 'Liberación de una reserva'), ('consumo', 'Consumo en producción'), ('devolucion', 'Devolución a almacén'), ('merma', 'Merma o desperdicio'), ('ajuste', 'Ajuste de inventario'), ('traslado_salida', 'Traslado: salida'), ('traslado_entrada', 'Traslado: entrada'), ('anulacion', 'Anulación de un movimiento')], db_index=True, max_length=20),
        ),
        migrations.AddConstraint(
            model_name='existencia',
            constraint=models.CheckConstraint(condition=models.Q(('comprometido__gte', Decimal('0'))), name='comprometido_no_negativo'),
        ),
        migrations.AddConstraint(
            model_name='existencia',
            constraint=models.CheckConstraint(condition=models.Q(('comprometido__lte', models.F('cantidad'))), name='comprometido_no_supera_lo_fisico'),
        ),
    ]
