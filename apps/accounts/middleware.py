import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .mfa import has_totp, is_mfa_required
from .models import User
from .session_security import invalidate_user_sessions


class SessionSecurityMiddleware:
    LAST_ACTIVITY_KEY = "accounts.last_activity"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            timeout = self._timeout_for(request.user)
            if timeout:
                now = int(time.time())
                last_activity = request.session.get(self.LAST_ACTIVITY_KEY)
                if last_activity and now - last_activity >= timeout:
                    logout(request)
                    messages.warning(request, "Your session expired due to inactivity.")
                    return redirect(settings.LOGIN_URL)
                request.session[self.LAST_ACTIVITY_KEY] = now
                request.session.set_expiry(timeout)

        response = self.get_response(request)
        if getattr(request, "_flush_sessions_after_security_change", False):
            user = request.user
            if user.is_authenticated:
                invalidate_user_sessions(user)
                logout(request)
        return response

    @staticmethod
    def _timeout_for(user):
        if user.role == User.Role.OWNER or user.is_superuser:
            return settings.OWNER_INACTIVITY_TIMEOUT
        if user.role in {User.Role.CASHIER, User.Role.STAFF}:
            return settings.STAFF_INACTIVITY_TIMEOUT
        return None


class RequiredMFAMiddleware:
    EXEMPT_PREFIXES = (
        "/security/2fa/",
        "/security/login/",
        "/security/logout/",
        "/security/reauthenticate/",
        "/accounts/logout/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and is_mfa_required(request.user)
            and not has_totp(request.user)
            and not request.path.startswith(self.EXEMPT_PREFIXES)
        ):
            return redirect("mfa_activate_totp")
        return self.get_response(request)
