import uuid

from rest_framework.test import APIClient, APITestCase

from core.models import ClassMember, PointTransaction, Student, StudentRoleOwnership, User

from . import test_mascots, test_scores


class RoleShopTests(APITestCase):
    setUp = test_scores.ScoreTests.setUp
    student_login = test_scores.ScoreTests.student_login
    award = test_mascots.MascotTests.award
    feed = test_mascots.MascotTests.feed

    def buy(self, client, role, request_id=None, **extra):
        return client.post(
            "/api/student/roles/purchases/",
            {"role": role, "request_id": request_id or str(uuid.uuid4()), **extra},
            format="json",
        )

    def unowned(self, client):
        data = client.get("/api/student/roles/").json()
        return [r["id"] for r in data["catalog"] if r["id"] not in data["owned"]]

    def test_purchase_retry_preserves_selection_and_score_then_free_switch(self):
        student = self.student_login()
        self.award(25)
        before = student.get("/api/student/roles/").json()
        self.assertEqual(before["point_balance"], 25)
        self.assertEqual({r["price"] for r in before["catalog"]}, {20})
        role, other = self.unowned(student)[:2]
        identity = str(uuid.uuid4())
        first = self.buy(student, role, identity)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["role"], role)
        self.assertEqual(first.json()["kind"], "purchase")
        self.assertEqual(self.buy(student, role, identity).json(), first.json())
        self.assertEqual(self.buy(student, other, identity).status_code, 400)
        self.assertEqual(self.buy(student, role).status_code, 400)
        after = student.get("/api/student/roles/").json()
        self.assertEqual(after["point_balance"], 5)
        self.assertEqual(after["selected"], before["selected"])
        self.assertEqual(set(after["owned"]), {*before["owned"], role})
        account = student.get("/api/student/mascot/").json()
        self.assertEqual(account["daily_remaining"], 5)
        self.assertEqual(account["mascot"]["exp"], 0)
        self.assertEqual(account["transactions"][0], first.json())
        self.assertEqual(account["transactions"][1]["source"]["reason"], "積極參與")
        self.assertEqual(student.get("/api/student/scores/").json()["total"], 3)
        self.assertEqual(student.post("/api/student/roles/", {"role": role}).status_code, 200)
        self.assertEqual(student.get("/api/student/roles/").json()["point_balance"], 5)
        self.assertEqual(self.feed(student, 1, identity).status_code, 400)
        feed_id = str(uuid.uuid4())
        self.assertEqual(self.feed(student, 1, feed_id).status_code, 201)
        self.assertEqual(self.buy(student, other, feed_id).status_code, 400)

    def test_insufficient_unknown_or_tampered_purchase_does_not_spend(self):
        student = self.student_login()
        self.award(19)
        role = self.unowned(student)[0]
        before = student.get("/api/student/roles/").json()
        for changes in [
            {},
            {"price": 1},
            {"student_id": self.students[1]["id"]},
            {"cohort_id": 999},
        ]:
            self.assertEqual(self.buy(student, role, **changes).status_code, 400)
        self.assertEqual(self.buy(student, "bear").status_code, 400)
        self.assertEqual(student.get("/api/student/roles/").json(), before)
        self.assertEqual(PointTransaction.objects.count(), 1)

    def test_purchase_requires_own_ready_session_and_csrf(self):
        initial = self.student_login(change=False)
        self.assertEqual(self.buy(initial, "dragon").status_code, 403)
        self.assertEqual(self.buy(APIClient(), "dragon").status_code, 403)
        self.assertEqual(self.buy(self.client, "dragon").status_code, 403)
        teacher = User.objects.create_user(username="coworker", email_verified=True)
        ClassMember.objects.create(cohort_id=self.cohort["id"], user=teacher, role="teacher")
        colleague = APIClient()
        colleague.force_login(teacher)
        self.assertEqual(self.buy(colleague, "dragon").status_code, 403)
        initial.post("/api/student/change-password/", {"password": "Garden!Meadow2026"})
        self.award(40)
        role = self.unowned(initial)[0]
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.cookies = initial.cookies.copy()
        self.assertEqual(self.buy(csrf, role).status_code, 403)
        token = csrf.get("/api/csrf/").json()["csrfToken"]
        csrf.credentials(HTTP_X_CSRFTOKEN=token)
        self.assertEqual(self.buy(csrf, role).status_code, 201)
        peer = self.student_login("002")
        self.assertEqual(self.buy(peer, self.unowned(peer)[0]).status_code, 400)
        self.assertEqual(peer.get("/api/student/mascot/").json()["transactions"], [])
        self.client.post(f"{self.base}students/{self.students[0]['id']}/reset-password/")
        self.assertEqual(self.buy(csrf, self.unowned(peer)[1]).status_code, 403)

    def test_student_and_class_deletion_remove_purchases_but_keep_other_class(self):
        student = self.student_login()
        self.award(40)
        self.assertEqual(self.buy(student, self.unowned(student)[0]).status_code, 201)
        original = self.cohort
        original_base = self.base
        original_id = self.students[0]["id"]
        self.cohort = self.client.post(
            "/api/classes/", {"name": "另一班", "entry_year": 2026, "current_grade": 1}
        ).json()
        self.base = f"/api/classes/{self.cohort['id']}/"
        self.client.post(self.base + "students/", {"text": "1\t小安\t001"})
        self.students = self.client.get(self.base + "students/").json()
        other = self.student_login()
        self.award(25)
        self.assertEqual(self.buy(other, self.unowned(other)[0]).status_code, 201)
        snapshot = other.get("/api/student/mascot/").json()
        other_roles = other.get("/api/student/roles/").json()
        self.assertEqual(
            self.buy(
                student, self.unowned(student)[0], student_id=self.students[0]["id"]
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.delete(
                f"{original_base}students/{original_id}/",
                {"confirmation_student_number": "001"},
                format="json",
            ).status_code,
            200,
        )
        self.assertFalse(PointTransaction.objects.filter(student_id=original_id).exists())
        self.assertFalse(StudentRoleOwnership.objects.filter(student_id=original_id).exists())
        self.assertEqual(self.buy(student, "dragon").status_code, 403)
        self.assertEqual(other.get("/api/student/mascot/").json(), snapshot)
        self.assertEqual(other.get("/api/student/roles/").json(), other_roles)
        # Delete the class containing the second real purchase; the first class survives.
        response = self.client.delete(
            self.base, {"confirmation_name": self.cohort["name"]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PointTransaction.objects.exists())
        self.assertEqual(self.buy(other, "dragon").status_code, 403)
        self.assertEqual(Student.objects.filter(cohort_id=original["id"]).count(), 1)
