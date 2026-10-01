import uuid
from datetime import timedelta

from allauth.account.signals import authentication_step_completed
from allauth.core import context
from allauth.mfa import signals as mfa_signals
from allauth.mfa.models import Authenticator
from axes.signals import user_locked_out
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms import MFAAuthenticateForm
from apps.accounts.models import AccountActivation, MFARecoveryCode, User
from apps.bookings.models import Booking

from .events import record_security_event
from .models import AuditLog, SecurityEvent


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    LOGIN_CAPTCHA_THRESHOLD=100,
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
    PUBLIC_BASE_URL="",
)
class SecurityEventTests(TestCase):
    def create_user(self, email="staff@example.com", role=User.Role.STAFF, **extra):
        values = {
            "role": role,
            "email_verified_at": timezone.now(),
            "is_active": True,
            "is_active_staff_member": True,
        }
        values.update(extra)
        return User.objects.create_user(email, PASSWORD, **values)

    def event_text(self):
        fields = (
            "action",
            "request_id",
            "ip_address",
            "user_agent",
            "target_type",
            "target_id",
            "result",
        )
        return "\n".join(
            str(getattr(event, field) or "")
            for event in SecurityEvent.objects.all()
            for field in fields
        )

    def test_event_writer_captures_safe_context_and_redacts_token_paths(self):
        secret = "password-reset-secret-token"
        request = RequestFactory().post(
            f"/accounts/password-reset/uid-value/{secret}/",
            REMOTE_ADDR="203.0.113.9",
            HTTP_USER_AGENT="Audit test browser",
        )
        request.user = AnonymousUser()
        request.audit_request_id = uuid.uuid4()

        event = record_security_event(
            SecurityEvent.Action.UNAUTHORIZED_ACCESS,
            request=request,
            target_type="path",
            target_id=request.path,
            result=SecurityEvent.Result.FAILURE,
        )

        self.assertEqual(event.request_id, request.audit_request_id)
        self.assertEqual(event.ip_address, "203.0.113.9")
        self.assertEqual(event.user_agent, "Audit test browser")
        self.assertEqual(event.target_id, "/accounts/password-reset/uid-value/<redacted>/")
        self.assertNotIn(secret, self.event_text())

    def test_authentication_password_and_session_events_do_not_store_passwords(self):
        user = self.create_user()
        wrong_password = "Wrong-Password-Never-Store-31!"
        new_password = "New-Password-Never-Store-82!"

        failed = self.client.post(
            reverse("accounts:login"),
            {"login": user.email, "password": wrong_password},
            REMOTE_ADDR="198.51.100.7",
        )
        self.assertEqual(failed.status_code, 200)
        logged_in = self.client.post(
            reverse("accounts:login"),
            {"login": user.email, "password": PASSWORD},
        )
        self.assertEqual(logged_in.status_code, 302)
        changed = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(changed.status_code, 302)
        self.client.post(reverse("accounts:password_reset"), {"email": user.email})

        actions = set(SecurityEvent.objects.values_list("action", flat=True))
        self.assertTrue(
            {
                SecurityEvent.Action.LOGIN_FAILED,
                SecurityEvent.Action.LOGIN_SUCCEEDED,
                SecurityEvent.Action.PASSWORD_CHANGED,
                SecurityEvent.Action.PASSWORD_RESET_REQUESTED,
                SecurityEvent.Action.SESSION_REVOKED,
                SecurityEvent.Action.LOGOUT,
            }.issubset(actions)
        )
        failed_event = SecurityEvent.objects.get(action=SecurityEvent.Action.LOGIN_FAILED)
        self.assertEqual(failed_event.user, user)
        self.assertEqual(failed_event.result, SecurityEvent.Result.FAILURE)
        event_text = self.event_text()
        self.assertNotIn(PASSWORD, event_text)
        self.assertNotIn(wrong_password, event_text)
        self.assertNotIn(new_password, event_text)

    def test_account_role_activation_and_deactivation_events(self):
        user = self.create_user()
        with self.captureOnCommitCallbacks(execute=True):
            user.role = User.Role.CASHIER
            user.save(update_fields=("role",))
        with self.captureOnCommitCallbacks(execute=True):
            user.is_active_staff_member = False
            user.save(update_fields=("is_active_staff_member",))

        self.assertTrue(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.ROLE_CHANGED,
                target_id=user.pk,
            ).exists()
        )
        self.assertTrue(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.ACCOUNT_DEACTIVATED,
                target_id=user.pk,
            ).exists()
        )
        self.assertGreaterEqual(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.SESSION_REVOKED,
                target_id=user.pk,
            ).count(),
            2,
        )

    def test_activation_records_success_and_failure_without_token(self):
        user = User.objects.create_user(
            "invitee@example.com",
            password=None,
            role=User.Role.STAFF,
            is_active=False,
            is_active_staff_member=False,
        )
        activation, token = AccountActivation.issue(user)
        bad_token = "wrong-activation-token-never-store"
        bad_url = reverse(
            "accounts:activate",
            kwargs={"public_id": activation.public_id, "token": bad_token},
        )
        self.assertEqual(self.client.get(bad_url).status_code, 400)

        valid_url = reverse(
            "accounts:activate",
            kwargs={"public_id": activation.public_id, "token": token},
        )
        self.assertEqual(self.client.get(valid_url).status_code, 200)
        self.assertEqual(self.client.post(valid_url).status_code, 302)
        response = self.client.post(
            reverse(
                "accounts:activation_password",
                kwargs={"public_id": activation.public_id},
            ),
            {"new_password1": PASSWORD, "new_password2": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)

        results = set(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.ACCOUNT_ACTIVATED,
            ).values_list("result", flat=True)
        )
        self.assertEqual(
            results,
            {SecurityEvent.Result.SUCCESS, SecurityEvent.Result.FAILURE},
        )
        failed_event = SecurityEvent.objects.get(
            action=SecurityEvent.Action.ACCOUNT_ACTIVATED,
            result=SecurityEvent.Result.FAILURE,
        )
        self.assertIsNone(failed_event.user)
        self.assertTrue(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.EMAIL_VERIFIED,
                target_id=user.pk,
            ).exists()
        )
        event_text = self.event_text()
        self.assertNotIn(token, event_text)
        self.assertNotIn(bad_token, event_text)
        self.assertNotIn(PASSWORD, event_text)

    def test_mfa_lockout_and_reauthentication_signals_are_recorded_safely(self):
        user = self.create_user()
        totp_secret = "totp-secret-never-store"
        request = RequestFactory().post(
            "/security/2fa/reauthenticate/",
            REMOTE_ADDR="192.0.2.10",
        )
        request.user = user
        request.audit_request_id = uuid.uuid4()
        authenticator = Authenticator.objects.create(
            user=user,
            type=Authenticator.Type.TOTP,
            data={"secret": totp_secret},
        )

        authentication_step_completed.send(
            sender=User,
            request=request,
            user=user,
            method="password",
            reauthenticated=True,
        )
        mfa_signals.authenticator_added.send(
            sender=Authenticator,
            request=request,
            user=user,
            authenticator=authenticator,
        )
        mfa_signals.authenticator_reset.send(
            sender=Authenticator,
            request=request,
            user=user,
            authenticator=authenticator,
        )
        mfa_signals.authenticator_removed.send(
            sender=Authenticator,
            request=request,
            user=user,
            authenticator=authenticator,
        )
        user_locked_out.send(
            sender="axes",
            request=request,
            username=user.email,
            ip_address="192.0.2.10",
        )

        recovery_code = MFARecoveryCode.regenerate_for_user(user)[0]
        with context.request_context(request):
            form = MFAAuthenticateForm({"code": recovery_code}, user=user)
            self.assertTrue(form.is_valid(), form.errors)

        actions = set(SecurityEvent.objects.values_list("action", flat=True))
        self.assertTrue(
            {
                SecurityEvent.Action.SENSITIVE_REAUTHENTICATION,
                SecurityEvent.Action.MFA_ENABLED,
                SecurityEvent.Action.MFA_DISABLED,
                SecurityEvent.Action.MFA_RECOVERY_RESET,
                SecurityEvent.Action.MFA_RECOVERY_USED,
                SecurityEvent.Action.ACCOUNT_LOCKED,
            }.issubset(actions)
        )
        event_text = self.event_text()
        self.assertNotIn(totp_secret, event_text)
        self.assertNotIn(recovery_code, event_text)

    def test_booking_verification_records_results_without_codes_or_tokens(self):
        verification_code = "87654321"
        booking = Booking(
            customer_name="Audit Guest",
            email="audit-guest@example.com",
            service_name="Classic Manicure",
            scheduled_for=timezone.now() + timedelta(days=2),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        booking.set_verification_code(
            verification_code,
            timezone.now() + timedelta(minutes=15),
        )
        booking.save()

        failed = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": "00000000"},
        )
        self.assertEqual(failed.status_code, 200)
        succeeded = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": verification_code},
        )
        self.assertEqual(succeeded.status_code, 302)
        access_token = succeeded["Location"].rstrip("/").split("/")[-1]

        results = set(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.BOOKING_VERIFIED,
            ).values_list("result", flat=True)
        )
        self.assertEqual(
            results,
            {SecurityEvent.Result.SUCCESS, SecurityEvent.Result.FAILURE},
        )
        event_text = self.event_text()
        self.assertNotIn(verification_code, event_text)
        self.assertNotIn(access_token, event_text)

    def test_audit_display_is_owner_only_and_admin_is_read_only(self):
        staff = self.create_user()
        owner = self.create_user("owner@example.com", User.Role.OWNER)
        SecurityEvent.objects.create(
            user=owner,
            action=SecurityEvent.Action.LOGIN_SUCCEEDED,
            result=SecurityEvent.Result.SUCCESS,
        )

        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("audittrail:index")).status_code, 403)
        self.assertTrue(
            SecurityEvent.objects.filter(
                action=SecurityEvent.Action.UNAUTHORIZED_ACCESS,
                user=staff,
            ).exists()
        )
        self.client.force_login(owner)
        response = self.client.get(reverse("audittrail:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successful login")

        model_admin = admin.site._registry[SecurityEvent]
        request = RequestFactory().get("/admin/audittrail/securityevent/")
        request.user = owner
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_http_audit_preserves_actor_when_logout_changes_request_user(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.get(path=reverse("accounts:logout"))
        self.assertEqual(log.user, user)
        self.assertEqual(log.method, "POST")
