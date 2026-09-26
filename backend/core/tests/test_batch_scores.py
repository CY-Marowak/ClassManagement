import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, ScoreAuditEvent, ScoreRecord, User

from . import test_scores


class BatchScoreTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp

    def payload(self, **changes):
        return {
            "student_ids": [s["id"] for s in self.students],
            "kind": "positive",
            "score": 3,
            "template": "other",
            "note": "",
            "request_id": str(uuid.uuid4()),
            **changes,
        }

    def batch(self, payload):
        return self.client.post(self.base + "score-batches/", payload, format="json")

    def test_invalid_batch_or_missing_student_leaves_no_partial_scores(self):
        for changes in [
            {"student_ids": []},
            {"student_ids": [s["id"] for s in self.students] + [999999]},
            {"student_ids": [self.students[0]["id"]] * 2},
            {"student_ids": list(range(1, 202))},
            {"score": 101},
            {"score": -1},
            {"score": 1.5},
            {"score": True},
            {"template": "rules"},
            {"note": "x" * 1001},
            {"creator_id": self.owner.pk},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(self.batch(self.payload(**changes)).status_code, 400)
                self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 0)
                self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 0)
        other = self.client.post(
            "/api/classes/", {"name": "他班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.assertEqual(
            self.client.post(
                f"/api/classes/{other['id']}/score-batches/", self.payload(), format="json"
            ).status_code,
            400,
        )
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [0, 0],
        )

    def test_stale_reason_selection_cancels_whole_batch_and_rejects_blank_or_forged_fields(self):
        records = self.batch(self.payload()).json()["results"]
        first = {"record_ids": [records[0]["id"]], "note": "已補", "request_id": str(uuid.uuid4())}
        self.assertEqual(self.fill(first).status_code, 200)
        second = {
            "record_ids": [r["id"] for r in records],
            "note": "不可覆寫",
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(self.fill(second).status_code, 400)
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 1)
        for changes in [
            {"note": "  "},
            {"note": "x" * 1001},
            {"score": 9},
            {"record_ids": []},
            {"record_ids": [records[1]["id"], 999999]},
        ]:
            self.assertEqual(self.fill({**second, **changes}).status_code, 400)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 3)

    def test_coteacher_can_fill_only_own_records_and_revocation_blocks_retry(self):
        owners = self.batch(self.payload()).json()["results"]
        co = User.objects.create_user(
            username="co-batch", email_verified=True, display_name="共同教師"
        )
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=co, role="coTeacher", approved=True
        )
        client = APIClient()
        client.force_login(co)
        self.assertEqual(client.get(self.base + "pending-reasons/").json()["count"], 0)
        batch = self.payload()
        own = client.post(self.base + "score-batches/", batch, format="json").json()["results"]
        mixed = {
            "record_ids": [owners[0]["id"], own[0]["id"]],
            "note": "補充",
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(
            client.post(self.base + "pending-reasons/", mixed, format="json").status_code, 400
        )
        self.assertEqual(client.get(self.base + "pending-reasons/").json()["count"], 2)
        fill = {**mixed, "record_ids": [r["id"] for r in own]}
        self.assertEqual(
            client.post(self.base + "pending-reasons/", fill, format="json").status_code, 200
        )
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 2)
        member.approved = False
        member.save()
        self.assertEqual(client.get(self.base + "pending-reasons/").status_code, 404)
        self.assertEqual(
            client.post(self.base + "pending-reasons/", fill, format="json").status_code, 404
        )
        self.assertEqual(
            client.post(self.base + "score-batches/", batch, format="json").status_code, 404
        )
        # Homeroom may fill co-teacher records, preserving their original authorship.
        member.approved = True
        member.save()
        another = client.post(self.base + "score-batches/", self.payload(), format="json").json()[
            "results"
        ]
        self.assertEqual(
            self.fill(
                {
                    "record_ids": [r["id"] for r in another],
                    "note": "導師補充",
                    "request_id": str(uuid.uuid4()),
                }
            ).status_code,
            200,
        )
        latest = self.client.get(self.base + "scores/").json()["results"][0]
        self.assertEqual(latest["creator_name"], "共同教師")

    def test_student_isolation_csrf_and_single_batch_identity_conflicts(self):
        payload = self.payload(kind="negative", score=0)
        records = self.batch(payload).json()["results"]
        student = test_scores.ScoreTests.student_login(self)
        own = student.get("/api/student/scores/").json()
        self.assertEqual(own["count"], 1)
        self.assertEqual(own["total"], 0)
        self.assertEqual(own["results"][0]["student_id"], self.students[0]["id"])
        for client in [student, APIClient()]:
            self.assertEqual(
                client.post(self.base + "score-batches/", payload, format="json").status_code, 403
            )
            self.assertEqual(client.get(self.base + "pending-reasons/").status_code, 403)
        secure = APIClient(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        fill = {
            "record_ids": [r["id"] for r in records],
            "note": "補充",
            "request_id": str(uuid.uuid4()),
        }
        for endpoint, data in [("score-batches/", payload), ("pending-reasons/", fill)]:
            self.assertEqual(
                secure.post(self.base + endpoint, data, format="json").status_code, 403
            )
        single = {k: v for k, v in payload.items() if k != "student_ids"}
        single["student_id"] = self.students[0]["id"]
        self.assertEqual(
            self.client.post(self.base + "scores/", single, format="json").status_code, 400
        )
        single["request_id"] = str(uuid.uuid4())
        self.assertEqual(
            self.client.post(self.base + "scores/", single, format="json").status_code, 201
        )
        self.assertEqual(
            self.batch({**payload, "request_id": single["request_id"]}).status_code, 400
        )

    def test_deleting_student_clears_own_batch_history_and_prevents_partial_retry(self):
        payload = self.payload()
        records = self.batch(payload).json()["results"]
        fill = {
            "record_ids": [r["id"] for r in records],
            "note": "補充",
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(self.fill(fill).status_code, 200)
        removed = self.students[0]
        self.assertEqual(
            self.client.delete(
                self.base + f"students/{removed['id']}/",
                {"confirmation_student_number": removed["student_number"]},
                format="json",
            ).status_code,
            200,
        )
        self.assertFalse(ScoreRecord.objects.filter(student_id=removed["id"]).exists())
        self.assertFalse(ScoreAuditEvent.objects.filter(record_id=records[0]["id"]).exists())
        self.assertEqual(self.batch(payload).status_code, 400)
        self.assertEqual(self.fill(fill).status_code, 400)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 1)
        self.assertEqual(
            self.client.get(self.base + "score-roster/").json()["students"][0]["total"], 3
        )
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": self.cohort["name"]}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(ScoreRecord.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertFalse(
            ScoreAuditEvent.objects.filter(record_id__in=[r["id"] for r in records]).exists()
        )

    def fill(self, payload):
        return self.client.post(self.base + "pending-reasons/", payload, format="json")

    def test_single_score_retry_after_reason_fill_uses_original_request(self):
        payload = test_scores.ScoreTests.payload(self, template="other", note="")
        record = self.client.post(self.base + "scores/", payload, format="json").json()
        self.assertEqual(
            self.fill(
                {"record_ids": [record["id"]], "note": "事後補充", "request_id": str(uuid.uuid4())}
            ).status_code,
            200,
        )
        retry = self.client.post(self.base + "scores/", payload, format="json")
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["note"], "事後補充")
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 1)
        student = test_scores.ScoreTests.student_login(self)
        self.assertEqual(
            student.get("/api/student/scores/").json()["results"][0]["note"], "事後補充"
        )

    def test_pending_pagination_and_other_class_records_do_not_leak(self):
        self.client.post(
            self.base + "students/",
            {"text": "\n".join(f"{i}\t學生{i}\t{i:03}" for i in range(3, 27))},
        )
        students = self.client.get(self.base + "students/").json()
        records = self.batch(self.payload(student_ids=[s["id"] for s in students])).json()[
            "results"
        ]
        first = self.client.get(self.base + "pending-reasons/").json()
        second = self.client.get(self.base + "pending-reasons/?page=2").json()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 1)
        self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        other = self.client.post(
            "/api/classes/", {"name": "另一班", "entry_year": 2026, "current_grade": 1}
        ).json()
        payload = {
            "record_ids": [records[0]["id"]],
            "note": "不可跨班",
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(
            self.client.post(
                f"/api/classes/{other['id']}/pending-reasons/", payload, format="json"
            ).status_code,
            400,
        )
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 26)

    def test_fill_pending_reasons_keeps_totals_and_creator_and_audits_once(self):
        original = self.payload()
        records = self.batch(original).json()["results"]
        pending = self.client.get(self.base + "pending-reasons/")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["count"], 2)
        payload = {
            "record_ids": [r["id"] for r in records],
            "note": "協助整理教室",
            "request_id": str(uuid.uuid4()),
        }
        self.assertEqual(self.fill(payload).status_code, 200)
        self.assertEqual(self.fill(payload).status_code, 200)
        self.assertEqual(self.fill({**payload, "note": "不同原因"}).status_code, 400)
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 0)
        updated = self.client.get(self.base + "scores/").json()["results"]
        self.assertTrue(all(r["note"] == "協助整理教室" and not r["needs_reason"] for r in updated))
        self.assertTrue(all(r["creator_name"] == "林老師" for r in updated))
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [3, 3],
        )
        events = self.client.get(self.base + "score-events/").json()
        self.assertEqual(events["count"], 4)
        self.assertEqual(events["results"][0]["action"], "reason_filled")
        self.assertEqual(events["results"][0]["before"]["note"], "")
        self.assertEqual(events["results"][0]["after"]["note"], "協助整理教室")
        self.assertEqual(self.batch(original).status_code, 200)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 2)

    def test_batch_creates_independent_records_with_shared_identity_and_safe_retry(self):
        payload = self.payload()
        created = self.batch(payload)
        self.assertEqual(created.status_code, 201)
        records = created.json()["results"]
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["id"], records[1]["id"])
        self.assertTrue(records[0]["batch_id"])
        self.assertEqual(records[0]["batch_id"], records[1]["batch_id"])
        retry = self.batch({**payload, "student_ids": list(reversed(payload["student_ids"]))})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), created.json())
        self.assertEqual(self.batch({**payload, "score": 4}).status_code, 400)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 2)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 2)
        self.assertEqual(
            [s["total"] for s in self.client.get(self.base + "score-roster/").json()["students"]],
            [3, 3],
        )
