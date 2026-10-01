from .models import AuditLog
from .events import safe_path


class AuditTrailMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        actor = request.user if request.user.is_authenticated else None
        response = self.get_response(request)
        if actor is not None and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            AuditLog.objects.create(
                user=actor,
                method=request.method,
                path=safe_path(request.path, max_length=500),
                status_code=response.status_code,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
        return response
