from rest_framework.test import APITestCase

from core.models import User


class ImportIssueTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="import-owner", email="import@example.com", email_verified=True
        )
        self.client.force_login(self.owner)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "匯入班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{self.cohort['id']}/"

    def test_errors_survive_sessions_accumulate_and_resolve_only_explicitly(self):
        self.client.post(self.base + "students/", {"text": "1\t小明\t001\n2\t缺欄"})
        self.client.logout()
        self.client.force_login(self.owner)
        response = self.client.get(self.base + "import-issues/")
        self.assertEqual(response.status_code, 200)
        first = response.json()["results"][0]
        self.assertEqual(first["raw"], "2\t缺欄")
        self.assertEqual(first["line"], 2)
        self.client.post(self.base + "students/", {"text": "2\t小美\t002\n3\t缺欄"})
        self.assertEqual(self.client.get(self.base + "import-issues/").json()["count"], 2)
        self.assertEqual(self.client.get(self.base + "dashboard/").json()["pending_students"], 2)
        url = self.base + f"import-issues/{first['id']}/"
        result = self.client.post(
            url,
            {
                "action": "retry",
                "revision": first["revision"],
                "raw": "1\t小美\t002",
            },
        ).json()
        self.assertEqual(result["status"], "pending")
        self.assertIn("學號已存在", result["message"])
        self.assertEqual(
            self.client.post(
                url,
                {
                    "action": "ignore",
                    "revision": first["revision"],
                },
            ).status_code,
            409,
        )
        payload = {"action": "retry", "revision": result["revision"], "raw": "2\t小美\t002"}
        result = self.client.post(url, payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["status"], "resolved")
        # A lost response can safely be retried: it never creates another student.
        self.assertEqual(self.client.post(url, payload).status_code, 200)
        self.assertEqual(len(self.client.get(self.base + "students/").json()), 2)
        remaining = self.client.get(self.base + "import-issues/").json()["results"][0]
        result = self.client.post(
            self.base + f"import-issues/{remaining['id']}/",
            {
                "action": "retry",
                "revision": remaining["revision"],
                "raw": "3\t小華\t003",
            },
        )
        self.assertEqual(result.json()["status"], "resolved")
        self.assertEqual(len(self.client.get(self.base + "students/").json()), 3)
        self.assertEqual(self.client.get(self.base + "dashboard/").json()["pending_students"], 0)

    def test_ignore_pagination_roles_csrf_and_permanent_class_deletion(self):
        from rest_framework.test import APIClient

        from core.models import ClassMember, StudentImportIssue

        self.client.post(self.base + "students/", {"text": "\n".join(["缺欄"] * 26)})
        page = self.client.get(self.base + "import-issues/").json()
        self.assertEqual(page["count"], 26)
        self.assertEqual(len(page["results"]), 25)
        issue = page["results"][0]
        url = self.base + f"import-issues/{issue['id']}/"
        payload = {"action": "ignore", "revision": 1}
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(protected.post(url, payload).status_code, 403)
        stranger = User.objects.create_user(username="stranger", email="stranger@example.com")
        member = ClassMember.objects.create(
            cohort_id=self.cohort["id"], user=stranger, role="coTeacher", approved=False
        )
        for approved, status in [(False, "pending"), (True, "pending"), (False, "removed")]:
            member.approved, member.inactive_status = approved, status
            member.save()
            self.client.force_login(stranger)
            for suffix in ("dashboard/", "import-issues/"):
                self.assertEqual(self.client.get(self.base + suffix).status_code, 404)
            self.assertEqual(self.client.post(url, payload).status_code, 404)
        self.client.force_login(self.owner)
        other = self.client.post(
            "/api/classes/", {"name": "保留班", "entry_year": 2026, "current_grade": 1}
        ).json()
        other_base = f"/api/classes/{other['id']}/"
        self.assertEqual(self.client.get(other_base + "dashboard/").json()["pending_students"], 0)
        self.client.post(other_base + "students/", {"text": "保留錯誤"})
        self.assertEqual(
            self.client.post(other_base + f"import-issues/{issue['id']}/", payload).status_code, 404
        )
        self.assertEqual(self.client.post(url, payload).json()["status"], "ignored")
        self.assertEqual(self.client.get(self.base + "import-issues/").json()["count"], 25)
        response = self.client.delete(self.base, {"confirmation_name": "匯入班"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentImportIssue.objects.filter(cohort_id=self.cohort["id"]).exists())
        self.assertEqual(self.client.get(other_base + "import-issues/").json()["count"], 1)
