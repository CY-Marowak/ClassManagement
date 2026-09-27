import uuid

from django.db import connection
from django.test import TransactionTestCase

from . import test_batch_score_transactions


class AwardTransactionTests(TransactionTestCase):
    setUp = test_batch_score_transactions.BatchScoreTransactionTests.setUp
    login = test_batch_score_transactions.BatchScoreTransactionTests.login
    parallel = test_batch_score_transactions.BatchScoreTransactionTests.parallel

    def payload(self):
        records = self.client.post(
            self.base + "score-batches/",
            {
                "student_ids": [s["id"] for s in self.students],
                "kind": "positive",
                "score": 2,
                "template": "participation",
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        ).json()["results"]
        return {
            "request_id": str(uuid.uuid4()),
            "items": [
                {"record_id": r["id"], "revision": r["revision"], "points": 3} for r in records
            ],
        }

    def balances(self):
        data = self.client.get(self.base + "point-awards/?status=awarded").json()
        return [s["point_balance"] for s in data["students"]]

    def test_parallel_same_request_and_competing_awards_never_double_pay(self):
        payload = self.payload()
        responses = self.parallel("point-awards/", payload, payload)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(self.balances(), [3, 3])
        another = self.payload()
        responses = self.parallel(
            "point-awards/", another, {**another, "request_id": str(uuid.uuid4())}
        )
        self.assertEqual(sorted(r.status_code for r in responses), [201, 400])
        self.assertEqual(self.balances(), [6, 6])

    def test_multiple_sources_for_same_student_accumulate_and_parallel_batches_keep_balance(self):
        first, second = self.payload(), self.payload()
        responses = self.parallel("point-awards/", first, second)
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(self.balances(), [6, 6])
        third, fourth = self.payload(), self.payload()
        third["items"] += fourth["items"]
        self.assertEqual(
            self.client.post(self.base + "point-awards/", third, format="json").status_code, 201
        )
        self.assertEqual(self.balances(), [12, 12])

    def test_second_transaction_failure_rolls_back_batch_transactions_and_balances(self):
        payload = self.payload()
        self.client.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_award_failure() RETURNS trigger AS $$
                BEGIN
                  IF (SELECT seat_number FROM core_student WHERE id=NEW.student_id)=2 THEN
                    RAISE EXCEPTION 'second award failed';
                  END IF;
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_award BEFORE INSERT ON core_pointtransaction
                FOR EACH ROW EXECUTE FUNCTION cm_test_award_failure();
            """)
        try:
            self.assertEqual(
                self.client.post(self.base + "point-awards/", payload, format="json").status_code,
                500,
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_award ON core_pointtransaction")
                cursor.execute("DROP FUNCTION cm_test_award_failure()")
        self.assertEqual(self.balances(), [])
        pending = self.client.get(self.base + "point-awards/").json()
        self.assertEqual([s["point_balance"] for s in pending["students"]], [0, 0])
        self.assertEqual(pending["week"]["points"], 0)
        self.assertEqual(
            self.client.post(self.base + "point-awards/", payload, format="json").status_code, 201
        )
        self.assertEqual(self.balances(), [3, 3])
