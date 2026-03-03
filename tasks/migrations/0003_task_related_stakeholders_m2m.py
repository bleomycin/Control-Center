from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("stakeholders", "0001_initial"),
        ("tasks", "0002_followup_response_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="related_stakeholders",
            field=models.ManyToManyField(
                blank=True,
                related_name="tasks_m2m",
                to="stakeholders.stakeholder",
            ),
        ),
    ]
