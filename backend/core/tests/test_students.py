from django.apps import apps
from rest_framework.test import APIClient, APITestCase

from core.models import User


class StudentWorkflowTests(APITestCase):
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
        self.assertEqual(apps.get_model("core", "Student").objects.count(), 30)
        self.assertEqual(User.objects.filter(account_type="student").count(), 30)

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
