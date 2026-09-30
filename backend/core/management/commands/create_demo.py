import json
import secrets
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Announcement,
    AnnouncementComment,
    ClassMember,
    Cohort,
    Mascot,
    Student,
    StudentImportIssue,
    TeacherAuditEvent,
    User,
)
from core.scores import create_score_with_audit
from core.students import import_student_row


def document(text):
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


class Command(BaseCommand):
    help = "Create a new, independent local demonstration. Existing data is never reset."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo 僅供本機開發，請設定 CM_DEBUG=1。")
        identity = uuid.uuid4().hex
        password = "Demo!" + secrets.token_urlsafe(16)
        credentials = {}
        teachers = {}
        with transaction.atomic():
            for role, name in [
                ("homeroom", "展示導師"),
                ("coTeacher", "展示共同教師"),
                ("pending", "展示待審教師"),
                ("other", "隔離班導師"),
            ]:
                email = f"demo-{role.lower()}-{identity}@example.com"
                teachers[role] = User.objects.create_user(
                    username=uuid.uuid4().hex,
                    email=email,
                    password=password,
                    display_name=name,
                    email_verified=True,
                )
                credentials[role] = {"email": email, "password": password}
            cohort = Cohort.objects.create(
                name=f"展示班 {identity[:8]}", entry_year=timezone.now().year, current_grade=1
            )
            other = Cohort.objects.create(
                name=f"隔離班 {identity[:8]}", entry_year=timezone.now().year, current_grade=1
            )
            for target, role, approved in [
                (cohort, "homeroom", True),
                (cohort, "coTeacher", True),
                (cohort, "pending", False),
                (other, "other", True),
            ]:
                member = ClassMember.objects.create(
                    cohort=target,
                    user=teachers[role],
                    approved=approved,
                    role="homeroom" if role in ("homeroom", "other") else "coTeacher",
                )
                if role in ("coTeacher", "pending"):
                    TeacherAuditEvent.objects.create(
                        cohort=target,
                        member=member,
                        actor=teachers[role],
                        actor_name=teachers[role].display_name,
                        teacher_name=teachers[role].display_name,
                        action="applied",
                        after={"status": "pending"},
                    )
                    if approved:
                        TeacherAuditEvent.objects.create(
                            cohort=target,
                            member=member,
                            actor=teachers["homeroom"],
                            actor_name=teachers["homeroom"].display_name,
                            teacher_name=teachers[role].display_name,
                            action="approved",
                            before={"status": "pending"},
                            after={"status": "approved"},
                        )
            Mascot.objects.create(cohort=cohort, animal="cat")
            Mascot.objects.create(cohort=other, animal="dog")
            batch = uuid.uuid4()
            for number, raw in enumerate(
                [
                    "1\t展示小晴\t001",
                    "2\t展示小安\t002",
                    "3\t展示小宇\t003",
                    "4\t展示小夏",
                    "5\t重複資料\t001",
                ],
                1,
            ):
                result = import_student_row(cohort, teachers["homeroom"], number, raw)
                if result["status"] == "error":
                    StudentImportIssue.objects.create(
                        cohort=cohort,
                        batch_id=batch,
                        line=number,
                        raw=raw,
                        message=result["message"],
                    )
            import_student_row(other, teachers["other"], 1, "1\t隔離班學生\t001")
            students = list(Student.objects.filter(cohort=cohort).select_related("user"))
            for student, role, template in [
                (students[0], "homeroom", "participation"),
                (students[1], "homeroom", "other"),
                (students[2], "coTeacher", "helping"),
            ]:
                create_score_with_audit(
                    teachers[role],
                    cohort.pk,
                    student,
                    {
                        "request_id": uuid.uuid4(),
                        "kind": "positive",
                        "score": 1,
                        "template": template,
                        "note": "",
                    },
                )
            announcement = Announcement.objects.create(
                cohort=cohort,
                creator=teachers["homeroom"],
                creator_name="展示導師",
                title="一起照顧班級吉祥物",
                body=document("完成課堂任務後，可自願使用點數餵食。"),
                is_pinned=True,
            )
            AnnouncementComment.objects.create(
                announcement=announcement,
                creator=teachers["coTeacher"],
                creator_name="展示共同教師",
                body=document("記得先完成自己的學習任務。"),
            )
        self.stdout.write(
            json.dumps(
                {
                    "demo_id": identity,
                    "teachers": credentials,
                    "cohort": {
                        "id": cohort.pk,
                        "name": cohort.name,
                        "student_login_code": cohort.student_login_code,
                    },
                    "other_cohort": {"id": other.pk, "name": other.name},
                    "student": {
                        "class_code": cohort.student_login_code,
                        "student_number": "001",
                        "password": "001",
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
