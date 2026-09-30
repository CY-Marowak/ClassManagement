from datetime import datetime, timezone
from unittest.mock import patch

from rest_framework.test import APITestCase

from core.models import ClassMember, ScoreRecord, User


class DashboardTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="dashboard-owner", email="dashboard@example.com", email_verified=True
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "首頁班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{self.cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t學生甲\t001\n2\t學生乙\t002"})
        self.students = self.client.get(self.base + "students/").json()

    def test_dashboard_counts_student_records_at_taipei_day_boundary_and_latest_ten(self):
        import uuid

        peer = User.objects.create_user(username="peer", display_name="共同老師")
        ClassMember.objects.create(cohort_id=self.cohort["id"], user=peer, role="coTeacher")
        pending = User.objects.create_user(username="pending", email="pending@example.com")
        ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=pending, role="coTeacher", approved=False
        )
        self.client.force_login(peer)
        response = self.client.post(
            self.base + "score-batches/",
            {
                "request_id": str(uuid.uuid4()),
                "student_ids": [s["id"] for s in self.students],
                "kind": "positive",
                "score": 1,
                "template": "other",
                "note": "",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.client.force_login(self.owner)
        records = []
        for i in range(11):
            response = self.client.post(
                self.base + "scores/",
                {
                    "request_id": str(uuid.uuid4()),
                    "student_id": self.students[0]["id"],
                    "kind": "positive",
                    "score": i,
                    "template": "participation",
                    "note": "",
                },
            )
            self.assertEqual(response.status_code, 201)
            records.append(response.json()["id"])
        # At 16:00 UTC it is the next Taipei day. Both ends must be half-open.
        ScoreRecord.objects.all().update(created_at=datetime(2026, 9, 29, 16, tzinfo=timezone.utc))
        ScoreRecord.objects.filter(pk=records[0]).update(
            created_at=datetime(2026, 9, 29, 15, 59, 59, tzinfo=timezone.utc)
        )
        ScoreRecord.objects.filter(pk=records[-1]).update(
            created_at=datetime(2026, 9, 30, 16, tzinfo=timezone.utc)
        )
        ScoreRecord.objects.filter(pk=records[1]).update(
            deleted_at=datetime(2026, 9, 30, 0, tzinfo=timezone.utc)
        )
        ScoreRecord.objects.filter(pk=records[-2]).update(score=42, is_modified=True)
        with patch(
            "django.utils.timezone.now", return_value=datetime(2026, 9, 30, 8, tzinfo=timezone.utc)
        ):
            response = self.client.get(self.base + "dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["date"], "2026-09-30")
        self.assertEqual(data["today_scores"], 10)
        self.assertEqual(data["pending_teachers"], 1)
        self.assertEqual(data["pending_reasons"], 2)
        self.assertEqual(len(data["recent_scores"]), 10)
        self.assertEqual(data["recent_scores"][0]["id"], records[-1])
        self.assertEqual(data["recent_scores"][1]["score"], 42)
        self.assertNotIn(records[1], [r["id"] for r in data["recent_scores"]])
        self.client.force_login(peer)
        self.assertEqual(self.client.get(self.base + "dashboard/").status_code, 404)
