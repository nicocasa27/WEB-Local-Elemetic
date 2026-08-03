import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0021_create_corte_laser_groups'),
    ]

    operations = [
        migrations.AddField(
            model_name='laserordenproduccion',
            name='pieza_alto_mm',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='laserordenproduccion',
            name='pieza_ancho_mm',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='LaserEstadoCambio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado_anterior', models.CharField(blank=True, default='', max_length=30)),
                ('estado_nuevo', models.CharField(blank=True, default='', max_length=30)),
                ('fecha_operacion', models.DateField(blank=True, db_index=True, null=True)),
                ('actor_username', models.CharField(blank=True, default='', max_length=120)),
                ('motivo_retroceso', models.CharField(blank=True, default='', max_length=255)),
                ('comentario', models.CharField(blank=True, default='', max_length=255)),
                ('creado_en', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('orden', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cambios_estado', to='catalogos.laserordenproduccion')),
            ],
            options={
                'ordering': ['-creado_en'],
            },
        ),
    ]
