from django.db import migrations


FIRM_TYPE_SEEDS = [
    ("firm_type", "law_firm", "Law Firm", 0),
    ("firm_type", "accounting", "Accounting Firm", 1),
    ("firm_type", "property_management", "Property Management", 2),
    ("firm_type", "financial_services", "Financial Services", 3),
    ("firm_type", "insurance", "Insurance", 4),
    ("firm_type", "title_company", "Title Company", 5),
    ("firm_type", "construction", "Construction", 6),
    ("firm_type", "consulting", "Consulting", 7),
    ("firm_type", "other", "Other", 8),
]


def seed_firm_types(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, label, sort_order in FIRM_TYPE_SEEDS:
        ChoiceOption.objects.get_or_create(
            category=category,
            value=value,
            defaults={"label": label, "sort_order": sort_order},
        )


def remove_firm_types(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.filter(category="firm_type").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0016_alter_choiceoption_category"),
    ]

    operations = [
        migrations.RunPython(seed_firm_types, remove_firm_types),
    ]
