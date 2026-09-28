import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from . import test_mascots, test_scores


class FeedingTransactionTests(TransactionTestCase):
    client_class = APIClient
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    award = test_mascots.MascotTests.award
    feed = test_mascots.MascotTests.feed

    def parallel(self, student, *amounts, same_request=False):
        barrier = Barrier(len(amounts))
        identity = str(uuid.uuid4())

        def run(amount):
            close_old_connections()
            try:
                client = APIClient()
                client.cookies = student.cookies.copy()
                barrier.wait(timeout=10)
                return self.feed(client, amount, identity if same_request else None)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(amounts)) as pool:
            futures = [pool.submit(run, amount) for amount in amounts]
            return [future.result(timeout=30) for future in futures]

    def test_parallel_retries_charge_once(self):
        student = self.student_login()
        self.award(5)
        responses = self.parallel(student, 2, 2, same_request=True)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(
            (data["point_balance"], data["daily_remaining"], data["mascot"]["exp"]), (3, 3, 2)
        )
        self.assertEqual(len(data["transactions"]), 2)

    def test_competing_feeds_never_exceed_daily_limit(self):
        student = self.student_login()
        self.award(10)
        responses = self.parallel(student, 3, 3)
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(
            (data["point_balance"], data["daily_remaining"], data["mascot"]["exp"]), (7, 2, 3)
        )

    def test_competing_feeds_never_overdraw_balance(self):
        student = self.student_login()
        self.award(3)
        responses = self.parallel(student, 2, 2)
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        data = student.get("/api/student/mascot/").json()
        self.assertEqual((data["point_balance"], data["mascot"]["exp"]), (1, 2))

    def test_parallel_students_keep_all_class_exp_and_individual_limits(self):
        first = self.student_login()
        second = self.student_login("002")
        self.award(5)
        self.award(5, 1)
        barrier = Barrier(2)

        def run(student):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.feed(student, 5)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, client) for client in [first, second]]
            self.assertEqual([f.result(timeout=30).status_code for f in futures], [201, 201])
        for student in [first, second]:
            data = student.get("/api/student/mascot/").json()
            self.assertEqual(
                (data["point_balance"], data["daily_remaining"], data["mascot"]["exp"]), (0, 0, 10)
            )
            self.assertEqual(len(data["transactions"]), 2)

    def test_exp_write_failure_rolls_back_debit_and_transaction_then_retry_succeeds(self):
        student = self.student_login()
        self.award(5)
        student.raise_request_exception = False
        identity = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_exp_failure() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'exp write failed'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_exp BEFORE UPDATE ON core_mascot
                FOR EACH ROW EXECUTE FUNCTION cm_test_exp_failure();
            """)
        try:
            self.assertEqual(self.feed(student, 2, identity).status_code, 500)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_exp ON core_mascot")
                cursor.execute("DROP FUNCTION cm_test_exp_failure()")
        data = student.get("/api/student/mascot/").json()
        self.assertEqual(
            (data["point_balance"], data["daily_remaining"], data["mascot"]["exp"]), (5, 5, 0)
        )
        self.assertEqual(len(data["transactions"]), 1)
        self.assertEqual(self.feed(student, 2, identity).status_code, 201)

    def test_parallel_award_and_feed_keep_both_balance_changes(self):
        student = self.student_login()
        self.award(5)
        barrier = Barrier(2)

        def award():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                self.award(3)
            finally:
                close_old_connections()

        def feed():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                self.assertEqual(self.feed(student, 2).status_code, 201)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(award), pool.submit(feed)]
            for future in futures:
                future.result(timeout=30)
        data = student.get("/api/student/mascot/").json()
        self.assertEqual((data["point_balance"], data["mascot"]["exp"]), (6, 2))
        self.assertEqual(len(data["transactions"]), 3)
