from django.db import migrations


def add_firm_entity_type(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.get_or_create(
        category="entity_type",
        value="firm",
        defaults={"label": "Firm", "sort_order": 7},
    )


def remove_firm_entity_type(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.filter(category="entity_type", value="firm").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_seed_choice_options"),
    ]

    operations = [
        migrations.RunPython(add_firm_entity_type, remove_firm_entity_type),
    ]
