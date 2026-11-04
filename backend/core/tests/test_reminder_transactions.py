import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import AnnouncementReminder, ClassMember, Cohort, Notification, User

from . import test_reminders


class ReminderTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_reminders.ReminderTests.setUp
    student_login = test_reminders.ReminderTests.student_login
    publish = test_reminders.ReminderTests.publish
    change = test_reminders.ReminderTests.change
    path = test_reminders.ReminderTests.path
    payload = test_reminders.ReminderTests.payload

    def test_parallel_requests_and_read_confirmation_share_the_cohort_lock(self):
        student = self.student_login()
        item = self.publish().json()
        payload = self.payload(item)

        def run(cookies, path, values, barrier):
            close_old_connections()
            try:
                client = APIClient()
                client.cookies = cookies.copy()
                barrier.wait(timeout=10)
                return client.post(path, values, format="json")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            for same_request in [True, False]:
                barrier = Barrier(2)
                futures = [
                    pool.submit(
                        run,
                        self.client.cookies,
                        self.path(item),
                        payload if same_request else self.payload(item),
                        barrier,
                    )
                    for _ in range(2)
                ]
                responses = [future.result(timeout=20) for future in futures]
                self.assertTrue(all(response.status_code in [200, 201] for response in responses))
                if same_request:
                    self.assertEqual(responses[0].json(), responses[1].json())
            self.assertEqual(AnnouncementReminder.objects.count(), 2)
            self.assertEqual(Notification.objects.filter(kind="announcement_reminder").count(), 2)
            fresh = self.publish(title="並行確認").json()
            barrier = Barrier(2)
            send = pool.submit(
                run,
                self.client.cookies,
                self.path(fresh),
                self.payload(fresh, student_id=self.students[0]["id"]),
                barrier,
            )
            read = pool.submit(
                run,
                student.cookies,
                f"/api/student/announcements/{fresh['id']}/read/",
                {"content_version": 1},
                barrier,
            )
            self.assertEqual(read.result(timeout=20).status_code, 200)
            result = send.result(timeout=20).json()
            self.assertEqual(result["sent"] + result["already_read"], 1)
            self.assertEqual(
                AnnouncementReminder.objects.filter(announcement_id=fresh["id"]).count(),
                result["sent"],
            )

    def test_waiting_sender_rechecks_read_version_permissions_and_session(self):
        student = self.student_login()

        def run(cookies, path, payload):
            close_old_connections()
            try:
                client = APIClient()
                client.cookies = cookies.copy()
                return client.post(path, payload, format="json")
            finally:
                close_old_connections()

        for action, status in [
            ("read", 201),
            ("version", 409),
            ("delete", 404),
            ("revocation", 404),
            ("password", 403),
        ]:
            self.client.force_login(User.objects.get(pk=self.owner.pk))
            ClassMember.objects.filter(cohort_id=self.cohort["id"], user=self.owner).update(
                approved=True
            )
            item = self.publish(title=action).json()
            with self.subTest(action=action), ThreadPoolExecutor(max_workers=1) as pool:
                with transaction.atomic():
                    Cohort.objects.select_for_update().get(pk=self.cohort["id"])
                    future = pool.submit(
                        run,
                        self.client.cookies,
                        self.path(item),
                        self.payload(item, student_id=self.students[0]["id"]),
                    )
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
                    if action == "read":
                        self.assertEqual(
                            student.post(
                                f"/api/student/announcements/{item['id']}/read/",
                                {"content_version": 1},
                            ).status_code,
                            200,
                        )
                    elif action == "version":
                        self.change(item, "edit", title="已變更", body=item["body"])
                    elif action == "delete":
                        self.change(item, "delete")
                    elif action == "revocation":
                        ClassMember.objects.filter(
                            cohort_id=self.cohort["id"], user=self.owner
                        ).update(approved=False)
                    else:
                        owner = User.objects.get(pk=self.owner.pk)
                        owner.set_password("Changed!Password2026")
                        owner.save(update_fields=["password"])
                response = future.result(timeout=20)
                self.assertEqual(response.status_code, status)
                if action == "read":
                    self.assertEqual(
                        (response.json()["sent"], response.json()["already_read"]), (0, 1)
                    )
                self.assertFalse(
                    AnnouncementReminder.objects.filter(announcement_id=item["id"]).exists()
                )

    def test_upgrade_preserves_notifications_without_backfilling_reminders(self):
        student = self.student_login()
        item = self.publish().json()
        before = student.get("/api/notifications/").json()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate([("core", "0026_in_app_notifications")])
        try:
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(student.get("/api/notifications/").json(), before)
            self.assertEqual(self.client.get(self.path(item)).json()["count"], 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
