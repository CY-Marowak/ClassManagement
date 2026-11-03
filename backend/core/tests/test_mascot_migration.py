from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import User


class MascotMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_all_existing_species_and_growth(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [("core", "0022_remove_pointtransaction_point_transaction_kind_range_and_more")]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            teacher = old.get_model("core", "User").objects.create(
                username="legacy-mascot-teacher", email_verified=True, account_type="teacher"
            )
            expected = []
            for animal, exp in [("cat", 999), ("dog", 4500), ("rabbit", 23100)]:
                cohort = old.get_model("core", "Cohort").objects.create(
                    name=animal, entry_year=2026, current_grade=1
                )
                old.get_model("core", "ClassMember").objects.create(
                    cohort=cohort, user=teacher, role="homeroom", approved=True
                )
                old.get_model("core", "Mascot").objects.create(
                    cohort=cohort, animal=animal, exp=exp
                )
                expected.append((cohort.pk, animal, exp))
            MigrationExecutor(connection).migrate(latest)
            client = APIClient()
            client.force_login(User.objects.get(pk=teacher.pk))
            for cohort_id, animal, exp in expected:
                response = client.get(f"/api/classes/{cohort_id}/mascot/")
                self.assertEqual(response.status_code, 200)
                self.assertEqual((response.json()["animal"], response.json()["exp"]), (animal, exp))
        finally:
            MigrationExecutor(connection).migrate(latest)
