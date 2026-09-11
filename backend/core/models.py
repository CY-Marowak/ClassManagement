import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, default=uuid.uuid4)
    email = models.EmailField(unique=True)
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


class Cohort(models.Model):
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
