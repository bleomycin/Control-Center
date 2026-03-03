from django.db import migrations


HEALTHCARE_SEEDS = [
    # Provider types
    ("provider_type", "primary_care", "Primary Care", 0),
    ("provider_type", "specialist", "Specialist", 1),
    ("provider_type", "dentist", "Dentist", 2),
    ("provider_type", "optometrist", "Optometrist", 3),
    ("provider_type", "ophthalmologist", "Ophthalmologist", 4),
    ("provider_type", "dermatologist", "Dermatologist", 5),
    ("provider_type", "psychiatrist", "Psychiatrist", 6),
    ("provider_type", "therapist", "Therapist", 7),
    ("provider_type", "physical_therapist", "Physical Therapist", 8),
    ("provider_type", "chiropractor", "Chiropractor", 9),
    ("provider_type", "other", "Other", 10),
    # Test types
    ("test_type", "lab", "Lab Work", 0),
    ("test_type", "imaging", "Imaging", 1),
    ("test_type", "mri", "MRI", 2),
    ("test_type", "ct_scan", "CT Scan", 3),
    ("test_type", "xray", "X-Ray", 4),
    ("test_type", "ultrasound", "Ultrasound", 5),
    ("test_type", "ekg", "EKG", 6),
    ("test_type", "blood_panel", "Blood Panel", 7),
    ("test_type", "biopsy", "Biopsy", 8),
    ("test_type", "other", "Other", 9),
    # Health insurance policy types
    ("policy_type", "health", "Health", 8),
    ("policy_type", "dental", "Dental", 9),
    ("policy_type", "vision", "Vision", 10),
]


def seed_choices(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, label, sort_order in HEALTHCARE_SEEDS:
        ChoiceOption.objects.get_or_create(
            category=category, value=value,
            defaults={"label": label, "sort_order": sort_order},
        )


def reverse_choices(apps, schema_editor):
    ChoiceOption = apps.get_model("dashboard", "ChoiceOption")
    for category, value, _, _ in HEALTHCARE_SEEDS:
        ChoiceOption.objects.filter(category=category, value=value).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("healthcare", "0002_seed_tabs"),
        ("dashboard", "0012_alter_choiceoption_category_healthcare"),
    ]

    operations = [
        migrations.RunPython(seed_choices, reverse_choices),
    ]
