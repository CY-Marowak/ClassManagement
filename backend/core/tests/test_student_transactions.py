from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Student, StudentCreatedEvent, User


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
        self.assertFalse(StudentCreatedEvent.objects.exists())

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
                CREATE TRIGGER cm_test_reject_event BEFORE INSERT ON core_studentcreatedevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_reject_second_event();
            """)
        self.client.raise_request_exception = False
        try:
            response = self.client.post(self.url, {"text": "1\t小明\t00001\n2\t小華\t00002"})
            self.assertEqual(response.status_code, 500)
            self.assertEqual(self.client.get(self.url).json(), [])
            self.assertFalse(User.objects.filter(account_type="student").exists())
            self.assertFalse(StudentCreatedEvent.objects.exists())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_reject_event ON core_studentcreatedevent")
                cursor.execute("DROP FUNCTION cm_test_reject_second_event()")
