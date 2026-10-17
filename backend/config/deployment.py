from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    # Render probes this frequently. Do not wake Neon or create a session.
    return JsonResponse({"status": "ok"})
