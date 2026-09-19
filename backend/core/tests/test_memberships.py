from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, Cohort, TeacherAuditEvent, User

from . import test_classes


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MembershipTests(APITestCase):
    teacher = test_classes.CohortTests.teacher

    def setUp(self):
        self.owner = self.teacher("owner@example.com")
        self.applicant = self.teacher("applicant@example.com")
        self.cohort = self.owner.post(
            "/api/classes/", {"name": "共同班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{self.cohort['id']}/"

    def code(self):
        response = self.owner.get(self.base + "teachers/")
        self.assertEqual(response.status_code, 200)
        return response.json()["application_code"]

    def apply(self, client=None, code=None):
        return (client or self.applicant).post(
            "/api/teacher-applications/", {"application_code": code or self.code()}, format="json"
        )

    def test_pending_application_is_private_and_duplicate_does_not_create_another(self):
        code = self.code()
        self.assertNotEqual(code, self.cohort["student_login_code"])
        response = self.apply(code=code)
        self.assertEqual(response.status_code, 201)
        application = response.json()
        self.assertEqual(set(application), {"id", "cohort_name", "homeroom_name", "status"})
        self.assertEqual(application["cohort_name"], "共同班")
        self.assertEqual(application["homeroom_name"], "林老師")
        self.assertEqual(application["status"], "pending")
        self.assertEqual(self.apply(code=code).json(), application)
        self.assertEqual(self.applicant.get("/api/teacher-applications/").json(), [application])
        self.assertEqual(self.applicant.get("/api/classes/").json(), [])
        for suffix in ("", "students/", "teachers/", "teacher-events/"):
            self.assertEqual(self.applicant.get(self.base + suffix).status_code, 404)
        self.assertEqual(
            self.owner.get(self.base + "teachers/").json()["members"][0]["status"], "pending"
        )

    def decide(self, member, action, client=None):
        return (client or self.owner).post(
            self.base + f"teachers/{member['id']}/",
            {"action": action, "revision": member["revision"]},
        )

    def member(self):
        return self.owner.get(self.base + "teachers/").json()["members"][0]

    def events(self):
        response = self.owner.get(self.base + "teacher-events/")
        self.assertEqual(response.status_code, 200)
        return response.json()["results"]

    def test_approval_removal_and_reapplication_require_fresh_review_and_preserve_history(self):
        application = self.apply().json()
        pending = self.member()
        self.assertEqual(self.decide(pending, "approve").status_code, 200)
        self.assertEqual(self.applicant.get(self.base).status_code, 200)
        approved = self.member()
        self.assertEqual(self.apply().json()["status"], "approved")
        self.assertEqual(self.decide(approved, "remove").status_code, 200)
        self.assertEqual(self.applicant.get(self.base).status_code, 404)
        self.assertEqual(self.applicant.get("/api/classes/").json(), [])
        self.assertEqual(self.applicant.get("/api/auth/me/").status_code, 200)
        self.assertEqual(self.decide(pending, "approve").status_code, 400)
        reapplied = self.apply().json()
        self.assertEqual(reapplied["id"], application["id"])
        self.assertEqual(reapplied["status"], "pending")
        self.assertEqual(self.decide(pending, "approve").status_code, 400)
        self.assertEqual(self.applicant.get(self.base).status_code, 404)
        self.assertEqual(self.decide(self.member(), "approve").status_code, 200)
        events = self.events()
        self.assertEqual(
            [e["action"] for e in events], ["approved", "applied", "removed", "approved", "applied"]
        )
        removed = events[2]
        self.assertEqual(removed["before"], {"status": "approved"})
        self.assertEqual(removed["after"], {"status": "removed"})
        self.assertEqual(removed["teacher_name"], "林老師")
        self.assertTrue(removed["actor_id"])
        self.assertTrue(removed["created_at"])

    def test_rotation_preserves_pending_and_student_code_but_invalidates_old_teacher_code(self):
        old = self.code()
        application = self.apply(code=old).json()
        response = self.owner.post(self.base + "teacher-code/", {"application_code": old})
        self.assertEqual(response.status_code, 200)
        new = response.json()["application_code"]
        self.assertNotEqual(new, old)
        self.assertEqual(self.code(), new)
        self.assertEqual(self.apply(code=old).status_code, 404)
        self.assertEqual(self.applicant.get("/api/teacher-applications/").json(), [application])
        self.assertEqual(
            self.owner.get(self.base).json()["student_login_code"],
            self.cohort["student_login_code"],
        )
        self.assertEqual(self.apply(code=new).json(), application)
        self.assertEqual(
            self.owner.post(self.base + "teacher-code/", {"application_code": old}).status_code, 400
        )
        self.assertEqual([e["action"] for e in self.events()], ["code_rotated", "applied"])
        self.assertNotIn(new, str(self.events()))
        self.assertNotIn(old, str(self.events()))

    def test_rejection_can_be_reapplied_and_own_class_cannot_be_demoted(self):
        self.apply()
        self.assertEqual(self.decide(self.member(), "reject").status_code, 200)
        self.assertEqual(
            self.applicant.get("/api/teacher-applications/").json()[0]["status"], "rejected"
        )
        self.assertEqual(self.apply().json()["status"], "pending")
        self.assertEqual(self.apply(client=self.owner).json()["status"], "approved")
        homeroom = ClassMember.objects.get(cohort_id=self.cohort["id"], role="homeroom")
        self.assertEqual(self.decide({"id": homeroom.pk, "revision": 1}, "remove").status_code, 404)
        self.assertEqual(self.owner.get(self.base).json()["role"], "homeroom")

    def test_only_verified_teachers_can_apply_and_student_code_is_not_an_application_code(self):
        code = self.code()
        unverified = self.teacher("unverified@example.com", verify=False)
        student = APIClient()
        self.owner.post(self.base + "students/", {"text": "1\t小明\t00001"})
        student.post(
            "/api/student/login/",
            {
                "class_code": self.cohort["student_login_code"],
                "student_number": "00001",
                "password": "00001",
            },
        )
        for client in (self.client, unverified, student):
            self.assertEqual(self.apply(client=client, code=code).status_code, 403)
        for invalid in (self.cohort["student_login_code"], "T-0000000000000000", [code]):
            self.assertIn(self.apply(code=invalid).status_code, [400, 404])
        self.assertEqual(self.applicant.get("/api/teacher-applications/").json(), [])

    def test_management_is_homeroom_only_even_after_approval_and_across_classes(self):
        self.apply()
        other = self.teacher("other@example.com")
        self.assertEqual(self.decide(self.member(), "approve").status_code, 200)
        approved = self.member()
        for client, expected in ((self.client, 403), (other, 404), (self.applicant, 404)):
            for suffix in ("teachers/", "teacher-events/", "students/", "student-events/"):
                self.assertEqual(client.get(self.base + suffix).status_code, expected)
            self.assertEqual(self.decide(approved, "remove", client).status_code, expected)
            self.assertEqual(
                client.post(
                    self.base + "teacher-code/", {"application_code": self.code()}
                ).status_code,
                expected,
            )
        other_class = other.post(
            "/api/classes/", {"name": "隔壁班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.assertEqual(
            other.post(
                f"/api/classes/{other_class['id']}/teachers/{approved['id']}/",
                {"action": "remove", "revision": approved["revision"]},
            ).status_code,
            404,
        )
        self.assertEqual(self.applicant.get(self.base).status_code, 200)

    def test_mutations_require_csrf_for_real_sessions(self):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies = self.applicant.cookies
        payload = {"application_code": self.code()}
        self.assertEqual(client.post("/api/teacher-applications/", payload).status_code, 403)
        token = client.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            client.post("/api/teacher-applications/", payload, HTTP_X_CSRFTOKEN=token).status_code,
            201,
        )
        client.cookies = self.owner.cookies
        member = self.member()
        self.assertEqual(self.decide(member, "approve", client).status_code, 403)
        self.assertEqual(client.post(self.base + "teacher-code/", payload).status_code, 403)

    def test_removal_preserves_other_class_and_audit_names_are_snapshots(self):
        self.apply()
        self.decide(self.member(), "approve")
        other = self.applicant.post(
            "/api/classes/", {"name": "自己的班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.decide(self.member(), "remove")
        User.objects.filter(email="applicant@example.com").update(display_name="新姓名")
        self.assertEqual(self.events()[0]["teacher_name"], "林老師")
        self.assertEqual(
            [c["id"] for c in self.applicant.get("/api/classes/").json()], [other["id"]]
        )
        self.assertEqual(self.applicant.get(self.base).status_code, 404)
        self.assertEqual(self.applicant.get(self.base + "students/").status_code, 404)

    def test_permanent_class_deletion_removes_applications_and_events_preserving_other_class(self):
        self.apply()
        kept = self.owner.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        kept_base = f"/api/classes/{kept['id']}/"
        kept_code = self.owner.get(kept_base + "teachers/").json()["application_code"]
        self.apply(code=kept_code)
        self.assertEqual(
            self.owner.delete(
                self.base, {"confirmation_name": "共同班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(Cohort.objects.filter(pk=self.cohort["id"]).exists())
        self.assertFalse(ClassMember.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertFalse(TeacherAuditEvent.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertEqual(self.owner.get(kept_base + "teacher-events/").json()["count"], 1)
        self.assertEqual(len(self.applicant.get("/api/teacher-applications/").json()), 1)
        self.assertEqual(User.objects.filter(account_type="teacher").count(), 2)
        self.assertEqual(self.applicant.get("/api/auth/me/").status_code, 200)
