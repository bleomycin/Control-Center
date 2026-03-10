from django.db import migrations


NEW_CATEGORIES = [
    ("document_category", "license", "License / Permit", 12),
    ("document_category", "environmental", "Environmental Report", 13),
]


def seed_new_categories(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, label, sort_order in NEW_CATEGORIES:
        ChoiceOption.objects.get_or_create(
            category=category, value=value,
            defaults={"label": label, "sort_order": sort_order},
        )
    # Bump "other" to sort_order 14
    ChoiceOption.objects.filter(
        category="document_category", value="other"
    ).update(sort_order=14)


def reverse_new_categories(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    ChoiceOption.objects.filter(
        category="document_category", value__in=["license", "environmental"]
    ).delete()
    ChoiceOption.objects.filter(
        category="document_category", value="other"
    ).update(sort_order=12)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0019_alter_choiceoption_category'),
    ]

    operations = [
        migrations.RunPython(seed_new_categories, reverse_new_categories),
    ]
