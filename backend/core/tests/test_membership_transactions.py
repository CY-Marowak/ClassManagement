from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import User


class MembershipTransactionTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            display_name="導師",
            password="Teacher!Ready2026",
            email_verified=True,
        )
        self.applicant = User.objects.create_user(
            username="applicant",
            email="applicant@example.com",
            display_name="共同教師",
            password="Teacher!Ready2026",
            email_verified=True,
        )
        self.client = self.login(self.owner)
        cohort = self.client.post(
            "/api/classes/", {"name": "交易班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{cohort['id']}/"
        self.code = self.client.get(self.base + "teachers/").json()["application_code"]

    def login(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def parallel(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def apply(self):
        return self.login(self.applicant).post(
            "/api/teacher-applications/", {"application_code": self.code}
        )

    def member(self):
        return self.client.get(self.base + "teachers/").json()["members"][0]

    def test_concurrent_applications_and_reviews_do_not_duplicate_membership_or_events(self):
        applications = self.parallel(self.apply, self.apply)
        self.assertEqual(sorted(r.status_code for r in applications), [200, 201])
        self.assertEqual(applications[0].json()["id"], applications[1].json()["id"])
        member = self.member()

        def approve():
            return self.login(self.owner).post(
                self.base + f"teachers/{member['id']}/",
                {
                    "action": "approve",
                    "revision": member["revision"],
                },
            )

        reviews = self.parallel(approve, approve)
        self.assertEqual(sorted(r.status_code for r in reviews), [200, 400])
        events = self.client.get(self.base + "teacher-events/").json()
        self.assertEqual([e["action"] for e in events["results"]], ["approved", "applied"])

    def test_rotation_racing_application_has_a_consistent_cutoff(self):
        responses = self.parallel(
            self.apply,
            lambda: self.login(self.owner).post(
                self.base + "teacher-code/",
                {
                    "application_code": self.code,
                },
            ),
        )
        self.assertIn(responses[0].status_code, [201, 404])
        self.assertEqual(responses[1].status_code, 200)
        self.assertEqual(self.apply().status_code, 404)
        applications = self.login(self.applicant).get("/api/teacher-applications/").json()
        self.assertEqual(len(applications), 1 if responses[0].status_code == 201 else 0)

    def test_audit_failure_rolls_back_application_decision_and_code_rotation(self):
        applicant = self.login(self.applicant)
        applicant.raise_request_exception = False
        self.client.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_reject_teacher_event() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'test teacher audit failure';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_teacher_event BEFORE INSERT ON core_teacherauditevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_reject_teacher_event();
            """)
        try:
            self.assertEqual(
                applicant.post(
                    "/api/teacher-applications/",
                    {
                        "application_code": self.code,
                    },
                ).status_code,
                500,
            )
            self.assertEqual(applicant.get("/api/teacher-applications/").json(), [])
            self.assertEqual(
                self.client.post(
                    self.base + "teacher-code/",
                    {
                        "application_code": self.code,
                    },
                ).status_code,
                500,
            )
            self.assertEqual(
                self.client.get(self.base + "teachers/").json()["application_code"], self.code
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    "ALTER TABLE core_teacherauditevent DISABLE TRIGGER cm_test_teacher_event"
                )
            self.apply()
            member = self.member()
            with connection.cursor() as cursor:
                cursor.execute(
                    "ALTER TABLE core_teacherauditevent ENABLE TRIGGER cm_test_teacher_event"
                )
            self.assertEqual(
                self.client.post(
                    self.base + f"teachers/{member['id']}/",
                    {
                        "action": "approve",
                        "revision": member["revision"],
                    },
                ).status_code,
                500,
            )
            self.assertEqual(self.member(), member)
            self.assertEqual(applicant.get(self.base).status_code, 404)
            self.assertEqual(self.client.get(self.base + "teacher-events/").json()["count"], 1)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_teacher_event ON core_teacherauditevent")
                cursor.execute("DROP FUNCTION cm_test_reject_teacher_event()")
