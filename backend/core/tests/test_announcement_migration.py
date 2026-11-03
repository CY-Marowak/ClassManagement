from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from . import test_announcements, test_scores


class AnnouncementMigrationTests(TransactionTestCase):
    from rest_framework.test import APIClient

    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login

    def test_existing_announcement_upgrades_unconfirmed_and_can_be_confirmed(self):
        student = self.student_login()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old_target = [("core", "0023_six_mascot_animals")]
        executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            item = old.get_model("core", "Announcement").objects.create(
                cohort_id=self.cohort["id"],
                creator_id=self.owner.pk,
                creator_name="林老師",
                title="舊公告",
                body=test_announcements.document(),
                revision=7,
            )
            MigrationExecutor(connection).migrate(latest)
            result = student.get("/api/student/announcements/").json()["results"][0]
            self.assertEqual(result["title"], "舊公告")
            self.assertEqual(result["revision"], 7)
            self.assertEqual(result["content_version"], 1)
            self.assertIsNone(result["confirmed_at"])
            response = student.post(
                f"/api/student/announcements/{item.pk}/read/", {"content_version": 1}
            )
            self.assertEqual(response.status_code, 200)
            confirmed = response.json()
            # Re-running the backfill must not change content or erase confirmations.
            MigrationExecutor(connection).migrate([("core", "0024_announcement_read_receipts")])
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(
                student.post(
                    f"/api/student/announcements/{item.pk}/read/", {"content_version": 1}
                ).json(),
                confirmed,
            )
        finally:
            MigrationExecutor(connection).migrate(latest)
