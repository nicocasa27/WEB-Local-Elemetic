"""Pone al día el estado de dos restricciones. **No toca la base.**

Django 5.2 renombró el argumento de `CheckConstraint` de `check=` a
`condition=`. Es el mismo SQL con otro nombre de parámetro: no cambia nada de
lo que hay en Postgres.

Pero el estado que Django reconstruye del historial de migraciones se quedó con
la forma vieja, así que cada `makemigrations` proponía tirar y volver a crear
las dos restricciones de `logisticaexpediente`. Eso venía arrastrándose desde
hace varias migraciones, y en cada una había que quitarlo a mano antes de
aplicarla; el día que a alguien se le pasara, el despliegue habría soltado
restricciones sobre tablas vivas para dejarlas exactamente igual.

`SeparateDatabaseAndState` con `database_operations=[]` es justo para esto:
actualiza lo que Django cree, sin ejecutar una sola instrucción SQL. Después de
esta migración, `makemigrations --check` queda limpio y el desajuste deja de
reaparecer.
"""

from django.db import migrations, models

#: La condición es idéntica en las dos tablas: o expediente de pedido, o de
#: orden de Corta, nunca los dos ni ninguno.
UNO_U_OTRO = models.Q(
    models.Q(("pedido__isnull", False), ("orden_corta__isnull", True)),
    models.Q(("pedido__isnull", True), ("orden_corta__isnull", False)),
    _connector="OR",
)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0046_centros_y_cuadrillas"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="logisticaexpediente",
                    name="logisticaexpediente_exactly_one_target",
                ),
                migrations.RemoveConstraint(
                    model_name="logisticaexpedientedescarga",
                    name="logisticaexpdescarga_exactly_one_target",
                ),
                migrations.AddConstraint(
                    model_name="logisticaexpediente",
                    constraint=models.CheckConstraint(
                        condition=UNO_U_OTRO,
                        name="logisticaexpediente_exactly_one_target",
                    ),
                ),
                migrations.AddConstraint(
                    model_name="logisticaexpedientedescarga",
                    constraint=models.CheckConstraint(
                        condition=UNO_U_OTRO,
                        name="logisticaexpdescarga_exactly_one_target",
                    ),
                ),
            ],
        ),
    ]
