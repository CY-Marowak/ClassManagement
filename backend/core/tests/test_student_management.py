from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, User


class StudentManagementTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            display_name="林老師",
            password="Teacher!Ready2026",
            email_verified=True,
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "向日葵班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.roster_url = f"/api/classes/{self.cohort['id']}/students/"
        self.audit_url = f"/api/classes/{self.cohort['id']}/student-events/"
        self.client.post(self.roster_url, {"text": "1\t小明\t00001\n2\t小美\t00002"})
        self.original = self.client.get(self.roster_url).json()[0]
        self.detail_url = f"{self.roster_url}{self.original['id']}/"

    def login(self, number="00001", password="00001"):
        client = APIClient()
        response = client.post(
            "/api/student/login/",
            {
                "class_code": self.cohort["student_login_code"],
                "student_number": number,
                "password": password,
            },
        )
        self.assertEqual(response.status_code, 200)
        return client

    def test_profile_correction_keeps_identity_password_avatar_and_audit_history(self):
        student = self.login()
        self.assertEqual(
            student.post(
                "/api/student/change-password/",
                {
                    "password": "Garden!Meadow2026",
                },
            ).status_code,
            200,
        )
        before_events = self.client.get(self.audit_url)
        self.assertEqual(before_events.status_code, 200)
        before_events = before_events.json()["results"]
        response = self.client.patch(
            self.detail_url,
            {
                "name": "林小明",
                "seat_number": 3,
                "student_number": "00901",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                **self.original,
                "name": "林小明",
                "seat_number": 3,
                "student_number": "00901",
            },
        )
        self.assertEqual(student.get("/api/student/me/").json()["id"], self.original["id"])
        returning = self.login("00901", "Garden!Meadow2026")
        self.assertEqual(
            returning.get("/api/student/me/").json()["avatar"], self.original["avatar"]
        )
        self.assertEqual(
            APIClient()
            .post(
                "/api/student/login/",
                {
                    "class_code": self.cohort["student_login_code"],
                    "student_number": "00001",
                    "password": "Garden!Meadow2026",
                },
            )
            .status_code,
            400,
        )
        events = self.client.get(self.audit_url).json()["results"]
        self.assertEqual(events[1:], before_events)
        event = events[0]
        self.assertEqual(event["action"], "profile_updated")
        self.assertEqual(event["actor_name"], "林老師")
        self.assertEqual(event["student_id"], self.original["id"])
        self.assertEqual(event["student_name"], "林小明")
        self.assertTrue(event["created_at"])
        self.assertEqual(
            event["before"], {"name": "小明", "seat_number": 1, "student_number": "00001"}
        )
        self.assertEqual(
            event["after"], {"name": "林小明", "seat_number": 3, "student_number": "00901"}
        )
        self.assertNotIn("Garden!Meadow2026", str(events))

    def test_reset_revokes_all_sessions_uses_current_number_and_requires_new_password(self):
        first = self.login()
        first.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        second = self.login(password="Garden!Meadow2026")
        other = self.login("00002", "00002")
        self.client.patch(self.detail_url, {"student_number": "00901"})
        response = self.client.post(self.detail_url + "reset-password/")
        self.assertEqual(response.status_code, 200)
        for client in [first, second]:
            self.assertEqual(client.get("/api/auth/me/").status_code, 403)
            self.assertEqual(
                client.post(
                    "/api/student/change-password/",
                    {
                        "password": "Forbidden!Meadow2026",
                    },
                ).status_code,
                403,
            )
        self.assertEqual(other.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(
            APIClient()
            .post(
                "/api/student/login/",
                {
                    "class_code": self.cohort["student_login_code"],
                    "student_number": "00901",
                    "password": "Garden!Meadow2026",
                },
            )
            .status_code,
            400,
        )
        reset = self.login("00901", "00901")
        self.assertTrue(reset.get("/api/auth/me/").json()["must_change_password"])
        self.assertEqual(reset.get("/api/student/me/").status_code, 403)
        self.assertEqual(
            reset.post("/api/student/change-password/", {"password": "00901"}).status_code, 400
        )
        self.assertEqual(
            reset.post(
                "/api/student/change-password/",
                {
                    "password": "Another!Journey2026",
                },
            ).status_code,
            200,
        )
        self.assertEqual(reset.get("/api/student/me/").json()["avatar"], self.original["avatar"])
        event = self.client.get(self.audit_url).json()["results"][0]
        self.assertEqual(event["action"], "password_reset")
        self.assertEqual(event["before"], {})
        self.assertEqual(event["after"], {})
        self.assertNotIn("00901", str(event))
        self.assertNotIn("Garden!Meadow2026", str(event))
        self.assertNotIn("pbkdf2", str(event))

    def test_conflicts_invalid_fields_and_no_change_leave_profile_and_history_untouched(self):
        original_roster = self.client.get(self.roster_url).json()
        original_events = self.client.get(self.audit_url).json()
        for payload in [
            {"name": "不應變更", "seat_number": 2},
            {"name": "不應變更", "student_number": "00002"},
            {"seat_number": 0},
            {"seat_number": 10000},
            {"name": ""},
            {"name": "名" * 81},
            {"student_number": "white space"},
            {"student_number": "a" * 65},
            {"avatar": "rabbit"},
            {"id": 999},
            {"cohort_id": 999},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(self.detail_url, payload).status_code, 400)
                self.assertEqual(self.client.get(self.roster_url).json(), original_roster)
                self.assertEqual(self.client.get(self.audit_url).json(), original_events)
        for payload in [{}, {"name": "小明"}]:
            self.assertEqual(self.client.patch(self.detail_url, payload).status_code, 200)
        self.assertEqual(self.client.get(self.audit_url).json(), original_events)

    def test_other_roles_cross_class_targets_and_csrf_are_rejected(self):
        outsider = User.objects.create_user(
            username="outside",
            email="outside@example.com",
            email_verified=True,
        )
        client = APIClient()
        for role, approved in [
            (None, False),
            ("coTeacher", False),
            ("coTeacher", True),
            ("homeroom", False),
        ]:
            if role:
                # Replace the owner's membership only for the pending-homeroom case.
                if role == "homeroom":
                    ClassMember.objects.filter(
                        cohort_id=self.cohort["id"], user=self.owner
                    ).delete()
                ClassMember.objects.update_or_create(
                    cohort_id=self.cohort["id"],
                    user=outsider,
                    defaults={"role": role, "approved": approved},
                )
            client.force_login(outsider)
            self.assertEqual(client.patch(self.detail_url, {"name": "越權"}).status_code, 404)
            self.assertEqual(client.post(self.detail_url + "reset-password/").status_code, 404)
            self.assertEqual(client.get(self.audit_url).status_code, 404)
        ClassMember.objects.filter(user=outsider).delete()
        ClassMember.objects.create(cohort_id=self.cohort["id"], user=self.owner, role="homeroom")
        student = self.login()
        for client in [APIClient(), student]:
            self.assertEqual(client.patch(self.detail_url, {"name": "越權"}).status_code, 403)
            self.assertEqual(client.post(self.detail_url + "reset-password/").status_code, 403)
            self.assertEqual(client.get(self.audit_url).status_code, 403)
        other = self.client.post(
            "/api/classes/",
            {
                "name": "另一班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        mixed = f"/api/classes/{other['id']}/students/{self.original['id']}/"
        self.assertEqual(self.client.patch(mixed, {"name": "越界"}).status_code, 404)
        self.assertEqual(self.client.post(mixed + "reset-password/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/classes/{other['id']}/student-events/").json()["results"], []
        )
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(protected.patch(self.detail_url, {"name": "改名"}).status_code, 403)
        self.assertEqual(protected.post(self.detail_url + "reset-password/").status_code, 403)
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.patch(self.detail_url, {"name": "改名"}, HTTP_X_CSRFTOKEN=token).status_code,
            200,
        )
        self.assertEqual(
            protected.post(self.detail_url + "reset-password/", HTTP_X_CSRFTOKEN=token).status_code,
            200,
        )

    def test_initial_password_survives_number_edit(self):
        self.client.patch(self.detail_url, {"student_number": "00901"})
        student = self.login("00901", "00001")
        self.assertTrue(student.get("/api/auth/me/").json()["must_change_password"])

    def test_events_paginate_with_stable_student_and_actor_snapshots(self):
        for i in range(26):
            self.assertEqual(
                self.client.patch(self.detail_url, {"name": f"小明{i}"}).status_code, 200
            )
        self.owner.display_name = "新老師名稱"
        self.owner.save(update_fields=["display_name"])
        first = self.client.get(self.audit_url).json()
        second = self.client.get(self.audit_url + "?page=2").json()
        self.assertEqual(first["count"], 28)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 3)
        self.assertTrue(first["next"])
        self.assertIsNone(second["next"])
        events = first["results"] + second["results"]
        self.assertEqual(len({e["id"] for e in events}), 28)
        self.assertTrue(all(e["actor_name"] == "林老師" for e in events))
        self.assertEqual(events[0]["student_name"], "小明25")
        self.assertEqual(events[-1]["student_name"], "小明")
        self.assertEqual(events[-1]["action"], "created")
        self.assertEqual(self.client.get(self.audit_url + "?page=0").status_code, 404)

    def test_delete_removes_all_audit_actions_and_preserves_other_class_history(self):
        from core.models import StudentAuditEvent

        other = self.client.post(
            "/api/classes/",
            {
                "name": "保留班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        self.client.post(f"/api/classes/{other['id']}/students/", {"text": "1\t保留\t00001"})
        kept_url = f"/api/classes/{other['id']}/student-events/"
        kept_events = self.client.get(kept_url).json()
        self.client.patch(self.detail_url, {"name": "修正姓名"})
        self.client.post(self.detail_url + "reset-password/")
        removed_ids = [event["id"] for event in self.client.get(self.audit_url).json()["results"]]
        self.assertEqual(len(removed_ids), 4)
        self.assertEqual(
            self.client.delete(
                f"/api/classes/{self.cohort['id']}/",
                {
                    "confirmation_name": "向日葵班",
                },
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(self.audit_url).status_code, 404)
        self.assertFalse(StudentAuditEvent.objects.filter(pk__in=removed_ids).exists())
        self.assertEqual(self.client.get(kept_url).json(), kept_events)
