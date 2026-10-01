from allauth.mfa.signals import (
    authenticator_added,
    authenticator_removed,
    authenticator_reset,
)
from axes.signals import user_locked_out
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .emails import send_branded_email
from .models import LoginDevice, User
from .session_security import invalidate_user_sessions, rotate_session_key


PRIVILEGE_FIELDS = (
    "role",
    "is_active",
    "is_active_staff_member",
    "is_locked",
    "is_staff",
    "is_superuser",
    "can_use_pos",
    "can_manage_bookings",
    "can_manage_customers",
    "can_assign_services",
)


@receiver(user_logged_in)
def rotate_identifier_after_login(sender, request, **kwargs):
    rotate_session_key(request)


@receiver(user_logged_in)
def notify_new_login_device(sender, request, user, **kwargs):
    if request.path not in {
        "/accounts/login/",
        "/security/login/",
        "/security/2fa/authenticate/",
        "/admin/login/",
    }:
        return
    fingerprint = salted_hmac(
        "accounts.login-device",
        f"{request.META.get('REMOTE_ADDR', '')}|{request.META.get('HTTP_USER_AGENT', '')[:512]}",
        algorithm="sha256",
    ).hexdigest()
    _, created = LoginDevice.objects.get_or_create(
        user=user,
        fingerprint_digest=fingerprint,
    )
    if not created:
        LoginDevice.objects.filter(user=user, fingerprint_digest=fingerprint).update(
            last_seen_at=timezone.now()
        )
        return
    transaction.on_commit(
        lambda: send_branded_email(
            user.email,
            f"New sign-in to {settings.BRAND_NAME}",
            "accounts/emails/new_device",
            {"occurred_at": timezone.now()},
            rate_action="new-device",
            rate_identifier=user.pk,
            fail_silently=True,
        )
    )


@receiver(user_locked_out)
def notify_suspicious_login(sender, request, username, **kwargs):
    user = User.objects.filter(email=(username or "").strip().lower()).first()
    if user is None:
        return
    transaction.on_commit(
        lambda: send_branded_email(
            user.email,
            f"Suspicious sign-in warning from {settings.BRAND_NAME}",
            "accounts/emails/suspicious_login",
            {"occurred_at": timezone.now()},
            rate_action="suspicious-login",
            rate_identifier=user.pk,
            fail_silently=True,
        )
    )


@receiver(pre_save, sender=User)
def remember_security_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_security_state = None
        return
    instance._previous_security_state = sender.objects.filter(pk=instance.pk).values(
        *PRIVILEGE_FIELDS
    ).first()


@receiver(post_save, sender=User)
def revoke_sessions_after_security_change(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_security_state", None)
    if created or not previous:
        return
    if any(previous[field] != getattr(instance, field) for field in PRIVILEGE_FIELDS):
        transaction.on_commit(lambda: invalidate_user_sessions(instance))


@receiver(authenticator_added)
def rotate_identifier_after_mfa_enrollment(sender, request, **kwargs):
    rotate_session_key(request)


@receiver(authenticator_removed)
@receiver(authenticator_reset)
def revoke_sessions_after_mfa_reset(sender, request, **kwargs):
    request._flush_sessions_after_security_change = True
