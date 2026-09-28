from datetime import timedelta
from math import isqrt
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .awards import StrictSerializer
from .models import Cohort, PointTransaction, Student
from .permissions import IsReadyUser, IsStudent, IsTeacher
from .scores import WholeNumberField, require_teacher

TAIPEI = ZoneInfo("Asia/Taipei")


class FeedSerializer(StrictSerializer):
    request_id = serializers.UUIDField()
    points = WholeNumberField(min_value=1, max_value=5)


def daily_usage(student):
    now = timezone.localtime(timezone.now(), TAIPEI)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    spent = (
        student.point_transactions.filter(
            kind="feed", created_at__gte=start, created_at__lt=end
        ).aggregate(total=Sum("points"))["total"]
        or 0
    )
    return 5 + spent, end


def transaction_data(entry):
    record = entry.record
    return {
        "id": entry.pk,
        "kind": entry.kind,
        "points": entry.points,
        "created_at": entry.created_at.isoformat(),
        "source": {
            "id": record.pk,
            "reason": record.reason,
            "note": record.note,
            "is_modified": record.is_modified,
            "is_deleted": record.deleted_at is not None,
        }
        if record
        else None,
    }


def mascot_data(mascot):
    # Level L starts at 50 * L * (L - 1). Integer arithmetic avoids boundary drift.
    level = (1 + isqrt(1 + mascot.exp // 50 * 4)) // 2
    start = 50 * level * (level - 1)
    next_exp = 50 * level * (level + 1)
    return {
        "animal": mascot.animal,
        "exp": mascot.exp,
        "level": level,
        "level_start_exp": start,
        "next_level_exp": next_exp,
        "remaining_exp": next_exp - mascot.exp,
    }


class ClassMascotView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            return Response(mascot_data(cohort.mascot))


class StudentMascotView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def locked_student(self, request):
        candidate = get_object_or_404(Student, user=request.user)
        get_object_or_404(Cohort.objects.select_for_update(), pk=candidate.cohort_id)
        student = get_object_or_404(
            Student.objects.select_related("user", "cohort"), pk=candidate.pk
        )
        # A concurrent reset/deletion may have happened while waiting for the class lock.
        if student.must_change_password or (
            request.session.get("_auth_user_hash") != student.user.get_session_auth_hash()
        ):
            raise PermissionDenied("登入已失效，請重新登入並完成密碼修改。")
        return student

    def get(self, request):
        with transaction.atomic():
            student = self.locked_student(request)
            remaining, reset_at = daily_usage(student)
            recent = student.point_transactions.select_related("record").order_by(
                "-created_at", "-pk"
            )[:20]
            return Response(
                {
                    "mascot": mascot_data(student.cohort.mascot),
                    "point_balance": student.point_balance,
                    "daily_remaining": remaining,
                    "daily_reset_at": reset_at.isoformat(),
                    "transactions": [transaction_data(t) for t in recent],
                }
            )

    def post(self, request):
        form = FeedSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        with transaction.atomic():
            student = self.locked_student(request)
            existing = student.point_transactions.filter(request_id=values["request_id"]).first()
            if existing:
                if existing.points != -values["points"]:
                    raise serializers.ValidationError(
                        "這次餵食已完成，請勿以相同識別送出不同內容。"
                    )
                return Response(transaction_data(existing))
            remaining, _ = daily_usage(student)
            if values["points"] > remaining:
                raise serializers.ValidationError("超過今日餵食剩餘額度，每人每天最多五點。")
            if values["points"] > student.point_balance:
                raise serializers.ValidationError("可用點數不足，尚未扣點。")
            student.point_balance -= values["points"]
            student.save(update_fields=["point_balance"])
            entry = PointTransaction.objects.create(
                student=student,
                kind="feed",
                points=-values["points"],
                request_id=values["request_id"],
            )
            mascot = student.cohort.mascot
            mascot.exp += values["points"]
            mascot.save(update_fields=["exp"])
            return Response(transaction_data(entry), status=201)
