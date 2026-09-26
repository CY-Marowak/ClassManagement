import uuid

from django.test import TransactionTestCase

from . import test_batch_score_transactions


class ScoreChangeTransactionTests(TransactionTestCase):
    setUp = test_batch_score_transactions.BatchScoreTransactionTests.setUp
    login = test_batch_score_transactions.BatchScoreTransactionTests.login
    payload = test_batch_score_transactions.BatchScoreTransactionTests.payload
    parallel = test_batch_score_transactions.BatchScoreTransactionTests.parallel
    fail_second_audit = test_batch_score_transactions.BatchScoreTransactionTests.fail_second_audit

    def edit_payload(self):
        records = self.client.post(
            self.base + "score-batches/", self.payload(), format="json"
        ).json()["results"]
        preview = self.client.get(
            self.base + f"scores/{records[0]['id']}/edit-preview/?scope=batch"
        ).json()
        return {
            "request_id": str(uuid.uuid4()),
            "preview_token": preview["token"],
            "action": "edit",
            "kind": "negative",
            "score": -3,
            "template": "rules",
            "note": "修正",
        }

    def test_parallel_retry_applies_delta_and_audits_once(self):
        payload = self.edit_payload()
        responses = self.parallel("score-changes/", payload, payload)
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [-3, -3],
        )
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 4)

    def test_competing_edits_cannot_overwrite_newer_revision(self):
        payload = self.edit_payload()
        other = {**payload, "request_id": str(uuid.uuid4()), "score": -8}
        responses = self.parallel("score-changes/", payload, other)
        self.assertEqual(sorted(r.status_code for r in responses), [200, 400])
        expected = -3 if responses[0].status_code == 200 else -8
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [expected, expected],
        )
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 4)

    def test_second_audit_failure_rolls_back_entire_batch_and_retry_succeeds(self):
        payload = self.edit_payload()
        self.fail_second_audit("score-changes/", payload)
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [2, 2],
        )
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 2)
        self.assertTrue(
            all(
                not r["is_modified"]
                for r in self.client.get(self.base + "scores/").json()["results"]
            )
        )
        self.assertEqual(
            self.client.post(self.base + "score-changes/", payload, format="json").status_code, 200
        )

    def test_delete_audit_failure_rolls_back_total_visibility_and_allows_retry(self):
        self.edit_payload()
        records = self.client.get(self.base + "scores/").json()["results"]
        record = next(r for r in records if r["seat_number"] == 2)
        preview = self.client.get(self.base + f"scores/{record['id']}/edit-preview/").json()
        payload = {
            "action": "delete",
            "request_id": str(uuid.uuid4()),
            "preview_token": preview["token"],
        }
        self.fail_second_audit("score-changes/", payload)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 2)
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [2, 2],
        )
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 2)
        self.assertEqual(
            self.client.post(self.base + "score-changes/", payload, format="json").status_code, 200
        )
