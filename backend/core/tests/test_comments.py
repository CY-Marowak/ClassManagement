import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, User

from . import test_announcements, test_scores


class CommentTests(APITestCase):
    student_login = test_scores.ScoreTests.student_login

    def setUp(self):
        test_scores.ScoreTests.setUp(self)
        self.announcement = test_announcements.AnnouncementTests.publish(self).json()
        self.path = self.base + f"announcements/{self.announcement['id']}/comments/"
        self.student_path = f"/api/student/announcements/{self.announcement['id']}/comments/"
        self.colleague = User.objects.create_user(
            username="comment-teacher", display_name="陳老師", email_verified=True
        )
        self.member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=self.colleague, role="coTeacher", approved=True
        )
        self.writer = APIClient()
        self.writer.force_login(self.colleague)

    def post_comment(self, client=None, **values):
        return (client or self.writer).post(
            self.path,
            {
                "body": test_announcements.document("記得帶雨衣"),
                "request_id": str(uuid.uuid4()),
                **values,
            },
            format="json",
        )

    def change_comment(self, item, client=None, **values):
        return (client or self.writer).post(
            self.path + f"{item['id']}/",
            {
                "action": "edit",
                "revision": item["revision"],
                "request_id": str(uuid.uuid4()),
                **values,
            },
            format="json",
        )

    def test_creator_edits_and_owner_only_deletes_with_revision_and_safe_retries(self):
        identity = str(uuid.uuid4())
        item = self.post_comment(request_id=identity).json()
        self.assertEqual(self.post_comment(request_id=identity).json(), item)
        self.assertEqual(
            self.post_comment(
                request_id=identity, body=test_announcements.document("不同")
            ).status_code,
            400,
        )
        body = test_announcements.document("請帶輕便雨衣")
        self.assertEqual(self.change_comment(item, self.client, body=body).status_code, 403)
        edit_id = str(uuid.uuid4())
        response = self.change_comment(item, body=body, request_id=edit_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.change_comment(item, body=body, request_id=edit_id).json(), response.json()
        )
        edited = response.json()
        self.assertEqual(edited["created_at"], item["created_at"])
        self.assertIsNotNone(edited["edited_at"])
        self.assertEqual(edited["revision"], 2)
        self.assertEqual(self.change_comment(item, action="delete").status_code, 409)
        other = User.objects.create_user(
            username="other-commenter", email="other-commenter@example.com", display_name="王老師"
        )
        ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=other, role="coTeacher", approved=True
        )
        client = APIClient()
        client.force_login(other)
        self.assertFalse(client.get(self.path).json()["results"][0]["can_edit"])
        self.assertEqual(self.change_comment(edited, client, body=body).status_code, 403)
        self.assertEqual(self.change_comment(edited, client, action="delete").status_code, 403)
        delete_id = str(uuid.uuid4())
        self.assertEqual(
            self.change_comment(
                edited, self.client, action="delete", request_id=delete_id
            ).status_code,
            200,
        )
        self.assertEqual(
            self.change_comment(
                edited, self.client, action="delete", request_id=delete_id
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(self.path).json()["count"], 0)
        self.assertEqual(
            self.client.get(self.base + "announcements/").json()["results"][0]["comment_count"], 0
        )

    def test_homeroom_authors_own_comments_and_others_only_read(self):
        identity = str(uuid.uuid4())
        response = self.post_comment(self.client, request_id=identity)
        self.assertEqual(response.status_code, 201)
        item = response.json()
        self.assertTrue(item["can_edit"])
        self.assertTrue(item["can_delete"])
        self.assertEqual(self.post_comment(self.client, request_id=identity).json(), item)
        self.assertEqual(self.client.get(self.path).json()["count"], 1)
        body = test_announcements.document("導師補充")
        self.assertEqual(self.change_comment(item, body=body).status_code, 403)
        self.assertEqual(self.change_comment(item, action="delete").status_code, 403)
        edited = self.change_comment(item, self.client, body=body)
        self.assertEqual(edited.status_code, 200)
        for client, path in [
            (self.writer, self.path),
            (self.student_login(), self.student_path),
        ]:
            visible = client.get(path).json()["results"][0]
            self.assertEqual(visible["body"], body)
            self.assertFalse(visible["can_edit"])
            self.assertFalse(visible["can_delete"])
        self.assertEqual(
            self.change_comment(edited.json(), self.client, action="delete").status_code, 200
        )
        self.assertEqual(self.client.get(self.path).json()["count"], 0)

    def test_approved_teachers_post_and_class_members_read_rich_text(self):
        body = test_announcements.document("記得帶雨衣", [{"type": "italic"}])
        response = self.post_comment(body=body)
        self.assertEqual(response.status_code, 201)
        item = response.json()
        self.assertEqual(item["creator_name"], "陳老師")
        self.assertEqual(item["body"], body)
        for client, path in [
            (self.writer, self.path),
            (self.client, self.path),
            (self.student_login(), self.student_path),
        ]:
            page = client.get(path).json()
            self.assertEqual(page["count"], 1)
            self.assertEqual(page["results"][0]["body"], body)
            self.assertEqual(page["can_create"], client is self.writer or client is self.client)
        self.assertEqual(
            self.client.get(self.base + "announcements/").json()["results"][0]["comment_count"], 1
        )
        student = self.student_login("002", change=False)
        self.assertEqual(student.get(self.student_path).status_code, 403)
        self.assertEqual(student.post(self.student_path, {}).status_code, 403)
        for approved in [False]:
            self.member.approved = approved
            self.member.save()
            self.assertEqual(self.post_comment().status_code, 404)
            self.assertEqual(self.writer.get(self.path).status_code, 404)
        self.assertEqual(self.client.get(self.path).json()["count"], 1)

    def test_ready_student_anonymous_and_removed_creator_cannot_mutate(self):
        identity = str(uuid.uuid4())
        item = self.post_comment(request_id=identity).json()
        student = self.student_login()
        self.assertEqual(student.post(self.student_path, {}).status_code, 405)
        self.assertEqual(self.post_comment(student).status_code, 403)
        self.assertEqual(self.change_comment(item, student, action="delete").status_code, 403)
        self.assertEqual(APIClient().get(self.path).status_code, 403)
        self.assertEqual(APIClient().get(self.student_path).status_code, 403)
        self.member.approved = False
        self.member.inactive_status = "removed"
        self.member.save()
        self.assertEqual(self.post_comment(request_id=identity).status_code, 404)
        self.assertEqual(self.change_comment(item, action="delete").status_code, 404)
        self.assertEqual(student.get(self.student_path).json()["count"], 1)
        other = self.client.post(
            "/api/classes/", {"name": "別班", "entry_year": 2026, "current_grade": 1}
        ).json()
        announcement = self.client.post(
            f"/api/classes/{other['id']}/announcements/",
            {
                "title": "別班公告",
                "body": test_announcements.document(),
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        ).json()
        self.assertEqual(
            student.get(f"/api/student/announcements/{announcement['id']}/comments/").status_code,
            404,
        )

    def test_format_length_and_page_order_are_preserved(self):
        for body in [
            test_announcements.document(" "),
            test_announcements.document("字" * 1001),
            test_announcements.document(marks=[{"type": "link", "attrs": {"href": "x"}}]),
        ]:
            self.assertEqual(self.post_comment(body=body).status_code, 400)
        items = [
            self.post_comment(
                body=test_announcements.document("字" * 1000 if i == 0 else str(i))
            ).json()
            for i in range(21)
        ]
        first = self.client.get(self.path).json()
        self.assertEqual(first["count"], 21)
        self.assertEqual([v["id"] for v in first["results"]], [v["id"] for v in items[:20]])
        self.assertEqual(
            self.client.get(self.path + "?page=2").json()["results"][0]["id"], items[20]["id"]
        )
        self.change_comment(items[0], body=test_announcements.document("更新最早留言"))
        self.assertEqual(self.client.get(self.path).json()["results"][0]["id"], items[0]["id"])

    def test_other_classes_and_deleted_announcements_reject_reads_writes_and_retries(self):
        identity = str(uuid.uuid4())
        item = self.post_comment(request_id=identity).json()
        other = self.client.post(
            "/api/classes/", {"name": "其他班", "entry_year": 2026, "current_grade": 1}
        ).json()
        wrong = f"/api/classes/{other['id']}/announcements/{self.announcement['id']}/comments/"
        self.assertEqual(self.client.get(wrong).status_code, 404)
        self.assertEqual(
            self.client.post(
                wrong + f"{item['id']}/",
                {"action": "delete", "revision": 1, "request_id": str(uuid.uuid4())},
                format="json",
            ).status_code,
            404,
        )
        student = self.student_login()
        test_announcements.AnnouncementTests.change(self, self.announcement, "delete")
        for client, path in [(self.client, self.path), (student, self.student_path)]:
            self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(self.post_comment(request_id=identity).status_code, 404)
        self.assertEqual(
            self.change_comment(item, body=test_announcements.document()).status_code, 404
        )

    def test_permanent_class_delete_clears_comments_operations_and_preserves_other_class(self):
        from core.models import AnnouncementComment, CommentOperation

        item = self.post_comment().json()
        self.change_comment(item, action="delete")
        self.assertTrue(
            AnnouncementComment.objects.filter(pk=item["id"], deleted_at__isnull=False).exists()
        )
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        ClassMember.objects.create(
            cohort_id=other["id"], user=self.colleague, role="coTeacher", approved=True
        )
        announcement = self.client.post(
            f"/api/classes/{other['id']}/announcements/",
            {
                "title": "保留",
                "body": test_announcements.document(),
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        ).json()
        keep_path = f"/api/classes/{other['id']}/announcements/{announcement['id']}/comments/"
        kept = self.writer.post(
            keep_path,
            {"body": test_announcements.document("保留留言"), "request_id": str(uuid.uuid4())},
            format="json",
        ).json()
        student = self.student_login()
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": "記分班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(AnnouncementComment.objects.filter(pk=item["id"]).exists())
        self.assertFalse(CommentOperation.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertTrue(AnnouncementComment.objects.filter(pk=kept["id"]).exists())
        self.assertTrue(CommentOperation.objects.filter(comment_id=kept["id"]).exists())
        self.assertEqual(self.writer.get(keep_path).json()["count"], 1)
        self.assertEqual(student.get(self.student_path).status_code, 403)
