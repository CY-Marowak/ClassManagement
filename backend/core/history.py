import csv
import io
from datetime import datetime, time, timedelta

from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from .awards import StrictSerializer
from .mascots import TAIPEI
from .models import Cohort, PointTransaction, ScoreRecord, Student
from .permissions import IsReadyUser
from .role_catalog import StudentRole
from .role_collection import locked_student
from .scores import ScorePagination, require_teacher


class HistoryFilters(StrictSerializer):
    start = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    end = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    kind = serializers.ChoiceField(choices=["award", "feed", "purchase"], required=False)
    student_id = serializers.IntegerField(min_value=1, required=False)
    page = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if attrs.get("start") and attrs.get("end") and attrs["start"] > attrs["end"]:
            raise serializers.ValidationError("起日不能晚於迄日。")
        if any(value.year >= 9999 for key, value in attrs.items() if key in ("start", "end")):
            raise serializers.ValidationError("日期超出可查詢範圍。")
        return attrs


SCORE_COLUMNS = [
    ("created_at", "紀錄時間（台北）"),
    ("kind", "加扣種類"),
    ("amount", "分數"),
    ("reason", "原因"),
    ("note", "補充原因"),
    ("needs_reason", "待補原因"),
    ("creator_name", "記分教師"),
    ("modified", "已修改"),
]
POINT_COLUMNS = [
    ("created_at", "交易時間（台北）"),
    ("kind", "交易類型"),
    ("amount", "點數"),
    ("reason", "原因"),
    ("note", "補充原因"),
    ("role", "購買角色"),
]
STUDENT_COLUMNS = [("seat_number", "座號"), ("student_name", "姓名"), ("student_number", "學號")]


def history_row(entry, kind, teacher):
    row = {
        "id": entry.pk,
        "created_at": timezone.localtime(entry.created_at, TAIPEI).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if teacher:
        row.update(
            seat_number=entry.student.seat_number,
            student_name=entry.student.user.display_name,
            student_number=entry.student.student_number,
        )
    if kind == "scores":
        row.update(
            kind=entry.get_kind_display(),
            amount=entry.score,
            reason=entry.reason,
            note=entry.note,
            needs_reason="是" if entry.template == "other" and not entry.note else "否",
            creator_name=entry.creator_name,
            modified="是" if entry.is_modified else "否",
        )
    else:
        record = entry.record
        reason = "餵食班級吉祥物" if entry.kind == "feed" else "購買學生角色"
        note = ""
        if record:
            reason = "來源分數已刪除" if record.deleted_at else record.reason
            note = "" if record.deleted_at else record.note
        row.update(
            kind=entry.get_kind_display(),
            amount=entry.points,
            reason=reason,
            note=note,
            role=StudentRole(entry.role).label if entry.role else "",
        )
    return row


def csv_cell(value):
    # Only untrusted text is escaped: real negative point amounts remain numeric.
    if isinstance(value, str):
        trimmed = value.lstrip().lstrip("\ufeff").lstrip()
        if trimmed.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or value.startswith(
            ("\t", "\r", "\n")
        ):
            return "'" + value
    return value


class HistoryView(APIView):
    permission_classes = [IsReadyUser]
    export = False

    def get(self, request, kind, pk=None):
        if kind not in ("scores", "points"):
            raise Http404
        form = HistoryFilters(data=request.query_params)
        form.is_valid(raise_exception=True)
        filters = form.validated_data
        teacher = pk is not None
        if (teacher and request.user.account_type != "teacher") or (
            not teacher and request.user.account_type != "student"
        ):
            raise PermissionDenied("無法存取此明細。")
        if (not teacher and "student_id" in filters) or (kind == "scores" and "kind" in filters):
            raise serializers.ValidationError("此明細不支援指定的篩選條件。")
        with transaction.atomic():
            if teacher:
                get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
                require_teacher(request.user, pk, homeroom=True)
                students = Student.objects.filter(cohort_id=pk)
                if "student_id" in filters:
                    chosen = get_object_or_404(students, pk=filters["student_id"])
                    students = students.filter(pk=chosen.pk)
            else:
                student = locked_student(request)
                students = Student.objects.filter(pk=student.pk)
            records = (
                ScoreRecord.objects.filter(student__in=students, deleted_at__isnull=True)
                if kind == "scores"
                else PointTransaction.objects.filter(student__in=students).select_related("record")
            )
            if "start" in filters:
                records = records.filter(
                    created_at__gte=datetime.combine(filters["start"], time.min, TAIPEI)
                )
            if "end" in filters:
                records = records.filter(
                    created_at__lt=datetime.combine(
                        filters["end"] + timedelta(days=1), time.min, TAIPEI
                    )
                )
            if "kind" in filters:
                records = records.filter(kind=filters["kind"])
            records = records.select_related("student__user").order_by("-created_at", "-pk")
            columns = (STUDENT_COLUMNS if teacher else []) + (
                SCORE_COLUMNS if kind == "scores" else POINT_COLUMNS
            )
            if self.export:
                # Materialize within the class lock; streaming later could bypass revocation/deletion.
                buffer = io.StringIO(newline="")
                writer = csv.writer(buffer)
                writer.writerow([label for _, label in columns])
                for entry in records.iterator(chunk_size=1000):
                    row = history_row(entry, kind, teacher)
                    writer.writerow([csv_cell(row[key]) for key, _ in columns])
                response = HttpResponse(
                    "\ufeff" + buffer.getvalue(), content_type="text/csv; charset=utf-8"
                )
                response["Content-Disposition"] = f'attachment; filename="cm-{kind}.csv"'
            else:
                paginator = ScorePagination()
                page = paginator.paginate_queryset(records, request)
                assert page is not None
                response = paginator.get_paginated_response(
                    [history_row(e, kind, teacher) for e in page]
                )
                response.data["columns"] = [{"key": key, "label": label} for key, label in columns]
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
