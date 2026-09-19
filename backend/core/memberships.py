from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, TeacherAuditEvent, teacher_application_code
from .permissions import IsTeacher
from .student_management import require_homeroom
from .throttling import consume


def application_data(member):
    homeroom = member.cohort.members.select_related("user").get(role="homeroom")
    return {
        "id": member.pk,
        "cohort_name": member.cohort.name,
        "homeroom_name": homeroom.user.display_name,
        "status": member.status,
    }


def member_data(member):
    return {
        "id": member.pk,
        "name": member.user.display_name,
        "status": member.status,
        "revision": member.revision,
    }


def record_event(cohort, actor, action, member=None, before=None, after=None):
    TeacherAuditEvent.objects.create(
        cohort=cohort,
        member=member,
        actor=actor,
        actor_name=actor.display_name,
        teacher_name=member.user.display_name if member else "",
        action=action,
        before=before or {},
        after=after or {},
    )


class ApplicationSerializer(serializers.Serializer):
    application_code = serializers.RegexField(r"^T-[A-F0-9]{16}$", max_length=18)


class TeacherApplicationsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        members = (
            ClassMember.objects.filter(user=request.user, role="coTeacher")
            .select_related("cohort")
            .order_by("pk")
        )
        return Response([application_data(member) for member in members])

    def post(self, request):
        if not request.user.email_verified:
            raise PermissionDenied("請先驗證 Email，再申請加入班級。")
        consume("teacher-application", str(request.user.pk), 30)
        form = ApplicationSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            cohort = get_object_or_404(
                Cohort.objects.select_for_update(),
                application_code=form.validated_data["application_code"],
            )
            member, created = ClassMember.objects.get_or_create(
                cohort=cohort,
                user=request.user,
                defaults={"role": "coTeacher", "approved": False},
            )
            if created:
                record_event(cohort, request.user, "applied", member, after={"status": "pending"})
            elif member.status in ("rejected", "removed"):
                previous = member.status
                member.inactive_status = "pending"
                member.revision += 1
                member.save(update_fields=["inactive_status", "revision"])
                record_event(
                    cohort,
                    request.user,
                    "applied",
                    member,
                    before={"status": previous},
                    after={"status": "pending"},
                )
            return Response(application_data(member), status=201 if created else 200)


class TeachersView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        require_homeroom(request.user, pk)
        cohort = get_object_or_404(Cohort, pk=pk)
        members = cohort.members.filter(role="coTeacher").select_related("user").order_by("pk")
        return Response(
            {
                "application_code": cohort.application_code,
                "members": [member_data(member) for member in members],
            }
        )


class DecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject", "remove"])
    revision = serializers.IntegerField(min_value=1)


class TeacherCodeView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk):
        with transaction.atomic():
            require_homeroom(request.user, pk, lock=True)
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            form = ApplicationSerializer(data=request.data)
            form.is_valid(raise_exception=True)
            if form.validated_data["application_code"] != cohort.application_code:
                raise serializers.ValidationError("申請碼已變更，請重新載入後再操作。")
            code = teacher_application_code()
            while Cohort.objects.filter(application_code=code).exists():
                code = teacher_application_code()
            cohort.application_code = code
            cohort.save(update_fields=["application_code"])
            record_event(cohort, request.user, "code_rotated")
        return Response({"application_code": code})


class TeacherDecisionView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk, member_id):
        with transaction.atomic():
            # Match existing management lock order: homeroom, then cohort.
            require_homeroom(request.user, pk, lock=True)
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            member = get_object_or_404(
                ClassMember.objects.select_related("user"),
                pk=member_id,
                cohort=cohort,
                role="coTeacher",
            )
            form = DecisionSerializer(data=request.data)
            form.is_valid(raise_exception=True)
            action = form.validated_data["action"]
            expected, target = {
                "approve": ("pending", "approved"),
                "reject": ("pending", "rejected"),
                "remove": ("approved", "removed"),
            }[action]
            if member.revision != form.validated_data["revision"] or member.status != expected:
                raise serializers.ValidationError("教師狀態已變更，請重新載入後再操作。")
            member.approved = target == "approved"
            if not member.approved:
                member.inactive_status = target
            member.revision += 1
            member.save(update_fields=["approved", "inactive_status", "revision"])
            record_event(
                cohort,
                request.user,
                target,
                member,
                before={"status": expected},
                after={"status": target},
            )
        return Response(member_data(member))


class TeacherEventPagination(PageNumberPagination):
    page_size = 25


class TeacherEventsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        require_homeroom(request.user, pk)
        events = TeacherAuditEvent.objects.filter(cohort_id=pk).order_by("-created_at", "-pk")
        paginator = TeacherEventPagination()
        page = paginator.paginate_queryset(events, request)
        assert page is not None
        return paginator.get_paginated_response(
            [
                {
                    "id": event.pk,
                    "member_id": event.member_id,
                    "actor_id": event.actor_id,
                    "actor_name": event.actor_name,
                    "teacher_name": event.teacher_name,
                    "action": event.action,
                    "before": event.before,
                    "after": event.after,
                    "created_at": event.created_at.isoformat(),
                }
                for event in page
            ]
        )
