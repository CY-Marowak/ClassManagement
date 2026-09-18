from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Student, StudentAuditEvent, User


class StudentTransactionTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="transaction-teacher",
            email="transactions@example.com",
            password="Teacher!Ready2026",
            email_verified=True,
        )
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "交易測試班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.url = f"/api/classes/{self.cohort['id']}/students/"

    def parallel(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                client = APIClient()
                client.force_login(self.owner)
                barrier.wait(timeout=10)
                return operation(client)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, operation) for operation in operations]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_replay_creates_one_set_of_students(self):
        def upload(client):
            return client.post(self.url, {"text": "1\t小明\t00001\n2\t小華\t00002"})

        responses = self.parallel(upload, upload)
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(sorted(r.json()["summary"]["created"] for r in responses), [0, 2])
        self.assertEqual(sorted(r.json()["summary"]["skipped"] for r in responses), [0, 2])
        self.assertEqual(len(self.client.get(self.url).json()), 2)

    def test_concurrent_corrections_cannot_claim_the_same_seat(self):
        self.client.post(self.url, {"text": "1\t小明\t00001\n2\t小華\t00002"})
        first, second = self.client.get(self.url).json()
        responses = self.parallel(
            lambda client: client.patch(f"{self.url}{first['id']}/", {"seat_number": 3}),
            lambda client: client.patch(f"{self.url}{second['id']}/", {"seat_number": 3}),
        )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 400])
        self.assertEqual(sum(s["seat_number"] == 3 for s in self.client.get(self.url).json()), 1)
        events = self.client.get(f"/api/classes/{self.cohort['id']}/student-events/").json()
        self.assertEqual(events["count"], 3)

    def test_reset_racing_delete_cannot_leave_audit_or_account(self):
        self.client.post(self.url, {"text": "1\t小明\t00001"})
        student = self.client.get(self.url).json()[0]
        responses = self.parallel(
            lambda client: client.post(f"{self.url}{student['id']}/reset-password/"),
            lambda client: client.delete(
                f"/api/classes/{self.cohort['id']}/",
                {"confirmation_name": "交易測試班"},
                format="json",
            ),
        )
        self.assertIn(responses[0].status_code, [200, 404])
        self.assertEqual(responses[1].status_code, 200)
        self.assertFalse(StudentAuditEvent.objects.exists())
        self.assertFalse(User.objects.filter(account_type="student").exists())

    def test_audit_write_failure_rolls_back_profile_password_and_session_revocation(self):
        self.client.post(self.url, {"text": "1\t小明\t00001"})
        original = self.client.get(self.url).json()
        endpoint = f"{self.url}{original[0]['id']}/"
        audit_url = f"/api/classes/{self.cohort['id']}/student-events/"
        original_events = self.client.get(audit_url).json()
        student = APIClient()
        student.post(
            "/api/student/login/",
            {
                "class_code": self.cohort["student_login_code"],
                "student_number": "00001",
                "password": "00001",
            },
        )
        student.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_reject_management_event() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'test audit write failure';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_reject_management BEFORE INSERT ON core_studentauditevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_reject_management_event();
            """)
        self.client.raise_request_exception = False
        try:
            self.assertEqual(
                self.client.patch(
                    endpoint,
                    {
                        "name": "不應保存",
                        "seat_number": 3,
                        "student_number": "00901",
                    },
                ).status_code,
                500,
            )
            self.assertEqual(self.client.get(self.url).json(), original)
            self.assertEqual(self.client.post(endpoint + "reset-password/").status_code, 500)
            self.assertEqual(student.get("/api/student/me/").status_code, 200)
            self.assertEqual(self.client.get(audit_url).json(), original_events)
            returning = APIClient()
            self.assertEqual(
                returning.post(
                    "/api/student/login/",
                    {
                        "class_code": self.cohort["student_login_code"],
                        "student_number": "00001",
                        "password": "Garden!Meadow2026",
                    },
                ).status_code,
                200,
            )
            self.assertFalse(returning.get("/api/auth/me/").json()["must_change_password"])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_reject_management ON core_studentauditevent")
                cursor.execute("DROP FUNCTION cm_test_reject_management_event()")

    def test_delete_racing_import_leaves_no_class_student_account_or_event(self):
        responses = self.parallel(
            lambda client: client.post(self.url, {"text": "1\t小明\t00001\n2\t小華\t00002"}),
            lambda client: client.delete(
                f"/api/classes/{self.cohort['id']}/",
                {"confirmation_name": "交易測試班"},
                format="json",
            ),
        )
        self.assertIn(responses[0].status_code, [200, 404])
        self.assertEqual(responses[1].status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertFalse(Student.objects.exists())
        self.assertFalse(User.objects.filter(account_type="student").exists())
        self.assertFalse(StudentAuditEvent.objects.exists())

    def test_database_failure_rolls_back_whole_import_including_created_accounts(self):
        # Inject a real database failure after an earlier row succeeded, at the DB seam.
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_reject_second_event() RETURNS trigger AS $$
                BEGIN
                    IF (SELECT seat_number FROM core_student WHERE id = NEW.student_id) = 2 THEN
                        RAISE EXCEPTION 'test database write failure';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_reject_event BEFORE INSERT ON core_studentauditevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_reject_second_event();
            """)
        self.client.raise_request_exception = False
        try:
            response = self.client.post(self.url, {"text": "1\t小明\t00001\n2\t小華\t00002"})
            self.assertEqual(response.status_code, 500)
            self.assertEqual(self.client.get(self.url).json(), [])
            self.assertFalse(User.objects.filter(account_type="student").exists())
            self.assertFalse(StudentAuditEvent.objects.exists())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_reject_event ON core_studentauditevent")
                cursor.execute("DROP FUNCTION cm_test_reject_second_event()")
