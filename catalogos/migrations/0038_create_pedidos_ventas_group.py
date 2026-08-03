from django.db import migrations


def _create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ["pedidos_ventas"]:
        Group.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("catalogos", "0037_logisticastockcorta_logisticaenviocorta_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(_create_groups, migrations.RunPython.noop),
    ]

