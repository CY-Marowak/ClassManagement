import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import Cohort, Student

from . import test_announcements, test_scores


class NotificationTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    publish = test_announcements.AnnouncementTests.publish
    change = test_announcements.AnnouncementTests.change

    def test_parallel_publish_retry_has_one_event_and_open_retry_keeps_view_time(self):
        student = self.student_login()

        def parallel(cookies, url, values):
            barrier = Barrier(2)

            def run():
                close_old_connections()
                try:
                    client = APIClient()
                    client.cookies = cookies.copy()
                    barrier.wait(timeout=10)
                    return client.post(url, values, format="json")
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run) for _ in range(2)]
                return [future.result(timeout=20) for future in futures]

        responses = parallel(
            self.client.cookies,
            self.base + "announcements/",
            {
                "title": "同一事件",
                "body": test_announcements.document(),
                "request_id": str(uuid.uuid4()),
            },
        )
        self.assertEqual(sorted(response.status_code for response in responses), [200, 201])
        inbox = student.get("/api/notifications/").json()
        self.assertEqual((inbox["count"], inbox["unread_count"]), (1, 1))
        path = f"/api/notifications/{inbox['results'][0]['id']}/open/"
        self.assertEqual(
            [response.status_code for response in parallel(student.cookies, path, {})], [200, 200]
        )
        viewed = student.get("/api/notifications/").json()["results"][0]["viewed_at"]
        student.post(path)
        self.assertEqual(
            student.get("/api/notifications/").json()["results"][0]["viewed_at"], viewed
        )

    def test_waiting_open_rechecks_announcement_deletion_and_password_reset(self):
        student = self.student_login()

        def run(path):
            close_old_connections()
            try:
                return student.post(path)
            finally:
                close_old_connections()

        for change in ["delete", "password"]:
            item = self.publish().json()
            notice = student.get("/api/notifications/").json()["results"][0]
            path = f"/api/notifications/{notice['id']}/open/"
            with self.subTest(change=change), ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    Cohort.objects.select_for_update().get(pk=self.cohort["id"])
                    future = pool.submit(run, path)
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
                    if change == "delete":
                        self.assertEqual(self.change(item, "delete").status_code, 200)
                    else:
                        user = Student.objects.get(pk=self.students[0]["id"]).user
                        user.set_password("Replacement!Password2026")
                        user.save(update_fields=["password"])
                self.assertEqual(
                    future.result(timeout=15).status_code, 404 if change == "delete" else 403
                )

    def test_upgrade_preserves_old_announcement_and_pending_application_without_notifications(self):
        student = self.student_login()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("core", "0025_backfill_announcement_versions")]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            item = old.get_model("core", "Announcement").objects.create(
                cohort_id=self.cohort["id"],
                creator_id=self.owner.pk,
                creator_name="林老師",
                title="升級前公告",
                body=test_announcements.document(),
            )
            applicant = old.get_model("core", "User").objects.create(username="legacy-applicant")
            old.get_model("core", "ClassMember").objects.create(
                cohort_id=self.cohort["id"],
                user_id=applicant.pk,
                role="coTeacher",
                approved=False,
            )
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(student.get("/api/notifications/").json()["count"], 0)
            self.assertEqual(self.client.get("/api/notifications/").json()["count"], 0)
            self.assertEqual(
                student.get("/api/student/announcements/").json()["results"][0]["id"], item.pk
            )
            self.assertEqual(
                self.client.get(self.base + "teachers/").json()["members"][0]["status"], "pending"
            )
        finally:
            MigrationExecutor(connection).migrate(latest)
