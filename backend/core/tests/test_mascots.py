import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, Cohort, Mascot, PointTransaction, Student, User

from . import test_scores


class MascotTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login

    def award(self, points=10, student_index=0):
        record = self.client.post(
            self.base + "scores/",
            test_scores.ScoreTests.payload(self, student_id=self.students[student_index]["id"]),
            format="json",
        ).json()
        response = self.client.post(
            self.base + "point-awards/",
            {
                "request_id": str(uuid.uuid4()),
                "items": [{"record_id": record["id"], "revision": 1, "points": points}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def feed(self, student, points, request_id=None):
        return student.post(
            "/api/student/mascot/",
            {"points": points, "request_id": request_id or str(uuid.uuid4())},
            format="json",
        )

    def test_feed_spends_points_grows_class_and_lists_only_own_recent_transactions(self):
        student = self.student_login()
        self.award(10)
        self.award(7, 1)
        response = self.feed(student, 2)
        self.assertEqual(response.status_code, 201)
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(data["point_balance"], 8)
        self.assertEqual(data["daily_remaining"], 3)
        self.assertEqual(data["mascot"]["exp"], 2)
        self.assertEqual(data["mascot"]["remaining_exp"], 98)
        self.assertEqual([t["points"] for t in data["transactions"]], [-2, 10])
        self.assertEqual([t["kind"] for t in data["transactions"]], ["feed", "award"])
        self.assertEqual(data["transactions"][1]["source"]["reason"], "積極參與")
        self.assertEqual(student.get("/api/student/me/").json()["point_balance"], 8)
        self.assertEqual(student.get("/api/student/scores/").json()["total"], 3)
        self.assertEqual(self.client.get(self.base + "mascot/").json()["exp"], 2)

    def test_class_has_random_fixed_mascot_immediately_and_grade_change_preserves_it(self):
        response = self.client.get(self.base + "mascot/")
        self.assertEqual(response.status_code, 200)
        mascot = response.json()
        self.assertIn(mascot["animal"], ["cat", "dog", "rabbit"])
        self.assertEqual(mascot["exp"], 0)
        self.assertEqual(mascot["level"], 1)
        self.assertEqual(mascot["remaining_exp"], 100)
        self.client.patch(self.base, {"current_grade": 2})
        self.assertEqual(self.client.get(self.base + "mascot/").json(), mascot)

    def test_invalid_insufficient_daily_limit_and_retry_preserve_money(self):
        student = self.student_login()
        self.assertEqual(self.feed(student, 1).status_code, 400)
        self.award(10)
        for invalid in [0, -1, 6, 1.5, True, "1.0", None]:
            self.assertEqual(self.feed(student, invalid).status_code, 400)
        identity = str(uuid.uuid4())
        first = self.feed(student, 3, identity)
        self.assertEqual(first.status_code, 201)
        retry = self.feed(student, 3, identity)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(self.feed(student, 2, identity).status_code, 400)
        self.assertEqual(self.feed(student, 3).status_code, 400)
        self.assertEqual(self.feed(student, 2).status_code, 201)
        self.assertEqual(self.feed(student, 1).status_code, 400)
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(data["daily_remaining"], 0)
        self.assertEqual(data["point_balance"], 5)
        self.assertEqual(data["mascot"]["exp"], 5)
        self.assertEqual(len(data["transactions"]), 3)

    def test_taipei_midnight_resets_limit_but_cross_day_retry_is_not_new_feed(self):
        student = self.student_login()
        self.award(10)
        identity = str(uuid.uuid4())
        with patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 9, 29, 15, 59, 59, tzinfo=timezone.utc),
        ):
            first = self.feed(student, 5, identity)
            self.assertEqual(first.status_code, 201)
            self.assertEqual(self.feed(student, 1).status_code, 400)
        with patch(
            "django.utils.timezone.now", return_value=datetime(2026, 9, 29, 16, tzinfo=timezone.utc)
        ):
            self.assertEqual(self.feed(student, 5, identity).json(), first.json())
            data = student.get("/api/student/mascot/").json()
            self.assertEqual(data["daily_remaining"], 5)
            self.assertEqual(data["daily_reset_at"], "2026-10-01T00:00:00+08:00")
            self.assertEqual(self.feed(student, 5).status_code, 201)
            data = student.get("/api/student/mascot/").json()
            self.assertEqual(data["point_balance"], 0)
            self.assertEqual(data["mascot"]["exp"], 10)

    def test_levels_follow_cumulative_thresholds_and_keep_growing(self):
        # Seed long-lived class history; assertions exercise the public read interface.
        for exp, level, remaining in [
            (0, 1, 100),
            (99, 1, 1),
            (100, 2, 200),
            (299, 2, 1),
            (300, 3, 300),
            (600, 4, 400),
            (1000, 5, 500),
            (495000, 100, 10000),
        ]:
            Mascot.objects.filter(cohort_id=self.cohort["id"]).update(exp=exp)
            data = self.client.get(self.base + "mascot/").json()
            self.assertEqual((data["level"], data["remaining_exp"]), (level, remaining))
        student = self.student_login()
        self.award(2)
        Mascot.objects.filter(cohort_id=self.cohort["id"]).update(exp=99)
        self.assertEqual(self.feed(student, 2).status_code, 201)
        data = student.get("/api/student/mascot/").json()["mascot"]
        self.assertEqual((data["level"], data["exp"], data["remaining_exp"]), (2, 101, 199))

    def test_access_is_own_student_only_and_approved_teacher_read_only(self):
        initial = self.student_login(change=False)
        self.assertEqual(initial.get("/api/student/mascot/").status_code, 403)
        self.assertEqual(self.feed(initial, 1).status_code, 403)
        self.assertEqual(APIClient().get("/api/student/mascot/").status_code, 403)
        self.assertEqual(self.feed(self.client, 1).status_code, 403)
        initial.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        self.award(5)
        self.assertEqual(
            initial.post(
                "/api/student/mascot/",
                {
                    "points": 1,
                    "request_id": str(uuid.uuid4()),
                    "student_id": self.students[1]["id"],
                },
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(initial.get(self.base + "mascot/").status_code, 403)
        other_student = self.student_login("002")
        self.assertEqual(other_student.get("/api/student/mascot/").json()["transactions"], [])
        outsider = User.objects.create_user(username="mascot-outsider", display_name="別班教師")
        other = APIClient()
        other.force_login(outsider)
        self.assertEqual(other.get(self.base + "mascot/").status_code, 404)
        membership = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=outsider, role="coTeacher", approved=False
        )
        self.assertEqual(other.get(self.base + "mascot/").status_code, 404)
        membership.approved = True
        membership.save()
        self.assertEqual(other.get(self.base + "mascot/").status_code, 200)
        self.assertEqual(self.feed(other, 1).status_code, 403)
        membership.approved = False
        membership.save()
        self.assertEqual(other.get(self.base + "mascot/").status_code, 404)

    def test_recent_limit_and_source_correction_do_not_rewrite_points(self):
        student = self.student_login()
        for _ in range(21):
            self.award(1)
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(len(data["transactions"]), 20)
        ids = [t["id"] for t in data["transactions"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        record_id = data["transactions"][0]["source"]["id"]
        preview = self.client.get(self.base + f"scores/{record_id}/edit-preview/").json()
        response = self.client.post(
            self.base + "score-changes/",
            {
                "action": "delete",
                "preview_token": preview["token"],
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = student.get("/api/student/mascot/").json()
        self.assertTrue(data["transactions"][0]["source"]["is_deleted"])
        self.assertEqual(data["transactions"][0]["points"], 1)
        self.assertEqual(data["point_balance"], 21)

    def test_permanent_student_and_class_deletion_remove_transactions_keep_other_data(self):
        student = self.student_login()
        self.award(5)
        self.award(3, 1)
        self.feed(student, 2)
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        identity = self.students[0]["id"]
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{identity}/",
                {"confirmation_student_number": "001"},
                format="json",
            ).status_code,
            200,
        )
        self.assertFalse(Student.objects.filter(pk=identity).exists())
        self.assertFalse(PointTransaction.objects.filter(student_id=identity).exists())
        self.assertEqual(self.client.get(self.base + "mascot/").json()["exp"], 2)
        self.assertTrue(PointTransaction.objects.filter(student_id=self.students[1]["id"]).exists())
        self.assertEqual(student.get("/api/student/mascot/").status_code, 403)
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": "記分班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(Mascot.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertFalse(
            PointTransaction.objects.filter(student_id=self.students[1]["id"]).exists()
        )
        self.assertTrue(Cohort.objects.filter(pk=other["id"]).exists())
        self.assertTrue(Mascot.objects.filter(cohort_id=other["id"]).exists())
