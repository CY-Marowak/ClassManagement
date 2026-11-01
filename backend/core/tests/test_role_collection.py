from rest_framework.test import APIClient, APITestCase

from core.models import User


class RoleCollectionTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="roles-teacher",
            email="roles@example.com",
            display_name="老師",
            email_verified=True,
        )
        self.client.force_login(self.teacher)
        self.cohort = self.client.post(
            "/api/classes/", {"name": "收藏班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.roster_url = f"/api/classes/{self.cohort['id']}/students/"
        self.rows = "1\t小明\t00001\n2\t小華\t00002"
        self.client.post(self.roster_url, {"text": self.rows})
        self.student = APIClient()
        self.login()
        self.student.post("/api/student/change-password/", {"password": "Roles!Garden2026"})

    def login(self, password="00001"):
        response = self.student.post(
            "/api/student/login/",
            {
                "class_code": self.cohort["student_login_code"],
                "student_number": "00001",
                "password": password,
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_initial_collection_and_reimport_keep_one_free_role_without_spending(self):
        profile = self.student.get("/api/student/me/").json()
        response = self.student.get("/api/student/roles/")
        self.assertEqual(response.status_code, 200)
        collection = response.json()
        self.assertEqual(collection["selected"], profile["avatar"])
        self.assertEqual(collection["owned"], [profile["avatar"]])
        self.assertEqual(
            [(role["id"], role["name"]) for role in collection["catalog"]],
            [
                ("rat", "鼠"),
                ("cow", "牛"),
                ("tiger", "虎"),
                ("rabbit", "兔"),
                ("dragon", "龍"),
                ("snake", "蛇"),
                ("horse", "馬"),
                ("goat", "羊"),
                ("monkey", "猴"),
                ("rooster", "雞"),
                ("dog", "狗"),
                ("pig", "豬"),
                ("cat", "貓"),
            ],
        )
        self.assertEqual(
            self.client.post(self.roster_url, {"text": self.rows}).json()["summary"]["skipped"], 2
        )
        self.assertEqual(self.student.get("/api/student/roles/").json(), collection)
        self.assertEqual(self.student.get("/api/student/me/").json(), profile)
        self.assertEqual(self.student.get("/api/student/mascot/").json()["transactions"], [])

    def test_select_owned_role_persists_and_rejects_unowned_or_foreign_selection(self):
        from core.models import Student, StudentRoleOwnership

        profile = self.student.get("/api/student/me/").json()
        alternate = "dragon" if profile["avatar"] != "dragon" else "cow"
        # Owned inventory fixture; buying is a separate ticket, not a hidden grant API.
        StudentRoleOwnership.objects.create(student_id=profile["id"], role=alternate)
        before = self.student.get("/api/student/mascot/").json()
        response = self.student.post("/api/student/roles/", {"role": alternate})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected"], alternate)
        self.assertEqual(set(response.json()["owned"]), {alternate, profile["avatar"]})
        self.assertEqual(self.student.get("/api/student/me/").json()["avatar"], alternate)
        self.assertEqual(
            self.student.post("/api/student/roles/", {"role": alternate}).status_code, 200
        )
        foreign = Student.objects.exclude(pk=profile["id"]).get()
        unowned = next(
            r for r in ["rat", "snake", "pig"] if r not in (profile["avatar"], alternate)
        )
        ownership, _ = StudentRoleOwnership.objects.get_or_create(student=foreign, role=unowned)
        for payload in [
            {"role": unowned},
            {"role": "invalid"},
            {},
            {"role": alternate, "student_id": foreign.pk},
            {"role": alternate, "ownership_id": ownership.pk},
        ]:
            self.assertEqual(self.student.post("/api/student/roles/", payload).status_code, 400)
        self.assertEqual(self.student.get("/api/student/mascot/").json(), before)
        self.student.post("/api/auth/logout/")
        self.login("Roles!Garden2026")
        self.assertEqual(self.student.get("/api/student/roles/").json()["selected"], alternate)

    def test_collection_requires_ready_student_and_csrf_and_ignores_foreign_query(self):
        from core.models import Student

        profile = self.student.get("/api/student/me/").json()
        original = self.student.get("/api/student/roles/").json()
        foreign = Student.objects.exclude(pk=profile["id"]).get()
        self.assertEqual(
            self.student.get(f"/api/student/roles/?student_id={foreign.pk}").json(), original
        )
        pending = APIClient()
        pending.force_login(foreign.user)
        for client in [self.client, APIClient(), pending]:
            self.assertEqual(client.get("/api/student/roles/").status_code, 403)
            self.assertEqual(
                client.post("/api/student/roles/", {"role": profile["avatar"]}).status_code, 403
            )
        protected = APIClient(enforce_csrf_checks=True)
        protected.force_login(Student.objects.get(pk=profile["id"]).user)
        self.assertEqual(
            protected.post("/api/student/roles/", {"role": profile["avatar"]}).status_code, 403
        )
        token = protected.get("/api/csrf/").json()["csrfToken"]
        self.assertEqual(
            protected.post(
                "/api/student/roles/", {"role": profile["avatar"]}, HTTP_X_CSRFTOKEN=token
            ).status_code,
            200,
        )
        self.client.post(f"{self.roster_url}{profile['id']}/reset-password/")
        self.assertEqual(self.student.get("/api/student/roles/").status_code, 403)
        self.assertEqual(
            self.student.post("/api/student/roles/", {"role": profile["avatar"]}).status_code, 403
        )
