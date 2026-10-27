"""CM transactional mail through HTTPS provider APIs."""

import json
import logging
import urllib.request
from email.utils import parseaddr
from http.client import HTTPException
from urllib.error import HTTPError

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class EmailDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = "目前無法寄送信件，請稍後再試。"
    default_code = "email_unavailable"


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            recipient = settings.RESEND_TEST_RECIPIENT
            sender_domain = parseaddr(message.from_email)[1].rpartition("@")[2].lower()
            if (
                not settings.RESEND_API_KEY
                or (sender_domain == "resend.dev" and not recipient)
                or (
                    recipient
                    and [address.lower() for address in message.recipients()] != [recipient]
                )
            ):
                logger.warning("Resend delivery blocked by configuration or recipient restriction")
                if self.fail_silently:
                    continue
                raise EmailDeliveryUnavailable()
            request = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps(
                    {
                        "from": message.from_email,
                        "to": message.to,
                        "subject": message.subject,
                        "text": message.body,
                    }
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "CM/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    result = json.load(response)
                if not isinstance(result, dict) or not result.get("id"):
                    raise ValueError("Missing message ID")
            except (OSError, ValueError, HTTPException) as error:
                # Never log request bodies, provider messages, tokens or credentials.
                status = error.code if isinstance(error, HTTPError) else "transport_or_response"
                logger.warning("Resend delivery failed (%s)", status)
                if self.fail_silently:
                    continue
                raise EmailDeliveryUnavailable() from None
            sent += 1
        return sent


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            name, address = parseaddr(message.from_email)
            if not settings.BREVO_API_KEY or not address or not message.to:
                logger.warning("Brevo delivery blocked by configuration")
                if self.fail_silently:
                    continue
                raise EmailDeliveryUnavailable()
            request = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=json.dumps(
                    {
                        "sender": {"name": name or "CM", "email": address},
                        "to": [{"email": recipient} for recipient in message.to],
                        "subject": message.subject,
                        "textContent": message.body,
                    }
                ).encode("utf-8"),
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "CM/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    result = json.load(response)
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("messageId"), str)
                    or not result["messageId"].strip()
                ):
                    raise ValueError("Missing message ID")
            except (OSError, ValueError, HTTPException) as error:
                # Never log provider bodies, action tokens, recipients or credentials.
                status = error.code if isinstance(error, HTTPError) else "transport_or_response"
                logger.warning("Brevo delivery failed (%s)", status)
                if self.fail_silently:
                    continue
                raise EmailDeliveryUnavailable() from None
            sent += 1
        return sent
