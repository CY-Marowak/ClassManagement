import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import AnnouncementReceipt, AnnouncementVersion, ClassMember, Student, User

from . import test_announcements, test_scores


class AnnouncementReceiptTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish
    change = test_announcements.AnnouncementTests.change

    def confirm(self, student, item):
        return student.post(
            f"/api/student/announcements/{item['id']}/read/",
            {"content_version": item["content_version"]},
            format="json",
        )

    def roster(self, item):
        return self.client.get(self.base + f"announcements/{item['id']}/read-receipts/")

    def test_manual_confirmation_is_personal_idempotent_and_visible_to_homeroom(self):
        student = self.student_login()
        item = self.publish().json()
        self.assertEqual(item.get("content_version"), 1)
        path = "/api/student/announcements/"
        self.assertIsNone(student.get(path).json()["results"][0]["confirmed_at"])
        initial = self.roster(item).json()
        self.assertEqual(initial["read_count"], 0)
        self.assertEqual(initial["unread_count"], 2)
        first = self.confirm(student, item)
        self.assertEqual(first.status_code, 200)
        self.assertIsNotNone(first.json()["confirmed_at"])
        self.assertEqual(self.confirm(student, item).json(), first.json())
        self.assertEqual(
            student.get(path).json()["results"][0]["confirmed_at"], first.json()["confirmed_at"]
        )
        roster = self.roster(item).json()
        self.assertEqual(roster["read_count"], 1)
        self.assertEqual(roster["unread_count"], 1)
        self.assertEqual(roster["students"][0]["name"], "小明")
        self.assertEqual(roster["students"][0]["confirmed_at"], first.json()["confirmed_at"])
        self.assertIsNone(roster["students"][1]["confirmed_at"])

    def test_only_content_changes_require_new_confirmation_and_stale_pages_are_rejected(self):
        student = self.student_login()
        item = self.publish().json()
        first = self.confirm(student, item).json()
        pinned = self.change(item, "pin", is_pinned=True).json()
        same = self.change(pinned, "edit", title=item["title"], body=item["body"]).json()
        self.assertEqual(same["content_version"], 1)
        self.assertEqual(self.confirm(student, item).json(), first)
        changed = self.change(same, "edit", title="新標題", body=item["body"]).json()
        self.assertEqual(changed["content_version"], 2)
        self.assertEqual(self.roster(item).json()["read_count"], 0)
        self.assertEqual(self.confirm(student, item).status_code, 409)
        self.assertEqual(self.confirm(student, changed).status_code, 200)
        changed_body = self.change(
            changed, "edit", title="新標題", body=test_announcements.document("新內容")
        ).json()
        self.assertEqual(changed_body["content_version"], 3)
        self.assertEqual(self.roster(item).json()["read_count"], 0)
        self.assertIsNone(
            student.get("/api/student/announcements/").json()["results"][0]["confirmed_at"]
        )

    def test_permissions_csrf_invalid_versions_and_no_withdrawal(self):
        item = self.publish().json()
        path = f"/api/student/announcements/{item['id']}/read/"
        roster = self.base + f"announcements/{item['id']}/read-receipts/"
        student = self.student_login(change=False)
        for client in [self.client, APIClient(), student]:
            self.assertEqual(client.post(path, {"content_version": 1}).status_code, 403)
        student.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        for payload in [
            {},
            {"content_version": 0},
            {"content_version": True},
            {"content_version": 1.5},
            {"content_version": 1, "student_id": self.students[1]["id"]},
        ]:
            self.assertEqual(student.post(path, payload, format="json").status_code, 400)
        self.assertEqual(student.get(roster).status_code, 403)
        self.assertEqual(student.delete(path).status_code, 405)
        teacher = User.objects.create_user(username="receipt-coteacher")
        ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=teacher, role="coTeacher", approved=True
        )
        client = APIClient()
        client.force_login(teacher)
        self.assertEqual(client.get(roster).status_code, 404)
        self.assertEqual(client.post(path, {"content_version": 1}).status_code, 403)
        protected = APIClient(enforce_csrf_checks=True)
        protected.cookies = student.cookies.copy()
        self.assertEqual(protected.post(path, {"content_version": 1}).status_code, 403)
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.post(path, {"content_version": 1}, HTTP_X_CSRFTOKEN=token).status_code, 200
        )
        other = self.client.post(
            "/api/classes/", {"name": "別班", "entry_year": 2026, "current_grade": 1}
        ).json()
        other_item = self.client.post(
            f"/api/classes/{other['id']}/announcements/",
            {"title": "別班公告", "body": item["body"], "request_id": str(uuid.uuid4())},
            format="json",
        ).json()
        self.assertEqual(self.confirm(student, other_item).status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/api/classes/{other['id']}/announcements/{item['id']}/read-receipts/"
            ).status_code,
            404,
        )
        self.client.post(self.base + f"students/{self.students[0]['id']}/reset-password/")
        self.assertEqual(self.confirm(student, item).status_code, 403)

    def test_later_student_is_unread_and_deleted_announcement_cannot_be_confirmed(self):
        item = self.publish().json()
        self.client.post(self.base + "students/", {"text": "3\t小新\t003"})
        student = self.student_login("003")
        self.assertEqual(self.roster(item).json()["unread_count"], 3)
        self.assertEqual(self.confirm(student, item).status_code, 200)
        self.assertEqual(self.roster(item).json()["read_count"], 1)
        self.change(item, "delete")
        self.assertEqual(self.confirm(student, item).status_code, 404)
        self.assertEqual(self.roster(item).status_code, 404)

    def test_student_and_cohort_deletion_remove_receipts_history_and_sessions_only_in_scope(self):
        student = self.student_login()
        second = self.student_login("002")
        item = self.publish().json()
        self.confirm(student, item)
        self.confirm(second, item)
        edited = self.change(item, "edit", title="新版", body=item["body"]).json()
        self.confirm(student, edited)
        self.confirm(second, edited)
        self.assertEqual(
            AnnouncementReceipt.objects.filter(version__announcement_id=item["id"]).count(), 4
        )
        self.assertEqual(
            list(
                AnnouncementVersion.objects.filter(announcement_id=item["id"])
                .order_by("number")
                .values_list("title", flat=True)
            ),
            ["戶外教學", "新版"],
        )
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        other_base = f"/api/classes/{other['id']}/"
        self.client.post(other_base + "students/", {"text": "1\t保留學生\t001"})
        original_base = self.base
        self.base = other_base
        keep = self.publish().json()
        self.base = original_base
        other_student = APIClient()
        other_student.force_login(Student.objects.get(cohort_id=other["id"]).user)
        other_student.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        self.confirm(other_student, keep)
        deleted_id = self.students[0]["id"]
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{deleted_id}/", {"confirmation_student_number": "001"}
            ).status_code,
            200,
        )
        self.assertFalse(AnnouncementReceipt.objects.filter(student_id=deleted_id).exists())
        self.assertEqual(
            AnnouncementReceipt.objects.filter(version__announcement_id=item["id"]).count(), 2
        )
        self.assertEqual(self.roster(edited).json()["read_count"], 1)
        self.assertEqual(self.confirm(student, edited).status_code, 403)
        self.assertEqual(
            self.client.delete(self.base, {"confirmation_name": "記分班"}).status_code, 200
        )
        self.assertFalse(AnnouncementVersion.objects.filter(announcement_id=item["id"]).exists())
        self.assertFalse(
            AnnouncementReceipt.objects.filter(version__announcement_id=item["id"]).exists()
        )
        self.assertEqual(self.confirm(second, edited).status_code, 403)
        self.assertEqual(self.confirm(other_student, keep).status_code, 200)
        self.assertTrue(AnnouncementVersion.objects.filter(announcement_id=keep["id"]).exists())
        self.assertEqual(AnnouncementReceipt.objects.count(), 1)
