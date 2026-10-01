import re
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audittrail.models import AuditLog

from .models import Booking


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="",
    BOOKING_VERIFICATION_MAX_ATTEMPTS=3,
    BOOKING_RESEND_COOLDOWN=timedelta(minutes=5),
    BOOKING_MAX_RESENDS=2,
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
)
class PublicBookingSecurityTests(TestCase):
    def booking_data(self, email="guest@example.com"):
        scheduled_for = timezone.localtime(timezone.now() + timedelta(days=2))
        return {
            "customer_name": "Guest Customer",
            "email": email,
            "phone_number": "09171234567",
            "service_name": "Classic Manicure",
            "scheduled_for": scheduled_for.strftime("%Y-%m-%dT%H:%M"),
        }

    def submit_booking(self, email="guest@example.com"):
        response = self.client.post(reverse("bookings:index"), self.booking_data(email))
        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(email=email)
        code = re.search(r"\n(\d{8})\n", mail.outbox[-1].body).group(1)
        return booking, code

    def verify_booking(self, booking, code):
        response = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": code},
        )
        self.assertEqual(response.status_code, 302)
        return response["Location"].split("/")[-2]

    def create_user(self, email, role, **permissions):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
            **permissions,
        )

    def test_submission_creates_only_unverified_booking_and_sends_hashed_code(self):
        user_count = User.objects.count()
        booking, code = self.submit_booking("GUEST@Example.com".lower())
        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(booking.status, Booking.Status.UNVERIFIED)
        self.assertTrue(booking.reference.isdigit())
        self.assertEqual(len(booking.reference), 10)
        self.assertNotEqual(booking.reference, str(booking.pk))
        self.assertNotEqual(booking.verification_code_digest, code)
        self.assertNotIn(code, booking.verification_code_digest)
        self.assertIsNone(booking.verified_at)

    def test_successful_verification_confirms_and_issues_hashed_access_token(self):
        booking, code = self.submit_booking()
        token = self.verify_booking(booking, code)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNotNone(booking.verified_at)
        self.assertEqual(booking.verification_code_digest, "")
        self.assertNotEqual(booking.public_access_token_digest, token)
        self.assertNotIn(token, booking.public_access_token_digest)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn(booking.reference, mail.outbox[-1].body)

        response = self.client.get(
            reverse(
                "bookings:public_status",
                kwargs={"reference": booking.reference, "token": token},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, booking.service_name)

    def test_verification_attempt_limit_and_expiry_are_enforced(self):
        booking, code = self.submit_booking()
        for _ in range(settings.BOOKING_VERIFICATION_MAX_ATTEMPTS):
            response = self.client.post(
                reverse("bookings:verify"),
                {"reference": booking.reference, "code": "00000000"},
            )
            self.assertContains(response, "invalid or unavailable")
        response = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": code},
        )
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(
            booking.verification_failed_attempts,
            settings.BOOKING_VERIFICATION_MAX_ATTEMPTS,
        )

        expired, expired_code = self.submit_booking("expired@example.com")
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=("expires_at",))
        self.client.post(
            reverse("bookings:verify"),
            {"reference": expired.reference, "code": expired_code},
        )
        expired.refresh_from_db()
        self.assertEqual(expired.status, Booking.Status.EXPIRED)

    def test_expired_verification_code_is_rejected_while_booking_remains_available(self):
        booking, code = self.submit_booking()
        booking.verification_code_expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=("verification_code_expires_at",))

        response = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": code},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or unavailable")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.UNVERIFIED)
        self.assertIsNone(booking.verified_at)

    def test_resend_is_generic_rate_limited_and_invalidates_old_code(self):
        booking, old_code = self.submit_booking()
        initial_mail_count = len(mail.outbox)
        response = self.client.post(
            reverse("bookings:resend"),
            {"reference": booking.reference, "email": booking.email},
            follow=True,
        )
        self.assertContains(response, "If the unverified booking is eligible")
        self.assertEqual(len(mail.outbox), initial_mail_count)

        booking.verification_sent_at = timezone.now() - timedelta(minutes=6)
        booking.save(update_fields=("verification_sent_at",))
        self.client.post(
            reverse("bookings:resend"),
            {"reference": booking.reference, "email": booking.email},
        )
        self.assertEqual(len(mail.outbox), initial_mail_count + 1)
        new_code = re.search(r"\n(\d{8})\n", mail.outbox[-1].body).group(1)
        self.assertNotEqual(old_code, new_code)

        old_response = self.client.post(
            reverse("bookings:verify"),
            {"reference": booking.reference, "code": old_code},
        )
        self.assertEqual(old_response.status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse("bookings:verify"),
                {"reference": booking.reference, "code": new_code},
            ).status_code,
            302,
        )

        missing = self.client.post(
            reverse("bookings:resend"),
            {"reference": "BK-missing-reference", "email": "missing@example.com"},
            follow=True,
        )
        self.assertContains(missing, "If the unverified booking is eligible")

    def test_status_cancel_and_reschedule_tokens_are_bound_to_one_booking(self):
        first, first_code = self.submit_booking("first@example.com")
        first_token = self.verify_booking(first, first_code)
        second, second_code = self.submit_booking("second@example.com")
        second_token = self.verify_booking(second, second_code)

        mismatched_url = reverse(
            "bookings:public_status",
            kwargs={"reference": second.reference, "token": first_token},
        )
        missing_url = reverse(
            "bookings:public_status",
            kwargs={"reference": "BK-does-not-exist", "token": first_token},
        )
        mismatched = self.client.get(mismatched_url)
        missing = self.client.get(missing_url)
        self.assertEqual(mismatched.status_code, missing.status_code)
        self.assertContains(mismatched, "Booking access unavailable", status_code=404)
        self.assertNotContains(mismatched, second.customer_name, status_code=404)

        new_time = timezone.localtime(timezone.now() + timedelta(days=4)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        reschedule_response = self.client.post(
            reverse(
                "bookings:reschedule",
                kwargs={"reference": first.reference, "token": first_token},
            ),
            {"scheduled_for": new_time},
        )
        self.assertEqual(reschedule_response.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(
            timezone.localtime(first.scheduled_for).strftime("%Y-%m-%dT%H:%M"),
            new_time,
        )

        cancel_response = self.client.post(
            reverse(
                "bookings:cancel",
                kwargs={"reference": first.reference, "token": first_token},
            ),
            {"confirm": "on"},
        )
        self.assertEqual(cancel_response.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.status, Booking.Status.CANCELLED)
        second.refresh_from_db()
        self.assertEqual(second.status, Booking.Status.CONFIRMED)
        self.assertTrue(second.accepts_public_access_token(second_token))

    def test_status_lookup_requires_reference_and_token_without_enumeration(self):
        booking, code = self.submit_booking()
        token = self.verify_booking(booking, code)
        valid = self.client.post(
            reverse("bookings:status_lookup"),
            {"reference": booking.reference, "access_token": token},
        )
        self.assertEqual(valid.status_code, 302)
        invalid = self.client.post(
            reverse("bookings:status_lookup"),
            {"reference": booking.reference, "access_token": "wrong-token"},
        )
        missing = self.client.post(
            reverse("bookings:status_lookup"),
            {"reference": "BK-not-found", "access_token": "wrong-token"},
        )
        self.assertEqual(invalid.status_code, missing.status_code)
        self.assertContains(invalid, "invalid or unavailable")

    def test_internal_querysets_enforce_management_and_assignment_scope(self):
        owner = self.create_user("owner@example.com", User.Role.OWNER)
        cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        staff = self.create_user("staff@example.com", User.Role.STAFF)
        other_staff = self.create_user("other@example.com", User.Role.STAFF)
        assigned_data = self.booking_data("assigned@example.com")
        assigned_data["scheduled_for"] = timezone.now() + timedelta(days=2)
        assigned = Booking.objects.create(
            **assigned_data,
            assigned_staff=staff,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        other_data = self.booking_data("other-booking@example.com")
        other_data["scheduled_for"] = timezone.now() + timedelta(days=2)
        other = Booking.objects.create(
            **other_data,
            assigned_staff=other_staff,
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        self.assertEqual(Booking.objects.visible_to(owner).count(), 2)
        self.assertEqual(Booking.objects.visible_to(cashier).count(), 2)
        self.assertEqual(list(Booking.objects.visible_to(staff)), [assigned])
        self.assertNotIn(other, Booking.objects.visible_to(staff))

    def test_expiry_management_command_marks_stale_requests(self):
        booking, _ = self.submit_booking()
        booking.expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=("expires_at",))
        call_command("expire_unverified_bookings", verbosity=0)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.EXPIRED)
        self.assertEqual(booking.verification_code_digest, "")

    def test_sensitive_action_reauthentication_period_is_configured(self):
        self.assertGreater(settings.ACCOUNT_REAUTHENTICATION_TIMEOUT, 0)

    def test_expired_access_token_is_rejected_and_tokens_are_redacted_from_audit(self):
        booking, code = self.submit_booking()
        token = self.verify_booking(booking, code)
        booking.public_access_expires_at = timezone.now() - timedelta(seconds=1)
        booking.save(update_fields=("public_access_expires_at",))
        expired = self.client.get(
            reverse(
                "bookings:public_status",
                kwargs={"reference": booking.reference, "token": token},
            )
        )
        self.assertEqual(expired.status_code, 404)

        booking.public_access_expires_at = timezone.now() + timedelta(hours=1)
        booking.save(update_fields=("public_access_expires_at",))
        customer = self.create_user("customer@example.com", User.Role.CUSTOMER)
        self.client.force_login(customer)
        new_time = timezone.localtime(timezone.now() + timedelta(days=5)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        self.client.post(
            reverse(
                "bookings:reschedule",
                kwargs={"reference": booking.reference, "token": token},
            ),
            {"scheduled_for": new_time},
        )
        audit_path = AuditLog.objects.latest("created_at").path
        self.assertNotIn(token, audit_path)
        self.assertIn("<redacted>", audit_path)
