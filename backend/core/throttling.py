from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import Throttled

from .models import AuthRateBucket


def consume(scope: str, subject: str, limit: int):
    # Stable keyed digests avoid storing raw emails/IPs in rate-limit keys.
    key = salted_hmac("cm-auth-rate", f"{scope}:{subject}", algorithm="sha256").hexdigest()
    now = timezone.now()
    with transaction.atomic():
        bucket, _ = AuthRateBucket.objects.get_or_create(key=key, defaults={"started_at": now})
        bucket = AuthRateBucket.objects.select_for_update().get(pk=bucket.pk)
        expires = bucket.started_at + timedelta(minutes=15)
        if expires <= now:
            bucket.started_at = now
            bucket.count = 0
        elif bucket.count >= limit:
            raise Throttled(
                wait=max(1, int((expires - now).total_seconds())),
                detail="嘗試次數過多，請稍後再試。",
            )
        bucket.count += 1
        bucket.save(update_fields=["started_at", "count"])


def throttle_auth(request, scope: str):
    consume(scope + ":ip", request.META.get("REMOTE_ADDR", "unknown"), 30)
    if hasattr(request.data, "get"):
        email = request.data.get("email")
        if isinstance(email, str) and len(email) <= 254:
            consume(scope + ":email", email.strip().lower(), 5 if scope == "login" else 3)
