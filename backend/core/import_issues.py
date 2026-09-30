from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cohort, StudentImportIssue
from .permissions import IsTeacher
from .scores import require_teacher
from .students import import_student_row


def issue_data(issue):
    return {
        "id": issue.pk,
        "batch_id": str(issue.batch_id),
        "line": issue.line,
        "raw": issue.raw,
        "draft_raw": issue.draft_raw,
        "message": issue.message,
        "status": issue.status,
        "revision": issue.revision,
        "created_at": issue.created_at.isoformat(),
    }


class ImportIssuesView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            issues = StudentImportIssue.objects.filter(cohort_id=pk, status="pending").order_by(
                "created_at", "pk"
            )
            pager = PageNumberPagination()
            pager.page_size = 25
            page = pager.paginate_queryset(issues, request)
            assert page is not None
            return pager.get_paginated_response([issue_data(i) for i in page])


class ResolveImportSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["retry", "ignore"])
    revision = serializers.IntegerField(min_value=1)
    raw = serializers.CharField(max_length=100000, trim_whitespace=False, required=False)

    def validate(self, attrs):
        if attrs["action"] == "retry":
            if "raw" not in attrs or len(attrs["raw"].splitlines()) != 1:
                raise serializers.ValidationError({"raw": "請提供單一列學生資料。"})
        return attrs


class ResolveImportIssueView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk, issue_id):
        form = ResolveImportSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        with transaction.atomic():
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            issue = get_object_or_404(StudentImportIssue, pk=issue_id, cohort=cohort)
            # Terminal rows cannot be re-opened; returning the state makes retries harmless.
            if issue.status != "pending":
                return Response(issue_data(issue))
            if issue.revision != values["revision"]:
                return Response({"detail": "這列資料已變更，請重新整理待修正名單。"}, status=409)
            if values["action"] == "ignore":
                issue.status = "ignored"
            else:
                result = import_student_row(cohort, request.user, issue.line, values["raw"])
                issue.draft_raw = values["raw"]
                issue.message = result["message"]
                if result["status"] in ("created", "skipped"):
                    issue.status = "resolved"
            if issue.status != "pending":
                # Do not retain a second copy of a student's personal data after resolution.
                issue.raw = ""
                issue.draft_raw = ""
                issue.message = ""
            issue.revision += 1
            issue.save()
            return Response(issue_data(issue))
