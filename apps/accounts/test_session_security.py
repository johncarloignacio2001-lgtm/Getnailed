import time

from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User


PASSWORD = "Correct-Horse-Battery-47!"
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
    LOGIN_CAPTCHA_THRESHOLD=100,
)
class SessionSecurityTests(TestCase):
    def setUp(self):
        cache.clear()

    def create_user(self, email="staff@example.com", role=User.Role.STAFF):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def login_client(self, client, user):
        response = client.post(
            reverse("accounts:login"),
            {"login": user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)

    def assert_logged_out(self, client):
        response = client.get(reverse("core:dashboard_router"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_database_backed_session_engine_is_explicit(self):
        self.assertIn(
            settings.SESSION_ENGINE,
            {
                "django.contrib.sessions.backends.db",
                "django.contrib.sessions.backends.cached_db",
            },
        )

    def test_session_identifier_rotates_after_login(self):
        user = self.create_user()
        anonymous_session = self.client.session
        anonymous_session["before_login"] = True
        anonymous_session.save()
        old_key = anonymous_session.session_key
        self.login_client(self.client, user)
        self.assertNotEqual(old_key, self.client.session.session_key)

    def test_logout_current_device_flushes_only_that_session(self):
        user = self.create_user()
        other_client = Client()
        self.login_client(self.client, user)
        self.login_client(other_client, user)
        current_key = self.client.session.session_key
        other_key = other_client.session.session_key

        self.assertRedirects(self.client.post(reverse("accounts:logout")), reverse("core:home"))
        self.assertFalse(Session.objects.filter(session_key=current_key).exists())
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())
        self.assert_logged_out(self.client)
        self.assertEqual(other_client.get(reverse("core:dashboard_router")).status_code, 302)

    def test_logout_all_devices_revokes_every_session(self):
        user = self.create_user()
        other_client = Client()
        self.login_client(self.client, user)
        self.login_client(other_client, user)
        self.assertEqual(self.client.get(reverse("accounts:logout_all_devices")).status_code, 200)

        response = self.client.post(reverse("accounts:logout_all_devices"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertFalse(Session.objects.filter(expire_date__gt=timezone.now()).exists())
        self.assert_logged_out(self.client)
        self.assert_logged_out(other_client)

    @override_settings(OWNER_INACTIVITY_TIMEOUT=30, STAFF_INACTIVITY_TIMEOUT=60)
    def test_internal_inactivity_timeout_is_role_specific_and_flushes_session(self):
        for email, role, timeout in (
            ("owner@example.com", User.Role.OWNER, 30),
            ("staff@example.com", User.Role.STAFF, 60),
        ):
            user = self.create_user(email, role)
            client = Client()
            self.login_client(client, user)
            session = client.session
            old_key = session.session_key
            session["accounts.last_activity"] = int(time.time()) - timeout
            session.save()

            response = client.get(reverse("core:dashboard_router"))
            self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
            self.assertFalse(Session.objects.filter(session_key=old_key).exists())

    @override_settings(STAFF_INACTIVITY_TIMEOUT=3600)
    def test_activity_renews_internal_session_expiry(self):
        user = self.create_user()
        self.login_client(self.client, user)
        self.client.get(reverse("core:dashboard_router"))
        self.assertLessEqual(self.client.session.get_expiry_age(), 3600)
        self.assertIn("accounts.last_activity", self.client.session)

    def test_deactivation_revokes_all_sessions(self):
        user = self.create_user()
        first = Client()
        second = Client()
        self.login_client(first, user)
        self.login_client(second, user)

        with self.captureOnCommitCallbacks(execute=True):
            user.is_active = False
            user.save(update_fields=("is_active",))
        self.assertFalse(Session.objects.filter(expire_date__gt=timezone.now()).exists())
        self.assert_logged_out(first)
        self.assert_logged_out(second)

    def test_role_or_permission_change_revokes_all_sessions(self):
        user = self.create_user()
        first = Client()
        second = Client()
        self.login_client(first, user)
        self.login_client(second, user)

        with self.captureOnCommitCallbacks(execute=True):
            user.role = User.Role.CASHIER
            user.can_use_pos = True
            user.save(update_fields=("role", "can_use_pos"))
        self.assertFalse(Session.objects.filter(expire_date__gt=timezone.now()).exists())

    def test_mfa_reset_revokes_all_sessions(self):
        user = self.create_user()
        TOTP.activate(user, TOTP_SECRET)
        response = self.client.post(
            reverse("accounts:login"),
            {"login": user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        code = format_hotp_value(
            hotp_value(TOTP_SECRET, next(yield_hotp_counters_from_time()))
        )
        self.assertEqual(
            self.client.post(reverse("mfa_authenticate"), {"code": code}).status_code,
            302,
        )
        other_client = Client()
        other_client.force_login(user)

        response = self.client.post(
            reverse("mfa_regenerate_recovery_codes"),
            {"confirm": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(expire_date__gt=timezone.now()).exists())
        self.assert_logged_out(self.client)
        self.assert_logged_out(other_client)

    def test_security_cookie_and_header_baseline_is_explicit(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertIn(settings.SESSION_COOKIE_SAMESITE, {"Lax", "Strict"})
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
