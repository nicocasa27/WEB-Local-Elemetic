from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0028_herrordenproduccion_cantidad_pintada_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="laserordenproduccion",
            name="archivo_dxf",
            field=models.FileField(blank=True, null=True, upload_to="corte_laser/dxf/"),
        ),
    ]

