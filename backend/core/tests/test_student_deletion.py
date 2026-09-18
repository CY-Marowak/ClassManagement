from django.contrib.sessions.models import Session
from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, Student, StudentAuditEvent, User


class StudentDeletionTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="delete-teacher",
            email="delete@example.com",
            display_name="導師",
            email_verified=True,
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/",
            {
                "name": "刪除測試班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        self.roster_url = f"/api/classes/{self.cohort['id']}/students/"
        self.audit_url = f"/api/classes/{self.cohort['id']}/student-events/"
        self.client.post(self.roster_url, {"text": "1\t小明\t00001\n2\t小華\t00002"})
        self.removed, self.kept = self.client.get(self.roster_url).json()
        self.url = f"{self.roster_url}{self.removed['id']}/"

    def login(self, number="00001", cohort=None):
        student = APIClient()
        self.assertEqual(
            student.post(
                "/api/student/login/",
                {
                    "class_code": (cohort or self.cohort)["student_login_code"],
                    "student_number": number,
                    "password": number,
                },
            ).status_code,
            200,
        )
        return student

    def test_delete_erases_account_all_history_and_sessions_but_keeps_other_students(self):
        self.client.patch(self.url, {"name": "改過姓名"})
        self.client.post(self.url + "reset-password/")
        sessions = [self.login(), self.login()]
        keys = [student.cookies["sessionid"].value for student in sessions]
        kept_login = self.login("00002")
        other = self.client.post(
            "/api/classes/",
            {
                "name": "其他班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        other_roster = f"/api/classes/{other['id']}/students/"
        self.client.post(other_roster, {"text": "1\t另一班學生\t00001"})
        other_login = self.login(cohort=other)
        other_before = self.client.get(other_roster).json()
        other_audit_url = f"/api/classes/{other['id']}/student-events/"
        other_history = self.client.get(other_audit_url).json()
        # Permanent deletion's agreed DB seam verifies real erasure, not just hidden API results.
        user_id = Student.objects.get(pk=self.removed["id"]).user_id
        self.assertEqual(
            self.client.delete(
                self.url,
                {
                    "confirmation_student_number": "00001",
                },
                format="json",
            ).status_code,
            200,
        )
        self.assertFalse(Student.objects.filter(pk=self.removed["id"]).exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(StudentAuditEvent.objects.filter(student_id=self.removed["id"]).exists())
        self.assertFalse(Session.objects.filter(session_key__in=keys).exists())
        self.assertEqual(self.client.get(self.roster_url).json(), [self.kept])
        history = self.client.get(self.audit_url).json()["results"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["student_id"], self.kept["id"])
        for student in sessions:
            self.assertEqual(student.get("/api/auth/me/").status_code, 403)
            self.assertEqual(
                student.post(
                    "/api/student/change-password/",
                    {
                        "password": "Garden!Meadow2026",
                    },
                ).status_code,
                403,
            )
        for client in [kept_login, other_login, self.client]:
            self.assertEqual(client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.client.get(other_roster).json(), other_before)
        self.assertEqual(self.client.get(other_audit_url).json(), other_history)
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
        self.assertEqual(
            self.client.delete(
                self.url,
                {
                    "confirmation_student_number": "00001",
                },
                format="json",
            ).status_code,
            404,
        )
        self.client.post(self.roster_url, {"text": "1\t小明\t00001"})
        recreated = self.client.get(self.roster_url).json()[0]
        self.assertNotEqual(recreated["id"], self.removed["id"])
        self.assertEqual(self.client.get(self.audit_url).json()["count"], 2)
        self.assertEqual(sessions[0].get("/api/auth/me/").status_code, 403)

    def test_confirmation_must_match_current_full_student_number(self):
        before = self.client.get(self.roster_url).json()
        history = self.client.get(self.audit_url).json()
        for payload in [
            {},
            {"confirmation_student_number": ""},
            {"confirmation_student_number": "1"},
            {"confirmation_student_number": "小明"},
            {"confirmation_student_number": "00001 "},
            {"confirmation_student_number": "00002"},
        ]:
            self.assertEqual(self.client.delete(self.url, payload, format="json").status_code, 400)
            self.assertEqual(self.client.get(self.roster_url).json(), before)
            self.assertEqual(self.client.get(self.audit_url).json(), history)
        self.client.patch(self.url, {"student_number": "00901"})
        self.assertEqual(
            self.client.delete(
                self.url,
                {
                    "confirmation_student_number": "00001",
                },
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.delete(
                self.url,
                {
                    "confirmation_student_number": "00901",
                },
                format="json",
            ).status_code,
            200,
        )

    def test_delete_rejects_unauthorized_roles_cross_class_and_missing_csrf(self):
        outsider = User.objects.create_user(username="outside", email="outside@example.com")
        teacher = APIClient()
        teacher.force_login(outsider)
        payload = {"confirmation_student_number": "00001"}
        before = self.client.get(self.roster_url).json()
        for approved in [None, False, True]:
            if approved is not None:
                ClassMember.objects.update_or_create(
                    cohort_id=self.cohort["id"],
                    user=outsider,
                    defaults={"role": "coTeacher", "approved": approved},
                )
            self.assertEqual(teacher.delete(self.url, payload, format="json").status_code, 404)
        membership = ClassMember.objects.get(cohort_id=self.cohort["id"], user=self.owner)
        membership.approved = False
        membership.save(update_fields=["approved"])
        self.assertEqual(self.client.delete(self.url, payload, format="json").status_code, 404)
        membership.approved = True
        membership.save(update_fields=["approved"])
        for client in [APIClient(), self.login()]:
            self.assertEqual(client.delete(self.url, payload, format="json").status_code, 403)
        other = self.client.post(
            "/api/classes/",
            {
                "name": "自己的另一班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        self.assertEqual(
            self.client.delete(
                f"/api/classes/{other['id']}/students/{self.removed['id']}/", payload, format="json"
            ).status_code,
            404,
        )
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(protected.delete(self.url, payload, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.roster_url).json(), before)
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.delete(self.url, payload, format="json", HTTP_X_CSRFTOKEN=token).status_code,
            200,
        )
