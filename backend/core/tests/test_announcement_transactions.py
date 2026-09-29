import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Cohort, Student

from . import test_announcements, test_scores


class AnnouncementTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish

    def test_session_changed_while_waiting_for_class_lock_cannot_read(self):
        student = self.student_login()
        self.publish()

        def read():
            close_old_connections()
            try:
                return student.get("/api/student/announcements/")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Cohort.objects.select_for_update().get(pk=self.cohort["id"])
                future = pool.submit(read)
                deadline = time.monotonic() + 10
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND query LIKE '%%core_cohort%%'"
                        )
                        waiting = cursor.fetchone()[0]
                    if waiting:
                        break
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                # Simulate reset followed by successful password change while the
                # old authenticated request is already waiting on the class lock.
                user = Student.objects.get(pk=self.students[0]["id"]).user
                user.set_password("Replacement!Password2026")
                user.save(update_fields=["password"])
            self.assertEqual(future.result(timeout=15).status_code, 403)

    def test_parallel_publish_retries_and_stale_changes_are_serialized(self):
        path = self.base + "announcements/"
        identity = str(uuid.uuid4())
        payload = {"request_id": identity, "title": "公告", "body": test_announcements.document()}

        def parallel(path, payloads):
            barrier = Barrier(2)

            def run(payload):
                close_old_connections()
                try:
                    client = APIClient()
                    client.cookies = self.client.cookies.copy()
                    barrier.wait(timeout=10)
                    return client.post(path, payload, format="json")
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, p) for p in payloads]
                return [f.result(timeout=20) for f in futures]

        responses = parallel(path, [payload, payload])
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        item = responses[0].json()
        changes = [
            {
                "request_id": str(uuid.uuid4()),
                "revision": 1,
                "action": "edit",
                "title": title,
                "body": test_announcements.document(),
            }
            for title in ["甲", "乙"]
        ]
        responses = parallel(path + f"{item['id']}/", changes)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.client.get(path).json()["count"], 1)
        self.assertEqual(self.client.get(path).json()["results"][0]["revision"], 2)

    def test_operation_write_failure_rolls_back_publish_and_edit(self):
        path = self.base + "announcements/"
        item = self.publish().json()
        self.client.raise_request_exception = False
        payload = {
            "request_id": str(uuid.uuid4()),
            "title": "新公告",
            "body": test_announcements.document(),
        }
        edit = {**payload, "request_id": str(uuid.uuid4()), "action": "edit", "revision": 1}
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_announcement_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'operation write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_announcement BEFORE INSERT ON core_announcementoperation
                FOR EACH ROW EXECUTE FUNCTION cm_test_announcement_failure();
            """)
        try:
            self.assertEqual(self.client.post(path, payload, format="json").status_code, 500)
            self.assertEqual(
                self.client.post(path + f"{item['id']}/", edit, format="json").status_code, 500
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_announcement ON core_announcementoperation")
                cursor.execute("DROP FUNCTION cm_test_announcement_failure()")
        self.assertEqual(self.client.get(path).json()["results"], [item])
        self.assertEqual(self.client.post(path, payload, format="json").status_code, 201)
        self.assertEqual(
            self.client.post(path + f"{item['id']}/", edit, format="json").status_code, 200
        )
