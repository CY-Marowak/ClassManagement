from django.apps import apps
from rest_framework.test import APIClient, APITestCase

from core.models import User


class StudentWorkflowTests(APITestCase):
    def test_roster_rejects_other_teachers_pending_members_students_and_missing_csrf(self):
        from core.models import ClassMember

        outsider = User.objects.create_user(
            username="outside", email="outside@example.com", password="Outside!2026"
        )
        client = APIClient()
        for membership in [None, "pending", "approved"]:
            if membership:
                ClassMember.objects.update_or_create(
                    cohort_id=self.cohort["id"],
                    user=outsider,
                    defaults={"role": "coTeacher", "approved": membership == "approved"},
                )
            client.force_login(outsider)
            self.assertEqual(client.get(self.roster_url).status_code, 404)
            self.assertEqual(
                client.post(self.roster_url, {"text": "1\t小明\t00001"}).status_code, 404
            )
        client.logout()
        self.assertEqual(client.get(self.roster_url).status_code, 403)
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(
            protected.post(self.roster_url, {"text": "1\t小明\t00001"}).status_code, 403
        )
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.post(
                self.roster_url, {"text": "1\t小明\t00001"}, HTTP_X_CSRFTOKEN=token
            ).status_code,
            200,
        )
        student = APIClient(enforce_csrf_checks=True)
        credentials = {
            "class_code": self.cohort["student_login_code"],
            "student_number": "00001",
            "password": "00001",
        }
        self.assertEqual(student.post("/api/student/login/", credentials).status_code, 403)
        token = student.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            student.post("/api/student/login/", credentials, HTTP_X_CSRFTOKEN=token).status_code,
            200,
        )
        self.assertEqual(
            student.post(
                "/api/student/change-password/", {"password": "Summer!Garden2026"}
            ).status_code,
            403,
        )
        token = student.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            student.post(
                "/api/student/change-password/",
                {"password": "Summer!Garden2026"},
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            200,
        )

    def test_import_validates_limits_original_lines_and_conflicts_without_overwrite(self):
        for text in [
            "\n\t\n",
            "座號\t姓名\t學號",
            "x" * 100001,
            "\n".join(f"{i}\t學生\t{i}" for i in range(1, 202)),
        ]:
            self.assertEqual(self.client.post(self.roster_url, {"text": text}).status_code, 400)
        text = (
            "\n座號\t姓名\t學號\n\n1\t 林 小明 \tAb001\n1\t林 小明\tAb001\n2\t不同\tAb001\n1\t另一位\tab001\n0\t錯誤\tzero\n10000\t錯誤\tlarge\n2\t錯誤\twhite space\n2\t"
            + "名" * 81
            + "\tlong\n2\t錯誤\t"
            + "a" * 65
            + "\n2\t小美\tab001"
        )
        result = self.client.post(self.roster_url, {"text": text}).json()
        self.assertEqual(result["summary"], {"created": 2, "skipped": 1, "error": 7})
        self.assertEqual([row["line"] for row in result["results"]], list(range(4, 14)))
        roster = self.client.get(self.roster_url).json()
        self.assertEqual(
            [(s["name"], s["student_number"]) for s in roster],
            [("林 小明", "Ab001"), ("小美", "ab001")],
        )
        code = self.cohort["student_login_code"]
        changed = self.client.patch(
            f"/api/classes/{self.cohort['id']}/",
            {"student_login_code": "AAAAAAAAAA", "name": "新班名"},
        ).json()
        self.assertEqual(changed["student_login_code"], code)

    def test_same_number_in_two_classes_has_independent_password_and_account_throttle(self):
        self.client.post(self.roster_url, {"text": "1\t小明\t00001"})
        other = self.client.post(
            "/api/classes/", {"name": "另一班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.assertNotEqual(other["student_login_code"], self.cohort["student_login_code"])
        self.client.post(f"/api/classes/{other['id']}/students/", {"text": "1\t小華\t00001"})
        student = self.student_login()
        self.assertEqual(
            student.post(
                "/api/student/change-password/", {"password": "Distinct!Garden2026"}
            ).status_code,
            200,
        )
        second = self.student_login(other)
        self.assertEqual(
            second.post(
                "/api/student/change-password/", {"password": "Other!Garden2026"}
            ).status_code,
            200,
        )
        self.assertEqual(
            second.get(
                "/api/student/me/?student_number=00001&class_id=" + str(self.cohort["id"])
            ).json()["name"],
            "小華",
        )
        self.assertEqual(student.get(f"/api/classes/{other['id']}/").status_code, 403)
        attacker = APIClient()
        payload = {
            "class_code": self.cohort["student_login_code"],
            "student_number": "00001",
            "password": "wrong",
        }
        for i in range(4):
            self.assertEqual(
                attacker.post(
                    "/api/student/login/", payload, REMOTE_ADDR=f"192.0.2.{i}"
                ).status_code,
                400,
            )
        self.assertEqual(
            attacker.post("/api/student/login/", payload, REMOTE_ADDR="192.0.2.20").status_code, 429
        )
        self.assertEqual(
            self.student_login(other, "Other!Garden2026").get("/api/student/me/").json()["name"],
            "小華",
        )

    def test_student_login_ip_throttle_covers_invalid_requests(self):
        anonymous = APIClient()
        for _ in range(30):
            self.assertEqual(anonymous.post("/api/student/login/", {}).status_code, 400)
        self.assertEqual(anonymous.post("/api/student/login/", {}).status_code, 429)

    def test_delete_class_erases_student_accounts_events_and_sessions_only_for_that_class(self):
        self.client.post(self.roster_url, {"text": "1\t小明\t00001"}, format="json")
        kept = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.client.post(
            f"/api/classes/{kept['id']}/students/", {"text": "1\t小華\t00001"}, format="json"
        )
        removed_login = self.student_login()
        kept_login = self.student_login(kept)
        session_key = removed_login.cookies["sessionid"].value
        Student = apps.get_model("core", "Student")
        student_id = Student.objects.get(cohort_id=self.cohort["id"]).pk
        user_id = Student.objects.get(pk=student_id).user_id
        response = self.client.delete(
            f"/api/classes/{self.cohort['id']}/", {"confirmation_name": "向日葵班"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Student.objects.filter(pk=student_id).exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(
            apps.get_model("core", "StudentCreatedEvent")
            .objects.filter(student_id=student_id)
            .exists()
        )
        self.assertFalse(
            apps.get_model("sessions", "Session").objects.filter(session_key=session_key).exists()
        )
        self.assertEqual(removed_login.get("/api/auth/me/").status_code, 403)
        self.assertEqual(kept_login.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(Student.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(
            APIClient()
            .post(
                "/api/student/login/",
                {
                    "class_code": self.cohort["student_login_code"],
                    "student_number": "00001",
                    "password": "00001",
                },
            )
            .status_code,
            400,
        )

    def setUp(self):
        self.owner = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="Teacher!Ready2026",
            display_name="林老師",
            email_verified=True,
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "向日葵班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.roster_url = f"/api/classes/{self.cohort['id']}/students/"

    def test_import_partial_success_replay_conflicts_and_seat_order(self):
        rows = [f"{i}\t學生{i}\t{i:05}" for i in range(1, 29)]
        text = "座號\t姓名\t學號\n\n" + "\n".join(reversed(rows)) + "\n29\t缺學號\n30\t衝突\t00001"
        response = self.client.post(self.roster_url, {"text": text}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], {"created": 28, "skipped": 0, "error": 2})
        self.assertEqual(response.json()["results"][-2]["line"], 31)
        roster = self.client.get(self.roster_url).json()
        self.assertEqual([s["seat_number"] for s in roster], list(range(1, 29)))
        self.assertEqual(roster[0]["student_number"], "00001")
        self.assertTrue(all(s["avatar"] in ("cat", "dog", "rabbit") for s in roster))
        replay = self.client.post(self.roster_url, {"text": text}, format="json").json()
        self.assertEqual(replay["summary"], {"created": 0, "skipped": 28, "error": 2})
        self.assertEqual(self.client.get(self.roster_url).json(), roster)
        fixed = self.client.post(
            self.roster_url, {"text": "29\t學生29\t00029\n30\t學生30\t00030"}, format="json"
        )
        self.assertEqual(fixed.json()["summary"], {"created": 2, "skipped": 0, "error": 0})
        self.assertEqual(len(self.client.get(self.roster_url).json()), 30)

    def student_login(self, cohort=None, password="00001"):
        client = APIClient()
        response = client.post(
            "/api/student/login/",
            {
                "class_code": (cohort or self.cohort)["student_login_code"].lower(),
                "student_number": "00001",
                "password": password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        return client

    def test_student_must_change_password_then_sees_only_self_with_persistent_avatar(self):
        self.client.post(self.roster_url, {"text": "1\t小明\t00001\n2\t小美\t00002"}, format="json")
        student = self.student_login()
        other_session = self.student_login()
        self.assertEqual(
            student.get("/api/auth/me/").json(),
            {"account_type": "student", "must_change_password": True},
        )
        self.assertEqual(student.get("/api/student/me/").status_code, 403)
        self.assertEqual(student.get(self.roster_url).status_code, 403)
        self.assertEqual(student.get("/api/classes/").status_code, 403)
        for password in ["00001", "short", "12345678901", "password123"]:
            response = student.post(
                "/api/student/change-password/", {"password": password}, format="json"
            )
            self.assertEqual(response.status_code, 400)
        response = student.post(
            "/api/student/change-password/", {"password": "Sunshine!New2026"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        profile = student.get("/api/student/me/").json()
        self.assertEqual(profile["name"], "小明")
        self.assertEqual(profile["cohort"]["name"], "向日葵班")
        self.assertNotIn("小美", str(profile))
        self.assertEqual(other_session.get("/api/student/me/").status_code, 403)
        self.assertEqual(student.get(self.roster_url).status_code, 403)
        self.assertEqual(
            student.post(
                "/api/classes/", {"name": "越權", "entry_year": 2026, "current_grade": 1}
            ).status_code,
            403,
        )
        self.client.post(self.roster_url, {"text": "1\t小明\t00001"}, format="json")
        student.post("/api/auth/logout/")
        self.assertEqual(
            student.post(
                "/api/student/login/",
                {
                    "class_code": self.cohort["student_login_code"],
                    "student_number": "00001",
                    "password": "00001",
                },
                format="json",
            ).status_code,
            400,
        )
        returning = self.student_login(password="Sunshine!New2026")
        self.assertEqual(returning.get("/api/student/me/").json(), profile)
        self.assertEqual(self.client.get("/api/student/me/").status_code, 403)
