from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0003_equipotrabajo_estados_json"),
    ]

    operations = [
        migrations.CreateModel(
            name="PdfExtractionTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("proyecto_normalizado", models.CharField(blank=True, db_index=True, max_length=120)),
                ("config_json", models.TextField(default="{}")),
                ("activo", models.BooleanField(default=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-activo", "nombre"],
            },
        ),
    ]

