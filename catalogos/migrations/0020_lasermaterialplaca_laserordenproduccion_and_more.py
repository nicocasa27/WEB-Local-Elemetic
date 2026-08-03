import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0019_herrordenproduccion_codigo_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='LaserMaterialPlaca',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('nombre_normalizado', models.CharField(db_index=True, max_length=120, unique=True)),
                ('largo_mm', models.PositiveIntegerField(default=0)),
                ('ancho_mm', models.PositiveIntegerField(default=0)),
                ('peso_kg', models.FloatField(default=0.0)),
                ('activo', models.BooleanField(default=True)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-activo', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='LaserOrdenProduccion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(blank=True, default='', max_length=60)),
                ('codigo_normalizado', models.CharField(blank=True, db_index=True, max_length=60, null=True, unique=True)),
                ('pieza_no', models.PositiveIntegerField(default=1)),
                ('total_piezas', models.PositiveIntegerField(default=1)),
                ('nombre', models.CharField(blank=True, default='', max_length=120)),
                ('nombre_normalizado', models.CharField(blank=True, db_index=True, default='', max_length=120)),
                ('descripcion', models.CharField(blank=True, default='', max_length=255)),
                ('archivo', models.FileField(blank=True, null=True, upload_to='corte_laser/archivos/')),
                ('fecha_compromiso', models.DateField(blank=True, db_index=True, null=True)),
                ('prioridad', models.PositiveSmallIntegerField(db_index=True, default=3)),
                ('logo_ancho_mm', models.PositiveIntegerField(default=0)),
                ('logo_alto_mm', models.PositiveIntegerField(default=0)),
                ('peso_kg', models.FloatField(default=0.0)),
                ('ultimo_cambio', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('estado_etapa', models.CharField(db_index=True, default='Espera de corte', max_length=30)),
                ('es_individual', models.BooleanField(db_index=True, default=False)),
                ('cantidad_objetivo', models.PositiveIntegerField(default=1)),
                ('estado', models.CharField(choices=[('Abierta', 'Abierta'), ('Cerrada', 'Cerrada'), ('Cancelada', 'Cancelada')], db_index=True, default='Abierta', max_length=20)),
                ('observaciones', models.CharField(blank=True, max_length=255)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('material', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='catalogos.lasermaterialplaca')),
                ('proyecto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='catalogos.proyecto')),
            ],
            options={
                'ordering': ['-creado_en'],
            },
        ),
        migrations.CreateModel(
            name='LaserOrdenItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etapa', models.CharField(choices=[('Corte', 'Corte'), ('Armado', 'Armado'), ('Soldadura', 'Soldadura'), ('Pintura', 'Pintura')], db_index=True, default='Corte', max_length=20)),
                ('item_nombre', models.CharField(blank=True, default='', max_length=120)),
                ('item_peso_kg', models.FloatField(default=0.0)),
                ('cantidad_requerida', models.PositiveIntegerField(default=1)),
                ('orden', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='catalogos.laserordenproduccion')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='LaserAsignacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etapa', models.CharField(db_index=True, max_length=30)),
                ('rol', models.CharField(db_index=True, max_length=20)),
                ('vigente', models.BooleanField(db_index=True, default=True)),
                ('asignado_por', models.CharField(blank=True, max_length=120)),
                ('asignado_en', models.DateTimeField(auto_now_add=True)),
                ('colaborador', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='catalogos.colaborador')),
                ('maquina', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='catalogos.maquina')),
                ('orden', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones_v2', to='catalogos.laserordenproduccion')),
            ],
            options={
                'ordering': ['-asignado_en'],
            },
        ),
        migrations.CreateModel(
            name='LaserProduccion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField(db_index=True)),
                ('cantidad', models.PositiveIntegerField(default=1)),
                ('observaciones', models.CharField(blank=True, max_length=255)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('operador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='laser_operaciones', to='catalogos.colaborador')),
                ('orden_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='producciones', to='catalogos.laserordenitem')),
            ],
            options={
                'ordering': ['-fecha', '-id'],
            },
        ),
        migrations.CreateModel(
            name='LaserOrdenAsignacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('etapa', models.CharField(choices=[('Corte', 'Corte'), ('Armado', 'Armado'), ('Soldadura', 'Soldadura'), ('Pintura', 'Pintura')], db_index=True, max_length=20)),
                ('asignado_por', models.CharField(blank=True, max_length=120)),
                ('asignado_en', models.DateTimeField(auto_now_add=True)),
                ('colaborador', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalogos.colaborador')),
                ('orden', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='asignaciones', to='catalogos.laserordenproduccion')),
            ],
            options={
                'ordering': ['-asignado_en'],
                'constraints': [models.UniqueConstraint(fields=('orden', 'etapa', 'colaborador'), name='laser_asig_unique')],
            },
        ),
    ]
