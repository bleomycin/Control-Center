from django.db import migrations


def migrate_fk_to_m2m(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    for task in Task.objects.filter(related_stakeholder__isnull=False).select_related("related_stakeholder"):
        task.related_stakeholders.add(task.related_stakeholder)


def migrate_m2m_to_fk(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    for task in Task.objects.prefetch_related("related_stakeholders"):
        first = task.related_stakeholders.first()
        if first:
            task.related_stakeholder = first
            task.save(update_fields=["related_stakeholder"])


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0003_task_related_stakeholders_m2m"),
    ]

    operations = [
        migrations.RunPython(migrate_fk_to_m2m, migrate_m2m_to_fk),
    ]
