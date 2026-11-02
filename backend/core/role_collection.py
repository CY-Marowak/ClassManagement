from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .awards import StrictSerializer
from .models import Cohort, PointTransaction, Student, StudentRoleOwnership
from .permissions import IsReadyUser, IsStudent
from .role_catalog import StudentRole

ROLE_PRICE = 20


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
        "point_balance": student.point_balance,
        "owned": list(student.owned_roles.order_by("role").values_list("role", flat=True)),
        "catalog": [
            {"id": role.value, "name": role.label, "price": ROLE_PRICE} for role in StudentRole
        ],
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


class PurchaseRoleSerializer(SelectRoleSerializer):
    request_id = serializers.UUIDField()


class StudentRolePurchasesView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def post(self, request):
        from .mascots import transaction_data

        form = PurchaseRoleSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        role = form.validated_data["role"]
        identity = form.validated_data["request_id"]
        with transaction.atomic():
            student = locked_student(request)
            existing = student.point_transactions.filter(request_id=identity).first()
            if existing:
                if existing.kind != "purchase" or existing.role != role:
                    raise serializers.ValidationError("此識別已用於其他交易，請勿更改重試內容。")
                return Response(transaction_data(existing))
            if student.owned_roles.filter(role=role).exists():
                raise serializers.ValidationError("已擁有這個角色，不能重複購買。")
            if student.point_balance < ROLE_PRICE:
                raise serializers.ValidationError("可用點數不足，尚未扣點。")
            student.point_balance -= ROLE_PRICE
            student.save(update_fields=["point_balance"])
            entry = PointTransaction.objects.create(
                student=student, kind="purchase", role=role, points=-ROLE_PRICE, request_id=identity
            )
            StudentRoleOwnership.objects.create(student=student, role=role)
            return Response(transaction_data(entry), status=201)
