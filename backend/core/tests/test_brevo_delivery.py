import io
import json
import re
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(
    EMAIL_BACKEND="core.email_backend.BrevoEmailBackend",
    BREVO_API_KEY="test-key-not-real",
    DEFAULT_FROM_EMAIL="CY <sender@example.com>",
    FRONTEND_URL="https://cm.example.com",
)
class BrevoDeliveryTests(APITestCase):
    registration = {
        "email": "external@example.com",
        "display_name": "測試老師",
        "password": "Classroom!2026Good",
    }

    def setUp(self):
        self.sent = []
        transport = patch("urllib.request.urlopen", side_effect=self.accept_email)
        self.transport = transport.start()
        self.addCleanup(transport.stop)

    def accept_email(self, request, **kwargs):
        self.assertEqual(request.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(request.get_header("Api-key"), "test-key-not-real")
        self.assertEqual(kwargs["timeout"], 10)
        self.sent.append(json.loads(request.data))
        return io.BytesIO(b'{"messageId":"test-message-id"}')

    def token(self):
        body = self.sent[-1]["textContent"]
        self.assertIn("https://cm.example.com/#", body)
        return re.search(r"token=([\w-]+)", body)[1]

    def test_external_teacher_can_verify_and_reset_password(self):
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 202
        )
        self.assertEqual(self.sent[-1]["to"], [{"email": "external@example.com"}])
        self.assertEqual(self.sent[-1]["sender"], {"name": "CY", "email": "sender@example.com"})
        token = self.token()
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": token}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": token}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login/", self.registration).status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/forgot-password/", {"email": self.registration["email"]}
            ).status_code,
            202,
        )
        payload = {"token": self.token(), "password": "UpdatedClassroom!2026"}
        self.assertEqual(self.client.post("/api/auth/reset-password/", payload).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/reset-password/", payload).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login/", self.registration).status_code, 400)
        self.assertEqual(
            self.client.post(
                "/api/auth/login/", {**self.registration, "password": payload["password"]}
            ).status_code,
            200,
        )

    def test_failed_registration_is_safe_and_retryable(self):
        for failure in (
            HTTPError("https://api.brevo.com/v3/smtp/email", 429, "private", {}, None),
            TimeoutError("private"),
            IncompleteRead(b"private", 100),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.registration = {
                    **self.registration,
                    "email": f"{type(failure).__name__}@example.com",
                }
                self.transport.side_effect = failure
                response = self.client.post("/api/auth/register/", self.registration)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "目前無法寄送信件，請稍後再試。"})
        self.transport.side_effect = self.accept_email
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 202
        )
        self.assertEqual(
            self.client.post("/api/auth/verify/", {"token": self.token()}).status_code, 200
        )

    def test_invalid_acceptance_is_not_reported_as_sent(self):
        for index, body in enumerate((b"bad-json", b"{}", b"null", b'{"messageId":""}')):
            with self.subTest(body=body):
                self.registration = {**self.registration, "email": f"invalid{index}@example.com"}
                self.transport.side_effect = lambda *args, **kwargs: io.BytesIO(body)
                self.assertEqual(
                    self.client.post("/api/auth/register/", self.registration).status_code, 503
                )

    @override_settings(BREVO_API_KEY="")
    def test_missing_key_blocks_delivery(self):
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 503
        )
        self.transport.assert_not_called()

    def test_failed_resend_and_reset_preserve_previous_links(self):
        self.client.post("/api/auth/register/", self.registration)
        token = self.token()
        self.transport.side_effect = TimeoutError("private")
        self.assertEqual(
            self.client.post(
                "/api/auth/resend-verification/", {"email": self.registration["email"]}
            ).status_code,
            503,
        )
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": token}).status_code, 200)
        self.transport.side_effect = self.accept_email
        self.client.post("/api/auth/forgot-password/", {"email": self.registration["email"]})
        token = self.token()
        self.transport.side_effect = TimeoutError("private")
        self.assertEqual(
            self.client.post(
                "/api/auth/forgot-password/", {"email": self.registration["email"]}
            ).status_code,
            503,
        )
        self.assertEqual(self.client.post("/api/auth/login/", self.registration).status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/reset-password/", {"token": token, "password": "UpdatedClassroom!2026"}
            ).status_code,
            200,
        )
