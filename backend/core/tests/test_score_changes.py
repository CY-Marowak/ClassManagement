import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, ScoreAuditEvent, ScoreRecord, User
from core.tests import test_scores


class ScoreChangeTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    payload = test_scores.ScoreTests.payload
    student_login = test_scores.ScoreTests.student_login

    def create(self, **changes):
        response = self.client.post(self.base + "scores/", self.payload(**changes), format="json")
        self.assertEqual(response.status_code, 201)
        return response.json()

    def preview(self, record, scope="single", client=None):
        response = (client or self.client).get(
            self.base + f"scores/{record['id']}/edit-preview/?scope={scope}"
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def change(self, preview, action="edit", client=None, **changes):
        payload = {
            "request_id": str(uuid.uuid4()),
            "preview_token": preview["token"],
            "action": action,
            **(
                {"kind": "positive", "score": 1, "template": "helping", "note": "修正"}
                if action == "edit"
                else {}
            ),
            **changes,
        }
        return (client or self.client).post(self.base + "score-changes/", payload, format="json")

    def test_single_edit_updates_total_mark_and_audit_without_changing_creator(self):
        record = self.create()
        student = self.student_login()
        response = self.change(self.preview(record), kind="negative", score=-2, template="rules")
        self.assertEqual(response.status_code, 200)
        result = student.get("/api/student/scores/").json()
        self.assertEqual(result["total"], -2)
        self.assertTrue(result["results"][0]["is_modified"])
        self.assertEqual(result["results"][0]["creator_id"], self.owner.pk)
        audit = self.client.get(self.base + "score-events/").json()["results"][0]
        self.assertEqual(audit["action"], "edited")
        self.assertEqual(audit["before"]["score"], 3)
        self.assertEqual(audit["after"]["score"], -2)

    def test_soft_delete_hides_effective_record_and_pending_reason_and_retries_once(self):
        record = self.create(kind="negative", score=-5, template="other", note="")
        student = self.student_login()
        preview = self.preview(record)
        request_id = str(uuid.uuid4())
        for _ in range(2):
            response = self.change(preview, "delete", request_id=request_id)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(student.get("/api/student/scores/").json()["total"], 0)
        self.assertEqual(student.get("/api/student/scores/").json()["count"], 0)
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 0)
        self.assertEqual(self.client.get(self.base + "pending-reasons/").json()["count"], 0)
        events = self.client.get(self.base + "score-events/").json()
        self.assertEqual(events["count"], 2)
        self.assertEqual(events["results"][0]["action"], "deleted")
        self.assertEqual(events["results"][0]["before"]["score"], -5)
        self.assertIsNotNone(events["results"][0]["after"]["deleted_at"])
        response = self.client.post(
            self.base + "pending-reasons/",
            {"request_id": str(uuid.uuid4()), "record_ids": [record["id"]], "note": "不可補回"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def batch(self):
        self.client.post(self.base + "students/", {"text": "3\t小華\t003\n4\t小文\t004"})
        students = self.client.get(self.base + "students/").json()
        payload = self.payload(score=2)
        del payload["student_id"]
        response = self.client.post(
            self.base + "score-batches/",
            {**payload, "student_ids": [s["id"] for s in students]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["results"]

    def test_batch_skips_individual_edits_and_deletions_and_remains_batch_editable(self):
        records = self.batch()
        self.assertEqual(self.change(self.preview(records[0])).status_code, 200)
        self.assertEqual(self.change(self.preview(records[1]), "delete").status_code, 200)
        preview = self.preview(records[2], "batch")
        self.assertEqual([r["id"] for r in preview["targets"]], [r["id"] for r in records[2:]])
        self.assertEqual({r["id"] for r in preview["skipped"]}, {r["id"] for r in records[:2]})
        self.assertEqual(self.change(preview, score=3).status_code, 200)
        self.assertEqual(self.change(self.preview(records[2], "batch"), score=4).status_code, 200)
        roster = self.client.get(self.base + "score-roster/").json()["students"]
        self.assertEqual([s["total"] for s in roster], [1, 0, 4, 4])
        results = self.client.get(self.base + "scores/").json()["results"]
        self.assertEqual({r["batch_id"] for r in results}, {records[0]["batch_id"]})

    def test_stale_batch_preview_cancels_all_targets_and_retry_is_idempotent(self):
        records = self.batch()
        stale = self.preview(records[0], "batch")
        self.assertEqual(self.change(self.preview(records[1]), score=7).status_code, 200)
        self.assertEqual(self.change(stale, score=9).status_code, 400)
        roster = self.client.get(self.base + "score-roster/").json()["students"]
        self.assertEqual([s["total"] for s in roster], [2, 7, 2, 2])
        fresh = self.preview(records[0], "batch")
        request_id = str(uuid.uuid4())
        for _ in range(2):
            self.assertEqual(self.change(fresh, score=8, request_id=request_id).status_code, 200)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 8)
        self.assertEqual(self.change(fresh, score=9, request_id=request_id).status_code, 400)

    def test_ownership_cannot_be_transferred_and_revoked_member_cannot_retry(self):
        colleague = User.objects.create_user(
            username="co-edit", display_name="陳老師", email_verified=True
        )
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=colleague, role="coTeacher"
        )
        teacher = APIClient()
        teacher.force_login(colleague)
        mine = self.create()
        theirs = teacher.post(self.base + "scores/", self.payload(), format="json").json()
        self.assertEqual(
            teacher.get(self.base + f"scores/{mine['id']}/edit-preview/").status_code, 404
        )
        self.assertEqual(
            self.change(self.preview(theirs), creator_id=self.owner.pk).status_code, 400
        )
        self.assertEqual(
            self.change(self.preview(theirs), student_id=self.students[1]["id"]).status_code, 400
        )
        self.assertEqual(self.change(self.preview(theirs)).status_code, 200)
        # Homeroom editing preserves the colleague's ownership and ability to correct it.
        preview = self.preview(theirs, client=teacher)
        request_id = str(uuid.uuid4())
        self.assertEqual(
            self.change(preview, client=teacher, request_id=request_id).status_code, 200
        )
        self.assertEqual(teacher.get(self.base + "score-events/").status_code, 404)
        member.approved = False
        member.inactive_status = "removed"
        member.save()
        self.assertEqual(
            self.change(preview, client=teacher, request_id=request_id).status_code, 404
        )
        result = self.client.get(self.base + "scores/").json()["results"][0]
        self.assertEqual(result["creator_id"], colleague.pk)
        self.assertEqual(self.change(self.preview(theirs), "delete").status_code, 200)

    def test_preview_is_bound_to_actor_class_and_signed_contents_and_csrf(self):
        record = self.create()
        preview = self.preview(record)
        forged = {**preview, "token": preview["token"] + "tamper"}
        self.assertEqual(self.change(forged).status_code, 400)
        other = self.client.post(
            "/api/classes/", {"name": "別班", "entry_year": 2026, "current_grade": 1}
        ).json()
        response = self.client.post(
            f"/api/classes/{other['id']}/score-changes/",
            {
                "action": "delete",
                "preview_token": preview["token"],
                "request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        colleague = User.objects.create_user(username="other-editor", email_verified=True)
        ClassMember.objects.create(cohort_id=self.cohort["id"], user=colleague, role="coTeacher")
        teacher = APIClient()
        teacher.force_login(colleague)
        self.assertEqual(self.change(preview, client=teacher).status_code, 400)
        for client in (APIClient(), self.student_login()):
            self.assertEqual(self.change(preview, client=client).status_code, 403)
            self.assertEqual(
                client.get(self.base + f"scores/{record['id']}/edit-preview/").status_code, 403
            )
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(self.change(preview, client=protected).status_code, 403)
        self.assertEqual(self.client.get(self.base + "score-events/").json()["count"], 1)

    def test_filling_reason_invalidates_preview_and_protects_it_from_batch_overwrite(self):
        records = self.batch()
        self.assertEqual(
            self.change(self.preview(records[0]), template="other", note="").status_code, 200
        )
        preview = self.preview(records[0])
        response = self.client.post(
            self.base + "pending-reasons/",
            {"request_id": str(uuid.uuid4()), "record_ids": [records[0]["id"]], "note": "已補原因"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.change(preview).status_code, 400)
        batch = self.preview(records[1], "batch")
        self.assertEqual([r["id"] for r in batch["skipped"]], [records[0]["id"]])
        self.assertEqual(self.change(batch, "delete").status_code, 400)

    def test_deleted_record_stays_deleted_on_original_create_retry_and_permanent_cleanup(self):
        payload = self.payload()
        record = self.client.post(self.base + "scores/", payload, format="json").json()
        kept = self.create(student_id=self.students[1]["id"], score=8)
        self.assertEqual(self.change(self.preview(record), "delete").status_code, 200)
        self.assertEqual(
            self.client.post(self.base + "scores/", payload, format="json").status_code, 200
        )
        self.assertEqual(self.client.get(self.base + "scores/").json()["count"], 1)
        # Permanent removal is the agreed exception where database absence must be proven.
        response = self.client.delete(
            self.base + f"students/{record['student_id']}/",
            {"confirmation_student_number": "001"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ScoreRecord.objects.filter(pk=record["id"]).exists())
        self.assertFalse(ScoreAuditEvent.objects.filter(record_id=record["id"]).exists())
        self.assertEqual(
            self.client.get(self.base + "scores/").json()["results"][0]["id"], kept["id"]
        )
        self.assertEqual(self.change(self.preview(kept), "delete").status_code, 200)
        self.assertEqual(
            self.client.delete(
                self.base, {"confirmation_name": "記分班"}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(ScoreRecord.objects.filter(pk=kept["id"]).exists())
        self.assertFalse(ScoreAuditEvent.objects.filter(record_id=kept["id"]).exists())
