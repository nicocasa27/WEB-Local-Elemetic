import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0022_laserordenproduccion_pieza_alto_mm_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CortaClienteProyecto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('nombre_normalizado', models.CharField(db_index=True, max_length=120, unique=True)),
                ('tipo', models.CharField(choices=[('cliente', 'Cliente'), ('proyecto', 'Proyecto'), ('mixto', 'Cliente/Proyecto')], db_index=True, default='mixto', max_length=12)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-activo', 'nombre'],
            },
        ),
        migrations.AddField(
            model_name='laserordenproduccion',
            name='corta_cliente_proyecto',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='catalogos.cortaclienteproyecto'),
        ),
    ]
