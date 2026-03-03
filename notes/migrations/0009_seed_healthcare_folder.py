from django.db import migrations


def seed_healthcare_folder(apps, schema_editor):
    Folder = apps.get_model("notes", "Folder")
    if not Folder.objects.filter(name="Healthcare").exists():
        Folder.objects.create(name="Healthcare", color="cyan", sort_order=5)


def unseed_healthcare_folder(apps, schema_editor):
    Folder = apps.get_model("notes", "Folder")
    Folder.objects.filter(name="Healthcare").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0008_note_healthcare_m2m"),
    ]

    operations = [
        migrations.RunPython(seed_healthcare_folder, unseed_healthcare_folder),
    ]
