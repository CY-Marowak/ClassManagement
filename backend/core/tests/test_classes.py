import re

from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CohortTests(APITestCase):
    def teacher(self, email, verify=True):
        client = APIClient()
        client.post(
            "/api/auth/register/",
            {"email": email, "display_name": "林老師", "password": "Classroom!2026Good"},
        )
        if verify:
            token = re.search(r"token=([\w-]+)", mail.outbox[-1].body)[1]
            self.assertEqual(client.post("/api/auth/verify/", {"token": token}).status_code, 200)
        self.assertEqual(
            client.post(
                "/api/auth/login/", {"email": email, "password": "Classroom!2026Good"}
            ).status_code,
            200,
        )
        return client

    def test_verified_teacher_creates_and_updates_same_cohort_privately(self):
        data = {"name": "向日葵班", "entry_year": 2026, "current_grade": 1}
        self.assertEqual(self.client.post("/api/classes/", data).status_code, 403)
        pending = self.teacher("pending@example.com", verify=False)
        self.assertEqual(pending.post("/api/classes/", data).status_code, 403)
        owner = self.teacher("owner@example.com")
        created = owner.post("/api/classes/", data)
        self.assertEqual(created.status_code, 201)
        cohort = created.json()
        self.assertEqual(cohort["role"], "homeroom")
        url = f"/api/classes/{cohort['id']}/"
        changed = owner.patch(url, {"current_grade": 2}, format="json")
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["id"], cohort["id"])
        self.assertEqual(changed.json()["current_grade"], 2)
        self.assertEqual(len(owner.get("/api/classes/").json()), 1)
        stranger = self.teacher("other@example.com")
        self.assertEqual(stranger.get("/api/classes/").json(), [])
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(stranger.patch(url, {"name": "別班"}, format="json").status_code, 404)
        self.assertNotIn("email", cohort)
