from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, User
from .permissions import IsTeacher
from .serializers import CohortSerializer, DeleteCohortSerializer
from .sessions import revoke_user_sessions


class ClassesView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        memberships = (
            ClassMember.objects.filter(user=request.user, approved=True)
            .select_related("cohort")
            .order_by("cohort_id")
        )
        return Response([{**CohortSerializer(m.cohort).data, "role": m.role} for m in memberships])

    def post(self, request):
        if not request.user.email_verified:
            raise PermissionDenied("請先驗證 Email，再建立班級。")
        serializer = CohortSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            cohort = serializer.save()
            ClassMember.objects.create(cohort=cohort, user=request.user, role="homeroom")
        return Response({**serializer.data, "role": "homeroom"}, status=201)


class ClassDetailView(APIView):
    permission_classes = [IsTeacher]

    def delete(self, request, pk):
        with transaction.atomic():
            membership = get_object_or_404(
                ClassMember.objects.select_for_update(),
                cohort_id=pk,
                user=request.user,
                role="homeroom",
                approved=True,
            )
            cohort = Cohort.objects.select_for_update().get(pk=membership.cohort_id)
            confirmation = DeleteCohortSerializer(data=request.data)
            confirmation.is_valid(raise_exception=True)
            if confirmation.validated_data["confirmation_name"] != cohort.name:
                raise ValidationError(
                    {"confirmation_name": "請輸入目前完整班級名稱，才可永久刪除。"}
                )
            student_user_ids = set(cohort.students.values_list("user_id", flat=True))
            # These users belong exclusively to this class; teacher identities stay intact.
            User.objects.filter(pk__in=student_user_ids, account_type="student").delete()
            revoke_user_sessions(student_user_ids)
            cohort.delete()
        return Response({"detail": "班級及所屬資料已永久刪除，無法復原。"})

    def get(self, request, pk):
        membership = get_object_or_404(
            ClassMember.objects.select_related("cohort"),
            cohort_id=pk,
            user=request.user,
            approved=True,
        )
        return Response({**CohortSerializer(membership.cohort).data, "role": membership.role})

    def patch(self, request, pk):
        with transaction.atomic():
            membership = get_object_or_404(
                ClassMember.objects.select_for_update(),
                cohort_id=pk,
                user=request.user,
                role="homeroom",
                approved=True,
            )
            cohort = Cohort.objects.select_for_update().get(pk=membership.cohort_id)
            serializer = CohortSerializer(cohort, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({**serializer.data, "role": membership.role})
