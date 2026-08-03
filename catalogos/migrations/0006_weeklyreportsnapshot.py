from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0005_vigaplano"),
    ]

    operations = [
        migrations.CreateModel(
            name="WeeklyReportSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField(db_index=True, unique=True)),
                ("week_end", models.DateField(db_index=True)),
                ("integrantes_total", models.PositiveIntegerField(default=0)),
                ("payload_json", models.TextField(default="{}")),
                ("generado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-week_start"],
            },
        ),
    ]

