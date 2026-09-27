from datetime import timedelta
from typing import TypedDict

from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .batch_scores import fingerprint, reject_unavailable
from .models import Cohort, PointAwardBatch, PointTransaction, ScoreRecord, Student
from .permissions import IsTeacher
from .scores import ScorePagination, WholeNumberField, record_data, require_teacher


class AwardStudent(TypedDict):
    id: int
    name: str
    seat_number: int
    point_balance: int
    records: list[dict]


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"detail": "包含不支援的欄位。"})
        return super().to_internal_value(data)


class AwardItemSerializer(StrictSerializer):
    record_id = WholeNumberField(min_value=1)
    revision = WholeNumberField(min_value=1)
    points = WholeNumberField(min_value=1, max_value=100, default=1)


class AwardSerializer(StrictSerializer):
    request_id = serializers.UUIDField()
    items: serializers.ListSerializer = serializers.ListSerializer(
        child=AwardItemSerializer(), allow_empty=False, max_length=200
    )

    def validate_items(self, items):
        if len({item["record_id"] for item in items}) != len(items):
            raise serializers.ValidationError("請勿重複選取相同來源。")
        return sorted(items, key=lambda item: item["record_id"])


def batch_data(batch):
    return {
        "batch_id": batch.pk,
        "results": [
            {"record_id": t.record_id, "student_id": t.student_id, "points": t.points}
            for t in batch.transactions.order_by("record_id")
        ],
    }


class PointAwardsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            status = request.query_params.get("status", "pending")
            if status not in ("pending", "awarded"):
                raise serializers.ValidationError("不支援的發點狀態。")
            records = ScoreRecord.objects.filter(cohort_id=pk, creator=request.user)
            if status == "pending":
                records = records.filter(
                    kind="positive", deleted_at__isnull=True, award__isnull=True
                )
            else:
                records = records.filter(award__isnull=False)
            # Page by student so one student's source records stay together.
            paginator = ScorePagination()
            students = (
                Student.objects.filter(cohort_id=pk, scores__in=records)
                .distinct()
                .order_by("seat_number", "pk")
            )
            page = paginator.paginate_queryset(students.select_related("user"), request)
            assert page is not None
            assert paginator.page is not None
            grouped: dict[int, AwardStudent] = {
                s.pk: {
                    "id": s.pk,
                    "name": s.user.display_name,
                    "seat_number": s.seat_number,
                    "point_balance": s.point_balance,
                    "records": [],
                }
                for s in page
            }
            for record in (
                records.filter(student_id__in=grouped)
                .select_related("student__user", "award")
                .order_by("-created_at", "-pk")
            ):
                grouped[record.student_id]["records"].append(record_data(record))
            now = timezone.localtime()
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
            week = PointTransaction.objects.filter(
                batch__cohort_id=pk,
                batch__actor=request.user,
                created_at__gte=start,
                created_at__lt=end,
            ).aggregate(points=Sum("points"), count=Count("id"))
            return Response(
                {
                    "students": list(grouped.values()),
                    "count": paginator.page.paginator.count,
                    "next": paginator.get_next_link(),
                    "previous": paginator.get_previous_link(),
                    "week": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "points": week["points"] or 0,
                        "count": week["count"],
                    },
                }
            )

    def post(self, request, pk):
        form = AwardSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        identity = fingerprint(values)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            items = {item["record_id"]: item for item in values["items"]}
            records = list(
                ScoreRecord.objects.filter(cohort_id=pk, creator=request.user, pk__in=items)
                .select_related("award")
                .order_by("pk")
            )
            reject_unavailable(set(items) - {r.pk for r in records})
            existing = PointAwardBatch.objects.filter(
                cohort_id=pk, actor=request.user, request_id=values["request_id"]
            ).first()
            if existing:
                if (
                    existing.request_fingerprint != identity
                    or existing.transactions.count() != existing.item_count
                ):
                    raise serializers.ValidationError(
                        "這次操作已完成，請勿以相同識別送出不同內容。"
                    )
                return Response(batch_data(existing))
            reject_unavailable(
                {
                    r.pk
                    for r in records
                    if r.deleted_at
                    or r.kind != "positive"
                    or hasattr(r, "award")
                    or r.revision != items[r.pk]["revision"]
                }
            )
            batch = PointAwardBatch.objects.create(
                cohort_id=pk,
                actor=request.user,
                actor_name=request.user.display_name,
                request_id=values["request_id"],
                request_fingerprint=identity,
                item_count=len(records),
            )
            students = {
                s.pk: s for s in Student.objects.filter(pk__in={r.student_id for r in records})
            }
            for record in records:
                points = items[record.pk]["points"]
                PointTransaction.objects.create(
                    batch=batch, student_id=record.student_id, record=record, points=points
                )
                students[record.student_id].point_balance += points
            for student in students.values():
                student.save(update_fields=["point_balance"])
            return Response(batch_data(batch), status=201)
