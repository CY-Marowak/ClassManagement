import re

from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, Cohort, User


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

    def test_delete_requires_exact_current_name_without_changing_data_on_error(self):
        owner = self.teacher("owner@example.com")
        cohort = owner.post(
            "/api/classes/", {"name": "舊班名", "entry_year": 2026, "current_grade": 1}
        ).json()
        url = f"/api/classes/{cohort['id']}/"
        self.assertEqual(owner.patch(url, {"name": "新班名"}, format="json").status_code, 200)
        for payload in (
            {},
            {"confirmation_name": None},
            {"confirmation_name": ""},
            {"confirmation_name": "舊班名"},
            {"confirmation_name": "新班名 "},
            {"confirmation_name": ["新班名"]},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(owner.delete(url, payload, format="json").status_code, 400)
                self.assertEqual(owner.get(url).json()["name"], "新班名")
                self.assertEqual(ClassMember.objects.filter(cohort_id=cohort["id"]).count(), 1)
        self.assertEqual(
            owner.delete(url, {"confirmation_name": "新班名"}, format="json").status_code, 200
        )

    def test_delete_rejects_anonymous_strangers_co_teachers_and_unapproved_homeroom(self):
        owner = self.teacher("owner@example.com")
        other = self.teacher("other@example.com")
        cohort = owner.post(
            "/api/classes/", {"name": "受保護班級", "entry_year": 2026, "current_grade": 1}
        ).json()
        url = f"/api/classes/{cohort['id']}/"
        payload = {"confirmation_name": "受保護班級"}
        self.assertEqual(self.client.delete(url, payload, format="json").status_code, 403)
        self.assertEqual(other.delete(url, payload, format="json").status_code, 404)
        ClassMember.objects.create(
            cohort_id=cohort["id"],
            user_id=other.get("/api/auth/me/").json()["id"],
            role="coTeacher",
        )
        self.assertEqual(other.delete(url, payload, format="json").status_code, 404)
        ClassMember.objects.filter(cohort_id=cohort["id"], role="homeroom").update(approved=False)
        self.assertEqual(owner.delete(url, payload, format="json").status_code, 404)
        self.assertTrue(Cohort.objects.filter(pk=cohort["id"]).exists())
        self.assertEqual(ClassMember.objects.filter(cohort_id=cohort["id"]).count(), 2)

    def test_delete_requires_csrf_with_a_real_session(self):
        owner = self.teacher("owner@example.com")
        cohort = owner.post(
            "/api/classes/", {"name": "CSRF 班", "entry_year": 2026, "current_grade": 1}
        ).json()
        client = APIClient(enforce_csrf_checks=True)
        client.cookies = owner.cookies
        url = f"/api/classes/{cohort['id']}/"
        payload = {"confirmation_name": "CSRF 班"}
        self.assertEqual(client.delete(url, payload, format="json").status_code, 403)
        self.assertEqual(owner.get(url).status_code, 200)
        csrf = client.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            client.delete(url, payload, format="json", HTTP_X_CSRFTOKEN=csrf).status_code, 200
        )

    def test_permanent_delete_removes_cohort_and_memberships_but_keeps_teachers_and_other_class(
        self,
    ):
        owner = self.teacher("owner@example.com")
        colleague = self.teacher("colleague@example.com")
        data = {"name": "待刪班級", "entry_year": 2026, "current_grade": 1}
        removed = owner.post("/api/classes/", data).json()
        kept = owner.post("/api/classes/", {**data, "name": "保留班級"}).json()
        colleague_id = colleague.get("/api/auth/me/").json()["id"]
        ClassMember.objects.create(cohort_id=removed["id"], user_id=colleague_id, role="coTeacher")
        ClassMember.objects.create(cohort_id=kept["id"], user_id=colleague_id, role="coTeacher")
        url = f"/api/classes/{removed['id']}/"

        self.assertEqual(
            owner.delete(url, {"confirmation_name": "待刪班級"}, format="json").status_code, 200
        )

        self.assertFalse(Cohort.objects.filter(pk=removed["id"]).exists())
        self.assertFalse(ClassMember.objects.filter(cohort_id=removed["id"]).exists())
        self.assertEqual(owner.get(url).status_code, 404)
        self.assertEqual(colleague.get(url).status_code, 404)
        self.assertEqual([c["id"] for c in owner.get("/api/classes/").json()], [kept["id"]])
        self.assertEqual([c["id"] for c in colleague.get("/api/classes/").json()], [kept["id"]])
        self.assertEqual(ClassMember.objects.filter(cohort_id=kept["id"]).count(), 2)
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(owner.get("/api/auth/me/").status_code, 200)
        self.assertEqual(colleague.get("/api/auth/me/").status_code, 200)
        self.assertEqual(
            owner.delete(url, {"confirmation_name": "待刪班級"}, format="json").status_code, 404
        )
