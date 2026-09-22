import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import User


class ScoreTransactionTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="score-owner",
            email="scores@example.com",
            display_name="導師",
            email_verified=True,
        )
        self.client = self.login()
        cohort = self.client.post(
            "/api/classes/",
            {
                "name": "交易班",
                "entry_year": 2026,
                "current_grade": 1,
            },
        ).json()
        self.base = f"/api/classes/{cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t小明\t001"})
        self.student = self.client.get(self.base + "students/").json()[0]

    def login(self):
        client = APIClient()
        client.force_login(self.owner)
        return client

    def payload(self):
        return {
            "student_id": self.student["id"],
            "kind": "positive",
            "score": 3,
            "template": "participation",
            "request_id": str(uuid.uuid4()),
        }

    def parallel(self, *payloads):
        barrier = Barrier(len(payloads))

        def run(payload):
            close_old_connections()
            try:
                client = self.login()
                barrier.wait(timeout=10)
                return client.post(self.base + "scores/", payload, format="json")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            futures = [pool.submit(run, payload) for payload in payloads]
            return [future.result(timeout=30) for future in futures]

    def test_parallel_retries_create_once_and_distinct_scores_do_not_lose_totals(self):
        payload = self.payload()
        responses = self.parallel(payload, payload)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 201])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
        responses = self.parallel(self.payload(), self.payload())
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(
            self.client.get(self.base + "score-roster/").json()["students"][0]["total"], 9
        )
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 3)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 3)

    def test_database_audit_failure_rolls_back_score_total_and_retry_identity(self):
        self.client.raise_request_exception = False
        payload = self.payload()
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE FUNCTION cm_test_reject_score_event() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'test score audit failure'; END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER cm_test_score_event BEFORE INSERT ON core_scoreauditevent
                FOR EACH ROW EXECUTE FUNCTION cm_test_reject_score_event();
            """)
        try:
            self.assertEqual(
                self.client.post(self.base + "scores/", payload, format="json").status_code, 500
            )
            self.assertEqual(
                self.client.get(self.base + "score-roster/").json()["students"][0]["total"], 0
            )
            self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 0)
            self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 0)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TRIGGER cm_test_score_event ON core_scoreauditevent")
                cursor.execute("DROP FUNCTION cm_test_reject_score_event()")
        self.assertEqual(
            self.client.post(self.base + "scores/", payload, format="json").status_code, 201
        )
        self.assertEqual(
            self.client.get(self.base + "score-roster/").json()["students"][0]["total"], 3
        )
