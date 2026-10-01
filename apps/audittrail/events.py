import re
import uuid
from contextvars import ContextVar

from .models import SecurityEvent


_current_request = ContextVar('audit_current_request', default=None)


def set_current_request(request):
    return _current_request.set(request)


def reset_current_request(token):
    _current_request.reset(token)


def get_current_request():
    return _current_request.get()


def safe_path(path, max_length=100):
    path = re.sub(r'(/bookings/access/[^/]+/)[^/]+/', r'\1<redacted>/', path or '')
    path = re.sub(r'(/accounts/activate/[^/]+/)[^/]+/', r'\1<redacted>/', path)
    path = re.sub(
        r'(/accounts/password-reset/[^/]+/)[^/]+/',
        r'\1<redacted>/',
        path,
    )
    return path[:max_length]


def record_security_event(
    action,
    *,
    request=None,
    user=None,
    target=None,
    target_type='',
    target_id='',
    result=SecurityEvent.Result.SUCCESS,
):
    request = request or get_current_request()
    if request is not None:
        request_id = getattr(request, 'audit_request_id', uuid.uuid4())
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
        if user is None and getattr(request, 'user', None) is not None:
            if request.user.is_authenticated:
                user = request.user
    else:
        request_id = uuid.uuid4()
        ip_address = None
        user_agent = ''

    if target is not None:
        target_type = target._meta.label
        target_id = str(target.pk)
    if target_type == 'path':
        target_id = safe_path(target_id)

    return SecurityEvent.objects.create(
        user=user if getattr(user, 'pk', None) else None,
        action=action,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        target_type=target_type[:100],
        target_id=str(target_id)[:100],
        result=result,
    )
