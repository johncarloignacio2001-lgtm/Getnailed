from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from PIL import features

from apps.accounts.forms import InternalAccountInvitationForm
from apps.accounts.models import AccountActivation, User
from apps.bookings.forms import BookingLookupForm, BookingVerificationForm, PublicBookingForm
from apps.bookings.models import Booking

from .upload_security import safe_image_upload_path, validate_image_upload


PASSWORD = "Correct-Horse-Battery-47!"


def image_upload(name="service.png", content_type="image/png", size=(8, 8)):
    data = BytesIO()
    Image.new("RGB", size, color="white").save(data, format="PNG")
    return SimpleUploadedFile(name, data.getvalue(), content_type=content_type)


def formatted_image_upload(name, image_format, content_type):
    data = BytesIO()
    Image.new("RGB", (8, 8), color="white").save(data, format=image_format)
    return SimpleUploadedFile(name, data.getvalue(), content_type=content_type)


class UploadSecurityTests(TestCase):
    def test_valid_image_uses_a_generated_safe_filename(self):
        uploaded = image_upload("../../customer-supplied-name.png")
        validate_image_upload(uploaded)
        path = safe_image_upload_path(None, uploaded.name)

        self.assertRegex(path, r"^service-images/[0-9a-f]{32}\.png$")
        self.assertNotIn("customer-supplied-name", path)
        self.assertNotIn("..", path)

    def test_supported_image_signatures_are_accepted(self):
        uploads = [
            formatted_image_upload("service.jpg", "JPEG", "image/jpeg"),
            formatted_image_upload("service.png", "PNG", "image/png"),
        ]
        if features.check("webp"):
            uploads.append(
                formatted_image_upload("service.webp", "WEBP", "image/webp")
            )
        for uploaded in uploads:
            with self.subTest(name=uploaded.name):
                validate_image_upload(uploaded)
                self.assertEqual(uploaded.tell(), 0)

    def test_upload_extension_mime_signature_and_size_are_server_validated(self):
        invalid_extension = image_upload("service.php")
        wrong_mime = image_upload("service.png", content_type="text/html")
        wrong_signature = SimpleUploadedFile(
            "service.png",
            b"<script>alert(1)</script>",
            content_type="image/png",
        )
        mismatched_signature = image_upload("service.jpg", content_type="image/jpeg")
        oversized = image_upload()
        oversized.size = settings.MAX_IMAGE_UPLOAD_SIZE + 1

        for uploaded in (
            invalid_extension,
            wrong_mime,
            wrong_signature,
            mismatched_signature,
            oversized,
        ):
            with self.subTest(name=uploaded.name), self.assertRaises(ValidationError):
                validate_image_upload(uploaded)

    def test_truncated_image_and_unsupported_safe_path_are_rejected(self):
        valid = formatted_image_upload("service.png", "PNG", "image/png")
        truncated = SimpleUploadedFile(
            "service.png",
            valid.read()[:20],
            content_type="image/png",
        )
        with self.assertRaises(ValidationError):
            validate_image_upload(truncated)
        self.assertEqual(truncated.tell(), 0)
        with self.assertRaises(ValidationError):
            safe_image_upload_path(None, "service.svg")

    @override_settings(MAX_IMAGE_UPLOAD_PIXELS=3)
    def test_upload_pixel_limit_is_enforced(self):
        with self.assertRaises(ValidationError):
            validate_image_upload(image_upload(size=(2, 2)))

    def test_media_storage_is_separate_from_static_locations(self):
        media_root = Path(settings.MEDIA_ROOT).resolve()
        for static_root in [settings.STATIC_ROOT, *settings.STATICFILES_DIRS]:
            static_root = Path(static_root).resolve()
            self.assertNotEqual(media_root, static_root)
            self.assertFalse(media_root.is_relative_to(static_root))
            self.assertFalse(static_root.is_relative_to(media_root))


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
)
class InputSecurityTests(TestCase):
    def create_user(self, email, role):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def test_empty_posts_are_bound_and_server_validation_errors_are_returned(self):
        response = self.client.post(reverse("bookings:index"), {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertIn("customer_name", response.context["form"].errors)

    def test_codes_tokens_phones_and_roles_reject_tampering(self):
        self.assertFalse(
            BookingVerificationForm(
                {"reference": "BK-valid_reference", "code": "abcdefgh"}
            ).is_valid()
        )
        self.assertFalse(
            BookingLookupForm(
                {"reference": "BK-valid_reference", "access_token": "x" * 65}
            ).is_valid()
        )
        booking_form = PublicBookingForm(
            {
                "customer_name": "Guest",
                "email": "guest@example.com",
                "phone_number": "javascript:alert(1)",
                "service_name": "Manicure",
                "scheduled_for": timezone.now() + timedelta(days=1),
            }
        )
        self.assertFalse(booking_form.is_valid())
        self.assertIn("phone_number", booking_form.errors)

        owner = self.create_user("owner@example.com", User.Role.OWNER)
        invitation = InternalAccountInvitationForm(
            {
                "first_name": "Mallory",
                "email": "mallory@example.com",
                "phone_number": "09171234567",
                "role": User.Role.OWNER,
            },
            actor=owner,
        )
        self.assertFalse(invitation.is_valid())
        self.assertIn("role", invitation.errors)

    def test_activation_state_transition_requires_csrf_protected_post(self):
        user = User.objects.create_user(
            "invitee@example.com",
            password=None,
            is_active=False,
            is_active_staff_member=False,
        )
        activation, token = AccountActivation.issue(user)
        url = reverse(
            "accounts:activate",
            kwargs={"public_id": activation.public_id, "token": token},
        )
        csrf_client = Client(enforce_csrf_checks=True)

        preview = csrf_client.get(url)
        self.assertEqual(preview.status_code, 200)
        self.assertNotIn("pending_account_activation", csrf_client.session)
        self.assertEqual(csrf_client.post(url).status_code, 403)

        csrf_token = csrf_client.cookies[settings.CSRF_COOKIE_NAME].value
        accepted = csrf_client.post(url, {"csrfmiddlewaretoken": csrf_token})
        self.assertEqual(accepted.status_code, 302)
        self.assertIn("pending_account_activation", csrf_client.session)

    def test_browser_form_actions_reject_missing_csrf_tokens(self):
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(reverse("bookings:index"), {}).status_code, 403)

        owner = self.create_user("owner@example.com", User.Role.OWNER)
        csrf_client.force_login(owner)
        self.assertEqual(
            csrf_client.post(reverse("accounts:invite_internal"), {}).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(reverse("accounts:logout_all_devices"), {}).status_code,
            403,
        )

    def test_user_generated_booking_output_is_html_escaped(self):
        owner = self.create_user("owner@example.com", User.Role.OWNER)
        payload = '<script id="stored-xss">alert(1)</script>'
        Booking.objects.create(
            customer_name=payload,
            email="guest@example.com",
            service_name=payload,
            scheduled_for=timezone.now() + timedelta(days=1),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        self.client.force_login(owner)

        response = self.client.get(reverse("bookings:manage"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, payload)
        self.assertContains(response, "&lt;script id=&quot;stored-xss&quot;&gt;", count=2)

    def test_oversized_invalid_password_reset_identifier_is_not_queried(self):
        oversized_email = "a" * 10000
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": oversized_email},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)

    def test_customer_dedicated_windows_render_successfully(self):
        customer_user = self.create_user("customer@example.com", User.Role.CUSTOMER)
        self.client.force_login(customer_user)

        # My Appointments window
        appts_res = self.client.get(reverse("core:customer_appointments"))
        self.assertEqual(appts_res.status_code, 200)
        self.assertContains(appts_res, "My Appointments")

        # Services & Pricing window
        services_res = self.client.get(reverse("core:customer_services"))
        self.assertEqual(services_res.status_code, 200)
        self.assertContains(services_res, "Services &amp; Pricing")

        # My Profile window
        profile_res = self.client.get(reverse("core:customer_profile"))
        self.assertEqual(profile_res.status_code, 200)
        self.assertContains(profile_res, "My Profile")

        # Profile update action
        update_res = self.client.post(
            reverse("core:customer_profile"),
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "phone": "+63 912 345 6789",
            },
        )
        self.assertRedirects(update_res, reverse("core:customer_profile"))
        customer_user.refresh_from_db()
        self.assertEqual(customer_user.first_name, "Jane")
        self.assertEqual(customer_user.last_name, "Doe")
