import django.db.models.deletion
from django.db import migrations, models


def preserve_student_names(apps, schema_editor):
    Event = apps.get_model("core", "StudentAuditEvent")
    for event in (
        Event.objects.using(schema_editor.connection.alias)
        .select_related("student__user")
        .iterator()
    ):
        event.student_name = event.student.user.display_name
        event.save(update_fields=["student_name"], using=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("core", "0005_cohort_student_login_code_user_account_type_and_more")]

    operations = [
        migrations.RenameModel(old_name="StudentCreatedEvent", new_name="StudentAuditEvent"),
        migrations.AlterField(
            model_name="studentauditevent",
            name="student",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="audit_events",
                to="core.student",
            ),
        ),
        migrations.AddField(
            model_name="studentauditevent",
            name="action",
            field=models.CharField(
                max_length=20,
                default="created",
                choices=[
                    ("created", "建立學生"),
                    ("profile_updated", "修改資料"),
                    ("password_reset", "重設密碼"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="studentauditevent",
            name="student_name",
            field=models.CharField(max_length=80, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="studentauditevent", name="before", field=models.JSONField(default=dict)
        ),
        migrations.AddField(
            model_name="studentauditevent", name="after", field=models.JSONField(default=dict)
        ),
        migrations.RunPython(preserve_student_names, migrations.RunPython.noop),
    ]
