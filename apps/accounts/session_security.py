from importlib import import_module

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.utils import timezone


def invalidate_user_sessions(user, exclude_session_key=None):
    session_keys = []
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if str(session.get_decoded().get(SESSION_KEY)) != str(user.pk):
            continue
        if exclude_session_key and session.session_key == exclude_session_key:
            continue
        session_keys.append(session.session_key)

    SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
    for session_key in session_keys:
        SessionStore(session_key=session_key).delete(session_key)
    from apps.audittrail.events import get_current_request, record_security_event
    from apps.audittrail.models import SecurityEvent

    request = get_current_request()
    actor = (
        request.user
        if request is not None and request.user.is_authenticated
        else user
    )
    record_security_event(
        SecurityEvent.Action.SESSION_REVOKED,
        request=request,
        user=actor,
        target=user,
    )
    return len(session_keys)


def rotate_session_key(request):
    if request and hasattr(request, "session"):
        request.session.cycle_key()
