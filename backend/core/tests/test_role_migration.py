from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient


class RoleMigrationTests(TransactionTestCase):
    def test_existing_roles_accounts_balances_and_mascot_survive_repeatable_upgrade(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old_target = [("core", "0019_import_issue_draft")]
        executor.migrate(old_target)
        try:
            old = executor.loader.project_state(old_target).apps
            cohort = old.get_model("core", "Cohort").objects.create(
                name="既有班", entry_year=2026, current_grade=2
            )
            old.get_model("core", "Mascot").objects.create(cohort=cohort, animal="dog", exp=250)
            password = make_password("Legacy!Garden2026")
            for seat, role in enumerate(["cat", "dog", "rabbit"], 1):
                user = old.get_model("core", "User").objects.create(
                    username=f"old-{seat}",
                    email=None,
                    account_type="student",
                    display_name=f"原學生{seat}",
                    password=password,
                )
                old.get_model("core", "Student").objects.create(
                    cohort=cohort,
                    user=user,
                    seat_number=seat,
                    student_number=f"00{seat}",
                    avatar=role,
                    must_change_password=False,
                    point_balance=19,
                    behavior_score_total=42,
                )
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            for seat, role in enumerate(["cat", "dog", "rabbit"], 1):
                client = APIClient()
                self.assertEqual(
                    client.post(
                        "/api/student/login/",
                        {
                            "class_code": cohort.student_login_code,
                            "student_number": f"00{seat}",
                            "password": "Legacy!Garden2026",
                        },
                    ).status_code,
                    200,
                )
                collection = client.get("/api/student/roles/").json()
                self.assertEqual(collection["owned"], [role])
                self.assertEqual(collection["selected"], role)
                self.assertEqual(client.get("/api/student/me/").json()["point_balance"], 19)
                mascot = client.get("/api/student/mascot/").json()["mascot"]
                self.assertEqual((mascot["animal"], mascot["exp"]), ("dog", 250))
            from core.models import Student, StudentRoleOwnership

            self.assertEqual(
                list(Student.objects.values_list("behavior_score_total", flat=True)), [42] * 3
            )
            # Re-run only the data upgrade, without dropping the ownership table.
            MigrationExecutor(connection).migrate([("core", "0020_student_role_ownership")])
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(StudentRoleOwnership.objects.count(), 3)
        finally:
            MigrationExecutor(connection).migrate(latest)
