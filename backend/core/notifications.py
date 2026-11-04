from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .awards import StrictSerializer
from .models import ClassMember, Cohort, Notification, Student, User
from .permissions import IsReadyUser
from .scores import WholeNumberField


def notify_homeroom(cohort_id, actor, kind, event_key, announcement=None, member=None):
    owner = ClassMember.objects.filter(cohort_id=cohort_id, role="homeroom", approved=True).first()
    if owner and owner.user_id != actor.pk:
        Notification.objects.create(
            cohort_id=cohort_id,
            recipient_id=owner.user_id,
            kind=kind,
            event_key=event_key,
            announcement=announcement,
            member=member,
        )


def notify_students(announcement, actor, kind, event_key):
    # Called within the originating event's cohort transaction and retry guard.
    Notification.objects.bulk_create(
        [
            Notification(
                cohort_id=announcement.cohort_id,
                recipient_id=student.user_id,
                student=student,
                announcement=announcement,
                kind=kind,
                event_key=event_key,
            )
            for student in Student.objects.filter(cohort_id=announcement.cohort_id).exclude(
                user=actor
            )
        ]
    )


def locked_inbox(request):
    user = request.user
    if user.account_type == "student":
        student = get_object_or_404(Student, user=user)
        cohort_ids = [student.cohort_id]
    else:
        cohort_ids = list(
            ClassMember.objects.filter(user=user, role="homeroom", approved=True).values_list(
                "cohort_id", flat=True
            )
        )
    # Same cohort locks as event creation, student reset and permanent deletion.
    list(Cohort.objects.select_for_update().filter(pk__in=cohort_ids).order_by("pk"))
    current = get_object_or_404(User, pk=user.pk)
    if request.session.get("_auth_user_hash") != current.get_session_auth_hash():
        raise PermissionDenied("登入已失效，請重新登入。")
    if user.account_type == "student":
        student = get_object_or_404(Student, user=user)
        if student.must_change_password:
            raise PermissionDenied("請先完成首次密碼修改。")
        allowed = Q(student=student, cohort_id=student.cohort_id)
    else:
        allowed = Q(
            student__isnull=True,
            cohort_id__in=ClassMember.objects.filter(
                user=user, role="homeroom", approved=True
            ).values("cohort_id"),
        )
    return (
        Notification.objects.filter(allowed, recipient=user)
        .filter(
            Q(announcement__deleted_at__isnull=True, announcement__isnull=False)
            | Q(member__isnull=False)
        )
        .select_related("announcement", "cohort", "member")
        .order_by("-pk")
    )


def notification_data(item):
    return {
        "id": item.pk,
        "kind": item.kind,
        "title": item.announcement.title if item.announcement_id else "教師加入申請",
        "cohort_name": item.cohort.name,
        "created_at": item.created_at.isoformat(),
        "viewed_at": item.viewed_at.isoformat() if item.viewed_at else None,
    }


class NotificationPagination(PageNumberPagination):
    page_size = 25


class NotificationsView(APIView):
    permission_classes = [IsReadyUser]

    def get(self, request):
        with transaction.atomic():
            inbox = locked_inbox(request)
            paginator = NotificationPagination()
            page: list[Notification] | None = paginator.paginate_queryset(inbox, request)
            assert page is not None
            response = paginator.get_paginated_response([notification_data(item) for item in page])
            response.data["unread_count"] = inbox.filter(viewed_at__isnull=True).count()
            response.data["latest_id"] = inbox.values_list("pk", flat=True).first() or 0
            return response


class OpenNotificationView(APIView):
    permission_classes = [IsReadyUser]

    def post(self, request, notification_id):
        with transaction.atomic():
            item = get_object_or_404(locked_inbox(request), pk=notification_id)
            if item.viewed_at is None:
                item.viewed_at = timezone.now()
                item.save(update_fields=["viewed_at"])
            return Response(
                {
                    "cohort_id": item.cohort_id,
                    "announcement_id": item.announcement_id,
                    "member_id": item.member_id,
                    "member_status": item.member.status if item.member_id else None,
                }
            )


class ViewAllSerializer(StrictSerializer):
    through_id = WholeNumberField(min_value=0)


class ViewAllNotificationsView(APIView):
    permission_classes = [IsReadyUser]

    def post(self, request):
        form = ViewAllSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            inbox = locked_inbox(request)
            # Keep notifications arriving after the displayed inbox unread, including on retry.
            inbox.filter(pk__lte=form.validated_data["through_id"], viewed_at__isnull=True).update(
                viewed_at=timezone.now()
            )
            return Response({"detail": "通知已標為已查看，公告已讀狀態不變。"})
