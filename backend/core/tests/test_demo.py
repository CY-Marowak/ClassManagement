import io
import json
import uuid

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APITestCase


@override_settings(DEBUG=True)
class DemoTests(APITestCase):
    @override_settings(DEBUG=False)
    def test_demo_requires_local_development_mode(self):
        from django.core.management import CommandError

        from core.models import Cohort

        with self.assertRaises(CommandError):
            call_command("create_demo", stdout=io.StringIO())
        self.assertFalse(Cohort.objects.exists())

    def test_two_runs_preserve_each_other_and_demo_supports_real_login_award_and_feeding(self):
        output = io.StringIO()
        call_command("create_demo", stdout=output)
        first = json.loads(output.getvalue())
        output = io.StringIO()
        call_command("create_demo", stdout=output)
        second = json.loads(output.getvalue())
        self.assertNotEqual(first["cohort"]["id"], second["cohort"]["id"])
        self.assertNotEqual(
            first["teachers"]["homeroom"]["email"], second["teachers"]["homeroom"]["email"]
        )
        self.assertEqual(
            self.client.post("/api/auth/login/", first["teachers"]["homeroom"]).status_code, 200
        )
        base = f"/api/classes/{first['cohort']['id']}/"
        dashboard = self.client.get(base + "dashboard/").json()
        self.assertEqual(dashboard["pending_students"], 2)
        self.assertEqual(dashboard["pending_teachers"], 1)
        self.assertEqual(dashboard["pending_reasons"], 1)
        self.assertEqual(dashboard["today_scores"], 3)
        self.assertEqual(
            self.client.get(f"/api/classes/{second['cohort']['id']}/dashboard/").status_code, 404
        )
        students = self.client.get(base + "students/").json()
        source = self.client.post(
            base + "scores/",
            {
                "request_id": str(uuid.uuid4()),
                "student_id": students[0]["id"],
                "kind": "positive",
                "score": 3,
                "template": "helping",
                "note": "展示",
            },
        ).json()
        award = self.client.post(
            base + "point-awards/",
            {
                "request_id": str(uuid.uuid4()),
                "items": [{"record_id": source["id"], "revision": source["revision"], "points": 3}],
            },
            format="json",
        )
        self.assertEqual(award.status_code, 201)
        self.client.logout()
        self.assertEqual(self.client.post("/api/student/login/", first["student"]).status_code, 200)
        self.assertEqual(self.client.get(base + "dashboard/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/student/change-password/", {"password": "Demo!StudentGarden2026"}
            ).status_code,
            200,
        )
        response = self.client.post(
            "/api/student/mascot/", {"request_id": str(uuid.uuid4()), "points": 2}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/api/student/me/").json()["point_balance"], 1)
