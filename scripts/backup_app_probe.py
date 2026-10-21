"""Local-only fake-data fixture and restored API probe used by test_backup.py."""

import io
import json
import os
import sys
import uuid
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
django.setup()

from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402


def run(mode, evidence):
    db = settings.DATABASES["default"]
    if db["HOST"] not in ("localhost", "127.0.0.1") or not db["NAME"].startswith(
        ("cm_backup_test_", "cm_restore_")
    ):
        raise RuntimeError("Probe only supports dedicated local test databases.")
    if mode == "seed":
        call_command("migrate", verbosity=0, stdout=io.StringIO())
        output = io.StringIO()
        call_command("create_demo", stdout=output)
        data = json.loads(output.getvalue())
        evidence.write_text(json.dumps(data), encoding="utf-8")
    else:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    teacher = APIClient()
    assert teacher.post("/api/auth/login/", data["teachers"]["homeroom"]).status_code == 200
    base = f"/api/classes/{data['cohort']['id']}/"
    assert teacher.get(base).status_code == 200
    assert teacher.get(f"/api/classes/{data['other_cohort']['id']}/").status_code == 404
    students = teacher.get(base + "students/").json()
    assert len(students) == 3
    if mode == "seed":
        score = teacher.post(
            base + "scores/",
            {
                "request_id": str(uuid.uuid4()),
                "student_id": students[0]["id"],
                "kind": "positive",
                "score": 3,
                "template": "helping",
                "note": "restore drill",
            },
            format="json",
        )
        assert score.status_code == 201
        record = score.json()
        award = teacher.post(
            base + "point-awards/",
            {
                "request_id": str(uuid.uuid4()),
                "items": [{"record_id": record["id"], "revision": record["revision"], "points": 3}],
            },
            format="json",
        )
        assert award.status_code == 201
    student = APIClient()
    login = dict(data["student"])
    if mode != "seed":
        login["password"] = "Restore!StudentGarden2026"
    assert student.post("/api/student/login/", login).status_code == 200
    if mode == "seed":
        assert (
            student.post(
                "/api/student/change-password/",
                {
                    "password": "Restore!StudentGarden2026",
                },
            ).status_code
            == 200
        )
        assert (
            student.post(
                "/api/student/mascot/",
                {
                    "request_id": str(uuid.uuid4()),
                    "points": 2,
                },
                format="json",
            ).status_code
            == 201
        )
    assert student.get("/api/student/scores/").json()["total"] == 4
    mascot = student.get("/api/student/mascot/").json()
    assert mascot["point_balance"] == 1
    assert mascot["mascot"]["exp"] == 2
    assert student.get(base + "students/").status_code == 403
    if mode != "seed":
        assert (
            student.post(
                "/api/student/mascot/",
                {
                    "request_id": str(uuid.uuid4()),
                    "points": 1,
                },
                format="json",
            ).status_code
            == 201
        )
        assert student.get("/api/student/mascot/").json()["mascot"]["exp"] == 3
    print("Fake-data teacher/student login, isolation, scores, points and mascot probe passed.")


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]))
