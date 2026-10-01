from collections import defaultdict

from axes.helpers import get_client_ip_address, get_cool_off
from axes.models import AccessAttempt
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .models import User


def normalize_axes_username(request, credentials=None):
    credentials = credentials or {}
    value = (
        credentials.get("email")
        or credentials.get("login")
        or credentials.get("username")
        or request.POST.get("login")
        or request.POST.get("email")
        or ""
    )
    if not isinstance(value, str):
        return ""
    return User.objects.normalize_email(value[:254])


def login_requires_captcha(request, email=None):
    if request is None:
        return False
    threshold = timezone.now() - get_cool_off(request)
    attempts = AccessAttempt.objects.filter(
        ip_address=get_client_ip_address(request),
        attempt_time__gte=threshold,
    )
    normalized_email = User.objects.normalize_email(email or "")
    if normalized_email:
        email_failures = attempts.filter(username=normalized_email).aggregate(
            total=Sum("failures_since_start")
        )["total"] or 0
        if email_failures >= settings.LOGIN_CAPTCHA_THRESHOLD:
            return True
    ip_failures = attempts.aggregate(total=Sum("failures_since_start"))["total"] or 0
    return ip_failures >= settings.LOGIN_CAPTCHA_THRESHOLD


def get_valid_account_lockouts():
    attempts = AccessAttempt.objects.filter(
        expiration__expires_at__gt=timezone.now(),
    ).order_by("username", "ip_address")
    grouped = defaultdict(lambda: {"failures": 0, "expires_at": None, "last_attempt": None})
    for attempt in attempts:
        key = (attempt.username, str(attempt.ip_address or ""))
        item = grouped[key]
        item["failures"] += attempt.failures_since_start
        expires_at = attempt.expiration.expires_at
        if item["expires_at"] is None or expires_at > item["expires_at"]:
            item["expires_at"] = expires_at
        if item["last_attempt"] is None or attempt.attempt_time > item["last_attempt"]:
            item["last_attempt"] = attempt.attempt_time

    valid_emails = set(
        User.objects.filter(email__in=[key[0] for key in grouped]).values_list(
            "email", flat=True
        )
    )
    lockouts = []
    for (username, ip_address), item in grouped.items():
        if username not in valid_emails or item["failures"] < settings.AXES_FAILURE_LIMIT:
            continue
        lockouts.append(
            {
                "username": username,
                "ip_address": ip_address,
                **item,
            }
        )
    return sorted(lockouts, key=lambda item: item["last_attempt"], reverse=True)
