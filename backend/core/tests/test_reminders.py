import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from rest_framework.test import APIClient, APITestCase

from core.models import (
    AnnouncementReminder,
    ClassMember,
    Notification,
    ReminderOperation,
    Student,
    User,
)

from . import test_announcements, test_scores


class ReminderTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish
    change = test_announcements.AnnouncementTests.change

    def path(self, item):
        return self.base + f"announcements/{item['id']}/reminders/"

    def test_history_pages_are_newest_first_and_student_has_no_history_access(self):
        item = self.publish().json()
        start = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
        for day in range(26):
            with patch("core.reminders.timezone.now", return_value=start + timedelta(days=day)):
                response = self.client.post(
                    self.path(item),
                    self.payload(item, student_id=self.students[0]["id"]),
                    format="json",
                )
                self.assertEqual(response.status_code, 201)
        first = self.client.get(self.path(item)).json()
        second = self.client.get(self.path(item) + "?page=2").json()
        self.assertEqual(
            (first["count"], len(first["results"]), len(second["results"])), (26, 25, 1)
        )
        self.assertGreater(first["results"][0]["id"], second["results"][0]["id"])
        self.assertEqual(self.student_login().get(self.path(item)).status_code, 403)

    def payload(self, item, **extra):
        return {
            "request_id": str(uuid.uuid4()),
            "content_version": item["content_version"],
            **extra,
        }

    def test_single_and_all_reminders_skip_read_and_daily_sent_and_retry_once(self):
        student = self.student_login()
        item = self.publish().json()
        payload = self.payload(item, student_id=self.students[0]["id"])
        first = self.client.post(self.path(item), payload, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["sent"], 1)
        self.assertEqual(
            self.client.post(self.path(item), payload, format="json").json(), first.json()
        )
        inbox = student.get("/api/notifications/").json()
        self.assertEqual(inbox["count"], 2)
        self.assertEqual(inbox["results"][0]["kind"], "announcement_reminder")
        student.post(f"/api/notifications/{inbox['results'][0]['id']}/open/")
        roster = self.client.get(self.base + f"announcements/{item['id']}/read-receipts/").json()
        self.assertEqual(roster["read_count"], 0)
        all_result = self.client.post(self.path(item), self.payload(item), format="json").json()
        self.assertEqual((all_result["sent"], all_result["already_reminded"]), (1, 1))
        student.post(f"/api/student/announcements/{item['id']}/read/", {"content_version": 1})
        result = self.client.post(self.path(item), self.payload(item), format="json").json()
        self.assertEqual(
            (result["sent"], result["already_read"], result["already_reminded"]), (0, 1, 1)
        )
        history = self.client.get(self.path(item)).json()
        self.assertEqual(history["count"], 2)
        self.assertEqual(
            {row["student_id"] for row in history["results"]}, {s["id"] for s in self.students}
        )

    def test_taipei_midnight_version_changes_and_cross_day_retry(self):
        item = self.publish().json()
        payload = self.payload(item)
        with patch(
            "core.reminders.timezone.now",
            return_value=datetime(2026, 11, 5, 15, 59, 59, tzinfo=timezone.utc),
        ):
            first = self.client.post(self.path(item), payload, format="json").json()
            self.assertEqual((first["sent_date"], first["sent"]), ("2026-11-05", 2))
            changed = self.change(item, "edit", title="新內容", body=item["body"]).json()
            self.assertEqual(
                self.client.post(self.path(item), self.payload(item), format="json").status_code,
                409,
            )
            result = self.client.post(self.path(item), self.payload(changed), format="json").json()
            self.assertEqual((result["sent"], result["already_reminded"]), (0, 2))
        with patch(
            "core.reminders.timezone.now",
            return_value=datetime(2026, 11, 5, 16, 0, 0, tzinfo=timezone.utc),
        ):
            self.assertEqual(
                self.client.post(self.path(item), payload, format="json").json(), first
            )
            result = self.client.post(self.path(item), self.payload(changed), format="json").json()
            self.assertEqual((result["sent_date"], result["sent"]), ("2026-11-06", 2))
        self.assertEqual(self.client.get(self.path(item)).json()["count"], 4)
        self.assertEqual(
            set(AnnouncementReminder.objects.values_list("version__number", flat=True)), {1, 2}
        )

    def test_permissions_invalid_targets_csrf_and_deleted_announcement(self):
        item = self.publish().json()
        student = self.student_login()
        co = User.objects.create_user(username="reminder-co")
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=co, role="coTeacher", approved=True
        )
        client = APIClient()
        client.force_login(co)
        for who, code in [(APIClient(), 403), (student, 403), (client, 404)]:
            self.assertEqual(who.get(self.path(item)).status_code, code)
            self.assertEqual(
                who.post(self.path(item), self.payload(item), format="json").status_code, code
            )
        protected = APIClient(enforce_csrf_checks=True)
        protected.cookies = self.client.cookies.copy()
        self.assertEqual(
            protected.post(self.path(item), self.payload(item), format="json").status_code, 403
        )
        for extra in [
            {"student_id": True},
            {"content_version": 1.5},
            {"student_ids": [1]},
            {"student_id": None},
        ]:
            self.assertEqual(
                self.client.post(
                    self.path(item), self.payload(item, **extra), format="json"
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                self.path(item), self.payload(item, student_id=999999), format="json"
            ).status_code,
            404,
        )
        payload = self.payload(item)
        self.client.post(self.path(item), payload, format="json")
        self.assertEqual(
            self.client.post(
                self.path(item), {**payload, "student_id": self.students[0]["id"]}, format="json"
            ).status_code,
            400,
        )
        self.change(item, "delete")
        self.assertEqual(self.client.get(self.path(item)).status_code, 404)
        self.assertEqual(self.client.post(self.path(item), payload, format="json").status_code, 404)
        self.assertEqual(student.get("/api/notifications/").json()["count"], 0)
        member.delete()

    def test_notification_failure_rolls_back_record_and_retry_guard(self):
        item = self.publish().json()
        with patch(
            "core.reminders.Notification.objects.create", side_effect=RuntimeError("offline")
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.path(item), self.payload(item), format="json")
        self.assertFalse(ReminderOperation.objects.exists())
        self.assertFalse(AnnouncementReminder.objects.exists())
        self.assertEqual(Notification.objects.filter(kind="announcement_reminder").count(), 0)

    def test_permanent_deletion_clears_student_records_and_keeps_other_people(self):
        student = self.student_login()
        other = self.student_login("002")
        item = self.publish().json()
        self.client.post(
            self.path(item), self.payload(item, student_id=self.students[0]["id"]), format="json"
        )
        self.client.post(self.path(item), self.payload(item), format="json")
        original_base = self.base
        cohort = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t保留學生\t009"})
        keep = self.publish().json()
        self.client.post(self.path(keep), self.payload(keep), format="json")
        self.assertEqual(
            self.client.post(
                self.path(keep),
                self.payload(keep, student_id=self.students[0]["id"]),
                format="json",
            ).status_code,
            404,
        )
        self.base = original_base
        student_id = self.students[0]["id"]
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{student_id}/", {"confirmation_student_number": "001"}
            ).status_code,
            200,
        )
        self.assertFalse(AnnouncementReminder.objects.filter(student_id=student_id).exists())
        self.assertFalse(ReminderOperation.objects.filter(target_student_id=student_id).exists())
        self.assertFalse(Notification.objects.filter(student_id=student_id).exists())
        self.assertEqual(student.get("/api/notifications/").status_code, 403)
        self.assertEqual(self.client.get(self.path(item)).json()["count"], 1)
        self.assertEqual(other.get("/api/notifications/").json()["count"], 2)
        self.assertEqual(
            self.client.delete(self.base, {"confirmation_name": "記分班"}).status_code, 200
        )
        self.assertEqual(AnnouncementReminder.objects.count(), 1)
        self.assertEqual(ReminderOperation.objects.count(), 1)
        self.assertEqual(Student.objects.count(), 1)
