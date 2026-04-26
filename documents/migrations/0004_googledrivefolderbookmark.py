# Generated for GoogleDriveFolderBookmark

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_add_picker_debug_to_gdrive_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='GoogleDriveFolderBookmark',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100)),
                ('folder_id', models.CharField(max_length=255)),
                ('sort_order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['sort_order', 'created_at'],
            },
        ),
    ]
