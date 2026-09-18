from collections.abc import Iterable

from django.contrib.sessions.models import Session


def revoke_user_sessions(user_ids: Iterable[int]) -> None:
    """Revoke stored sessions inside the caller's account-change transaction."""
    targets = {str(user_id) for user_id in user_ids}
    if not targets:
        return
    for session in Session.objects.all().iterator():
        if session.get_decoded().get("_auth_user_id") in targets:
            session.delete()
