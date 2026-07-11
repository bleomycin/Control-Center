from django.db import migrations

# Sonnet 5's tokenizer emits ~30% more tokens for the same text than the
# 4.x generation. 0009 raised the FIELD default to 12288, but existing
# singleton rows keep their stored value — and 8192 (the old default) is
# truthy, so DEFAULT_MAX_TOKENS never applies to them. Without this, an
# existing install that switches its model to Sonnet 5 silently loses ~30%
# of its real output ceiling and starts truncating answers that used to
# fit. Only the exact old default is bumped; a hand-tuned value is kept.

OLD_DEFAULT = 8192
NEW_DEFAULT = 12288


def bump_default_rows(apps, schema_editor):
    AssistantSettings = apps.get_model("assistant", "AssistantSettings")
    AssistantSettings.objects.filter(max_tokens=OLD_DEFAULT).update(
        max_tokens=NEW_DEFAULT
    )


def restore_default_rows(apps, schema_editor):
    AssistantSettings = apps.get_model("assistant", "AssistantSettings")
    AssistantSettings.objects.filter(max_tokens=NEW_DEFAULT).update(
        max_tokens=OLD_DEFAULT
    )


class Migration(migrations.Migration):

    dependencies = [
        ("assistant", "0009_alter_assistantsettings_max_tokens_and_more"),
    ]

    operations = [
        migrations.RunPython(bump_default_rows, restore_default_rows),
    ]
