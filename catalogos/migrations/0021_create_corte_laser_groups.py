from django.db import migrations


def _create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ["corte_laser", "corte_laser_supervision"]:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0020_lasermaterialplaca_laserordenproduccion_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(_create_groups, migrations.RunPython.noop),
    ]

