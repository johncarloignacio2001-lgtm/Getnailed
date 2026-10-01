from django.db import migrations


def seed_receipt_sequence(apps, schema_editor):
    ReceiptSequence = apps.get_model("pos", "ReceiptSequence")
    ReceiptSequence.objects.get_or_create(pk=1, defaults={"last_value": 0})


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_receipt_sequence, migrations.RunPython.noop),
    ]
