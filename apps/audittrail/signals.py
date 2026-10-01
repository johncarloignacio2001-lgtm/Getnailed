from allauth.account.signals import authentication_step_completed
from allauth.mfa.models import Authenticator
from allauth.mfa.signals import authenticator_added, authenticator_removed, authenticator_reset
from axes.signals import user_locked_out
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.login_security import normalize_axes_username
from apps.accounts.models import User

from .events import get_current_request, record_security_event
from .models import SecurityEvent


def _known_user(request, credentials=None, username=None):
    normalized = username or normalize_axes_username(request, credentials or {})
    return User.objects.filter(email=(normalized or '').strip().lower()).first()


@receiver(user_logged_in)
def audit_login_success(sender, request, user, **kwargs):
    record_security_event(
        SecurityEvent.Action.LOGIN_SUCCEEDED,
        request=request,
        user=user,
        target=user,
    )


@receiver(user_login_failed)
def audit_login_failure(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    user = _known_user(request, credentials=credentials)
    record_security_event(
        SecurityEvent.Action.LOGIN_FAILED,
        request=request,
        user=user,
        target=user,
        result=SecurityEvent.Result.FAILURE,
    )


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    record_security_event(
        SecurityEvent.Action.LOGOUT,
        request=request,
        user=user,
        target=user,
    )


@receiver(user_locked_out)
def audit_account_lockout(sender, request, username, **kwargs):
    user = _known_user(request, username=username)
    record_security_event(
        SecurityEvent.Action.ACCOUNT_LOCKED,
        request=request,
        user=user,
        target=user,
        result=SecurityEvent.Result.FAILURE,
    )


@receiver(authentication_step_completed)
def audit_sensitive_reauthentication(sender, request, user, **kwargs):
    if not kwargs.get('reauthenticated'):
        return
    record_security_event(
        SecurityEvent.Action.SENSITIVE_REAUTHENTICATION,
        request=request,
        user=user,
        target=user,
    )


@receiver(authenticator_added)
def audit_mfa_enabled(sender, request, user, authenticator, **kwargs):
    if authenticator.type != Authenticator.Type.TOTP:
        return
    record_security_event(
        SecurityEvent.Action.MFA_ENABLED,
        request=request,
        user=user,
        target=authenticator,
    )


@receiver(authenticator_removed)
def audit_mfa_disabled(sender, request, user, authenticator, **kwargs):
    if authenticator and authenticator.type != Authenticator.Type.TOTP:
        return
    record_security_event(
        SecurityEvent.Action.MFA_DISABLED,
        request=request,
        user=user,
        target_type='accounts.User',
        target_id=user.pk,
    )


@receiver(authenticator_reset)
def audit_mfa_recovery_reset(sender, request, user, authenticator, **kwargs):
    record_security_event(
        SecurityEvent.Action.MFA_RECOVERY_RESET,
        request=request,
        user=user,
        target=authenticator,
    )


@receiver(post_save, sender=User)
def audit_user_security_change(sender, instance, created, **kwargs):
    if created:
        return
    previous = getattr(instance, '_previous_security_state', None)
    if not previous:
        return
    request = get_current_request()
    actor = (
        request.user
        if request is not None and request.user.is_authenticated
        else instance
    )
    if previous['role'] != instance.role:
        record_security_event(
            SecurityEvent.Action.ROLE_CHANGED,
            request=request,
            user=actor,
            target=instance,
        )
    was_active = previous['is_active'] and previous['is_active_staff_member']
    is_active = instance.is_active and instance.is_active_staff_member
    if was_active != is_active:
        record_security_event(
            SecurityEvent.Action.ACCOUNT_ACTIVATED
            if is_active
            else SecurityEvent.Action.ACCOUNT_DEACTIVATED,
            request=request,
            user=actor,
            target=instance,
        )
