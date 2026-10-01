from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.adapters import AccountAdapter
from apps.accounts.emails import send_branded_email
from apps.accounts.models import LoginDevice, User


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
    LOGIN_CAPTCHA_THRESHOLD=100,
)
class EmailSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()

    def create_user(self, email="staff@example.com", role=User.Role.STAFF):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def assert_multipart(self, message):
        self.assertTrue(message.body.strip())
        self.assertEqual(len(message.alternatives), 1)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")
        self.assertIn("get nailed", message.alternatives[0].content.lower())

    def test_branded_security_email_has_plain_text_and_html_without_credentials(self):
        send_branded_email(
            "person@example.com",
            "Security notification",
            "accounts/emails/password_changed",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assert_multipart(mail.outbox[0])
        self.assertNotIn(PASSWORD, mail.outbox[0].body)
        self.assertNotIn("DJANGO_SECRET_KEY", mail.outbox[0].body)

    def test_password_change_sends_notification_without_new_password(self):
        user = self.create_user()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("accounts:login"),
                {"login": user.email, "password": PASSWORD},
                HTTP_USER_AGENT="EmailSecurityTest/1",
            )
        mail.outbox.clear()
        new_password = "A-New-Secure-Password-58!"
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )
        self.assertEqual(response.status_code, 302)
        notification = next(message for message in mail.outbox if "password changed" in message.subject)
        self.assert_multipart(notification)
        self.assertNotIn(new_password, notification.body)

    def test_mfa_change_uses_branded_notification_without_secret_or_codes(self):
        user = self.create_user()
        AccountAdapter().send_notification_mail("mfa/email/totp_activated", user)
        self.assertEqual(len(mail.outbox), 1)
        self.assert_multipart(mail.outbox[0])
        self.assertIn("MFA security changed", mail.outbox[0].subject)
        self.assertNotIn("recovery code", mail.outbox[0].body.lower())
        self.assertNotIn("otpauth", mail.outbox[0].body.lower())

    def test_optional_security_email_failure_does_not_break_state_change(self):
        user = self.create_user()
        with patch("apps.accounts.emails.send_mail", side_effect=OSError("SMTP down")):
            with self.assertLogs("apps.accounts.emails", level="ERROR"):
                self.assertFalse(
                    send_branded_email(
                        user.email,
                        "Security notification",
                        "accounts/emails/password_changed",
                        fail_silently=True,
                    )
                )
                AccountAdapter().send_notification_mail("mfa/email/totp_activated", user)

    def test_password_change_succeeds_when_notification_email_is_unavailable(self):
        user = self.create_user()
        self.client.force_login(user)
        new_password = "A-New-Secure-Password-93!"
        with patch("apps.accounts.emails.send_mail", side_effect=OSError("SMTP down")):
            with self.assertLogs("apps.accounts.emails", level="ERROR"):
                response = self.client.post(
                    reverse("accounts:password_change"),
                    {
                        "old_password": PASSWORD,
                        "new_password1": new_password,
                        "new_password2": new_password,
                    },
                )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))

    def test_new_device_warning_is_sent_once_per_hashed_fingerprint(self):
        user = self.create_user()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("accounts:login"),
                {"login": user.email, "password": PASSWORD},
                REMOTE_ADDR="198.51.100.80",
                HTTP_USER_AGENT="KnownBrowser/1",
            )
        self.assertEqual(LoginDevice.objects.filter(user=user).count(), 1)
        device = LoginDevice.objects.get(user=user)
        self.assertEqual(len(device.fingerprint_digest), 64)
        self.assertFalse(hasattr(device, "ip_address"))
        self.assertFalse(hasattr(device, "user_agent"))
        warnings = [message for message in mail.outbox if "New sign-in" in message.subject]
        self.assertEqual(len(warnings), 1)
        self.assertNotIn("198.51.100.80", warnings[0].body)
        self.client.post(reverse("accounts:logout"))

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse("accounts:login"),
                {"login": user.email, "password": PASSWORD},
                REMOTE_ADDR="198.51.100.80",
                HTTP_USER_AGENT="KnownBrowser/1",
            )
        warnings = [message for message in mail.outbox if "New sign-in" in message.subject]
        self.assertEqual(len(warnings), 1)

    def test_valid_account_lockout_sends_rate_limited_suspicious_warning(self):
        user = self.create_user()
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(5):
                self.client.post(
                    reverse("accounts:login"),
                    {"login": user.email, "password": "wrong-password"},
                    REMOTE_ADDR="198.51.100.81",
                )
        warnings = [message for message in mail.outbox if "Suspicious" in message.subject]
        self.assertEqual(len(warnings), 1)
        self.assert_multipart(warnings[0])
        self.assertNotIn("wrong-password", warnings[0].body)

    @override_settings(PASSWORD_RESET_EMAIL_LIMIT=2, PASSWORD_RESET_EMAIL_WINDOW=900)
    def test_password_reset_email_is_generically_rate_limited(self):
        user = self.create_user()
        responses = []
        for _ in range(3):
            responses.append(
                self.client.post(
                    reverse("accounts:password_reset"),
                    {"email": user.email},
                    REMOTE_ADDR="198.51.100.82",
                )
            )
        self.assertTrue(all(response.status_code == 302 for response in responses))
        reset_messages = [message for message in mail.outbox if "Reset your" in message.subject]
        self.assertEqual(len(reset_messages), 2)
        for message in reset_messages:
            self.assert_multipart(message)
