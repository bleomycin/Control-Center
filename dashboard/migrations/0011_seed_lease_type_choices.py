from django.db import migrations


LEASE_TYPE_SEEDS = [
    ("lease_type", "residential", "Residential", 0),
    ("lease_type", "commercial", "Commercial", 1),
    ("lease_type", "industrial", "Industrial", 2),
    ("lease_type", "retail", "Retail", 3),
    ("lease_type", "office", "Office", 4),
    ("lease_type", "ground_lease", "Ground Lease", 5),
    ("lease_type", "sublease", "Sublease", 6),
    ("lease_type", "other", "Other", 7),
]


def seed_lease_types(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, label, sort_order in LEASE_TYPE_SEEDS:
        ChoiceOption.objects.get_or_create(
            category=category,
            value=value,
            defaults={"label": label, "sort_order": sort_order},
        )


def remove_lease_types(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.filter(category="lease_type").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0010_alter_choiceoption_category"),
    ]

    operations = [
        migrations.RunPython(seed_lease_types, remove_lease_types),
    ]
