import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=500)
    status_code = models.PositiveSmallIntegerField(default=200)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.method} {self.path}'


class SecurityEvent(models.Model):
    class Action(models.TextChoices):
        LOGIN_SUCCEEDED = 'LOGIN_SUCCEEDED', 'Successful login'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Failed login'
        LOGOUT = 'LOGOUT', 'Logout'
        ACCOUNT_LOCKED = 'ACCOUNT_LOCKED', 'Account lockout'
        ACCOUNT_ACTIVATED = 'ACCOUNT_ACTIVATED', 'Account activated'
        ACCOUNT_DEACTIVATED = 'ACCOUNT_DEACTIVATED', 'Account deactivated'
        EMAIL_VERIFIED = 'EMAIL_VERIFIED', 'Email verified'
        PASSWORD_RESET_REQUESTED = 'PASSWORD_RESET_REQUESTED', 'Password reset requested'
        PASSWORD_CHANGED = 'PASSWORD_CHANGED', 'Password changed'
        MFA_ENABLED = 'MFA_ENABLED', 'MFA enabled'
        MFA_DISABLED = 'MFA_DISABLED', 'MFA disabled'
        MFA_FAILED = 'MFA_FAILED', 'MFA code rejected'
        MFA_LOCKED = 'MFA_LOCKED', 'MFA temporarily locked'
        MFA_RECOVERY_USED = 'MFA_RECOVERY_USED', 'MFA recovery used'
        MFA_RECOVERY_RESET = 'MFA_RECOVERY_RESET', 'MFA recovery reset'
        ROLE_CHANGED = 'ROLE_CHANGED', 'Role changed'
        SESSION_REVOKED = 'SESSION_REVOKED', 'Session revocation'
        UNAUTHORIZED_ACCESS = 'UNAUTHORIZED_ACCESS', 'Unauthorized access attempt'
        SENSITIVE_REAUTHENTICATION = 'SENSITIVE_REAUTHENTICATION', 'Sensitive-action reauthentication'
        BOOKING_VERIFIED = 'BOOKING_VERIFIED', 'Booking verified'
        SERVICE_STATUS_CHANGED = 'SERVICE_STATUS_CHANGED', 'Service status changed'
        SERVICE_ASSIGNED = 'SERVICE_ASSIGNED', 'Service staff assignment changed'

    class Result(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILURE = 'FAILURE', 'Failure'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='security_events',
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    result = models.CharField(max_length=10, choices=Result.choices)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.action} ({self.result})'
