import hashlib
import secrets
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import EmailToken, User


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def use_action_token(raw: str, purpose: str):
    digest = token_digest(raw)
    candidate = EmailToken.objects.filter(digest=digest, purpose=purpose).first()
    if not candidate:
        raise ValidationError({"detail": "連結已失效，請重新申請。"})
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=candidate.user_id)
        token = (
            EmailToken.objects.select_for_update()
            .filter(pk=candidate.pk, used=False, expires_at__gt=timezone.now())
            .first()
        )
        if token is None or not user.is_active:
            raise ValidationError({"detail": "連結已失效，請重新申請。"})
        yield user
        token.used = True
        token.save(update_fields=["used"])


def send_action_email(user, purpose: str):
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        # Serialise issuance for this user, so two resend requests cannot leave two links valid.
        type(user).objects.select_for_update().get(pk=user.pk)
        EmailToken.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
        EmailToken.objects.create(
            user=user,
            purpose=purpose,
            digest=token_digest(token),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        title = "驗證你的 CM 帳號" if purpose == "verify" else "重設 CM 密碼"
        url = f"{settings.FRONTEND_URL}/#{purpose}?token={token}"
        # An email failure rolls back token issuance. Tokens stay out of HTTP access logs.
        send_mail(
            title,
            f"請開啟以下連結，30 分鐘內有效且只能使用一次：\n{url}\n\n若非本人操作，請忽略此信。",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )
