import uuid
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, PointAwardBatch, PointTransaction, User

from . import test_scores


class AwardTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    score_payload = test_scores.ScoreTests.payload
    student_login = test_scores.ScoreTests.student_login

    def test_week_boundary_counts_award_time_in_taipei_not_source_time(self):
        records = [self.source() for _ in range(3)]
        for record, when in zip(
            records,
            [
                datetime(2026, 9, 27, 23, 59, tzinfo=ZoneInfo("Asia/Taipei")),
                datetime(2026, 9, 28, 0, 0, tzinfo=ZoneInfo("Asia/Taipei")),
                datetime(2026, 10, 5, 0, 0, tzinfo=ZoneInfo("Asia/Taipei")),
            ],
        ):
            with patch("django.utils.timezone.now", return_value=when):
                self.assertEqual(self.award(self.payload(record)).status_code, 201)
        with patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 9, 30, 12, tzinfo=ZoneInfo("Asia/Taipei")),
        ):
            week = self.client.get(self.base + "point-awards/").json()["week"]
        self.assertEqual(week["points"], 1)
        self.assertEqual(week["count"], 1)
        self.assertEqual(week["start"], "2026-09-28T00:00:00+08:00")
        self.assertEqual(week["end"], "2026-10-05T00:00:00+08:00")

    def test_student_group_pagination_and_default_upper_limit_points(self):
        self.client.post(
            self.base + "students/",
            {"text": "\n".join(f"{i}\t學生{i}\t{i:03}" for i in range(3, 27))},
        )
        students = self.client.get(self.base + "students/").json()
        response = self.client.post(
            self.base + "score-batches/",
            {
                "student_ids": [s["id"] for s in students],
                "kind": "positive",
                "score": 0,
                "template": "other",
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        first = self.client.get(self.base + "point-awards/").json()
        second = self.client.get(self.base + "point-awards/?page=2").json()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["students"]), 25)
        self.assertEqual(len(second["students"]), 1)
        self.assertEqual(second["students"][0]["seat_number"], 26)
        records = response.json()["results"]
        payload = self.payload(records[0], records[1])
        del payload["items"][0]["points"]
        payload["items"][1]["points"] = 100
        self.assertEqual(self.award(payload).status_code, 201)
        self.assertEqual(self.client.get(self.base + "point-awards/").json()["week"]["points"], 101)

    def source(self, **changes):
        response = self.client.post(
            self.base + "scores/", self.score_payload(**changes), format="json"
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def payload(self, *records):
        return {
            "request_id": str(uuid.uuid4()),
            "items": [
                {"record_id": r["id"], "revision": r["revision"], "points": i + 1}
                for i, r in enumerate(records)
            ],
        }

    def award(self, payload):
        return self.client.post(self.base + "point-awards/", payload, format="json")

    def test_award_zero_positive_grouping_balance_and_idempotent_retry(self):
        first = self.source(score=0)
        second = self.source(student_id=self.students[1]["id"])
        student = self.student_login()
        self.assertEqual(student.get("/api/student/me/").json()["point_balance"], 0)
        pending = self.client.get(self.base + "point-awards/")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual([s["seat_number"] for s in pending.json()["students"]], [1, 2])
        payload = self.payload(first, second)
        created = self.award(payload)
        self.assertEqual(created.status_code, 201)
        retry = self.award({**payload, "items": list(reversed(payload["items"]))})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), created.json())
        self.assertEqual(student.get("/api/student/me/").json()["point_balance"], 1)
        self.assertEqual(student.get("/api/student/scores/").json()["total"], 0)
        listing = self.client.get(self.base + "point-awards/").json()
        self.assertEqual(listing["students"], [])
        self.assertEqual(listing["week"]["points"], 3)
        self.assertEqual(listing["week"]["count"], 2)
        history = self.client.get(self.base + "point-awards/?status=awarded").json()
        self.assertEqual([s["records"][0]["awarded_points"] for s in history["students"]], [1, 2])
        self.assertEqual(self.award({**payload, "request_id": str(uuid.uuid4())}).status_code, 400)
        payload["items"][0]["points"] = 5
        self.assertEqual(self.award(payload).status_code, 400)

    def change(self, record, action="edit", **changes):
        preview = self.client.get(self.base + f"scores/{record['id']}/edit-preview/").json()
        payload = {
            "action": action,
            "preview_token": preview["token"],
            "request_id": str(uuid.uuid4()),
        }
        if action == "edit":
            payload.update(kind="negative", score=-1, template="disruption", note="修正")
        return self.client.post(self.base + "score-changes/", {**payload, **changes}, format="json")

    def test_awarded_source_delete_preview_and_late_award_requires_fresh_confirmation(self):
        record = self.source()
        preview = self.client.get(self.base + f"scores/{record['id']}/edit-preview/").json()
        payload = self.payload(record)
        self.assertEqual(self.award(payload).status_code, 201)
        stale_delete = {
            "action": "delete",
            "preview_token": preview["token"],
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(
            self.client.post(self.base + "score-changes/", stale_delete, format="json").status_code,
            400,
        )
        current = self.client.get(self.base + f"scores/{record['id']}/edit-preview/").json()
        self.assertEqual(current["targets"][0]["awarded_points"], 1)
        self.assertEqual(self.change(record).status_code, 200)
        self.assertEqual(self.change(record, "delete").status_code, 200)
        student = self.student_login()
        self.assertEqual(student.get("/api/student/me/").json()["point_balance"], 1)
        self.assertEqual(student.get("/api/student/scores/").json()["count"], 0)
        self.assertEqual(self.award(payload).status_code, 200)
        history = self.client.get(self.base + "point-awards/?status=awarded").json()
        self.assertEqual(history["students"][0]["records"][0]["awarded_points"], 1)
        self.assertIsNotNone(history["students"][0]["records"][0]["deleted_at"])

    def test_invalid_points_or_sources_cancel_whole_batch(self):
        first, second = self.source(), self.source(student_id=self.students[1]["id"])
        for value in [0, -1, 101, 1.5, True, "1.0"]:
            payload = self.payload(first, second)
            payload["items"][1]["points"] = value
            self.assertEqual(self.award(payload).status_code, 400)
        for changes in [
            {"record_id": 999999},
            {"revision": 999},
            {"student_id": self.students[0]["id"]},
        ]:
            payload = self.payload(first, second)
            payload["items"][1].update(changes)
            self.assertEqual(self.award(payload).status_code, 400)
        for items in [[], self.payload(first)["items"] * 2, self.payload(first)["items"] * 201]:
            self.assertEqual(
                self.award({"request_id": str(uuid.uuid4()), "items": items}).status_code, 400
            )
        self.assertEqual(self.change(second).status_code, 200)
        self.assertEqual(self.award(self.payload(first, second)).status_code, 400)
        self.assertEqual(
            self.client.get(self.base + "point-awards/?status=awarded").json()["students"], []
        )
        self.assertEqual(
            self.client.get(self.base + "point-awards/").json()["students"][0]["point_balance"], 0
        )
        self.assertEqual(self.award(self.payload(first)).status_code, 201)
        third = self.source()
        self.assertEqual(self.award(self.payload(third, first)).status_code, 400)
        self.assertEqual(self.change(third, "delete").status_code, 200)
        self.assertEqual(self.award(self.payload(third)).status_code, 400)
        self.assertEqual(self.client.get(self.base + "point-awards/").json()["week"]["points"], 1)

    def test_only_original_author_can_award_and_revocation_blocks_retries(self):
        owner_record = self.source()
        co = User.objects.create_user(
            username="award-co", email_verified=True, display_name="共同教師"
        )
        member = ClassMember.objects.create(cohort_id=self.cohort["id"], user=co, role="coTeacher")
        client = APIClient()
        client.force_login(co)
        record = client.post(self.base + "scores/", self.score_payload(), format="json").json()
        self.assertEqual(self.award(self.payload(owner_record, record)).status_code, 400)
        self.assertEqual(
            client.post(
                self.base + "point-awards/", self.payload(record, owner_record), format="json"
            ).status_code,
            400,
        )
        # Homeroom edits another teacher's score, but does not acquire award rights.
        self.assertEqual(
            self.change(record, kind="positive", score=2, template="helping").status_code, 200
        )
        record = client.get(self.base + "point-awards/").json()["students"][0]["records"][0]
        self.assertEqual(self.award(self.payload(record)).status_code, 400)
        payload = self.payload(record)
        self.assertEqual(
            client.post(self.base + "point-awards/", payload, format="json").status_code, 201
        )
        self.assertEqual(self.client.get(self.base + "point-awards/").json()["week"]["points"], 0)
        member.approved = False
        member.save()
        self.assertEqual(client.get(self.base + "point-awards/").status_code, 404)
        self.assertEqual(
            client.post(self.base + "point-awards/", payload, format="json").status_code, 404
        )
        student = self.student_login()
        for unauthorized in [student, APIClient()]:
            self.assertEqual(unauthorized.get(self.base + "point-awards/").status_code, 403)
            self.assertEqual(
                unauthorized.post(self.base + "point-awards/", payload, format="json").status_code,
                403,
            )
        secure = APIClient(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(
            secure.post(
                self.base + "point-awards/", self.payload(owner_record), format="json"
            ).status_code,
            403,
        )
        other = self.client.post(
            "/api/classes/", {"name": "另一班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.assertEqual(
            self.client.post(
                f"/api/classes/{other['id']}/point-awards/",
                self.payload(owner_record),
                format="json",
            ).status_code,
            400,
        )

    def test_permanent_deletion_clears_points_without_affecting_other_students_or_classes(self):
        first, second = self.source(), self.source(student_id=self.students[1]["id"])
        payload = self.payload(first, second)
        self.assertEqual(self.award(payload).status_code, 201)
        solo = self.source()
        solo_batch = self.award(self.payload(solo)).json()["batch_id"]
        original_base = self.base
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{other['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t他班生\t001"})
        other_student = self.client.get(self.base + "students/").json()[0]
        other_record = self.source(student_id=other_student["id"])
        self.assertEqual(self.award(self.payload(other_record)).status_code, 201)
        self.base = original_base
        removed = self.students[0]
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{removed['id']}/",
                {"confirmation_student_number": removed["student_number"]},
                format="json",
            ).status_code,
            200,
        )
        self.assertFalse(PointTransaction.objects.filter(student_id=removed["id"]).exists())
        self.assertFalse(PointAwardBatch.objects.filter(pk=solo_batch).exists())
        self.assertEqual(self.award(payload).status_code, 400)
        history = self.client.get(self.base + "point-awards/?status=awarded").json()
        self.assertEqual(history["students"][0]["point_balance"], 2)
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": self.cohort["name"]}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(PointAwardBatch.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertFalse(
            PointTransaction.objects.filter(record_id__in=[first["id"], second["id"]]).exists()
        )
        retained = self.client.get(
            f"/api/classes/{other['id']}/point-awards/?status=awarded"
        ).json()
        self.assertEqual(retained["students"][0]["point_balance"], 1)
