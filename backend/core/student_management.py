from django.contrib.sessions.models import Session
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, Student, StudentAuditEvent, User
from .permissions import IsTeacher
from .students import StudentRowSerializer, student_data


def require_homeroom(user, cohort_id, *, lock=False):
    memberships = ClassMember.objects.all()
    if lock:
        memberships = memberships.select_for_update()
    return get_object_or_404(
        memberships, cohort_id=cohort_id, user=user, role="homeroom", approved=True
    )


class EditStudentSerializer(StudentRowSerializer):
    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("只能修改姓名、座號及學號。")
        return attrs


class StudentDetailView(APIView):
    permission_classes = [IsTeacher]

    def patch(self, request, pk, student_id):
        with transaction.atomic():
            require_homeroom(request.user, pk, lock=True)
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            student = get_object_or_404(
                Student.objects.select_related("user"), cohort_id=pk, pk=student_id
            )
            form = EditStudentSerializer(data=request.data, partial=True)
            form.is_valid(raise_exception=True)
            values = form.validated_data
            others = Student.objects.filter(cohort_id=pk).exclude(pk=student_id)
            for field, label in [("seat_number", "座號"), ("student_number", "學號")]:
                if field in values and others.filter(**{field: values[field]}).exists():
                    raise serializers.ValidationError({field: f"{label}已被其他學生使用。"})
            previous = student_data(student)
            changes = {key: value for key, value in values.items() if value != previous[key]}
            if changes:
                if "name" in changes:
                    student.user.display_name = changes["name"]
                    student.user.save(update_fields=["display_name"])
                for field in ("seat_number", "student_number"):
                    if field in changes:
                        setattr(student, field, changes[field])
                student.save(update_fields=[key for key in changes if key != "name"])
                StudentAuditEvent.objects.create(
                    student=student,
                    actor=request.user,
                    actor_name=request.user.display_name,
                    student_name=student.user.display_name,
                    action="profile_updated",
                    before={key: previous[key] for key in changes},
                    after=changes,
                )
        return Response(student_data(student))


class ResetStudentPasswordView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk, student_id):
        with transaction.atomic():
            require_homeroom(request.user, pk, lock=True)
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            student = get_object_or_404(
                Student.objects.select_for_update(), cohort_id=pk, pk=student_id
            )
            user = get_object_or_404(User.objects.select_for_update(), pk=student.user_id)
            user.set_password(student.student_number)
            user.save(update_fields=["password"])
            student.must_change_password = True
            student.save(update_fields=["must_change_password"])
            for session in Session.objects.all().iterator():
                if session.get_decoded().get("_auth_user_id") == str(user.pk):
                    session.delete()
            StudentAuditEvent.objects.create(
                student=student,
                actor=request.user,
                actor_name=request.user.display_name,
                student_name=user.display_name,
                action="password_reset",
            )
        return Response({"detail": "密碼已重設，原登入已失效；學生重新登入後必須修改密碼。"})


class StudentAuditPagination(PageNumberPagination):
    page_size = 25


class StudentEventsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        require_homeroom(request.user, pk)
        events = StudentAuditEvent.objects.filter(student__cohort_id=pk).order_by(
            "-created_at", "-pk"
        )
        paginator = StudentAuditPagination()
        page = paginator.paginate_queryset(events, request)
        assert page is not None  # This paginator always has a fixed page size.
        return paginator.get_paginated_response(
            [
                {
                    "id": event.pk,
                    "student_id": event.student_id,
                    "student_name": event.student_name,
                    "actor_id": event.actor_id,
                    "actor_name": event.actor_name,
                    "action": event.action,
                    "created_at": event.created_at.isoformat(),
                    "before": event.before,
                    "after": event.after,
                }
                for event in page
            ]
        )
