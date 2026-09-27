from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .batch_scores import editable_records, fingerprint, reject_unavailable
from .models import Cohort, ScoreAuditEvent
from .permissions import IsTeacher
from .scores import TEMPLATES, ScoreValuesSerializer, record_data, require_teacher

PREVIEW_SALT = "score-change-preview"


class ScoreEditPreviewView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk, record_id):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            record = get_object_or_404(
                editable_records(request.user, pk, member).select_related("student__user"),
                pk=record_id,
                deleted_at__isnull=True,
            )
            scope = request.query_params.get("scope", "single")
            if scope not in ("single", "batch") or (scope == "batch" and not record.batch_id):
                raise serializers.ValidationError("不支援的修改範圍。")
            targets = [record]
            skipped = []
            if scope == "batch":
                batch = (
                    editable_records(request.user, pk, member)
                    .filter(batch_id=record.batch_id)
                    .select_related("student__user")
                    .order_by("pk")
                )
                targets = []
                for item in batch:
                    if item.deleted_at or item.individually_modified:
                        skipped.append(
                            {
                                **record_data(item),
                                "skip_reason": "已刪除" if item.deleted_at else "已個別修改",
                            }
                        )
                    else:
                        targets.append(item)
            token = signing.dumps(
                {
                    "cohort": pk,
                    "actor": request.user.pk,
                    "scope": scope,
                    "targets": [[r.pk, r.revision] for r in targets],
                    "awards": {
                        str(r.pk): r.award.points if hasattr(r, "award") else None for r in targets
                    },
                },
                salt=PREVIEW_SALT,
            )
            return Response(
                {"token": token, "targets": [record_data(r) for r in targets], "skipped": skipped}
            )


class ScoreChangeSerializer(ScoreValuesSerializer):
    preview_token = serializers.CharField()
    action = serializers.ChoiceField(choices=["edit"])


class DeleteScoreSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    preview_token = serializers.CharField()
    action = serializers.ChoiceField(choices=["delete"])

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "包含不支援的欄位。"})
        return super().to_internal_value(data)


class ScoreChangesView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk):
        if not isinstance(request.data, dict):
            raise serializers.ValidationError("請提供有效的修改內容。")
        serializer = (
            DeleteScoreSerializer
            if request.data.get("action") == "delete"
            else ScoreChangeSerializer
        )
        form = serializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        try:
            preview = signing.loads(values["preview_token"], salt=PREVIEW_SALT, max_age=3600)
        except signing.BadSignature:
            raise serializers.ValidationError("預覽已過期或無效，請重新載入。") from None
        if preview["cohort"] != pk or preview["actor"] != request.user.pk:
            raise serializers.ValidationError("預覽不屬於目前班級或教師。")
        if not preview["targets"] or (
            values["action"] == "delete" and preview["scope"] != "single"
        ):
            raise serializers.ValidationError("沒有可修改的紀錄，或刪除範圍不是單筆。")
        identity = fingerprint(values)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            expected = dict(preview["targets"])
            records = list(
                editable_records(request.user, pk, member)
                .filter(pk__in=expected)
                .select_related("student__user")
                .order_by("pk")
            )
            reject_unavailable(set(expected) - {r.pk for r in records})
            existing = list(
                ScoreAuditEvent.objects.filter(
                    record__cohort_id=pk, actor=request.user, request_id=values["request_id"]
                )
            )
            if existing:
                if {e.record_id for e in existing} != set(expected) or any(
                    e.request_fingerprint != identity for e in existing
                ):
                    raise serializers.ValidationError(
                        "這次操作已完成，請勿以相同識別送出不同內容。"
                    )
                return Response({"results": [record_data(r) for r in records]})
            reject_unavailable(
                {r.pk for r in records if r.deleted_at or r.revision != expected[r.pk]}
            )
            if values["action"] == "delete":
                reject_unavailable(
                    {
                        r.pk
                        for r in records
                        if (r.award.points if hasattr(r, "award") else None)
                        != preview.get("awards", {}).get(str(r.pk))
                    }
                )
            results = []
            for record in records:
                before = record_data(record)
                old_score = record.score
                deleting = values["action"] == "delete"
                if deleting:
                    record.deleted_at = timezone.now()
                else:
                    for field in ("kind", "score", "template", "note"):
                        setattr(record, field, values[field])
                    record.reason = TEMPLATES[record.kind].get(record.template, "其他")
                    record.is_modified = True
                    if preview["scope"] == "single":
                        record.individually_modified = True
                record.revision += 1
                record.save()
                record.student.behavior_score_total += (0 if deleting else record.score) - old_score
                record.student.save(update_fields=["behavior_score_total"])
                after = record_data(record)
                ScoreAuditEvent.objects.create(
                    record=record,
                    actor=request.user,
                    actor_name=request.user.display_name,
                    action="deleted" if deleting else "edited",
                    before=before,
                    after=after,
                    request_id=values["request_id"],
                    request_fingerprint=identity,
                )
                results.append(after)
        return Response({"results": results})
