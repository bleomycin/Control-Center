from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0004_migrate_stakeholder_fk_to_m2m"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="task",
            name="related_stakeholder",
        ),
        migrations.AlterField(
            model_name="task",
            name="related_stakeholders",
            field=models.ManyToManyField(
                blank=True,
                related_name="tasks",
                to="stakeholders.stakeholder",
            ),
        ),
    ]
