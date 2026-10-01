from datetime import timedelta

from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    hotp_value,
    yield_hotp_counters_from_time,
)
from axes.models import AccessAttempt, AccessFailureLog
from captcha.models import CaptchaStore
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountActivation, User


PASSWORD = "Correct-Horse-Battery-47!"
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
ATTACKER_IP = "198.51.100.24"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=True,
    MFA_REQUIRE_INTERNAL_USERS=False,
    LOGIN_CAPTCHA_THRESHOLD=100,
)
class LoginProtectionTests(TestCase):
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

    def login_payload(self, email, password="wrong-password"):
        return {"login": email, "password": password}

    def fail_login(self, client, email, count, ip=ATTACKER_IP, user_agent="SecurityTest/1.0"):
        responses = []
        for _ in range(count):
            responses.append(
                client.post(
                    reverse("accounts:login"),
                    self.login_payload(email),
                    REMOTE_ADDR=ip,
                    HTTP_USER_AGENT=user_agent,
                    HTTP_ACCEPT="text/html",
                )
            )
        return responses

    def current_totp_code(self):
        return format_hotp_value(hotp_value(TOTP_SECRET, next(yield_hotp_counters_from_time())))

    def authenticate_owner(self):
        owner = self.create_user("owner@example.com", User.Role.OWNER)
        TOTP.activate(owner, TOTP_SECRET)
        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(owner.email, PASSWORD),
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post(
            reverse("mfa_authenticate"),
            {"code": self.current_totp_code()},
        )
        self.assertEqual(response.status_code, 302)
        return owner

    def test_five_failures_create_temporary_email_ip_lockout_and_safe_logs(self):
        user = self.create_user("Person@Example.com")
        responses = self.fail_login(self.client, "PERSON@EXAMPLE.COM", 5)
        self.assertEqual(responses[-1].status_code, 429)
        self.assertContains(responses[-1], "temporarily unavailable", status_code=429)

        attempt = AccessAttempt.objects.get(username=user.email, ip_address=ATTACKER_IP)
        self.assertEqual(attempt.failures_since_start, 5)
        self.assertNotIn("wrong-password", attempt.post_data)
        self.assertIn("password=********************", attempt.post_data)
        self.assertIn("login=********************", attempt.post_data)
        self.assertEqual(AccessFailureLog.objects.filter(username=user.email).count(), 5)

        locked_response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(user.email, PASSWORD),
            REMOTE_ADDR=ATTACKER_IP,
            HTTP_USER_AGENT="SecurityTest/1.0",
        )
        self.assertEqual(
            locked_response.status_code,
            429,
            locked_response.context["form"].errors if locked_response.context else "",
        )

        other_ip_response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(user.email, PASSWORD),
            REMOTE_ADDR="198.51.100.25",
        )
        self.assertEqual(other_ip_response.status_code, 302)

    def test_lockout_expires_instead_of_permanently_locking_account(self):
        user = self.create_user()
        self.fail_login(self.client, user.email, 5)
        expired_at = timezone.now() - timedelta(minutes=16)
        AccessAttempt.objects.filter(username=user.email).update(attempt_time=expired_at)
        for attempt in AccessAttempt.objects.filter(username=user.email):
            attempt.expiration.expires_at = expired_at
            attempt.expiration.save(update_fields=("expires_at",))

        response = self.client.post(
            reverse("accounts:login"),
            self.login_payload(user.email, PASSWORD),
            REMOTE_ADDR=ATTACKER_IP,
            HTTP_USER_AGENT="SecurityTest/1.0",
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AccessAttempt.objects.filter(username=user.email).exists())

    @override_settings(LOGIN_CAPTCHA_THRESHOLD=2)
    def test_captcha_appears_only_after_repeated_failures_and_is_required(self):
        user = self.create_user()
        initial = self.client.get(reverse("accounts:login"), REMOTE_ADDR=ATTACKER_IP)
        self.assertNotContains(initial, "Security check")
        self.fail_login(self.client, user.email, 2)

        challenged = self.client.get(reverse("accounts:login"), REMOTE_ADDR=ATTACKER_IP)
        self.assertContains(challenged, "Security check")
        missing_captcha = self.client.post(
            reverse("accounts:login"),
            self.login_payload(user.email, PASSWORD),
            REMOTE_ADDR=ATTACKER_IP,
        )
        self.assertEqual(missing_captcha.status_code, 200)

        captcha_key = CaptchaStore.generate_key()
        captcha_answer = CaptchaStore.objects.get(hashkey=captcha_key).response
        passed = self.client.post(
            reverse("accounts:login"),
            {
                **self.login_payload(user.email, PASSWORD),
                "captcha_0": captcha_key,
                "captcha_1": captcha_answer,
            },
            REMOTE_ADDR=ATTACKER_IP,
        )
        self.assertEqual(passed.status_code, 302)

    def test_owner_can_review_and_clear_only_valid_account_lockouts(self):
        self.authenticate_owner()
        locked_user = self.create_user("locked@example.com")
        attack_client = Client()
        self.fail_login(attack_client, locked_user.email, 5)
        self.fail_login(attack_client, "unknown@example.com", 5, ip="198.51.100.30")

        response = self.client.get(reverse("accounts:login_lockouts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, locked_user.email)
        self.assertNotContains(response, "unknown@example.com")
        lockouts = response.context["lockouts"]
        self.assertEqual(len(lockouts), 1)

        response = self.client.post(
            reverse("accounts:login_lockouts"),
            {"lockout": lockouts[0]["token"]},
        )
        self.assertRedirects(response, reverse("accounts:login_lockouts"))
        self.assertFalse(AccessAttempt.objects.filter(username=locked_user.email).exists())
        self.assertTrue(AccessAttempt.objects.filter(username="unknown@example.com").exists())

    def test_lockout_management_requires_owner_and_recent_reauthentication(self):
        staff = self.create_user()
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("accounts:login_lockouts")).status_code, 403)

        owner = self.create_user("owner@example.com", User.Role.OWNER)
        TOTP.activate(owner, TOTP_SECRET)
        self.client.force_login(owner)
        response = self.client.get(reverse("accounts:login_lockouts"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("reauthenticate", response["Location"])

    def test_external_redirects_are_rejected_across_authentication_flows(self):
        user = self.create_user()
        evil_url = "https://evil.example/steal"
        login_response = self.client.post(
            f"{reverse('accounts:login')}?next={evil_url}",
            {**self.login_payload(user.email, PASSWORD), "next": evil_url},
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertFalse(login_response["Location"].startswith(evil_url))

        logout_response = self.client.post(
            reverse("accounts:logout"),
            {"next": evil_url},
        )
        self.assertRedirects(logout_response, reverse("core:home"))

        invited = User.objects.create_user(
            "invitee@example.com",
            password=None,
            is_active=False,
            is_active_staff_member=False,
        )
        activation, token = AccountActivation.issue(invited)
        activation_url = reverse(
            "accounts:activate",
            kwargs={"public_id": activation.public_id, "token": token},
        )
        self.assertEqual(self.client.get(activation_url, {"next": evil_url}).status_code, 200)
        activation_response = self.client.post(activation_url, {"next": evil_url})
        self.assertRedirects(
            activation_response,
            reverse("accounts:activation_password", kwargs={"public_id": activation.public_id}),
        )

        reset_response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "missing@example.com", "next": evil_url},
        )
        self.assertRedirects(reset_response, reverse("accounts:password_reset_done"))
