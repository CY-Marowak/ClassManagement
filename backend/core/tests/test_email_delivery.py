import io
import json
import re
from datetime import timedelta
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase


@override_settings(
    EMAIL_BACKEND="core.email_backend.ResendEmailBackend",
    RESEND_API_KEY="test-key-not-real",
    DEFAULT_FROM_EMAIL="CM <onboarding@resend.dev>",
    RESEND_TEST_RECIPIENT="teacher@example.com",
    FRONTEND_URL="https://cm.example.com",
)
class EmailDeliveryTests(APITestCase):
    registration = {
        "email": "teacher@example.com",
        "display_name": "測試老師",
        "password": "Classroom!2026Good",
    }

    def setUp(self):
        self.sent = []
        self.transport = patch("urllib.request.urlopen", side_effect=self.accept_email).start()
        self.addCleanup(patch.stopall)

    def accept_email(self, request, **kwargs):
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-not-real")
        self.assertEqual(kwargs["timeout"], 10)
        self.sent.append(json.loads(request.data))
        return io.BytesIO(b'{"id":"test-message-id"}')

    def token(self):
        text = self.sent[-1]["text"]
        self.assertIn("https://cm.example.com/#", text)
        return re.search(r"token=([\w-]+)", text)[1]

    def test_registration_delivers_verification_then_reset_revokes_session(self):
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 202
        )
        self.assertEqual(self.sent[-1]["to"], ["teacher@example.com"])
        self.assertEqual(self.sent[-1]["from"], "CM <onboarding@resend.dev>")
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

    def test_failed_registration_is_retryable_without_leaking_provider_details(self):
        self.transport.side_effect = HTTPError(
            "https://api.resend.com/emails", 403, "private-provider-details", {}, None
        )
        response = self.client.post("/api/auth/register/", self.registration)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "目前無法寄送信件，請稍後再試。"})
        self.transport.side_effect = self.accept_email
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 202
        )
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(
            self.client.post("/api/auth/verify/", {"token": self.token()}).status_code, 200
        )

    def test_failed_resend_preserves_previous_verification_link(self):
        self.client.post("/api/auth/register/", self.registration)
        token = self.token()
        self.transport.side_effect = URLError("private-network-details")
        response = self.client.post(
            "/api/auth/resend-verification/", {"email": self.registration["email"]}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.post("/api/auth/verify/", {"token": token}).status_code, 200)

    def test_test_sender_never_sends_to_another_address_or_redirects_their_token(self):
        response = self.client.post(
            "/api/auth/register/", {**self.registration, "email": "another@example.com"}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.sent, [])

    @override_settings(RESEND_TEST_RECIPIENT="")
    def test_test_sender_requires_explicit_recipient(self):
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 503
        )
        self.assertEqual(self.sent, [])

    @override_settings(RESEND_API_KEY="")
    def test_missing_credentials_fail_before_network_request(self):
        self.assertEqual(
            self.client.post("/api/auth/register/", self.registration).status_code, 503
        )
        self.assertEqual(self.sent, [])

    def test_failed_reset_request_preserves_old_link_and_password(self):
        self.client.post("/api/auth/register/", self.registration)
        self.client.post("/api/auth/verify/", {"token": self.token()})
        self.client.post("/api/auth/forgot-password/", {"email": self.registration["email"]})
        token = self.token()
        self.transport.side_effect = TimeoutError("private-timeout-details")
        self.assertEqual(
            self.client.post(
                "/api/auth/forgot-password/", {"email": self.registration["email"]}
            ).status_code,
            503,
        )
        self.assertEqual(self.client.post("/api/auth/login/", self.registration).status_code, 200)
        payload = {"token": token, "password": "UpdatedClassroom!2026"}
        self.assertEqual(self.client.post("/api/auth/reset-password/", payload).status_code, 200)

    def test_reset_link_expires_after_thirty_minutes(self):
        self.client.post("/api/auth/register/", self.registration)
        self.client.post("/api/auth/forgot-password/", {"email": self.registration["email"]})
        token = self.token()
        future = timezone.now() + timedelta(minutes=31)
        with patch("django.utils.timezone.now", return_value=future):
            response = self.client.post(
                "/api/auth/reset-password/", {"token": token, "password": "UpdatedClassroom!2026"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login/", self.registration).status_code, 200)

    def test_invalid_provider_response_is_not_reported_as_sent(self):
        for body in (b"not-json", b"{}", b"null"):
            with self.subTest(body=body):
                self.transport.side_effect = lambda *args, **kwargs: io.BytesIO(body)
                response = self.client.post("/api/auth/register/", self.registration)
                self.assertEqual(response.status_code, 503)

    def test_truncated_provider_response_returns_safe_retryable_error(self):
        self.transport.side_effect = IncompleteRead(b"private-response-fragment", 100)
        response = self.client.post("/api/auth/register/", self.registration)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "目前無法寄送信件，請稍後再試。"})

    @override_settings(
        DEFAULT_FROM_EMAIL="CM <hello@verified.example.com>", RESEND_TEST_RECIPIENT=""
    )
    def test_verified_sender_can_deliver_to_requested_recipient(self):
        response = self.client.post(
            "/api/auth/register/", {**self.registration, "email": "another@example.com"}
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.sent[-1]["to"], ["another@example.com"])
