from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0004_pdfextractiontemplate"),
    ]

    operations = [
        migrations.CreateModel(
            name="VigaPlano",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("viga_internal_id", models.PositiveIntegerField(db_index=True, unique=True)),
                ("archivo_pdf", models.FileField(upload_to="planos_vigas/%Y/%m/%d")),
                ("nombre_original", models.CharField(blank=True, max_length=255)),
                ("subido_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-subido_en"],
            },
        ),
    ]

