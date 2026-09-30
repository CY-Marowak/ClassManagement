from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, ScoreRecord, StudentImportIssue
from .permissions import IsTeacher
from .scores import record_data, require_teacher


class DashboardView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            require_teacher(request.user, pk, homeroom=True)
            today = timezone.now().astimezone(ZoneInfo("Asia/Taipei")).date()
            start = datetime.combine(today, time.min, tzinfo=ZoneInfo("Asia/Taipei"))
            records = ScoreRecord.objects.filter(cohort_id=pk, deleted_at__isnull=True)
            return Response(
                {
                    "date": today.isoformat(),
                    "pending_students": StudentImportIssue.objects.filter(
                        cohort_id=pk, status="pending"
                    ).count(),
                    "pending_teachers": ClassMember.objects.filter(
                        cohort_id=pk, role="coTeacher", approved=False, inactive_status="pending"
                    ).count(),
                    "pending_reasons": records.filter(template="other", note="").count(),
                    "today_scores": records.filter(
                        created_at__gte=start, created_at__lt=start + timedelta(days=1)
                    ).count(),
                    "recent_scores": [
                        record_data(r)
                        for r in records.select_related("student__user", "award").order_by(
                            "-created_at", "-pk"
                        )[:10]
                    ],
                }
            )
