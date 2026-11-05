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

from django.apps import apps  # noqa: E402
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
                "items": [
                    {"record_id": record["id"], "revision": record["revision"], "points": 25}
                ],
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
                "/api/student/roles/purchases/",
                {
                    "role": "rabbit" if students[0]["avatar"] != "rabbit" else "cat",
                    "request_id": str(uuid.uuid4()),
                },
                format="json",
            ).status_code
            == 201
        )
        roles = student.get("/api/student/roles/").json()
        data["purchased_role"] = next(role for role in roles["owned"] if role != roles["selected"])
        assert (
            student.post("/api/student/roles/", {"role": data["purchased_role"]}).status_code == 200
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
    assert mascot["point_balance"] == 3
    assert mascot["mascot"]["exp"] == 2
    assert student.get(base + "students/").status_code == 403
    if mode == "seed":
        body = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "restore drill"}]}
            ],
        }
        published = teacher.post(
            base + "announcements/",
            {"request_id": str(uuid.uuid4()), "title": "Restore v1", "body": body},
            format="json",
        )
        assert published.status_code == 201
        item = published.json()
        read_path = f"/api/student/announcements/{item['id']}/read/"
        assert student.post(read_path, {"content_version": 1}).status_code == 200
        edited = teacher.post(
            base + f"announcements/{item['id']}/",
            {
                "request_id": str(uuid.uuid4()),
                "action": "edit",
                "revision": item["revision"],
                "title": "Restore v2",
                "body": body,
            },
            format="json",
        )
        assert edited.status_code == 200
        assert edited.json()["content_version"] == 2
        reminders = teacher.post(
            base + f"announcements/{item['id']}/reminders/",
            {
                "request_id": str(uuid.uuid4()),
                "content_version": 2,
                "student_id": students[0]["id"],
            },
            format="json",
        )
        assert reminders.status_code == 201
        assert reminders.json()["sent"] == 1
        inbox = student.get("/api/notifications/").json()
        reminder = next(row for row in inbox["results"] if row["kind"] == "announcement_reminder")
        assert student.post(f"/api/notifications/{reminder['id']}/open/").status_code == 200
        roster = teacher.get(base + f"announcements/{item['id']}/read-receipts/").json()
        assert roster["read_count"] == 0
        assert student.post(read_path, {"content_version": 2}).status_code == 200
        data["announcement_id"] = item["id"]
    assert student.get("/api/student/roles/").json()["selected"] == data["purchased_role"]
    assert len(student.get("/api/student/roles/").json()["owned"]) == 2
    assert (
        teacher.get(base + f"announcements/{data['announcement_id']}/read-receipts/").json()[
            "read_count"
        ]
        == 1
    )
    assert (
        teacher.get(base + f"announcements/{data['announcement_id']}/reminders/").json()["count"]
        == 1
    )
    for kind in ("scores", "points"):
        assert student.get(f"/api/student/history/{kind}/").status_code == 200
        assert student.get(f"/api/student/history/{kind}/export/").status_code == 200
    # Compare all durable business rows, including versions, receipts, operations,
    # role ownership and notification read state. Sessions legitimately change on login.
    snapshot = {
        model.__name__: list(model.objects.order_by("pk").values())
        for model in apps.get_app_config("core").get_models()
        if model.__name__ != "AuthRateBucket"
    }
    for user in snapshot["User"]:
        user.pop("last_login", None)
    snapshot = json.loads(json.dumps(snapshot, default=str))
    if mode == "seed":
        data["snapshot"] = snapshot
        evidence.write_text(json.dumps(data), encoding="utf-8")
    else:
        changed = [name for name in snapshot if snapshot[name] != data["snapshot"].get(name)]
        assert not changed, f"Restored business rows differ: {changed}"
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
    print(
        "V2 restore probe passed: login, isolation, scores, roles, feeding, exports, versions, receipts, notifications and reminders."
    )


if __name__ == "__main__":
    run(sys.argv[1], Path(sys.argv[2]))
