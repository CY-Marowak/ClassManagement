from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .announcement_content import validate_document
from .announcements import locked_announcement_student
from .awards import StrictSerializer
from .batch_scores import fingerprint
from .models import Announcement, AnnouncementComment, Cohort, CommentOperation
from .permissions import IsReadyUser, IsStudent, IsTeacher
from .scores import WholeNumberField, require_teacher


class CommentSerializer(StrictSerializer):
    request_id = serializers.UUIDField()
    body = serializers.JSONField()

    def validate_body(self, value):
        return validate_document(value, max_length=1000, label="留言")


class CommentChangeSerializer(CommentSerializer):
    action = serializers.ChoiceField(choices=["edit", "delete"])
    revision = WholeNumberField(min_value=1)
    body = serializers.JSONField(required=False)

    def validate(self, attrs):
        fields = {"body"} if attrs["action"] == "edit" else set()
        if set(attrs) != fields | {"action", "revision", "request_id"}:
            raise serializers.ValidationError("操作欄位不完整或包含不支援的欄位。")
        return attrs


def active_announcement(cohort_id, announcement_id):
    return get_object_or_404(
        Announcement, pk=announcement_id, cohort_id=cohort_id, deleted_at__isnull=True
    )


def comment_data(item, user, member):
    own = member is not None and item.creator_id == user.pk
    return {
        "id": item.pk,
        "body": item.body,
        "creator_name": item.creator_name,
        "revision": item.revision,
        "created_at": item.created_at.isoformat(),
        "edited_at": item.edited_at.isoformat() if item.edited_at else None,
        "can_edit": own,
        "can_delete": own or (member is not None and member.role == "homeroom"),
    }


class CommentPagination(PageNumberPagination):
    page_size = 20


def comment_page(request, announcement: Announcement, member=None):
    paginator = CommentPagination()
    page = paginator.paginate_queryset(
        announcement.comments.filter(deleted_at__isnull=True).order_by("created_at", "pk"), request
    )
    assert page is not None
    response = paginator.get_paginated_response(
        [comment_data(item, request.user, member) for item in page]
    )
    response.data["can_create"] = member is not None
    return response


def prior_comment_result(cohort_id, user, values, digest):
    operation = CommentOperation.objects.filter(
        cohort_id=cohort_id, actor=user, request_id=values["request_id"]
    ).first()
    if operation:
        if operation.fingerprint != digest:
            raise serializers.ValidationError("相同操作識別不可送出不同內容。")
        return operation.result
    return None


def save_comment_result(item, user, values, digest, result):
    CommentOperation.objects.create(
        comment=item,
        cohort_id=item.announcement.cohort_id,
        actor=user,
        request_id=values["request_id"],
        fingerprint=digest,
        result=result,
    )


class CommentsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk, announcement_id):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            return comment_page(request, active_announcement(pk, announcement_id), member)

    def post(self, request, pk, announcement_id):
        form = CommentSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        digest = fingerprint({"action": "create", "announcement_id": announcement_id, **values})
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            announcement = active_announcement(pk, announcement_id)
            previous = prior_comment_result(pk, request.user, values, digest)
            if previous is not None:
                return Response(previous)
            item = AnnouncementComment.objects.create(
                announcement=announcement,
                creator=request.user,
                creator_name=request.user.display_name,
                body=values["body"],
            )
            result = comment_data(item, request.user, member)
            save_comment_result(item, request.user, values, digest, result)
            return Response(result, status=201)


class CommentChangeView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk, announcement_id, comment_id):
        form = CommentChangeSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        digest = fingerprint(
            {"announcement_id": announcement_id, "comment_id": comment_id, **values}
        )
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = require_teacher(request.user, pk)
            announcement = active_announcement(pk, announcement_id)
            # Check current rights even for a retry of a completed operation.
            item = get_object_or_404(AnnouncementComment, pk=comment_id, announcement=announcement)
            allowed = comment_data(item, request.user, member)["can_" + values["action"]]
            if not allowed:
                raise PermissionDenied("只能修改自己的留言；導師可刪除本班留言。")
            previous = prior_comment_result(pk, request.user, values, digest)
            if previous is not None:
                return Response(previous)
            if item.deleted_at:
                return Response({"detail": "留言已刪除，請重新載入。"}, status=404)
            if item.revision != values["revision"]:
                return Response({"detail": "留言已變更，請重新載入後再操作。"}, status=409)
            if values["action"] == "edit":
                if item.body != values["body"]:
                    item.body = values["body"]
                    item.edited_at = timezone.now()
            else:
                item.deleted_at = timezone.now()
            item.revision += 1
            item.save()
            result = (
                {"detail": "留言已刪除。"}
                if item.deleted_at
                else comment_data(item, request.user, member)
            )
            save_comment_result(item, request.user, values, digest, result)
            return Response(result)


class StudentCommentsView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def get(self, request, announcement_id):
        with transaction.atomic():
            student = locked_announcement_student(request)
            return comment_page(request, active_announcement(student.cohort_id, announcement_id))
