from django.db import migrations, models


def seed_tabs(apps, schema_editor):
    StakeholderTab = apps.get_model("stakeholders", "StakeholderTab")
    tabs = [
        {"key": "all", "label": "All", "entity_types": [], "sort_order": 0, "is_builtin": True},
        {"key": "firms", "label": "Firms & Teams", "entity_types": [], "sort_order": 1, "is_builtin": True},
        {"key": "attorneys", "label": "Attorneys", "entity_types": ["attorney"], "sort_order": 2, "is_builtin": False},
        {"key": "lenders", "label": "Lenders", "entity_types": ["lender"], "sort_order": 3, "is_builtin": False},
        {"key": "business-partners", "label": "Business Partners", "entity_types": ["business_partner"], "sort_order": 4, "is_builtin": False},
        {"key": "advisors", "label": "Advisors", "entity_types": ["advisor", "professional"], "sort_order": 5, "is_builtin": False},
    ]
    for tab_data in tabs:
        StakeholderTab.objects.create(**tab_data)


def reverse_seed(apps, schema_editor):
    StakeholderTab = apps.get_model("stakeholders", "StakeholderTab")
    StakeholderTab.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("stakeholders", "0002_alter_contactlog_stakeholder_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="StakeholderTab",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(unique=True)),
                ("label", models.CharField(max_length=100)),
                ("entity_types", models.JSONField(blank=True, default=list, help_text="List of entity_type values for this tab")),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_builtin", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["sort_order", "pk"],
            },
        ),
        migrations.RunPython(seed_tabs, reverse_seed),
    ]
