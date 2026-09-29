import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Cohort, Student

from . import test_comments
from .test_announcements import document


class CommentTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_comments.CommentTests.setUp
    post_comment = test_comments.CommentTests.post_comment
    change_comment = test_comments.CommentTests.change_comment
    student_login = test_comments.CommentTests.student_login

    def parallel(self, path, payloads):
        barrier = Barrier(2)

        def run(payload):
            close_old_connections()
            try:
                client = APIClient()
                client.cookies = self.writer.cookies.copy()
                barrier.wait(timeout=10)
                return client.post(path, payload, format="json")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, p) for p in payloads]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_retries_create_once_and_competing_changes_reject_stale_version(self):
        payload = {"request_id": str(uuid.uuid4()), "body": document()}
        replies = self.parallel(self.path, [payload, payload])
        self.assertEqual(sorted(r.status_code for r in replies), [200, 201])
        self.assertEqual(replies[0].json(), replies[1].json())
        item = replies[0].json()
        replies = self.parallel(
            self.path + f"{item['id']}/",
            [
                {
                    "request_id": str(uuid.uuid4()),
                    "action": "edit",
                    "revision": 1,
                    "body": document(text),
                }
                for text in ["甲", "乙"]
            ],
        )
        self.assertEqual(sorted(r.status_code for r in replies), [200, 409])
        self.assertEqual(self.client.get(self.path).json()["count"], 1)
        self.assertEqual(self.client.get(self.path).json()["results"][0]["revision"], 2)

    def test_operation_failure_rolls_back_create_edit_and_delete(self):
        item = self.post_comment().json()
        self.writer.raise_request_exception = False
        identity = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_comment_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'comment operation write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_comment BEFORE INSERT ON core_commentoperation
                FOR EACH ROW EXECUTE FUNCTION cm_test_comment_failure();
            """)
        try:
            self.assertEqual(self.post_comment(request_id=identity).status_code, 500)
            self.assertEqual(self.change_comment(item, body=document("修改")).status_code, 500)
            self.assertEqual(self.change_comment(item, action="delete").status_code, 500)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_comment ON core_commentoperation")
                cursor.execute("DROP FUNCTION cm_test_comment_failure()")
        self.assertEqual(self.writer.get(self.path).json()["results"], [item])
        self.assertEqual(self.post_comment(request_id=identity).status_code, 201)

    def waiting_request(self, request, change):
        def run():
            close_old_connections()
            try:
                return request()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Cohort.objects.select_for_update().get(pk=self.cohort["id"])
                future = pool.submit(run)
                deadline = time.monotonic() + 10
                while True:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute(
                            "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%%core_cohort%%'"
                        )
                        if cursor.fetchone()[0]:
                            break
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.02)
                change()
            return future.result(timeout=15)

    def test_removed_teacher_waiting_to_post_is_rejected(self):
        def revoke():
            self.member.approved = False
            self.member.inactive_status = "removed"
            self.member.save()

        self.assertEqual(self.waiting_request(self.post_comment, revoke).status_code, 404)
        self.assertEqual(self.client.get(self.path).json()["count"], 0)

    def test_student_session_changed_while_waiting_cannot_read_comments(self):
        self.post_comment()
        student = self.student_login()

        def reset():
            user = Student.objects.get(pk=self.students[0]["id"]).user
            user.set_password("Replacement!Password2026")
            user.save(update_fields=["password"])

        self.assertEqual(
            self.waiting_request(lambda: student.get(self.student_path), reset).status_code, 403
        )
