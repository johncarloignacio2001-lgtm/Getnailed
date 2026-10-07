from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.authorization import (
    CAPABILITY_ASSIGN_SERVICES,
    CAPABILITY_MANAGE_BOOKINGS,
    CAPABILITY_MANAGE_CUSTOMERS,
    CAPABILITY_USE_POS,
    has_capability,
    scope_owned_or_assigned,
)
from apps.accounts.decorators import (
    CashierOrOwnerRequiredMixin,
    InternalUserRequiredMixin,
    OwnerRequiredMixin,
    StaffRequiredMixin,
)
from apps.accounts.forms import InternalAccountInvitationForm
from apps.accounts.models import User
from apps.audittrail.models import AuditLog


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
    LOGIN_CAPTCHA_THRESHOLD=100,
)
class AuthorizationMatrixTests(TestCase):
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

    def setUp(self):
        self.owner = self.create_user("owner@example.com", User.Role.OWNER)
        self.cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        self.staff = self.create_user("staff@example.com", User.Role.STAFF)
        self.granted_staff = self.create_user(
            "granted@example.com",
            User.Role.STAFF,
            can_use_pos=True,
            can_manage_bookings=True,
            can_manage_customers=True,
            can_assign_services=True,
        )
        self.customer = self.create_user("customer@example.com", User.Role.CUSTOMER)

    def assert_access(self, user, url_name, expected_status):
        client = Client()
        if user is not None:
            client.force_login(user)
        response = client.get(reverse(url_name))
        self.assertEqual(
            response.status_code,
            expected_status,
            f"{getattr(user, 'email', 'anonymous')} -> {url_name}",
        )
        if user is None and expected_status == 302:
            self.assertIn(reverse("accounts:login"), response["Location"])

    def test_direct_dashboard_urls_enforce_role_server_side(self):
        matrix = {
            "core:owner_dashboard": {
                self.owner: 200,
                self.cashier: 403,
                self.staff: 403,
                self.customer: 403,
                None: 302,
            },
            "core:staff_dashboard": {
                self.owner: 200,
                self.cashier: 200,
                self.staff: 200,
                self.customer: 403,
                None: 302,
            },
            "core:customer_dashboard": {
                self.owner: 403,
                self.cashier: 403,
                self.staff: 403,
                self.customer: 200,
                None: 302,
            },
        }
        for url_name, expectations in matrix.items():
            for user, status in expectations.items():
                self.assert_access(user, url_name, status)

    def test_owner_only_business_and_security_surfaces(self):
        owner_only = (
            "reports:index",
            "forecasting:index",
            "audittrail:index",
            "accounts:invite_internal",
            "pos:void_approval",
        )
        for url_name in owner_only:
            self.assert_access(self.owner, url_name, 200)
            for denied in (self.cashier, self.staff, self.granted_staff, self.customer):
                self.assert_access(denied, url_name, 403)
            self.assert_access(None, url_name, 302)

    def test_cashier_operational_permissions_and_limits(self):
        for allowed in (
            "services:index",
            "customers:index",
            "bookings:manage",
            "pos:index",
            "monitoring:index",
            "monitoring:assignments",
            "reports:daily_summary",
        ):
            self.assert_access(self.cashier, allowed, 200)
        for denied in (
            "reports:index",
            "forecasting:index",
            "audittrail:index",
            "accounts:invite_internal",
        ):
            self.assert_access(self.cashier, denied, 403)

    def test_staff_requires_explicit_grants_for_management_surfaces(self):
        self.assert_access(self.staff, "services:index", 403)
        self.assert_access(self.granted_staff, "services:index", 403)
        for denied in ("customers:index", "bookings:manage", "pos:index"):
            self.assert_access(self.staff, denied, 403)
            self.assert_access(self.granted_staff, denied, 200)
        self.assert_access(self.staff, "monitoring:index", 200)
        self.assert_access(self.staff, "bookings:assigned", 200)
        self.assert_access(self.staff, "monitoring:assignments", 403)
        self.assert_access(self.granted_staff, "monitoring:assignments", 200)
        self.assert_access(self.staff, "reports:daily_summary", 403)
        self.assert_access(self.staff, "reports:index", 403)
        self.assert_access(self.staff, "forecasting:index", 403)

    def test_staff_password_login_reaches_restricted_dashboard_only(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"login": self.staff.email, "password": PASSWORD},
        )
        self.assertRedirects(
            response,
            reverse("core:dashboard_router"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(reverse("core:dashboard_router")),
            reverse("core:staff_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.get(reverse("core:staff_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("reports:index")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:invite_internal")).status_code, 403)

    def test_customer_cannot_access_internal_data_surfaces(self):
        for denied in (
            "services:index",
            "customers:index",
            "bookings:manage",
            "bookings:assigned",
            "pos:index",
            "monitoring:index",
            "reports:index",
            "reports:daily_summary",
            "forecasting:index",
            "audittrail:index",
        ):
            self.assert_access(self.customer, denied, 403)
        self.assert_access(self.customer, "notifications:index", 200)
        self.assert_access(self.customer, "bookings:index", 200)
        self.assert_access(None, "bookings:index", 200)

    def test_customer_login_requires_customer_role_and_redirects_to_customer_dashboard(self):
        customer_client = Client()
        response = customer_client.post(
            reverse("customers:customer_login"),
            {"login": self.customer.email, "password": PASSWORD},
        )
        self.assertRedirects(
            response,
            reverse("customers:customer_login_verify_otp"),
            fetch_redirect_response=False,
        )
        import re
        from django.core import mail
        match = re.search(r"\b\d{6}\b", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        verify_resp = customer_client.post(
            reverse("customers:customer_login_verify_otp"),
            {"code": match.group(0)},
        )
        self.assertRedirects(
            verify_resp,
            reverse("core:customer_dashboard"),
            fetch_redirect_response=False,
        )

        staff_client = Client()
        response = staff_client.post(
            reverse("customers:customer_login"),
            {"login": self.staff.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This login is for customer accounts only.")

    def test_customer_dashboard_shows_web_navbar_and_navigation(self):
        client = Client()
        client.force_login(self.customer)

        response = client.get(reverse("core:customer_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'customer-navbar')
        self.assertNotContains(response, 'class="sidebar"')
        self.assertContains(response, f'href="{reverse("core:dashboard_router")}"')
        self.assertContains(response, f'href="{reverse("mfa_index")}"')
        self.assertContains(response, f'href="{reverse("notifications:index")}"')

        # Internal staff dashboard still uses the vertical sidebar
        staff_client = Client()
        staff_client.force_login(self.staff)
        staff_response = staff_client.get(reverse("core:staff_dashboard"))
        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, 'class="sidebar"')
        self.assertNotContains(staff_response, 'customer-navbar')

    def test_customer_logout_redirects_to_landing_page(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:home"))

    def test_customer_logout_all_devices_redirects_to_landing_page(self):
        self.client.post(
            reverse("customers:customer_login"),
            {"login": self.customer.email, "password": PASSWORD},
        )
        import re
        from django.core import mail
        match = re.search(r"\b\d{6}\b", mail.outbox[-1].body)
        self.client.post(
            reverse("customers:customer_login_verify_otp"),
            {"code": match.group(0)},
        )
        response = self.client.post(reverse("accounts:logout_all_devices"))
        self.assertRedirects(response, reverse("core:home"))

    def test_fine_grained_capabilities_are_not_role_field_tampering(self):
        self.assertTrue(has_capability(self.cashier, CAPABILITY_USE_POS))
        self.assertTrue(has_capability(self.cashier, CAPABILITY_MANAGE_BOOKINGS))
        self.assertTrue(has_capability(self.cashier, CAPABILITY_MANAGE_CUSTOMERS))
        self.assertTrue(has_capability(self.cashier, CAPABILITY_ASSIGN_SERVICES))
        self.assertFalse(has_capability(self.staff, CAPABILITY_USE_POS))
        self.assertTrue(has_capability(self.granted_staff, CAPABILITY_USE_POS))
        self.assertFalse(has_capability(self.customer, CAPABILITY_USE_POS))

    def test_account_creation_form_rechecks_owner_authorization(self):
        data = {"email": "new@example.com", "role": User.Role.STAFF}
        denied_form = InternalAccountInvitationForm(data, actor=self.cashier)
        self.assertFalse(denied_form.is_valid())
        self.assertIn("Only an owner", denied_form.non_field_errors()[0])
        owner_form = InternalAccountInvitationForm(data, actor=self.owner)
        self.assertTrue(owner_form.is_valid())

    def test_user_queryset_prevents_other_staff_information_access(self):
        self.assertEqual(list(User.objects.visible_to(self.staff)), [self.staff])
        self.assertEqual(User.objects.visible_to(self.owner).count(), User.objects.count())
        self.assertFalse(User.objects.visible_to(AnonymousUser()).exists())

    def test_scoped_queryset_blocks_changed_object_ids(self):
        own_log = AuditLog.objects.create(user=self.staff, method="POST", path="/own/")
        other_log = AuditLog.objects.create(user=self.granted_staff, method="POST", path="/other/")
        scoped = scope_owned_or_assigned(
            AuditLog.objects.all(),
            self.staff,
            owner_field="user",
        )
        self.assertEqual(get_object_or_404(scoped, pk=own_log.pk), own_log)
        with self.assertRaises(Http404):
            get_object_or_404(scoped, pk=other_log.pk)

    def test_required_decorator_mixins_expose_consistent_predicates(self):
        self.assertTrue(OwnerRequiredMixin.permission_predicate(self.owner))
        self.assertFalse(OwnerRequiredMixin.permission_predicate(self.cashier))
        self.assertTrue(CashierOrOwnerRequiredMixin.permission_predicate(self.cashier))
        self.assertTrue(StaffRequiredMixin.permission_predicate(self.staff))
        self.assertFalse(StaffRequiredMixin.permission_predicate(self.cashier))
        self.assertTrue(InternalUserRequiredMixin.permission_predicate(self.cashier))
        self.assertFalse(InternalUserRequiredMixin.permission_predicate(self.customer))

    def test_unused_allauth_account_mutation_routes_are_closed(self):
        for path in (
            "/security/signup/",
            "/security/email/",
            "/security/password/change/",
            "/security/password/reset/",
        ):
            self.assertEqual(self.client.get(path).status_code, 404)
