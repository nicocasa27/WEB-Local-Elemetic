from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0006_weeklyreportsnapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="Colaborador",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                (
                    "rol",
                    models.CharField(
                        choices=[("Soldador", "Soldador"), ("Auxiliar", "Auxiliar"), ("Pintor", "Pintor")],
                        max_length=20,
                    ),
                ),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "equipo",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="colaboradores", to="catalogos.equipotrabajo"),
                ),
            ],
            options={
                "ordering": ["equipo__nombre", "rol", "nombre"],
            },
        ),
        migrations.CreateModel(
            name="VigaAsignacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("viga_internal_id", models.PositiveIntegerField(db_index=True)),
                ("etapa", models.CharField(db_index=True, max_length=30)),
                ("rol", models.CharField(db_index=True, max_length=20)),
                ("vigente", models.BooleanField(db_index=True, default=True)),
                ("asignado_por", models.CharField(blank=True, max_length=120)),
                ("asignado_en", models.DateTimeField(auto_now_add=True)),
                ("colaborador", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="catalogos.colaborador")),
            ],
            options={
                "ordering": ["-asignado_en"],
            },
        ),
        migrations.AddIndex(
            model_name="vigaasignacion",
            index=models.Index(fields=["viga_internal_id", "etapa", "rol", "vigente"], name="catalogos_viga_i_8a2308_idx"),
        ),
    ]
