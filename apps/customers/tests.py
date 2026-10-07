from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.customers.otp import (
    SESSION_KEY_ATTEMPTS,
    SESSION_KEY_DIGEST,
    SESSION_KEY_EXPIRES_AT,
    SESSION_KEY_USER_ID,
    hash_otp_code,
)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
)
class CustomerLoginOTPTests(TestCase):
    def setUp(self):
        self.password = "ValidPassword123!"
        self.customer_user = User.objects.create_user(
            email="cust_test@example.com",
            password=self.password,
            first_name="Maria",
            last_name="Clara",
            role=User.Role.CUSTOMER,
            is_active=True,
            email_verified_at=timezone.now(),
        )
        self.customer = Customer.objects.create(
            user=self.customer_user,
            first_name="Maria",
            last_name="Clara",
            email=self.customer_user.email,
            phone="09171234567",
        )
        self.client = Client()

    def test_customer_login_initiates_otp_and_sends_email(self):
        mail.outbox.clear()
        response = self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer_user.email, "password": self.password},
        )
        self.assertRedirects(response, reverse("customers:customer_login_verify_otp"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.customer_user.email])
        self.assertIn("verification code", mail.outbox[0].subject.lower())

        session = self.client.session
        self.assertEqual(session.get(SESSION_KEY_USER_ID), self.customer_user.pk)
        self.assertTrue(session.get(SESSION_KEY_DIGEST))

    def test_customer_verify_otp_success(self):
        # Step 1: Login to get OTP sent
        self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer_user.email, "password": self.password},
        )
        # Extract code from email body
        email_body = mail.outbox[-1].body
        # Code is 6 digits
        import re
        match = re.search(r"\b\d{6}\b", email_body)
        self.assertIsNotNone(match)
        code = match.group(0)

        # Step 2: Post OTP code
        response = self.client.post(
            reverse("customers:customer_login_verify_otp"),
            {"code": code},
        )
        self.assertRedirects(response, reverse("core:customer_dashboard"))

        # Verify user is now authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user.pk, self.customer_user.pk)

    def test_customer_verify_otp_invalid_code(self):
        self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer_user.email, "password": self.password},
        )
        response = self.client.post(
            reverse("customers:customer_login_verify_otp"),
            {"code": "000000"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid code")

    def test_customer_verify_otp_expired(self):
        self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer_user.email, "password": self.password},
        )
        session = self.client.session
        session[SESSION_KEY_EXPIRES_AT] = (timezone.now() - timedelta(minutes=1)).isoformat()
        session.save()

        response = self.client.post(
            reverse("customers:customer_login_verify_otp"),
            {"code": "123456"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")

    def test_customer_resend_otp(self):
        mail.outbox.clear()
        self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer_user.email, "password": self.password},
        )
        self.assertEqual(len(mail.outbox), 1)

        # Attempt immediate resend (blocked by 60s cooldown)
        response = self.client.post(reverse("customers:customer_login_resend_otp"))
        self.assertRedirects(response, reverse("customers:customer_login_verify_otp"))
        self.assertEqual(len(mail.outbox), 1)  # not resent yet

        # Fast forward time or simulate elapsed cooldown
        session = self.client.session
        session["customer_otp_sent_at"] = (timezone.now() - timedelta(seconds=65)).isoformat()
        session.save()

        response = self.client.post(reverse("customers:customer_login_resend_otp"))
        self.assertRedirects(response, reverse("customers:customer_login_verify_otp"))
        self.assertEqual(len(mail.outbox), 2)  # resent successfully!


class CustomerRegistrationPasswordCriteriaTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_registration_page_renders_password_checklist(self):
        response = self.client.get(reverse("customers:register_customer"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Minimum length 8 characters")
        self.assertContains(response, "One uppercase letter [A-Z]")
        self.assertContains(response, "One lowercase letter [a-z]")
        self.assertContains(response, "One numeric character [0-9]")
        self.assertContains(response, "One special character ['!@$% etc]")
        self.assertContains(response, "toggle-password-btn")

    def test_password_criteria_validation(self):
        from apps.customers.forms import CustomerRegistrationForm

        # 1. Less than 8 chars
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "Pass1!",
            "password_confirmation": "Pass1!",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("at least 8 characters", str(form.errors.get("password")))

        # 2. No uppercase
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "password123!",
            "password_confirmation": "password123!",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("uppercase letter", str(form.errors.get("password")))

        # 3. No lowercase
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "PASSWORD123!",
            "password_confirmation": "PASSWORD123!",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("lowercase letter", str(form.errors.get("password")))

        # 4. No number
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "PasswordSpecial!",
            "password_confirmation": "PasswordSpecial!",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("numeric character", str(form.errors.get("password")))

        # 5. No special char
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "Password1234",
            "password_confirmation": "Password1234",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("special character", str(form.errors.get("password")))

        # 6. Passwords do not match
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "ValidPassword123!",
            "password_confirmation": "DifferentPass123!",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("passwords do not match", str(form.errors.get("password_confirmation")).lower())

        # 7. Valid password meeting all 5 criteria
        form = CustomerRegistrationForm({
            "first_name": "Anna",
            "last_name": "Reyes",
            "email": "anna@example.com",
            "phone": "09181112233",
            "password": "ValidPassword123!",
            "password_confirmation": "ValidPassword123!",
        })
        self.assertTrue(form.is_valid())

    def test_successful_customer_registration_flow(self):
        response = self.client.post(
            reverse("customers:register_customer"),
            {
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "email": "juan.dc@example.com",
                "phone": "09191234567",
                "password": "SecurePass123!#",
                "password_confirmation": "SecurePass123!#",
            },
        )
        self.assertRedirects(response, reverse("customers:customer_login"))
        user = User.objects.get(email="juan.dc@example.com")
        self.assertEqual(user.first_name, "Juan")
        self.assertEqual(user.last_name, "Dela Cruz")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        customer = Customer.objects.get(user=user)
        self.assertEqual(customer.phone, "09191234567")

