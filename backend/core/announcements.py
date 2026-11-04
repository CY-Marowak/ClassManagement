from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .announcement_content import validate_document
from .awards import StrictSerializer
from .batch_scores import fingerprint
from .models import (
    Announcement,
    AnnouncementOperation,
    AnnouncementReceipt,
    AnnouncementVersion,
    Cohort,
    Student,
)
from .notifications import notify_students
from .permissions import IsReadyUser, IsStudent, IsTeacher
from .scores import WholeNumberField, require_teacher


class PublishSerializer(StrictSerializer):
    request_id = serializers.UUIDField()
    title = serializers.CharField(max_length=100)
    body = serializers.JSONField()

    def validate_title(self, value):
        if "\n" in value or "\r" in value:
            raise serializers.ValidationError("標題請使用單行文字。")
        return value

    def validate_body(self, value):
        return validate_document(value)


class ChangeSerializer(PublishSerializer):
    action = serializers.ChoiceField(choices=["edit", "pin", "delete"])
    revision = WholeNumberField(min_value=1)
    title = serializers.CharField(max_length=100, required=False)
    body = serializers.JSONField(required=False)
    is_pinned = serializers.BooleanField(required=False)

    def validate(self, attrs):
        fields = (
            {"title", "body"}
            if attrs["action"] == "edit"
            else ({"is_pinned"} if attrs["action"] == "pin" else set())
        )
        if set(attrs) != fields | {"action", "revision", "request_id"}:
            raise serializers.ValidationError("操作欄位不完整或包含不支援的欄位。")
        return attrs


def prior_result(cohort_id, user, request_id, digest):
    operation = AnnouncementOperation.objects.filter(
        cohort_id=cohort_id,
        actor=user,
        request_id=request_id,
    ).first()
    if operation:
        if operation.fingerprint != digest:
            raise serializers.ValidationError("相同操作識別不可送出不同內容。")
        return operation.result
    return None


def save_result(item, user, values, digest, result):
    AnnouncementOperation.objects.create(
        announcement=item,
        cohort_id=item.cohort_id,
        actor=user,
        request_id=values["request_id"],
        fingerprint=digest,
        result=result,
    )


def announcement_data(item, confirmed_at=None):
    return {
        "comment_count": item.comments.filter(deleted_at__isnull=True).count(),
        "id": item.pk,
        "title": item.title,
        "body": item.body,
        "creator_name": item.creator_name,
        "is_pinned": item.is_pinned,
        "revision": item.revision,
        "content_version": item.content_version,
        "confirmed_at": confirmed_at.isoformat() if confirmed_at else None,
        "created_at": item.created_at.isoformat(),
        "edited_at": item.edited_at.isoformat() if item.edited_at else None,
    }


class AnnouncementPagination(PageNumberPagination):
    page_size = 10


def announcement_page(request, cohort_id, student=None):
    paginator = AnnouncementPagination()
    items = Announcement.objects.filter(cohort_id=cohort_id, deleted_at__isnull=True)
    if "announcement_id" in request.query_params:
        field = WholeNumberField(min_value=1)
        item_id = field.run_validation(request.query_params["announcement_id"])
        get_object_or_404(items, pk=item_id)
        items = items.filter(pk=item_id)
    page = paginator.paginate_queryset(
        items.order_by("-is_pinned", "-created_at", "-pk"),
        request,
    )
    assert page is not None
    receipts = {}
    if student:
        receipts = {
            (receipt.version.announcement_id, receipt.version.number): receipt.confirmed_at
            for receipt in AnnouncementReceipt.objects.filter(
                student=student, version__announcement__in=page
            ).select_related("version")
        }
    return paginator.get_paginated_response(
        [announcement_data(item, receipts.get((item.pk, item.content_version))) for item in page]
    )


def save_content_version(item):
    AnnouncementVersion.objects.create(
        announcement=item, number=item.content_version, title=item.title, body=item.body
    )


class AnnouncementsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk)
            return announcement_page(request, pk)

    def post(self, request, pk):
        form = PublishSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        digest = fingerprint({"action": "publish", **values})
        with transaction.atomic():
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            previous = prior_result(pk, request.user, values["request_id"], digest)
            if previous is not None:
                return Response(previous)
            item = Announcement.objects.create(
                cohort=cohort,
                creator=request.user,
                creator_name=request.user.display_name,
                title=values["title"],
                body=values["body"],
            )
            save_content_version(item)
            notify_students(
                item, request.user, "announcement_published", f"announcement:{item.pk}:1"
            )
            result = announcement_data(item)
            save_result(item, request.user, values, digest, result)
            return Response(result, status=201)


class AnnouncementChangeView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk, announcement_id):
        form = ChangeSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        digest = fingerprint({"announcement_id": announcement_id, **values})
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            previous = prior_result(pk, request.user, values["request_id"], digest)
            if previous is not None:
                return Response(previous)
            item = get_object_or_404(
                Announcement,
                pk=announcement_id,
                cohort_id=pk,
                deleted_at__isnull=True,
            )
            if item.revision != values["revision"]:
                return Response({"detail": "公告已變更，請重新整理後再操作。"}, status=409)
            if values["action"] == "edit":
                if (item.title, item.body) != (values["title"], values["body"]):
                    item.title, item.body = values["title"], values["body"]
                    item.edited_at = timezone.now()
                    item.content_version += 1
                    save_content_version(item)
                    notify_students(
                        item,
                        request.user,
                        "announcement_updated",
                        f"announcement:{item.pk}:{item.content_version}",
                    )
            elif values["action"] == "pin":
                item.is_pinned = values["is_pinned"]
            else:
                item.deleted_at = timezone.now()
            item.revision += 1
            item.save()
            result = {"detail": "公告已刪除。"} if item.deleted_at else announcement_data(item)
            save_result(item, request.user, values, digest, result)
            return Response(result)


def locked_announcement_student(request):
    student = get_object_or_404(Student, user=request.user)
    get_object_or_404(Cohort.objects.select_for_update(), pk=student.cohort_id)
    student = get_object_or_404(Student.objects.select_related("user"), pk=student.pk)
    if student.must_change_password or (
        request.session.get("_auth_user_hash") != student.user.get_session_auth_hash()
    ):
        raise PermissionDenied("登入已失效，請重新登入並完成密碼修改。")
    return student


class StudentAnnouncementsView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def get(self, request):
        with transaction.atomic():
            student = locked_announcement_student(request)
            return announcement_page(request, student.cohort_id, student)


class ConfirmReadSerializer(StrictSerializer):
    content_version = WholeNumberField(min_value=1)


class StudentAnnouncementReadView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def post(self, request, announcement_id):
        form = ConfirmReadSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            student = locked_announcement_student(request)
            item = get_object_or_404(
                Announcement,
                pk=announcement_id,
                cohort_id=student.cohort_id,
                deleted_at__isnull=True,
            )
            if item.content_version != form.validated_data["content_version"]:
                return Response(
                    {"detail": "公告內容已更新，請重新載入並閱讀後再確認。"}, status=409
                )
            version = get_object_or_404(
                AnnouncementVersion, announcement=item, number=item.content_version
            )
            receipt, _ = AnnouncementReceipt.objects.get_or_create(version=version, student=student)
            return Response(
                {
                    "content_version": version.number,
                    "confirmed_at": receipt.confirmed_at.isoformat(),
                }
            )


class AnnouncementReceiptsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk, announcement_id):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            item = get_object_or_404(
                Announcement, pk=announcement_id, cohort_id=pk, deleted_at__isnull=True
            )
            receipts = dict(
                AnnouncementReceipt.objects.filter(
                    version__announcement=item, version__number=item.content_version
                ).values_list("student_id", "confirmed_at")
            )
            students = [
                {
                    "id": student.pk,
                    "seat_number": student.seat_number,
                    "name": student.user.display_name,
                    "confirmed_at": receipts[student.pk].isoformat()
                    if student.pk in receipts
                    else None,
                }
                for student in Student.objects.filter(cohort_id=pk)
                .select_related("user")
                .order_by("seat_number", "pk")
            ]
            return Response(
                {
                    "content_version": item.content_version,
                    "read_count": len(receipts),
                    "unread_count": len(students) - len(receipts),
                    "students": students,
                }
            )
