from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .awards import StrictSerializer
from .models import Cohort, Student
from .permissions import IsReadyUser, IsStudent
from .role_catalog import StudentRole


def locked_student(request):
    candidate = get_object_or_404(Student, user=request.user)
    get_object_or_404(Cohort.objects.select_for_update(), pk=candidate.cohort_id)
    student = get_object_or_404(Student.objects.select_related("user"), pk=candidate.pk)
    if (
        student.must_change_password
        or not student.user.is_active
        or (request.session.get("_auth_user_hash") != student.user.get_session_auth_hash())
    ):
        raise PermissionDenied("登入已失效，請重新登入並完成密碼修改。")
    return student


def collection_data(student):
    return {
        "selected": student.avatar,
        "owned": list(student.owned_roles.order_by("role").values_list("role", flat=True)),
        "catalog": [{"id": role.value, "name": role.label} for role in StudentRole],
    }


class StudentRolesView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def get(self, request):
        with transaction.atomic():
            return Response(collection_data(locked_student(request)))

    def post(self, request):
        form = SelectRoleSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        with transaction.atomic():
            student = locked_student(request)
            role = form.validated_data["role"]
            if not student.owned_roles.filter(role=role).exists():
                raise serializers.ValidationError({"role": "只能選用已擁有的角色。"})
            student.avatar = role
            student.save(update_fields=["avatar"])
            return Response(collection_data(student))


class SelectRoleSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=StudentRole.choices)
