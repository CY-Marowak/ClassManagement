import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TeacherAccountsTests(APITestCase):
    def test_csrf_required_even_before_login(self):
        client = APIClient(enforce_csrf_checks=True)
        data = {
            "email": "csrf@example.com",
            "display_name": "林老師",
            "password": "Classroom!2026Good",
        }
        self.assertEqual(client.post("/api/auth/register/", data).status_code, 403)
        csrf = client.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            client.post("/api/auth/register/", data, HTTP_X_CSRFTOKEN=csrf).status_code, 202
        )

    def test_verification_expires_and_resend_invalidates_old_link(self):
        self.client.post(
            "/api/auth/register/",
            {
                "email": "resend@example.com",
                "display_name": "老師",
                "password": "Classroom!2026Good",
            },
        )
        old = re.search(r"token=([\w-]+)", mail.outbox[-1].body)[1]
        self.client.post("/api/auth/resend-verification/", {"email": "resend@example.com"})
        current = re.search(r"token=([\w-]+)", mail.outbox[-1].body)[1]
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": old}).status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/auth/reset-password/", {"token": current, "password": "NewClassroom!2026Good"}
            ).status_code,
            400,
        )
        future = timezone.now() + timedelta(minutes=31)
        with patch("django.utils.timezone.now", return_value=future):
            self.assertEqual(
                self.client.post("/api/auth/verify/", {"token": current}).status_code, 400
            )

    def test_registration_duplicate_and_recovery_do_not_disclose_existing_email(self):
        data = {
            "email": "teacher@example.com",
            "display_name": "老師",
            "password": "Classroom!2026Good",
        }
        first = self.client.post("/api/auth/register/", data)
        data["email"] = "TEACHER@example.com"
        repeated = self.client.post("/api/auth/register/", data)
        self.assertEqual((first.status_code, first.json()), (repeated.status_code, repeated.json()))
        self.assertEqual(len(mail.outbox), 1)
        known = self.client.post("/api/auth/forgot-password/", {"email": "teacher@example.com"})
        unknown = self.client.post("/api/auth/forgot-password/", {"email": "missing@example.com"})
        self.assertEqual((known.status_code, known.json()), (unknown.status_code, unknown.json()))

    def test_teacher_registers_verifies_and_signs_in(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "teacher@example.com",
                "display_name": "林老師",
                "password": "Classroom!2026Good",
            },
        )
        self.assertEqual(response.status_code, 202)
        token = re.search(r"token=([\w-]+)", mail.outbox[-1].body)[1]
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": token}).status_code, 200)
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": "TEACHER@example.com",
                "password": "Classroom!2026Good",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").json()["display_name"], "林老師")

    def test_password_reset_is_single_use_and_revokes_old_session(self):
        self.test_teacher_registers_verifies_and_signs_in()
        from rest_framework.test import APIClient

        recovery = APIClient()
        response = recovery.post("/api/auth/forgot-password/", {"email": "teacher@example.com"})
        self.assertEqual(response.status_code, 202)
        token = re.search(r"token=([\w-]+)", mail.outbox[-1].body)[1]
        new_password = "NewClassroom!2026Better"
        payload = {"token": token, "password": new_password}
        self.assertEqual(recovery.post("/api/auth/reset-password/", payload).status_code, 200)
        self.assertEqual(recovery.post("/api/auth/reset-password/", payload).status_code, 400)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.assertEqual(
            recovery.post(
                "/api/auth/login/",
                {"email": "teacher@example.com", "password": "Classroom!2026Good"},
            ).status_code,
            400,
        )
        self.assertEqual(
            recovery.post(
                "/api/auth/login/", {"email": "teacher@example.com", "password": new_password}
            ).status_code,
            200,
        )
        self.assertEqual(recovery.post("/api/auth/logout/").status_code, 200)
        self.assertEqual(recovery.get("/api/auth/me/").status_code, 403)

    def test_login_and_recovery_are_rate_limited(self):
        for _ in range(5):
            self.assertEqual(
                self.client.post(
                    "/api/auth/login/", {"email": "absent@example.com", "password": "incorrect"}
                ).status_code,
                400,
            )
        self.assertEqual(
            self.client.post(
                "/api/auth/login/", {"email": "absent@example.com", "password": "incorrect"}
            ).status_code,
            429,
        )
        for _ in range(3):
            self.assertEqual(
                self.client.post(
                    "/api/auth/forgot-password/", {"email": "absent@example.com"}
                ).status_code,
                202,
            )
        self.assertEqual(
            self.client.post(
                "/api/auth/forgot-password/", {"email": "absent@example.com"}
            ).status_code,
            429,
        )
