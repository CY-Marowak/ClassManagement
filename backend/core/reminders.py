from zoneinfo import ZoneInfo

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .awards import StrictSerializer
from .batch_scores import fingerprint
from .models import (
    Announcement,
    AnnouncementReceipt,
    AnnouncementReminder,
    AnnouncementVersion,
    Cohort,
    Notification,
    ReminderOperation,
    Student,
    User,
)
from .permissions import IsTeacher
from .scores import WholeNumberField, require_teacher


def reminder_today():
    return timezone.localdate(timezone.now(), ZoneInfo("Asia/Taipei"))


def locked_reminder_announcement(request, pk, announcement_id):
    get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
    require_teacher(request.user, pk, homeroom=True)
    user = get_object_or_404(User, pk=request.user.pk)
    if request.session.get("_auth_user_hash") != user.get_session_auth_hash():
        raise PermissionDenied("登入已失效，請重新登入。")
    return get_object_or_404(
        Announcement, pk=announcement_id, cohort_id=pk, deleted_at__isnull=True
    )


class ReminderSerializer(StrictSerializer):
    request_id = serializers.UUIDField()
    content_version = WholeNumberField(min_value=1)
    student_id = WholeNumberField(min_value=1, required=False)


class ReminderPagination(PageNumberPagination):
    page_size = 25


class AnnouncementRemindersView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk, announcement_id):
        with transaction.atomic():
            item = locked_reminder_announcement(request, pk, announcement_id)
            history = (
                AnnouncementReminder.objects.filter(announcement=item)
                .select_related("student__user", "version", "operation__actor")
                .order_by("-pk")
            )
            paginator = ReminderPagination()
            page = paginator.paginate_queryset(history, request)
            assert page is not None
            return paginator.get_paginated_response(
                [
                    {
                        "id": row.pk,
                        "student_id": row.student_id,
                        "seat_number": row.student.seat_number,
                        "name": row.student.user.display_name,
                        "actor_name": row.operation.actor.display_name,
                        "content_version": row.version.number,
                        "sent_date": row.sent_date.isoformat(),
                        "created_at": row.created_at.isoformat(),
                    }
                    for row in page
                ]
            )

    def post(self, request, pk, announcement_id):
        form = ReminderSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        digest = fingerprint({k: v for k, v in values.items() if k != "request_id"})
        with transaction.atomic():
            item = locked_reminder_announcement(request, pk, announcement_id)
            prior = ReminderOperation.objects.filter(
                announcement=item, actor=request.user, request_id=values["request_id"]
            ).first()
            if prior:
                if prior.fingerprint != digest:
                    raise serializers.ValidationError("相同操作識別不可送出不同內容。")
                return Response(prior.result)
            if values["content_version"] != item.content_version:
                return Response({"detail": "公告內容已更新，請載入最新公告後再提醒。"}, status=409)
            students = Student.objects.filter(cohort_id=pk).order_by("pk")
            target = None
            if "student_id" in values:
                target = get_object_or_404(students, pk=values["student_id"])
                students = students.filter(pk=target.pk)
            today = reminder_today()
            version = get_object_or_404(
                AnnouncementVersion, announcement=item, number=item.content_version
            )
            read = set(
                AnnouncementReceipt.objects.filter(version=version).values_list(
                    "student_id", flat=True
                )
            )
            reminded = set(
                AnnouncementReminder.objects.filter(announcement=item, sent_date=today).values_list(
                    "student_id", flat=True
                )
            )
            result = {
                "sent": 0,
                "already_read": 0,
                "already_reminded": 0,
                "content_version": item.content_version,
                "sent_date": today.isoformat(),
            }
            operation = ReminderOperation.objects.create(
                announcement=item,
                actor=request.user,
                target_student=target,
                request_id=values["request_id"],
                fingerprint=digest,
                result=result,
            )
            for student in students:
                if student.pk in read:
                    result["already_read"] += 1
                elif student.pk in reminded:
                    result["already_reminded"] += 1
                else:
                    notice = Notification.objects.create(
                        cohort_id=pk,
                        recipient_id=student.user_id,
                        student=student,
                        announcement=item,
                        kind="announcement_reminder",
                        event_key=f"reminder:{item.pk}:{student.pk}:{today.isoformat()}",
                    )
                    AnnouncementReminder.objects.create(
                        announcement=item,
                        version=version,
                        student=student,
                        operation=operation,
                        notification=notice,
                        sent_date=today,
                    )
                    result["sent"] += 1
            operation.result = result
            operation.save(update_fields=["result"])
            return Response(result, status=201)
