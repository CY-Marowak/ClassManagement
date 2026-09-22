import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import User


class ScoreTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="score-owner",
            email="score@example.com",
            display_name="林老師",
            email_verified=True,
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "記分班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{self.cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t小明\t001\n2\t小美\t002"})
        self.students = self.client.get(self.base + "students/").json()

    def payload(self, **changes):
        return {
            "student_id": self.students[0]["id"],
            "kind": "positive",
            "score": 3,
            "template": "participation",
            "note": "主動分享",
            "request_id": str(uuid.uuid4()),
            **changes,
        }

    def student_login(self, number="001", change=True):
        client = APIClient()
        self.assertEqual(
            client.post(
                "/api/student/login/",
                {
                    "class_code": self.cohort["student_login_code"],
                    "student_number": number,
                    "password": number,
                },
            ).status_code,
            200,
        )
        if change:
            self.assertEqual(
                client.post(
                    "/api/student/change-password/",
                    {
                        "password": "Garden!Meadow2026",
                    },
                ).status_code,
                200,
            )
        return client

    def test_teacher_creates_score_and_student_sees_own_total_reason_and_author(self):
        student = self.student_login()
        response = self.client.post(self.base + "scores/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        record = response.json()
        self.assertEqual(record["score"], 3)
        self.assertEqual(record["reason"], "積極參與")
        self.assertEqual(record["note"], "主動分享")
        self.assertEqual(record["creator_name"], "林老師")
        self.assertFalse(record["needs_reason"])
        result = student.get("/api/student/scores/").json()
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"], [record])
        events = self.client.get(self.base + "score-events/").json()["results"]
        self.assertEqual(events[0]["action"], "created")
        self.assertEqual(events[0]["before"], {})
        self.assertEqual(events[0]["after"]["score"], 3)
        self.assertEqual(events[0]["actor_name"], "林老師")

    def test_zero_both_kinds_negative_totals_and_retry_do_not_duplicate(self):
        student = self.student_login()
        self.assertEqual(student.get("/api/student/scores/").json()["total"], 0)
        for kind, score, template in [
            ("positive", 0, "other"),
            ("negative", 0, "other"),
            ("negative", -100, "rules"),
            ("positive", 100, "helping"),
            ("negative", -2, "incomplete"),
        ]:
            payload = self.payload(kind=kind, score=score, template=template, note="  ")
            created = self.client.post(self.base + "scores/", payload, format="json")
            self.assertEqual(created.status_code, 201)
            retry = self.client.post(self.base + "scores/", payload, format="json")
            self.assertEqual(retry.status_code, 200)
            self.assertEqual(retry.json(), created.json())
            self.assertEqual(created.json()["kind"], kind)
            self.assertEqual(created.json()["needs_reason"], template == "other")
            conflicting = self.client.post(
                self.base + "scores/",
                {
                    **payload,
                    "note": "changed",
                },
                format="json",
            )
            self.assertEqual(conflicting.status_code, 400)
        result = student.get("/api/student/scores/").json()
        self.assertEqual(result["total"], -2)
        self.assertEqual(result["count"], 5)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 5)

    def test_invalid_values_templates_and_forged_fields_leave_everything_unchanged(self):
        for changes in [
            {"score": 101},
            {"score": -101, "kind": "negative"},
            {"score": -1},
            {"score": 1, "kind": "negative"},
            {"score": 1.5},
            {"score": "1.0"},
            {"score": True},
            {"kind": "unknown"},
            {"template": "rules"},
            {"template": "unknown"},
            {"note": "a" * 1001},
            {"creator_id": 999},
            {"request_id": "invalid"},
            {"student_id": 1.2},
            {"student_id": 999999},
        ]:
            with self.subTest(changes=changes):
                response = self.client.post(
                    self.base + "scores/", self.payload(**changes), format="json"
                )
                self.assertIn(response.status_code, [400, 404])
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 0)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 0)

    def test_co_teacher_sees_all_students_but_students_only_see_themselves(self):
        from core.models import ClassMember

        colleague = User.objects.create_user(
            username="colleague", email="co@example.com", display_name="陳老師", email_verified=True
        )
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=colleague, role="coTeacher"
        )
        teacher = APIClient()
        teacher.force_login(colleague)
        response = teacher.post(self.base + "scores/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(teacher.get(self.base + "score-events/").status_code, 404)
        roster = teacher.get(self.base + "score-roster/").json()
        self.assertEqual([s["name"] for s in roster["students"]], ["小明", "小美"])
        self.assertEqual([s["total"] for s in roster["students"]], [3, 0])
        self.assertNotIn("student_number", str(roster))
        self.client.post(
            self.base + "scores/",
            self.payload(student_id=self.students[1]["id"], score=5),
            format="json",
        )
        self.assertEqual(teacher.get(self.base + "scores/").json()["count"], 2)
        selected = teacher.get(self.base + f"scores/?student_id={self.students[0]['id']}").json()
        self.assertEqual(selected["count"], 1)
        self.assertEqual(selected["total"], 3)
        student = self.student_login()
        own = student.get(f"/api/student/scores/?student_id={self.students[1]['id']}").json()
        self.assertEqual(own["count"], 1)
        self.assertEqual(own["total"], 3)
        self.assertEqual(own["results"][0]["student_id"], self.students[0]["id"])
        pending_student = self.student_login("002", change=False)
        self.assertEqual(pending_student.get("/api/student/scores/").status_code, 403)
        for client in [student, pending_student, APIClient()]:
            for url in ["scores/", "score-roster/", "score-events/"]:
                self.assertEqual(client.get(self.base + url).status_code, 403)
            self.assertEqual(
                client.post(self.base + "scores/", self.payload(), format="json").status_code, 403
            )
        for status in ["pending", "rejected", "removed"]:
            member.approved = False
            member.inactive_status = status
            member.save()
            self.assertEqual(teacher.get(self.base + "scores/").status_code, 404)
            self.assertEqual(teacher.get(self.base + "score-roster/").status_code, 404)
            self.assertEqual(
                teacher.post(self.base + "scores/", self.payload(), format="json").status_code, 404
            )
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 2)

    def test_cross_class_targets_outsider_and_csrf(self):
        other = self.client.post(
            "/api/classes/",
            {
                "name": "另一班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        other_url = f"/api/classes/{other['id']}/scores/"
        self.assertEqual(
            self.client.post(other_url, self.payload(), format="json").status_code, 404
        )
        self.assertEqual(
            self.client.get(other_url + f"?student_id={self.students[0]['id']}").status_code, 404
        )
        outsider = User.objects.create_user(username="outside", email="outside@example.com")
        client = APIClient()
        client.force_login(outsider)
        self.assertEqual(client.get(self.base + "scores/").status_code, 404)
        self.assertEqual(
            client.post(self.base + "scores/", self.payload(), format="json").status_code, 404
        )
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        payload = self.payload()
        self.assertEqual(
            protected.post(self.base + "scores/", payload, format="json").status_code, 403
        )
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.post(
                self.base + "scores/", payload, format="json", HTTP_X_CSRFTOKEN=token
            ).status_code,
            201,
        )

    def test_pagination_and_historical_teacher_name_survive_renaming(self):
        for i in range(26):
            self.assertEqual(
                self.client.post(
                    self.base + "scores/", self.payload(note=str(i)), format="json"
                ).status_code,
                201,
            )
        self.owner.display_name = "新名字"
        self.owner.save()
        first = self.client.get(self.base + "scores/").json()
        second = self.client.get(self.base + "scores/?page=2").json()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual(first["results"][0]["note"], "25")
        self.assertEqual(second["results"][0]["note"], "0")
        self.assertEqual(len({r["id"] for r in first["results"] + second["results"]}), 26)
        self.assertTrue(all(r["creator_name"] == "林老師" for r in first["results"]))
        self.assertEqual(self.client.get(self.base + "scores/?page=0").status_code, 404)

    def test_permanent_student_and_class_deletion_remove_scores_and_audit_only_for_targets(self):
        from core.models import ScoreAuditEvent, ScoreRecord

        other = self.client.post(
            "/api/classes/",
            {
                "name": "保留班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        kept_base = f"/api/classes/{other['id']}/"
        self.client.post(kept_base + "students/", {"text": "1\t保留\t001"})
        kept_student = self.client.get(kept_base + "students/").json()[0]
        kept = self.client.post(
            kept_base + "scores/", self.payload(student_id=kept_student["id"]), format="json"
        ).json()
        removed = self.client.post(self.base + "scores/", self.payload(), format="json").json()
        sibling = self.client.post(
            self.base + "scores/", self.payload(student_id=self.students[1]["id"]), format="json"
        ).json()
        student = self.student_login()
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{self.students[0]['id']}/",
                {"confirmation_student_number": "001"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(student.get("/api/student/scores/").status_code, 403)
        self.assertFalse(ScoreRecord.objects.filter(pk=removed["id"]).exists())
        self.assertFalse(ScoreAuditEvent.objects.filter(record_id=removed["id"]).exists())
        self.assertEqual(self.client.get(self.base + "scores/").json()["results"], [sibling])
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": "記分班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(ScoreRecord.objects.filter(pk=sibling["id"]).exists())
        self.assertFalse(ScoreAuditEvent.objects.filter(record_id=sibling["id"]).exists())
        self.assertEqual(self.client.get(kept_base + "scores/").json()["results"], [kept])
        self.assertEqual(self.client.get(kept_base + "score-events/").json()["count"], 1)
