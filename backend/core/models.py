import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, default=uuid.uuid4)
    # Students have no email; this intentionally widens AbstractUser's field to nullable.
    email = models.EmailField(unique=True, null=True, blank=True)  # type: ignore[assignment]
    account_type = models.CharField(
        max_length=10, choices=[("teacher", "教師"), ("student", "學生")], default="teacher"
    )
    display_name = models.CharField(max_length=80)
    email_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_case_unique")]


class EmailToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=10)
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)


def student_login_code():
    return secrets.token_hex(5).upper()


def teacher_application_code():
    return "T-" + secrets.token_hex(8).upper()


class Cohort(models.Model):
    application_code = models.CharField(
        max_length=18, unique=True, default=teacher_application_code, editable=False
    )
    student_login_code = models.CharField(
        max_length=10, unique=True, default=student_login_code, editable=False
    )
    name = models.CharField(max_length=80)
    entry_year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
    current_grade = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ClassMember(models.Model):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    role = models.CharField(
        max_length=12, choices=[("homeroom", "導師"), ("coTeacher", "共同教師")]
    )
    approved = models.BooleanField(default=True)
    inactive_status = models.CharField(
        max_length=10,
        choices=[("pending", "待審核"), ("rejected", "已拒絕"), ("removed", "已移除")],
        default="pending",
    )
    revision = models.PositiveIntegerField(default=1)

    @property
    def status(self):
        return "approved" if self.approved else self.inactive_status

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cohort", "user"], name="one_membership_per_teacher"),
            models.UniqueConstraint(
                fields=["cohort"],
                condition=models.Q(role="homeroom"),
                name="one_homeroom_per_cohort",
            ),
        ]


class AuthRateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    started_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)


class TeacherAuditEvent(models.Model):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="teacher_events")
    member = models.ForeignKey(ClassMember, on_delete=models.CASCADE, null=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actor_name = models.CharField(max_length=80)
    teacher_name = models.CharField(max_length=80, blank=True)
    action = models.CharField(max_length=20)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Student(models.Model):
    behavior_score_total = models.BigIntegerField(default=0)
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="students")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student")
    seat_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(9999)]
    )
    student_number = models.CharField(max_length=64)
    avatar = models.CharField(
        max_length=10, choices=[("cat", "貓"), ("dog", "狗"), ("rabbit", "兔")]
    )
    must_change_password = models.BooleanField(default=True)

    class Meta:
        ordering = ["seat_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["cohort", "student_number"], name="student_number_per_cohort"
            ),
            models.UniqueConstraint(
                fields=["cohort", "seat_number"], name="seat_number_per_cohort"
            ),
            models.CheckConstraint(
                condition=models.Q(seat_number__gte=1, seat_number__lte=9999),
                name="student_seat_range",
            ),
        ]


class StudentAuditEvent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actor_name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(
        max_length=20,
        choices=[
            ("created", "建立學生"),
            ("profile_updated", "修改資料"),
            ("password_reset", "重設密碼"),
        ],
        default="created",
    )
    student_name = models.CharField(max_length=80)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)


class ScoreRecord(models.Model):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE)
    request_id = models.UUIDField(default=uuid.uuid4)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scores")
    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    creator_name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8, choices=[("positive", "加分"), ("negative", "扣分")])
    score = models.SmallIntegerField()
    template = models.CharField(max_length=30)
    reason = models.CharField(max_length=80)
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cohort", "creator", "request_id"], name="score_request_once"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="positive", score__gte=0, score__lte=100)
                    | models.Q(kind="negative", score__gte=-100, score__lte=0)
                ),
                name="score_kind_range",
            ),
        ]


class ScoreAuditEvent(models.Model):
    record = models.ForeignKey(ScoreRecord, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actor_name = models.CharField(max_length=80)
    action = models.CharField(max_length=20, default="created")
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
