import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from . import test_score_transactions


class BatchScoreTransactionTests(TransactionTestCase):
    login = test_score_transactions.ScoreTransactionTests.login

    def setUp(self):
        test_score_transactions.ScoreTransactionTests.setUp(self)
        self.client.post(self.base + "students/", {"text": "2\t小美\t002"})
        self.students = self.client.get(self.base + "students/").json()

    def payload(self):
        return {
            "student_ids": [s["id"] for s in self.students],
            "kind": "positive",
            "score": 2,
            "template": "other",
            "request_id": str(uuid.uuid4()),
        }

    def parallel(self, endpoint, *payloads):
        barrier = Barrier(len(payloads))

        def run(payload):
            close_old_connections()
            try:
                client = self.login()
                barrier.wait(timeout=10)
                return client.post(self.base + endpoint, payload, format="json")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            futures = [pool.submit(run, payload) for payload in payloads]
            return [future.result(timeout=30) for future in futures]

    def test_parallel_batch_retries_and_distinct_batches_keep_exact_totals(self):
        payload = self.payload()
        responses = self.parallel("score-batches/", payload, payload)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        self.assertEqual(
            [
                r.status_code
                for r in self.parallel("score-batches/", self.payload(), self.payload())
            ],
            [201, 201],
        )
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [6, 6],
        )
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 6)

    def test_parallel_reason_fill_does_not_overwrite_or_duplicate_audits(self):
        records = self.client.post(
            self.base + "score-batches/", self.payload(), format="json"
        ).json()["results"]
        payload = {
            "record_ids": [r["id"] for r in records],
            "note": "先完成",
            "request_id": str(uuid.uuid4()),
        }
        different = {**payload, "note": "不可覆寫", "request_id": str(uuid.uuid4())}
        responses = self.parallel("pending-reasons/", payload, different)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 400])
        winner = payload if responses[0].status_code == 200 else different
        retries = self.parallel("pending-reasons/", winner, winner)
        self.assertEqual([r.status_code for r in retries], [200, 200])
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 4)
        self.assertTrue(
            all(
                r["note"] == winner["note"]
                for r in self.client.get(self.base + "scores/").json()["results"]
            )
        )

    def fail_second_audit(self, endpoint, payload):
        # Fault injection at the real PostgreSQL boundary: fail after one item was written.
        self.client.raise_request_exception = False
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_batch_audit_failure() RETURNS trigger AS $$
                BEGIN
                  IF (SELECT s.seat_number FROM core_student s JOIN core_scorerecord r
                      ON r.student_id=s.id WHERE r.id=NEW.record_id)=2 THEN
                    RAISE EXCEPTION 'second batch audit failure';
                  END IF;
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_batch_audit BEFORE INSERT ON core_scoreauditevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_batch_audit_failure();
            """)
        try:
            self.assertEqual(
                self.client.post(self.base + endpoint, payload, format="json").status_code, 500
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_batch_audit ON core_scoreauditevent")
                cursor.execute("DROP FUNCTION cm_test_batch_audit_failure()")

    def test_batch_second_audit_failure_rolls_back_all_students_and_retry(self):
        payload = self.payload()
        self.fail_second_audit("score-batches/", payload)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 0)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 0)
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [0, 0],
        )
        self.assertEqual(
            self.client.post(self.base + "score-batches/", payload, format="json").status_code, 201
        )

    def test_reason_second_audit_failure_rolls_back_all_reasons_and_retry(self):
        records = self.client.post(
            self.base + "score-batches/", self.payload(), format="json"
        ).json()["results"]
        payload = {
            "record_ids": [r["id"] for r in records],
            "note": "補充",
            "request_id": str(uuid.uuid4()),
        }
        self.fail_second_audit("pending-reasons/", payload)
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 2)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 2)
        self.assertEqual(
            self.client.post(self.base + "pending-reasons/", payload, format="json").status_code,
            200,
        )
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 0)
