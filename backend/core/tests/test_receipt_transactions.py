import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Cohort, Student

from . import test_announcements, test_scores


class ReceiptTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish
    change = test_announcements.AnnouncementTests.change

    def test_parallel_confirmation_is_one_receipt_and_edit_race_never_confirms_new_version(self):
        student = self.student_login()
        item = self.publish().json()
        path = f"/api/student/announcements/{item['id']}/read/"

        def parallel(requests):
            barrier = Barrier(2)

            def run(cookies, url, payload):
                close_old_connections()
                try:
                    client = APIClient()
                    client.cookies = cookies.copy()
                    barrier.wait(timeout=10)
                    return client.post(url, payload, format="json")
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, *args) for args in requests]
                return [future.result(timeout=20) for future in futures]

        responses = parallel([(student.cookies, path, {"content_version": 1})] * 2)
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        responses = parallel(
            [
                (student.cookies, path, {"content_version": 1}),
                (
                    self.client.cookies,
                    self.base + f"announcements/{item['id']}/",
                    {
                        "action": "edit",
                        "revision": 1,
                        "title": "新版",
                        "body": item["body"],
                        "request_id": str(uuid.uuid4()),
                    },
                ),
            ]
        )
        self.assertIn(responses[0].status_code, [200, 409])
        self.assertEqual(responses[1].status_code, 200)
        roster = self.client.get(self.base + f"announcements/{item['id']}/read-receipts/").json()
        self.assertEqual(roster["content_version"], 2)
        self.assertEqual(roster["read_count"], 0)

    def test_waiting_confirmation_rechecks_password_reset_and_content_version(self):
        student = self.student_login()
        item = self.publish().json()
        path = f"/api/student/announcements/{item['id']}/read/"

        def confirm():
            close_old_connections()
            try:
                return student.post(path, {"content_version": 1})
            finally:
                close_old_connections()

        for change in ["content", "password"]:
            with self.subTest(change=change), ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    Cohort.objects.select_for_update().get(pk=self.cohort["id"])
                    future = pool.submit(confirm)
                    deadline = time.monotonic() + 10
                    while True:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_stat_clear_snapshot()")
                            cursor.execute(
                                "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND query LIKE '%%core_cohort%%'"
                            )
                            if cursor.fetchone()[0]:
                                break
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.02)
                    if change == "content":
                        self.assertEqual(
                            self.change(
                                item, "edit", title="新內容", body=item["body"]
                            ).status_code,
                            200,
                        )
                    else:
                        user = Student.objects.get(pk=self.students[0]["id"]).user
                        user.set_password("Replacement!Password2026")
                        user.save(update_fields=["password"])
                self.assertEqual(
                    future.result(timeout=15).status_code, 409 if change == "content" else 403
                )
        self.assertEqual(
            self.client.get(self.base + f"announcements/{item['id']}/read-receipts/").json()[
                "read_count"
            ],
            0,
        )
