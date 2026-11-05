import importlib
import uuid

from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from .test_announcements import document


class V2UpgradeTests(TransactionTestCase):
    def test_v1_business_rows_survive_full_upgrade_and_backfills_are_repeatable(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("core", "0019_import_issue_draft")]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            models = {
                name: old.get_model("core", name)
                for name in (
                    "User",
                    "Cohort",
                    "ClassMember",
                    "Student",
                    "Mascot",
                    "ScoreRecord",
                    "PointAwardBatch",
                    "PointTransaction",
                    "Announcement",
                    "AnnouncementComment",
                )
            }
            teacher = models["User"].objects.create(
                username="upgrade-teacher",
                account_type="teacher",
                email_verified=True,
                password=make_password("Upgrade!Teacher2026"),
            )
            cohort = models["Cohort"].objects.create(
                name="v1保留班", entry_year=2026, current_grade=2
            )
            models["ClassMember"].objects.create(
                cohort=cohort, user=teacher, role="homeroom", approved=True
            )
            user = models["User"].objects.create(
                username="upgrade-student",
                account_type="student",
                password=make_password("Upgrade!Student2026"),
            )
            student = models["Student"].objects.create(
                cohort=cohort,
                user=user,
                student_number="001",
                seat_number=1,
                avatar="rabbit",
                must_change_password=False,
                point_balance=23,
                behavior_score_total=4,
            )
            models["Mascot"].objects.create(cohort=cohort, animal="dog", exp=2)
            record = models["ScoreRecord"].objects.create(
                cohort=cohort,
                student=student,
                creator=teacher,
                creator_name="舊老師",
                kind="positive",
                score=4,
                template="helping",
                reason="協助同學",
            )
            batch = models["PointAwardBatch"].objects.create(
                cohort=cohort,
                actor=teacher,
                actor_name="舊老師",
                request_id=uuid.uuid4(),
                request_fingerprint="old",
                item_count=1,
            )
            models["PointTransaction"].objects.create(
                student=student, kind="award", batch=batch, record=record, points=25
            )
            models["PointTransaction"].objects.create(
                student=student, kind="feed", request_id=uuid.uuid4(), points=-2
            )
            item = models["Announcement"].objects.create(
                cohort=cohort,
                creator=teacher,
                creator_name="舊老師",
                title="舊公告",
                body=document("舊內文"),
                revision=7,
            )
            models["AnnouncementComment"].objects.create(
                announcement=item, creator=teacher, creator_name="舊老師", body=document("舊留言")
            )
            snapshots = {name: list(model.objects.values()) for name, model in models.items()}
            MigrationExecutor(connection).migrate(latest)
            from django.apps import apps

            for name, rows in snapshots.items():
                for row in rows:
                    self.assertEqual(
                        apps.get_model("core", name).objects.values(*row).get(pk=row["id"]), row
                    )
            client = APIClient()
            self.assertEqual(
                client.post(
                    "/api/student/login/",
                    {
                        "class_code": cohort.student_login_code,
                        "student_number": "001",
                        "password": "Upgrade!Student2026",
                    },
                ).status_code,
                200,
            )
            self.assertEqual(client.get("/api/student/roles/").json()["owned"], ["rabbit"])
            self.assertEqual(client.get("/api/student/history/points/").json()["count"], 2)
            self.assertEqual(client.get("/api/notifications/").json()["count"], 0)
            announcement = client.get("/api/student/announcements/").json()["results"][0]
            self.assertEqual(
                (announcement["content_version"], announcement["confirmed_at"]), (1, None)
            )
            # Both backfills are idempotent with existing ownership/version rows.
            for migration in (
                "0021_backfill_role_ownership",
                "0025_backfill_announcement_versions",
            ):
                module = importlib.import_module("core.migrations." + migration)
                operation = module.Migration.operations[0]
                with connection.schema_editor() as editor:
                    operation.code(apps, editor)
            self.assertEqual(apps.get_model("core", "StudentRoleOwnership").objects.count(), 1)
            self.assertEqual(apps.get_model("core", "AnnouncementVersion").objects.count(), 1)
            self.assertEqual(apps.get_model("core", "Notification").objects.count(), 0)
            self.assertEqual(apps.get_model("core", "AnnouncementReminder").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
