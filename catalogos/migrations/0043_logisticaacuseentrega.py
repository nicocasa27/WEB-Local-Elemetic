from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0042_expediente_para_corta"),
    ]

    operations = [
        migrations.CreateModel(
            name="LogisticaAcuseEntrega",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad", models.PositiveIntegerField(default=1)),
                ("fecha", models.DateField(db_index=True)),
                ("entregado_por", models.CharField(blank=True, default="", max_length=120)),
                ("recibido_por", models.CharField(blank=True, default="", max_length=120)),
                ("creado_en", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "pedido_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acuses_logistica",
                        to="catalogos.pedidoproduccionitem",
                    ),
                ),
            ],
            options={
                "ordering": ["-creado_en"],
            },
        ),
    ]

