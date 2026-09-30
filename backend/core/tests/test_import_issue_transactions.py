from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from . import test_import_issues


class ImportIssueTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_import_issues.ImportIssueTests.setUp

    def test_concurrent_resolution_creates_one_student(self):
        self.client.post(self.base + "students/", {"text": "1\t缺欄"})
        issue = self.client.get(self.base + "import-issues/").json()["results"][0]
        barrier = Barrier(2)

        def resolve():
            close_old_connections()
            try:
                client = APIClient()
                client.cookies = self.client.cookies.copy()
                barrier.wait(timeout=10)
                return client.post(
                    self.base + f"import-issues/{issue['id']}/",
                    {
                        "action": "retry",
                        "revision": 1,
                        "raw": "1\t小明\t001",
                    },
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(resolve) for _ in range(2)]
            responses = [future.result(timeout=20) for future in futures]
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(len(self.client.get(self.base + "students/").json()), 1)
        self.assertEqual(self.client.get(self.base + "import-issues/").json()["count"], 0)

    def test_database_failure_rolls_back_import_and_resolution_with_student_and_audit(self):
        self.client.post(self.base + "students/", {"text": "2\t缺欄"})
        issue = self.client.get(self.base + "import-issues/").json()["results"][0]
        self.client.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_import_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'import task write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_import BEFORE INSERT OR UPDATE ON core_studentimportissue
                FOR EACH ROW EXECUTE FUNCTION cm_test_import_failure();
            """)
        try:
            self.assertEqual(
                self.client.post(
                    self.base + "students/",
                    {
                        "text": "1\t小明\t001\n3\t缺欄",
                    },
                ).status_code,
                500,
            )
            self.assertEqual(
                self.client.post(
                    self.base + f"import-issues/{issue['id']}/",
                    {
                        "action": "retry",
                        "revision": 1,
                        "raw": "2\t小美\t002",
                    },
                ).status_code,
                500,
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_import ON core_studentimportissue")
                cursor.execute("DROP FUNCTION cm_test_import_failure()")
        self.assertEqual(self.client.get(self.base + "students/").json(), [])
        self.assertEqual(self.client.get(self.base + "student-events/").json()["count"], 0)
        self.assertEqual(self.client.get(self.base + "import-issues/").json()["results"], [issue])
