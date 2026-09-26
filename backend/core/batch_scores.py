import hashlib
import json
import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cohort, ScoreAuditEvent, ScoreRecord, Student
from .permissions import IsTeacher
from .scores import (
    ScoreValuesSerializer,
    create_score_with_audit,
    record_data,
    require_teacher,
    score_page,
)


class SelectedIdsField(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(
            child=serializers.IntegerField(min_value=1), min_length=1, max_length=200, **kwargs
        )

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        if len(set(values)) != len(values):
            raise serializers.ValidationError("請勿重複選取相同項目。")
        return sorted(values)


class BatchScoreSerializer(ScoreValuesSerializer):
    student_ids = SelectedIdsField()


def fingerprint(values):
    payload = {k: v for k, v in values.items() if k != "request_id"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def reject_unavailable(ids):
    if ids:
        raise serializers.ValidationError(
            {
                "detail": "選取項目已失效或無權限，整批未儲存。請重新整理並調整選取。",
                "unavailable_ids": sorted(ids),
            }
        )


class ScoreBatchesView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk):
        form = BatchScoreSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        identity = fingerprint(values)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            students = list(
                Student.objects.filter(cohort_id=pk, pk__in=values["student_ids"])
                .select_related("user")
                .order_by("pk")
            )
            reject_unavailable(set(values["student_ids"]) - {s.pk for s in students})
            existing = list(
                ScoreRecord.objects.filter(
                    cohort_id=pk, creator=request.user, request_id=values["request_id"]
                )
                .select_related("student__user")
                .order_by("student_id")
            )
            if existing:
                if len(existing) != len(students) or any(
                    r.request_fingerprint != identity or not r.batch_id for r in existing
                ):
                    raise serializers.ValidationError(
                        "這次操作已完成，請勿以相同識別送出不同內容。"
                    )
                return Response({"results": [record_data(r) for r in existing]})
            batch_id = uuid.uuid4()
            result = []
            for student in students:
                result.append(
                    create_score_with_audit(request.user, pk, student, values, batch_id, identity)
                )
        return Response({"results": result}, status=201)


class FillReasonsSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    record_ids = SelectedIdsField()
    note = serializers.CharField(max_length=1000, allow_blank=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "包含不支援的欄位。"})
        return super().to_internal_value(data)


def editable_records(user, pk, member):
    records = ScoreRecord.objects.filter(cohort_id=pk)
    if member.role != "homeroom":
        records = records.filter(creator=user)
    return records


class PendingReasonsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            records = editable_records(request.user, pk, member).filter(template="other", note="")
            return score_page(request, records)

    def post(self, request, pk):
        form = FillReasonsSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        identity = fingerprint(values)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            records = list(
                editable_records(request.user, pk, member)
                .filter(pk__in=values["record_ids"])
                .select_related("student__user")
                .order_by("pk")
            )
            reject_unavailable(set(values["record_ids"]) - {r.pk for r in records})
            existing = list(
                ScoreAuditEvent.objects.filter(
                    record__cohort_id=pk, actor=request.user, request_id=values["request_id"]
                )
            )
            if existing:
                if {e.record_id for e in existing} != set(values["record_ids"]) or any(
                    e.request_fingerprint != identity for e in existing
                ):
                    raise serializers.ValidationError(
                        "這次操作已完成，請勿以相同識別送出不同內容。"
                    )
                return Response({"results": [record_data(r) for r in records]})
            reject_unavailable({r.pk for r in records if r.template != "other" or r.note})
            result = []
            for record in records:
                before = record_data(record)
                record.note = values["note"]
                record.save(update_fields=["note"])
                after = record_data(record)
                ScoreAuditEvent.objects.create(
                    record=record,
                    actor=request.user,
                    actor_name=request.user.display_name,
                    action="reason_filled",
                    before=before,
                    after=after,
                    request_id=values["request_id"],
                    request_fingerprint=identity,
                )
                result.append(after)
        return Response({"results": result})
