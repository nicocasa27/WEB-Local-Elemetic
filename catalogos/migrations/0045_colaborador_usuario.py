"""Enlaza la cuenta con la que entra una persona y su ficha de colaborador.

Sin esto el sistema no puede responder a «qué me toca a mí»: sabe a quién se
le asignó cada orden, pero no sabe que esa persona es la que acaba de iniciar
sesión. Es lo que hace posible la pantalla del celular.

Sólo añade una columna, y nula. Nada de lo que hay se toca.

Django quiso meter aquí, además, quitar y recrear dos restricciones de
`logisticaexpediente`. Es un cambio puramente cosmético —renombrar `check=`
por `condition=`, que es lo que pide Django 6— pero sobre la base del taller
significa borrar y volver a crear restricciones de tablas vivas. Se han
quitado a mano.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogos", "0044_tipos_de_movimiento_por_destino")]

    operations = [
        migrations.AddField(
            model_name="colaborador",
            name="usuario",
            field=models.CharField(blank=True, db_index=True, max_length=150),
        ),
    ]
