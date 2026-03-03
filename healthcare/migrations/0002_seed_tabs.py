from django.db import migrations


def seed_tabs(apps, schema_editor):
    HealthcareTab = apps.get_model("healthcare", "HealthcareTab")
    tabs = [
        {
            "key": "active-care",
            "label": "Active Care",
            "healthcare_types": ["providers", "prescriptions", "supplements", "conditions"],
            "sort_order": 0,
            "is_builtin": True,
        },
        {
            "key": "records",
            "label": "Records",
            "healthcare_types": ["test_results", "visits"],
            "sort_order": 1,
            "is_builtin": True,
        },
        {
            "key": "planning",
            "label": "Planning",
            "healthcare_types": ["appointments", "advice"],
            "sort_order": 2,
            "is_builtin": True,
        },
    ]
    for tab_data in tabs:
        HealthcareTab.objects.get_or_create(key=tab_data["key"], defaults=tab_data)


def reverse_tabs(apps, schema_editor):
    HealthcareTab = apps.get_model("healthcare", "HealthcareTab")
    HealthcareTab.objects.filter(key__in=["active-care", "records", "planning"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("healthcare", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_tabs, reverse_tabs),
    ]
