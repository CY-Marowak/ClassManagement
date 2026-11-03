from django.db import migrations


def backfill(apps, schema_editor):
    Announcement = apps.get_model("core", "Announcement")
    Version = apps.get_model("core", "AnnouncementVersion")
    database = schema_editor.connection.alias
    for item in Announcement.objects.using(database).iterator():
        Version.objects.using(database).get_or_create(
            announcement_id=item.pk,
            number=item.content_version,
            defaults={"title": item.title, "body": item.body},
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0024_announcement_read_receipts")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
