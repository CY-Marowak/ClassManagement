import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from . import test_comment_transactions, test_mascots, test_role_shop, test_scores


class RolePurchaseTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    award = test_mascots.MascotTests.award
    feed = test_mascots.MascotTests.feed
    buy = test_role_shop.RoleShopTests.buy
    unowned = test_role_shop.RoleShopTests.unowned
    waiting_request = test_comment_transactions.CommentTransactionTests.waiting_request

    def parallel(self, *operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(run, op) for op in operations]
            return sorted(f.result(timeout=30).status_code for f in futures)

    def test_concurrent_same_role_with_same_or_distinct_ids_debits_only_once(self):
        student = self.student_login()
        second = APIClient()
        second.cookies = student.cookies.copy()
        self.award(80)
        one, two = self.unowned(student)[:2]
        identity = str(uuid.uuid4())
        self.assertEqual(
            self.parallel(
                lambda: self.buy(student, one, identity), lambda: self.buy(second, one, identity)
            ),
            [200, 201],
        )
        self.assertEqual(
            self.parallel(lambda: self.buy(student, two), lambda: self.buy(second, two)), [201, 400]
        )
        data = student.get("/api/student/roles/").json()
        self.assertEqual(data["point_balance"], 40)
        self.assertEqual(len(data["owned"]), 3)
        self.assertEqual(len(student.get("/api/student/mascot/").json()["transactions"]), 3)

    def test_purchase_competes_with_feed_and_another_role_without_overspending(self):
        student = self.student_login()
        second = APIClient()
        second.cookies = student.cookies.copy()
        self.award(20)
        one, two = self.unowned(student)[:2]
        self.assertEqual(
            self.parallel(lambda: self.buy(student, one), lambda: self.feed(second, 1)), [201, 400]
        )
        account = student.get("/api/student/mascot/").json()
        self.assertIn(
            (account["point_balance"], account["mascot"]["exp"], account["daily_remaining"]),
            [(0, 0, 5), (19, 1, 4)],
        )
        self.award(20)
        self.assertEqual(
            self.parallel(
                lambda: self.buy(student, two), lambda: self.buy(second, self.unowned(second)[-1])
            ),
            [201, 400],
        )
        self.assertGreaterEqual(student.get("/api/student/roles/").json()["point_balance"], 0)

    def test_failed_ownership_write_rolls_back_debit_and_transaction_then_retries(self):
        student = self.student_login()
        self.award(20)
        role = self.unowned(student)[0]
        before = student.get("/api/student/roles/").json()
        account = student.get("/api/student/mascot/").json()
        identity = str(uuid.uuid4())
        student.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_purchase_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'ownership write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_purchase BEFORE INSERT ON core_studentroleownership
                FOR EACH ROW EXECUTE FUNCTION cm_test_purchase_failure();
            """)
        try:
            self.assertEqual(self.buy(student, role, identity).status_code, 500)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_purchase ON core_studentroleownership")
                cursor.execute("DROP FUNCTION cm_test_purchase_failure()")
        self.assertEqual(student.get("/api/student/roles/").json(), before)
        self.assertEqual(student.get("/api/student/mascot/").json(), account)
        self.assertEqual(self.buy(student, role, identity).status_code, 201)

    def test_waiting_purchase_rechecks_reset_and_student_deletion(self):
        student = self.student_login()
        self.award(40)
        role = self.unowned(student)[0]
        url = f"{self.base}students/{self.students[0]['id']}/"
        result = self.waiting_request(
            lambda: self.buy(student, role), lambda: self.client.post(url + "reset-password/")
        )
        self.assertEqual(result.status_code, 403)
        student = self.student_login()
        self.assertEqual(student.get("/api/student/roles/").json()["point_balance"], 40)
        result = self.waiting_request(
            lambda: self.buy(student, role),
            lambda: self.client.delete(url, {"confirmation_student_number": "001"}, format="json"),
        )
        self.assertEqual(result.status_code, 404)
