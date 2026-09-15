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


class Cohort(models.Model):
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


class Student(models.Model):
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


class StudentCreatedEvent(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="creation_events")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    actor_name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)
