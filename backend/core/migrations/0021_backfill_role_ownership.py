from django.db import migrations


def backfill(apps, schema_editor):
    Student = apps.get_model("core", "Student")
    Ownership = apps.get_model("core", "StudentRoleOwnership")
    alias = schema_editor.connection.alias
    # Preserve the current avatar; no new draw, spending, or inventory removal.
    batch = []
    for student_id, avatar in Student.objects.using(alias).values_list("id", "avatar").iterator():
        batch.append(Ownership(student_id=student_id, role=avatar))
        if len(batch) == 1000:
            Ownership.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        Ownership.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0020_student_role_ownership")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
