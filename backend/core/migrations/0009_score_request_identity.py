import uuid

import django.db.models.deletion
from django.db import migrations, models


def fill_identity(apps, schema_editor):
    Record = apps.get_model("core", "ScoreRecord")
    for record in Record.objects.select_related("student").iterator():
        record.cohort_id = record.student.cohort_id
        record.request_id = uuid.uuid4()
        record.save(update_fields=["cohort", "request_id"])


class Migration(migrations.Migration):
    dependencies = [("core", "0008_student_behavior_score_total_scorerecord_and_more")]
    operations = [
        migrations.AddField(model_name="scorerecord", name="cohort", field=models.ForeignKey(
            null=True, on_delete=django.db.models.deletion.CASCADE, to="core.cohort")),
        migrations.AddField(model_name="scorerecord", name="request_id",
                            field=models.UUIDField(null=True)),
        migrations.RunPython(fill_identity, migrations.RunPython.noop),
        migrations.AlterField(model_name="scorerecord", name="cohort", field=models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE, to="core.cohort")),
        migrations.AlterField(model_name="scorerecord", name="request_id",
                              field=models.UUIDField(default=uuid.uuid4)),
        migrations.AddConstraint(model_name="scorerecord", constraint=models.UniqueConstraint(
            fields=["cohort", "creator", "request_id"], name="score_request_once")),
        migrations.AddConstraint(model_name="scorerecord", constraint=models.CheckConstraint(
            condition=(models.Q(kind="positive", score__gte=0, score__lte=100)
                       | models.Q(kind="negative", score__gte=-100, score__lte=0)),
            name="score_kind_range")),
    ]
