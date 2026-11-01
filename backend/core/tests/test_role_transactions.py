from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import StudentRoleOwnership

from . import test_comment_transactions, test_role_collection


class RoleTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_role_collection.RoleCollectionTests.setUp
    login = test_role_collection.RoleCollectionTests.login
    waiting_request = test_comment_transactions.CommentTransactionTests.waiting_request

    def test_waiting_selection_rechecks_password_reset(self):
        profile = self.student.get("/api/student/me/").json()
        result = self.waiting_request(
            lambda: self.student.post("/api/student/roles/", {"role": profile["avatar"]}),
            lambda: self.client.post(f"{self.roster_url}{profile['id']}/reset-password/"),
        )
        self.assertEqual(result.status_code, 403)

    def test_waiting_selection_cannot_recreate_deleted_student_or_inventory(self):
        profile = self.student.get("/api/student/me/").json()
        result = self.waiting_request(
            lambda: self.student.post("/api/student/roles/", {"role": profile["avatar"]}),
            lambda: self.client.delete(
                f"{self.roster_url}{profile['id']}/",
                {"confirmation_student_number": "00001"},
                format="json",
            ),
        )
        self.assertEqual(result.status_code, 404)
        self.assertFalse(StudentRoleOwnership.objects.filter(student_id=profile["id"]).exists())
        self.assertEqual(StudentRoleOwnership.objects.count(), 1)

    def test_failed_initial_ownership_write_rolls_back_import_and_can_retry(self):
        before = self.client.get(self.roster_url).json()
        self.client.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_role_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'ownership write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_role BEFORE INSERT ON core_studentroleownership
                FOR EACH ROW EXECUTE FUNCTION cm_test_role_failure();
            """)
        try:
            self.assertEqual(
                self.client.post(self.roster_url, {"text": "3\t小安\t00003"}).status_code, 500
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_role ON core_studentroleownership")
                cursor.execute("DROP FUNCTION cm_test_role_failure()")
        self.assertEqual(self.client.get(self.roster_url).json(), before)
        result = self.client.post(self.roster_url, {"text": "3\t小安\t00003"})
        self.assertEqual(result.json()["summary"]["created"], 1)
