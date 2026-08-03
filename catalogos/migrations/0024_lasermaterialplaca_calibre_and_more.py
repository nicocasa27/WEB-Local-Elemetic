from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0023_cortaclienteproyecto_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lasermaterialplaca',
            name='calibre',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddField(
            model_name='lasermaterialplaca',
            name='espesor_mm',
            field=models.FloatField(default=0.0),
        ),
    ]
