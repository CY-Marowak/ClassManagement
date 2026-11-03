import csv
import io
import uuid
from datetime import datetime, timezone

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, PointTransaction, ScoreRecord, User

from . import test_mascots


class HistoryTests(APITestCase):
    setUp = test_mascots.MascotTests.setUp
    student_login = test_mascots.MascotTests.student_login
    award = test_mascots.MascotTests.award
    feed = test_mascots.MascotTests.feed

    def csv_rows(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("attachment;", response["Content-Disposition"])
        return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))

    def test_old_points_beyond_recent_twenty_are_pageable_and_exportable(self):
        for _ in range(28):
            PointTransaction.objects.create(
                student_id=self.students[0]["id"], kind="feed", points=-1, request_id=uuid.uuid4()
            )
        student = self.student_login()
        url = "/api/student/history/points/"
        self.assertEqual(student.get(url).json()["count"], 28)
        self.assertEqual(len(student.get(url, {"page": 2}).json()["results"]), 3)
        self.assertEqual(len(self.csv_rows(student.get(url + "export/", {"page": 2}))), 28)

    def test_deleted_student_session_cannot_download_and_other_students_keep_access(self):
        first = self.student_login()
        second = self.student_login("002")
        self.award(4)
        self.award(7, 1)
        response = self.client.delete(
            self.base + f"students/{self.students[0]['id']}/",
            {"confirmation_student_number": "001"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        for kind in ["scores", "points"]:
            url = f"/api/student/history/{kind}/export/"
            self.assertEqual(first.get(url).status_code, 403)
            self.assertEqual(len(self.csv_rows(second.get(url))), 1)

    def test_personal_scores_page_and_csv_share_taipei_inclusive_dates(self):
        # Arrange old history; observable results are read via authenticated HTTP.
        for number in range(28):
            record = ScoreRecord.objects.create(
                cohort_id=self.cohort["id"],
                student_id=self.students[0]["id"],
                creator=self.owner,
                creator_name="老師",
                request_id=uuid.uuid4(),
                kind="positive",
                score=1,
                template="other",
                reason="其他",
                note="",
            )
            ScoreRecord.objects.filter(pk=record.pk).update(
                created_at=datetime(2026, 11, 2, 16, number, tzinfo=timezone.utc)
            )
        student = self.student_login()
        url = "/api/student/history/scores/"
        filters = {"start": "2026-11-03", "end": "2026-11-03"}
        response = student.get(url, filters)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 28)
        self.assertEqual(len(response.json()["results"]), 25)
        self.assertEqual(len(student.get(url, {**filters, "page": 2}).json()["results"]), 3)
        rows = self.csv_rows(student.get(url + "export/", {**filters, "page": 2}))
        self.assertEqual(len(rows), 28)
        self.assertEqual(rows[-1]["紀錄時間（台北）"], "2026-11-03 00:00:00")
        self.assertEqual(rows[-1]["待補原因"], "是")
        self.assertNotIn("學號", rows[0])
        self.assertEqual(student.get(url, {"end": "2026-11-02"}).json()["count"], 0)

    def test_points_include_awards_feeding_purchases_and_export_all_filters(self):
        student = self.student_login()
        self.award(30)
        self.award(7, 1)
        self.assertEqual(self.feed(student, 2).status_code, 201)
        collection = student.get("/api/student/roles/").json()
        role = next(
            item["id"] for item in collection["catalog"] if item["id"] not in collection["owned"]
        )
        response = student.post(
            "/api/student/roles/purchases/",
            {"role": role, "request_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        url = "/api/student/history/points/"
        data = student.get(url).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual([r["amount"] for r in data["results"]], [-20, -2, 30])
        self.assertEqual([r["kind"] for r in data["results"]], ["購買角色", "餵食", "獲得點數"])
        for kind, amount in [("purchase", "-20"), ("feed", "-2"), ("award", "30")]:
            filtered = student.get(url, {"kind": kind}).json()
            rows = self.csv_rows(student.get(url + "export/", {"kind": kind}))
            self.assertEqual((filtered["count"], len(rows)), (1, 1))
            self.assertEqual(rows[0]["點數"], amount)
        purchase = PointTransaction.objects.get(student_id=self.students[0]["id"], kind="purchase")
        PointTransaction.objects.filter(pk=purchase.pk).update(
            created_at=datetime(2026, 11, 3, 15, 59, 59, tzinfo=timezone.utc)
        )
        filters = {"start": "2026-11-03", "end": "2026-11-03", "kind": "purchase"}
        self.assertEqual(student.get(url, filters).json()["count"], 1)
        self.assertEqual(
            self.csv_rows(student.get(url + "export/", filters))[0]["交易時間（台北）"],
            "2026-11-03 23:59:59",
        )
        PointTransaction.objects.filter(pk=purchase.pk).update(
            created_at=datetime(2026, 11, 3, 16, tzinfo=timezone.utc)
        )
        self.assertEqual(student.get(url, filters).json()["count"], 0)
        self.assertEqual(self.csv_rows(student.get(url + "export/", filters)), [])

    def test_teacher_export_matches_current_scores_student_filter_and_safe_csv_text(self):
        self.award(3)
        self.award(5, 1)
        record = ScoreRecord.objects.get(student_id=self.students[0]["id"])
        special = '中文,引號"及\n換行'
        for text in [
            "=1+1",
            "+SUM(A1)",
            "-1+2",
            "@SUM(A1)",
            "  =1",
            "\t=1",
            "\r=1",
            "\n=1",
            "\ufeff=1",
            "＝1",
        ]:
            ScoreRecord.objects.filter(pk=record.pk).update(note=text, is_modified=True)
            response = self.client.get(
                self.base + "history/scores/export/", {"student_id": self.students[0]["id"]}
            )
            row = self.csv_rows(response)[0]
            self.assertEqual(row["補充原因"], "'" + text)
            self.assertEqual(row["學號"], "001")
            self.assertEqual(row["已修改"], "是")
        ScoreRecord.objects.filter(pk=record.pk).update(note=special, reason="已修正原因")
        rows = self.csv_rows(
            self.client.get(
                self.base + "history/scores/export/", {"student_id": self.students[0]["id"]}
            )
        )
        self.assertEqual((rows[0]["原因"], rows[0]["補充原因"]), ("已修正原因", special))
        self.assertEqual(
            len(self.csv_rows(self.client.get(self.base + "history/points/export/"))), 2
        )
        ScoreRecord.objects.filter(pk=record.pk).update(deleted_at=datetime.now(timezone.utc))
        self.assertEqual(
            self.client.get(
                self.base + "history/scores/", {"student_id": self.students[0]["id"]}
            ).json()["count"],
            0,
        )
        self.assertEqual(
            len(self.csv_rows(self.client.get(self.base + "history/scores/export/"))), 1
        )
        points = self.csv_rows(
            self.client.get(
                self.base + "history/points/export/", {"student_id": self.students[0]["id"]}
            )
        )
        self.assertEqual(
            (points[0]["點數"], points[0]["原因"], points[0]["補充原因"]),
            ("3", "來源分數已刪除", ""),
        )

    def test_filters_empty_export_and_direct_download_authorization(self):
        student = self.student_login()
        pending = self.student_login("002", change=False)
        outsider = User.objects.create_user(username="history-other", email_verified=True)
        other = APIClient()
        other.force_login(outsider)
        membership = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=outsider, role="coTeacher", approved=True
        )
        other_class = other.post(
            "/api/classes/", {"name": "別班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.client.post(self.base + "students/", {"text": "3\t隔離同學\t003"})
        for kind in ["scores", "points"]:
            url = f"/api/student/history/{kind}/"
            export = url + "export/"
            self.assertEqual(self.csv_rows(student.get(export)), [])
            self.assertEqual(APIClient().get(export).status_code, 403)
            self.assertEqual(pending.get(export).status_code, 403)
            self.assertEqual(self.client.get(export).status_code, 403)
            self.assertEqual(
                student.get(export, {"student_id": self.students[1]["id"]}).status_code, 400
            )
            teacher_export = self.base + f"history/{kind}/export/"
            self.assertEqual(student.get(teacher_export).status_code, 403)
            self.assertEqual(other.get(teacher_export).status_code, 404)
            self.assertEqual(
                self.client.get(
                    f"/api/classes/{other_class['id']}/history/{kind}/export/"
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(teacher_export, {"student_id": 999999}).status_code, 404
            )
            for invalid in [
                {"start": "bad"},
                {"end": "2026-02-30"},
                {"start": "2026-11-04", "end": "2026-11-03"},
                {"end": "9999-12-31"},
                {"page": 0},
                {"secret": "anything"},
                {"kind": "invalid"},
            ]:
                self.assertEqual(student.get(export, invalid).status_code, 400)
            self.assertEqual(student.get(url, {"page": 2}).status_code, 404)
        membership.approved = False
        membership.save()
        self.assertEqual(other.get(self.base + "history/points/export/").status_code, 404)
        self.client.post(self.base + f"students/{self.students[0]['id']}/reset-password/")
        for kind in ["scores", "points"]:
            self.assertEqual(student.get(f"/api/student/history/{kind}/export/").status_code, 403)
