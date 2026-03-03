from django.db import migrations


def seed_leases_tab(apps, schema_editor):
    AssetTab = apps.get_model("assets", "AssetTab")
    # Update "All" builtin tab to include leases
    try:
        all_tab = AssetTab.objects.get(key="all")
        if "leases" not in all_tab.asset_types:
            all_tab.asset_types = all_tab.asset_types + ["leases"]
            all_tab.save()
    except AssetTab.DoesNotExist:
        pass

    # Create "Leases" tab if it doesn't exist
    last = AssetTab.objects.order_by("-sort_order").first()
    next_order = (last.sort_order + 1) if last else 0
    AssetTab.objects.get_or_create(
        key="leases",
        defaults={
            "label": "Leases",
            "asset_types": ["leases"],
            "sort_order": next_order,
            "is_builtin": False,
        },
    )


def remove_leases_tab(apps, schema_editor):
    AssetTab = apps.get_model("assets", "AssetTab")
    AssetTab.objects.filter(key="leases").delete()
    # Remove leases from All tab
    try:
        all_tab = AssetTab.objects.get(key="all")
        if "leases" in all_tab.asset_types:
            all_tab.asset_types = [t for t in all_tab.asset_types if t != "leases"]
            all_tab.save()
    except AssetTab.DoesNotExist:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0009_lease_leaseparty_lease_stakeholders"),
    ]

    operations = [
        migrations.RunPython(seed_leases_tab, remove_leases_tab),
    ]
