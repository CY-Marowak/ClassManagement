import uuid
from copy import deepcopy

from rest_framework.test import APIClient, APITestCase

from core.models import Announcement, AnnouncementOperation, ClassMember, User

from . import test_scores


def document(text="明天請帶水壺", marks=None):
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return {"type": "doc", "content": [{"type": "paragraph", "content": [node]}]}


class AnnouncementTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login

    def publish(self, **changes):
        payload = {
            "request_id": str(uuid.uuid4()),
            "title": "戶外教學",
            "body": document(),
            **changes,
        }
        return self.client.post(self.base + "announcements/", payload, format="json")

    def change(self, item, action, **values):
        return self.client.post(
            self.base + f"announcements/{item['id']}/",
            {
                "action": action,
                "revision": item["revision"],
                "request_id": str(uuid.uuid4()),
                **values,
            },
            format="json",
        )

    def test_edit_pin_delete_and_retries_preserve_order_and_reject_stale_changes(self):
        student = self.student_login()
        identity = str(uuid.uuid4())
        first = self.publish(request_id=identity).json()
        self.assertEqual(self.publish(request_id=identity).json(), first)
        self.assertEqual(self.publish(request_id=identity, title="不同內容").status_code, 400)
        second = self.publish(title="較新公告").json()
        edited = self.change(first, "edit", title="修正公告", body=document("帶雨衣"))
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["created_at"], first["created_at"])
        self.assertIsNotNone(edited.json()["edited_at"])
        self.assertEqual(self.change(first, "delete").status_code, 409)
        edited = edited.json()
        pin_id = str(uuid.uuid4())
        pinned = self.change(edited, "pin", is_pinned=True, request_id=pin_id)
        self.assertEqual(pinned.status_code, 200)
        self.assertEqual(
            self.change(edited, "pin", is_pinned=True, request_id=pin_id).json(), pinned.json()
        )
        self.assertEqual(
            self.change(edited, "pin", is_pinned=False, request_id=pin_id).status_code, 400
        )
        results = student.get("/api/student/announcements/").json()["results"]
        self.assertEqual([a["id"] for a in results], [first["id"], second["id"]])
        delete_id = str(uuid.uuid4())
        self.assertEqual(
            self.change(pinned.json(), "delete", request_id=delete_id).status_code, 200
        )
        self.assertEqual(
            self.change(pinned.json(), "delete", request_id=delete_id).status_code, 200
        )
        self.assertEqual(
            self.change(pinned.json(), "edit", title="復活", body=document()).status_code, 404
        )
        self.assertEqual(self.publish(request_id=identity).json(), first)
        self.assertEqual(student.get("/api/student/announcements/").json()["count"], 1)

    def test_homeroom_publishes_formatted_announcement_and_class_members_read_it(self):
        student = self.student_login()
        body = document(
            marks=[
                {"type": "bold"},
                {
                    "type": "textStyle",
                    "attrs": {
                        "color": "#b42318",
                        "fontSize": "20px",
                    },
                },
            ]
        )
        response = self.publish(body=body)
        self.assertEqual(response.status_code, 201)
        announcement = response.json()
        self.assertEqual(announcement["title"], "戶外教學")
        self.assertEqual(announcement["body"], body)
        self.assertEqual(announcement["creator_name"], "林老師")
        self.assertFalse(announcement["is_pinned"])
        self.assertIsNone(announcement["edited_at"])
        self.assertEqual(announcement["revision"], 1)
        for client, endpoint in [
            (self.client, self.base + "announcements/"),
            (student, "/api/student/announcements/"),
        ]:
            result = client.get(endpoint)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["results"], [announcement])

    def test_content_limits_and_only_supported_rich_text_are_accepted(self):
        for title, body in [
            (" ", document()),
            ("x" * 101, document()),
            ("a\nb", document()),
            ("公告", document("   ")),
            ("公告", document("字" * 5001)),
            ("公告", {"type": "doc", "content": [{"type": "image", "attrs": {"src": "x"}}]}),
            ("公告", document(marks=[{"type": "link", "attrs": {"href": "javascript:alert(1)"}}])),
            ("公告", document(marks=[{"type": "textStyle", "attrs": {"color": "url(x)"}}])),
            ("公告", document(marks=[{"type": "textStyle", "attrs": {"fontSize": "999px"}}])),
            ("公告", {"type": "doc", "onclick": "alert(1)", "content": []}),
            ("公告", "<script>alert(1)</script>"),
        ]:
            with self.subTest(title=title[:10], body=str(body)[:100]):
                self.assertEqual(self.publish(title=title, body=body).status_code, 400)
        self.assertEqual(self.client.get(self.base + "announcements/").json()["count"], 0)
        rich = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "清單",
                                            "marks": [
                                                {"type": "italic"},
                                                {"type": "underline"},
                                            ],
                                        },
                                        {"type": "hardBreak"},
                                        {"type": "text", "text": "下一行"},
                                    ],
                                }
                            ],
                        }
                    ],
                },
                {
                    "type": "orderedList",
                    "attrs": {"start": 1},
                    "content": [{"type": "listItem", "content": [document("編號")["content"][0]]}],
                },
            ],
        }
        response = self.publish(title="  公告  ", body=rich)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["body"], rich)
        self.assertEqual(response.json()["title"], "公告")
        self.assertEqual(
            self.publish(title="字" * 100, body=document("字" * 5000)).status_code, 201
        )
        malicious = deepcopy(rich)
        malicious["content"][0]["content"][0]["attrs"] = {"style": "position:fixed"}
        self.assertEqual(self.publish(body=malicious).status_code, 400)

    def test_untrusted_json_types_return_validation_errors(self):
        for body in [
            {"type": []},
            document(marks=[{"type": "textStyle", "attrs": {"color": []}}]),
            document(marks=[{"type": "textStyle", "attrs": {"fontSize": {}}}]),
            {"type": "doc", "content": [{"type": "paragraph", "content": [None]}]},
        ]:
            self.assertEqual(self.publish(body=body).status_code, 400)

    def test_roles_pending_removed_and_other_classes_cannot_manage_or_leak_announcements(self):
        item = self.publish().json()
        path = self.base + "announcements/"
        student = self.student_login(change=False)
        self.assertEqual(student.get("/api/student/announcements/").status_code, 403)
        student.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        self.assertEqual(student.get(path).status_code, 403)
        self.assertEqual(student.post(path, {}).status_code, 403)
        self.assertEqual(student.post("/api/student/announcements/", {}).status_code, 405)
        self.assertEqual(APIClient().get(path).status_code, 403)
        teacher = User.objects.create_user(
            username="announcement-coteacher", display_name="共同教師"
        )
        client = APIClient()
        client.force_login(teacher)
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=teacher, role="coTeacher", approved=False
        )
        self.assertEqual(client.get(path).status_code, 404)
        member.approved = True
        member.save()
        self.assertEqual(client.get(path).json()["results"], [item])
        self.assertEqual(
            client.post(
                path,
                {"request_id": str(uuid.uuid4()), "title": "越權", "body": document()},
                format="json",
            ).status_code,
            404,
        )
        for action, extra in [
            ("pin", {"is_pinned": True}),
            ("edit", {"title": "越權", "body": document()}),
            ("delete", {}),
        ]:
            self.assertEqual(
                client.post(
                    path + f"{item['id']}/",
                    {
                        "action": action,
                        "revision": 1,
                        "request_id": str(uuid.uuid4()),
                        **extra,
                    },
                    format="json",
                ).status_code,
                404,
            )
        member.approved = False
        member.save()
        self.assertEqual(client.get(path).status_code, 404)
        other = self.client.post(
            "/api/classes/", {"name": "別班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.assertEqual(
            self.client.get(f"/api/classes/{other['id']}/announcements/").json()["count"], 0
        )
        self.assertEqual(
            self.client.post(
                f"/api/classes/{other['id']}/announcements/{item['id']}/",
                {
                    "action": "delete",
                    "revision": 1,
                    "request_id": str(uuid.uuid4()),
                },
                format="json",
            ).status_code,
            404,
        )
        # Student query parameters cannot switch their class.
        self.assertEqual(
            student.get(f"/api/student/announcements/?cohort_id={other['id']}").json()["results"],
            [item],
        )

    def test_multiple_pins_pagination_unpin_and_edits_keep_publication_order(self):
        items = [self.publish(title=f"公告 {i}").json() for i in range(12)]
        self.change(items[0], "pin", is_pinned=True)
        self.change(items[2], "pin", is_pinned=True)
        page = self.client.get(self.base + "announcements/").json()
        self.assertEqual(page["count"], 12)
        self.assertEqual(len(page["results"]), 10)
        self.assertEqual(
            [a["id"] for a in page["results"][:3]],
            [items[2]["id"], items[0]["id"], items[11]["id"]],
        )
        second = self.client.get(self.base + "announcements/?page=2").json()["results"]
        self.assertEqual([a["id"] for a in second], [items[3]["id"], items[1]["id"]])
        self.change(items[1], "edit", title="編輯舊公告", body=document())
        self.assertEqual(
            self.client.get(self.base + "announcements/?page=2").json()["results"][-1]["id"],
            items[1]["id"],
        )
        self.change(page["results"][0], "pin", is_pinned=False)
        self.assertEqual(
            self.client.get(self.base + "announcements/").json()["results"][0]["id"], items[0]["id"]
        )

    def test_soft_delete_retains_data_and_permanent_class_deletion_clears_only_its_announcements(
        self,
    ):
        student = self.student_login()
        item = self.publish().json()
        self.change(item, "delete")
        self.assertTrue(
            Announcement.objects.filter(pk=item["id"], deleted_at__isnull=False).exists()
        )
        self.assertEqual(student.get("/api/student/announcements/").json()["count"], 0)
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        keep = self.client.post(
            f"/api/classes/{other['id']}/announcements/",
            {
                "title": "保留公告",
                "body": document(),
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        ).json()
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": "記分班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(Announcement.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertFalse(AnnouncementOperation.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertTrue(Announcement.objects.filter(pk=keep["id"]).exists())
        self.assertTrue(AnnouncementOperation.objects.filter(announcement_id=keep["id"]).exists())
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertEqual(student.get("/api/student/announcements/").status_code, 403)
