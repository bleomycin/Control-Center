from django.db import migrations

from dashboard.choice_seed_data import SEED_DATA


def seed_choices(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, label, sort_order in SEED_DATA:
        ChoiceOption.objects.get_or_create(
            category=category,
            value=value,
            defaults={"label": label, "sort_order": sort_order},
        )


def unseed_choices(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0003_choiceoption"),
    ]

    operations = [
        migrations.RunPython(seed_choices, unseed_choices),
    ]
