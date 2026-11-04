import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, Notification, Student, User

from . import test_announcements, test_scores


class NotificationTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish
    change = test_announcements.AnnouncementTests.change
    path = "/api/notifications/"

    def inbox(self, client):
        response = client.get(self.path)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_publication_retry_and_viewing_are_personal_and_do_not_confirm_reading(self):
        student = self.student_login()
        other = self.student_login("002")
        identity = str(uuid.uuid4())
        item = self.publish(request_id=identity).json()
        self.publish(request_id=identity)
        inbox = self.inbox(student)
        self.assertEqual((inbox["count"], inbox["unread_count"]), (1, 1))
        notice = inbox["results"][0]
        self.assertEqual(notice["kind"], "announcement_published")
        self.assertEqual(notice["title"], "戶外教學")
        self.assertEqual(self.inbox(self.client)["count"], 0)
        target = student.post(self.path + f"{notice['id']}/open/")
        self.assertEqual(target.status_code, 200)
        self.assertEqual(target.json()["announcement_id"], item["id"])
        self.assertEqual(self.inbox(student)["unread_count"], 0)
        self.assertEqual(self.inbox(other)["unread_count"], 1)
        self.assertIsNone(
            student.get("/api/student/announcements/").json()["results"][0]["confirmed_at"]
        )
        self.assertEqual(other.post(self.path + f"{notice['id']}/open/").status_code, 404)

    def test_content_updates_all_viewed_cutoff_and_new_students_have_no_history(self):
        student = self.student_login()
        item = self.publish().json()
        cutoff = self.inbox(student)["latest_id"]
        pinned = self.change(item, "pin", is_pinned=True).json()
        same = self.change(pinned, "edit", title=item["title"], body=item["body"]).json()
        self.assertEqual(self.inbox(student)["count"], 1)
        edited = self.change(same, "edit", title="已更新", body=item["body"]).json()
        self.assertEqual(self.inbox(student)["results"][0]["kind"], "announcement_updated")
        for _ in range(2):
            self.assertEqual(
                student.post(self.path + "viewed/", {"through_id": cutoff}).status_code, 200
            )
        self.assertEqual(self.inbox(student)["unread_count"], 1)
        self.assertEqual(self.inbox(student)["count"], 2)
        self.client.post(self.base + "students/", {"text": "3\t新學生\t003"})
        newcomer = self.student_login("003")
        self.assertEqual(self.inbox(newcomer)["count"], 0)
        self.assertIsNone(
            newcomer.get("/api/student/announcements/").json()["results"][0]["confirmed_at"]
        )
        changed = self.change(
            edited, "edit", title="已更新", body=test_announcements.document("新內文")
        ).json()
        self.assertEqual(self.inbox(newcomer)["count"], 1)
        self.assertEqual(self.inbox(student)["count"], 3)
        notification_id = self.inbox(student)["results"][0]["id"]
        self.change(changed, "delete")
        self.assertEqual(self.inbox(student)["unread_count"], 0)
        self.assertEqual(self.inbox(student)["count"], 0)
        self.assertEqual(student.post(self.path + f"{notification_id}/open/").status_code, 404)

    def test_application_and_comment_retries_follow_recipient_and_event_rules(self):
        teacher = User.objects.create_user(
            username="applicant", display_name="共同老師", email_verified=True
        )
        co = APIClient()
        co.force_login(teacher)
        code = self.client.get(self.base + "teachers/").json()["application_code"]
        for _ in range(2):
            application = co.post("/api/teacher-applications/", {"application_code": code})
            self.assertIn(application.status_code, [200, 201])
        self.assertEqual(self.inbox(self.client)["count"], 1)
        self.assertEqual(self.inbox(co)["count"], 0)
        member = self.client.get(self.base + "teachers/").json()["members"][0]
        self.client.post(
            self.base + f"teachers/{member['id']}/",
            {"action": "approve", "revision": member["revision"]},
        )
        notice = self.inbox(self.client)["results"][0]
        opened = self.client.post(self.path + f"{notice['id']}/open/").json()
        self.assertEqual(opened["member_status"], "approved")
        student = self.student_login()
        item = self.publish().json()
        comments = self.base + f"announcements/{item['id']}/comments/"
        payload = {
            "request_id": str(uuid.uuid4()),
            "body": test_announcements.document("不複製到通知的留言"),
        }
        first = co.post(comments, payload, format="json").json()
        co.post(comments, payload, format="json")
        self.assertEqual(self.inbox(self.client)["count"], 2)
        self.assertEqual(self.inbox(student)["count"], 1)
        self.assertEqual(self.inbox(co)["count"], 0)
        pinned = self.change(item, "pin", is_pinned=True).json()
        payload["request_id"] = str(uuid.uuid4())
        comment = self.client.post(comments, payload, format="json").json()
        self.assertEqual(self.inbox(self.client)["count"], 2)  # no self-notification
        self.assertEqual(self.inbox(student)["count"], 2)
        co.post(
            comments + f"{first['id']}/",
            {
                "request_id": str(uuid.uuid4()),
                "action": "edit",
                "revision": 1,
                "body": test_announcements.document("修改"),
            },
            format="json",
        )
        self.client.post(
            comments + f"{comment['id']}/",
            {"request_id": str(uuid.uuid4()), "action": "delete", "revision": 1},
            format="json",
        )
        self.change(pinned, "pin", is_pinned=False)
        self.assertEqual(self.inbox(student)["count"], 2)
        self.assertNotIn("不複製到通知的留言", str(self.inbox(student)))
        self.assertEqual(self.inbox(self.client)["count"], 2)
        # A genuinely new application after rejection/removal is a new event.
        member = self.client.get(self.base + "teachers/").json()["members"][0]
        self.client.post(
            self.base + f"teachers/{member['id']}/",
            {"action": "remove", "revision": member["revision"]},
        )
        co.post("/api/teacher-applications/", {"application_code": code})
        co.post("/api/teacher-applications/", {"application_code": code})
        self.assertEqual(self.inbox(self.client)["count"], 3)

    def test_notification_target_can_open_an_older_announcement_and_rejects_other_classes(self):
        student = self.student_login()
        item = self.publish().json()
        self.publish(title="較新公告")
        result = student.get(f"/api/student/announcements/?announcement_id={item['id']}").json()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["id"], item["id"])
        self.assertEqual(
            student.get("/api/student/announcements/?announcement_id=0").status_code, 400
        )
        self.assertEqual(
            student.get("/api/student/announcements/?announcement_id=999999").status_code, 404
        )

    def test_permissions_csrf_session_reset_and_revocation_apply_to_every_action(self):
        unready = self.student_login(change=False)
        item = self.publish().json()
        for client in [APIClient(), unready]:
            self.assertEqual(client.get(self.path).status_code, 403)
            self.assertEqual(
                client.post(self.path + "viewed/", {"through_id": 999}).status_code, 403
            )
            self.assertEqual(client.post(self.path + "1/open/").status_code, 403)
        unready.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        student = unready
        notice = self.inbox(student)["results"][0]
        protected = APIClient(enforce_csrf_checks=True)
        protected.cookies = student.cookies.copy()
        self.assertEqual(protected.post(self.path + f"{notice['id']}/open/").status_code, 403)
        self.assertEqual(
            protected.post(self.path + "viewed/", {"through_id": notice["id"]}).status_code, 403
        )
        for values in [
            {},
            {"through_id": -1},
            {"through_id": True},
            {"through_id": 1.5},
            {"through_id": 1, "recipient": self.owner.pk},
        ]:
            self.assertEqual(
                student.post(self.path + "viewed/", values, format="json").status_code, 400
            )
        self.client.post(self.base + f"students/{self.students[0]['id']}/reset-password/")
        self.assertEqual(student.get(self.path).status_code, 403)
        self.assertEqual(student.post(self.path + f"{notice['id']}/open/").status_code, 403)
        self.assertEqual(
            student.post(self.path + "viewed/", {"through_id": notice["id"]}).status_code, 403
        )
        # A previously notified homeroom cannot use an old notification after losing that role.
        co_user = User.objects.create_user(username="revocation-commenter")
        ClassMember.objects.create(cohort_id=self.cohort["id"], user=co_user, role="coTeacher")
        co = APIClient()
        co.force_login(co_user)
        co.post(
            self.base + f"announcements/{item['id']}/comments/",
            {"request_id": str(uuid.uuid4()), "body": test_announcements.document()},
            format="json",
        )
        owner_notice = self.inbox(self.client)["results"][0]
        ClassMember.objects.filter(cohort_id=self.cohort["id"], user=self.owner).update(
            approved=False
        )
        self.assertEqual(self.inbox(self.client)["count"], 0)
        self.assertEqual(
            self.client.post(self.path + f"{owner_notice['id']}/open/").status_code, 404
        )

    def test_permanent_student_and_cohort_deletion_remove_notifications_and_keep_others(self):
        student = self.student_login()
        other = self.student_login("002")
        self.publish()
        other_cohort = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        old_base = self.base
        self.base = f"/api/classes/{other_cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t保留學生\t009"})
        self.publish()
        keep_student = Student.objects.get(cohort_id=other_cohort["id"])
        keep = APIClient()
        keep.force_login(keep_student.user)
        keep.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        self.base = old_base
        student_id = self.students[0]["id"]
        user_id = Student.objects.get(pk=student_id).user_id
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{student_id}/", {"confirmation_student_number": "001"}
            ).status_code,
            200,
        )
        self.assertFalse(Notification.objects.filter(student_id=student_id).exists())
        self.assertFalse(Notification.objects.filter(recipient_id=user_id).exists())
        self.assertEqual(student.get(self.path).status_code, 403)
        self.assertEqual(self.inbox(other)["count"], 1)
        self.assertEqual(self.inbox(keep)["count"], 1)
        self.assertEqual(
            self.client.delete(self.base, {"confirmation_name": "記分班"}).status_code, 200
        )
        self.assertFalse(Notification.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertEqual(other.get(self.path).status_code, 403)
        self.assertEqual(self.inbox(keep)["count"], 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_pagination_and_all_viewed_include_every_visible_notification(self):
        student = self.student_login()
        for number in range(26):
            self.publish(title=f"公告{number}")
        first = self.inbox(student)
        self.assertEqual(
            (first["count"], first["unread_count"], len(first["results"])), (26, 26, 25)
        )
        second = student.get(self.path + "?page=2").json()
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(second["results"][0]["title"], "公告0")
        student.post(self.path + "viewed/", {"through_id": first["latest_id"]})
        self.assertEqual(self.inbox(student)["unread_count"], 0)
        self.assertIsNotNone(student.get(self.path + "?page=2").json()["results"][0]["viewed_at"])
