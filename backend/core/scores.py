import re

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, ScoreAuditEvent, ScoreRecord, Student
from .permissions import IsReadyUser, IsStudent, IsTeacher

TEMPLATES = {
    "positive": {"participation": "積極參與", "helping": "主動協助", "completion": "認真完成任務"},
    "negative": {"disruption": "干擾秩序", "incomplete": "未完成任務", "rules": "不遵守課堂規範"},
}


def require_teacher(user, cohort_id, homeroom=False):
    filters = {"role": "homeroom"} if homeroom else {}
    return get_object_or_404(ClassMember, cohort_id=cohort_id, user=user, approved=True, **filters)


def record_data(record):
    return {
        "id": record.pk,
        "student_id": record.student_id,
        "student_name": record.student.user.display_name,
        "seat_number": record.student.seat_number,
        "creator_id": record.creator_id,
        "creator_name": record.creator_name,
        "kind": record.kind,
        "score": record.score,
        "template": record.template,
        "reason": record.reason,
        "note": record.note,
        "needs_reason": record.template == "other" and not record.note,
        "created_at": record.created_at.isoformat(),
    }


class ScorePagination(PageNumberPagination):
    page_size = 25


def score_page(request, records, total=None):
    paginator = ScorePagination()
    page: list[ScoreRecord] | None = paginator.paginate_queryset(
        records.select_related("student__user").order_by("-created_at", "-pk"), request
    )
    assert page is not None
    response = paginator.get_paginated_response([record_data(record) for record in page])
    response.data["total"] = total
    return response


class WholeNumberField(serializers.IntegerField):
    def to_internal_value(self, data):
        if isinstance(data, bool) or not re.fullmatch(r"-?\d+", str(data)):
            self.fail("invalid")
        return super().to_internal_value(data)


class CreateScoreSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    student_id = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=["positive", "negative"])
    score = WholeNumberField(min_value=-100, max_value=100)
    template = serializers.CharField(max_length=30)
    note = serializers.CharField(max_length=1000, allow_blank=True, default="")

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "包含不支援的欄位。"})
        return super().to_internal_value(data)

    def validate(self, attrs):
        kind = attrs["kind"]
        if attrs["template"] not in {**TEMPLATES[kind], "other": "其他"}:
            raise serializers.ValidationError({"template": "請選擇對應加扣分種類的原因。"})
        if (kind == "positive" and attrs["score"] < 0) or (
            kind == "negative" and attrs["score"] > 0
        ):
            raise serializers.ValidationError({"score": "加分為 0～100；扣分為 −100～0。"})
        return attrs


class ScoresView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            records = ScoreRecord.objects.filter(cohort_id=pk)
            total = None
            if "student_id" in request.query_params:
                selection = StudentSelectionSerializer(data=request.query_params)
                selection.is_valid(raise_exception=True)
                student = get_object_or_404(
                    Student, cohort_id=pk, **{"pk": selection.validated_data["student_id"]}
                )
                records = records.filter(student=student)
                total = student.behavior_score_total
            return score_page(request, records, total)

    def post(self, request, pk):
        form = CreateScoreSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            student = get_object_or_404(
                Student.objects.select_related("user"), pk=values["student_id"], cohort_id=pk
            )
            existing = (
                ScoreRecord.objects.filter(
                    cohort_id=pk, creator=request.user, request_id=values["request_id"]
                )
                .select_related("student__user")
                .first()
            )
            if existing:
                if any(
                    getattr(existing, field) != values[field]
                    for field in ("student_id", "kind", "score", "template", "note")
                ):
                    raise serializers.ValidationError(
                        "這次操作已完成，請勿以相同識別送出不同內容。"
                    )
                return Response(record_data(existing))
            record = ScoreRecord.objects.create(
                cohort_id=pk,
                request_id=values["request_id"],
                student=student,
                creator=request.user,
                creator_name=request.user.display_name,
                kind=values["kind"],
                score=values["score"],
                template=values["template"],
                reason=TEMPLATES[values["kind"]].get(values["template"], "其他"),
                note=values["note"],
            )
            student.behavior_score_total += record.score
            student.save(update_fields=["behavior_score_total"])
            data = record_data(record)
            ScoreAuditEvent.objects.create(
                record=record, actor=request.user, actor_name=request.user.display_name, after=data
            )
        return Response(data, status=201)


class StudentScoresView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def get(self, request):
        candidate = get_object_or_404(Student, user=request.user)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=candidate.cohort_id)
            student = get_object_or_404(Student, user=request.user)
            return score_page(request, student.scores.all(), student.behavior_score_total)


class StudentSelectionSerializer(serializers.Serializer):
    student_id = serializers.IntegerField(min_value=1)


class ScoreRosterView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        require_teacher(request.user, pk)
        students = Student.objects.filter(cohort_id=pk).select_related("user")
        return Response(
            {
                "students": [
                    {
                        "id": s.pk,
                        "name": s.user.display_name,
                        "seat_number": s.seat_number,
                        "total": s.behavior_score_total,
                    }
                    for s in students
                ],
                "templates": TEMPLATES,
            }
        )


class ScoreEventsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        require_teacher(request.user, pk, homeroom=True)
        events = ScoreAuditEvent.objects.filter(record__student__cohort_id=pk).order_by(
            "-created_at", "-pk"
        )
        paginator = ScorePagination()
        page = paginator.paginate_queryset(events, request)
        assert page is not None
        return paginator.get_paginated_response(
            [
                {
                    "id": event.pk,
                    "record_id": event.record_id,
                    "actor_id": event.actor_id,
                    "actor_name": event.actor_name,
                    "action": event.action,
                    "before": event.before,
                    "after": event.after,
                    "created_at": event.created_at.isoformat(),
                }
                for event in page
            ]
        )
