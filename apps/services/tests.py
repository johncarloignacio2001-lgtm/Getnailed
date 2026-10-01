import os
import tempfile
from decimal import Decimal
from io import BytesIO

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import User

from .forms import ServiceCategoryForm, ServiceForm, StaffProfileForm
from .models import Service, ServiceCategory, StaffProfile


PASSWORD = "Correct-Horse-Battery-47!"


def image_upload(name="service.png", image_format="PNG", content_type="image/png"):
    data = BytesIO()
    Image.new("RGB", (20, 20), color="#c9aeb1").save(data, format=image_format)
    return SimpleUploadedFile(name, data.getvalue(), content_type=content_type)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MFA_ENCRYPTION_KEY="test-only-mfa-encryption-key",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
    LOGIN_CAPTCHA_THRESHOLD=100,
)
class ServicesModuleTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        self.owner = self.create_user("owner@example.com", User.Role.OWNER)
        self.cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        self.staff = self.create_user("staff@example.com", User.Role.STAFF)
        self.customer = self.create_user("customer@example.com", User.Role.CUSTOMER)
        self.category = ServiceCategory.objects.create(
            name="Manicure",
            description="Nail grooming services",
        )

    def create_user(self, email, role):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def create_service(self, name="Classic Manicure", **extra):
        values = {
            "category": self.category,
            "description": "Shape, cuticle care, massage, and polish.",
            "duration_minutes": 45,
            "price": Decimal("350.00"),
            "is_active": True,
        }
        values.update(extra)
        return Service.objects.create(name=name, **values)

    def login(self, user):
        response = self.client.post(
            reverse("accounts:login"),
            {"login": user.email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)

    def test_category_and_service_validation_and_constraints(self):
        duplicate = ServiceCategory(name=" manicure ")
        duplicate.name = duplicate.name.strip()
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

        for duration, price in ((0, "350.00"), (481, "350.00"), (45, "0.00")):
            service = Service(
                name=f"Invalid {duration} {price}",
                category=self.category,
                duration_minutes=duration,
                price=price,
            )
            with self.subTest(duration=duration, price=price), self.assertRaises(ValidationError):
                service.full_clean()

        self.create_service()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_service(name="classic manicure")

    def test_staff_profile_accepts_only_staff_and_preserves_user_on_delete(self):
        profile = StaffProfile.objects.create(
            user=self.staff,
            specialty="Gel extensions",
        )
        self.assertEqual(profile.availability_status, StaffProfile.Availability.AVAILABLE)

        with self.assertRaises(ValidationError):
            StaffProfile.objects.create(user=self.cashier, specialty="Invalid")

        profile.delete()
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_staff_role_cannot_change_while_profile_exists(self):
        StaffProfile.objects.create(user=self.staff, specialty="Nail art")
        self.staff.role = User.Role.CASHIER
        with self.assertRaises(ValidationError):
            self.staff.full_clean()
        with self.assertRaises(ValidationError):
            self.staff.save(update_fields=("role",))

    def test_owner_managed_forms_recheck_actor_and_prevent_role_tampering(self):
        denied_category = ServiceCategoryForm({"name": "Nail Art"}, actor=self.cashier)
        self.assertFalse(denied_category.is_valid())
        self.assertIn("Only an owner", denied_category.non_field_errors()[0])

        denied_service = ServiceForm(
            {
                "name": "Gel Manicure",
                "category": self.category.pk,
                "duration_minutes": 60,
                "price": "650.00",
                "is_active": "on",
            },
            actor=self.staff,
        )
        self.assertFalse(denied_service.is_valid())

        profile_form = StaffProfileForm(
            {
                "user": self.cashier.pk,
                "specialty": "Tampered role",
                "availability_status": StaffProfile.Availability.AVAILABLE,
                "is_active": "on",
            },
            actor=self.owner,
        )
        self.assertFalse(profile_form.is_valid())
        self.assertIn("user", profile_form.errors)

    def test_catalog_read_permissions_and_inactive_service_scope(self):
        active = self.create_service()
        inactive = self.create_service("Retired Manicure", is_active=False)

        for user in (self.owner, self.cashier):
            client = Client()
            client.force_login(user)
            response = client.get(reverse("services:index"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, active.name)
            if user == self.owner:
                self.assertContains(response, inactive.name)
            else:
                self.assertNotContains(response, inactive.name)
                self.assertNotContains(response, "Add service")

        for user in (self.staff, self.customer):
            client = Client()
            client.force_login(user)
            self.assertEqual(client.get(reverse("services:index")).status_code, 403)
        self.assertEqual(Client().get(reverse("services:index")).status_code, 302)

    def test_management_routes_are_owner_only(self):
        routes = (
            reverse("services:service_create"),
            reverse("services:category_list"),
            reverse("services:category_create"),
            reverse("services:staff_list"),
            reverse("services:staff_create"),
        )
        for route in routes:
            owner_client = Client()
            owner_client.force_login(self.owner)
            self.assertEqual(owner_client.get(route).status_code, 200)
            for denied in (self.cashier, self.staff, self.customer):
                denied_client = Client()
                denied_client.force_login(denied)
                self.assertEqual(denied_client.get(route).status_code, 403)
            self.assertEqual(Client().get(route).status_code, 302)

    def test_update_delete_routes_enforce_owner_and_recent_reauthentication(self):
        service = self.create_service()
        profile = StaffProfile.objects.create(user=self.staff)
        protected_updates = (
            reverse("services:service_update", args=(service.pk,)),
            reverse("services:category_update", args=(self.category.pk,)),
            reverse("services:staff_update", args=(profile.pk,)),
        )
        protected_deletes = (
            reverse("services:service_delete", args=(service.pk,)),
            reverse("services:category_delete", args=(self.category.pk,)),
            reverse("services:staff_delete", args=(profile.pk,)),
        )
        for user in (self.cashier, self.staff, self.customer):
            client = Client()
            client.force_login(user)
            for route in (*protected_updates, *protected_deletes):
                self.assertEqual(client.get(route).status_code, 403)

        stale_owner = Client()
        stale_owner.force_login(self.owner)
        for route in protected_deletes:
            response = stale_owner.get(route)
            self.assertEqual(response.status_code, 302)
            self.assertIn("reauthenticate", response["Location"])

    def test_owner_can_create_update_and_delete_catalog_records(self):
        self.login(self.owner)
        category_response = self.client.post(
            reverse("services:category_create"),
            {"name": " Nail Art ", "description": "Creative details"},
        )
        self.assertEqual(category_response.status_code, 302)
        category = ServiceCategory.objects.get(name="Nail Art")

        create_response = self.client.post(
            reverse("services:service_create"),
            {
                "name": "French Tip Finish",
                "category": category.pk,
                "description": "Classic clean tips",
                "duration_minutes": 25,
                "price": "250.00",
                "is_active": "on",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        service = Service.objects.get(name="French Tip Finish")

        update_response = self.client.post(
            reverse("services:service_update", args=(service.pk,)),
            {
                "name": "French Tip Design",
                "category": category.pk,
                "description": "Updated",
                "duration_minutes": 30,
                "price": "275.00",
                "is_active": "on",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        service.refresh_from_db()
        self.assertEqual(service.name, "French Tip Design")
        self.assertEqual(service.price, Decimal("275.00"))

        delete_response = self.client.post(
            reverse("services:service_delete", args=(service.pk,))
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Service.objects.filter(pk=service.pk).exists())

    def test_category_with_services_is_protected_from_deletion(self):
        self.create_service()
        self.login(self.owner)
        response = self.client.post(
            reverse("services:category_delete", args=(self.category.pk,)),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ServiceCategory.objects.filter(pk=self.category.pk).exists())
        self.assertContains(response, "Move or delete this category")

    def test_owner_can_manage_staff_profiles_without_changing_accounts(self):
        self.login(self.owner)
        create_response = self.client.post(
            reverse("services:staff_create"),
            {
                "user": self.staff.pk,
                "specialty": " Gel and acrylic enhancements ",
                "availability_status": StaffProfile.Availability.NOT_ACCEPTING,
                "is_active": "on",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        profile = StaffProfile.objects.get(user=self.staff)
        self.assertEqual(profile.specialty, "Gel and acrylic enhancements")

        update_response = self.client.post(
            reverse("services:staff_update", args=(profile.pk,)),
            {
                "user": self.staff.pk,
                "specialty": "Nail art",
                "availability_status": StaffProfile.Availability.AVAILABLE,
                "is_active": "on",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        profile.refresh_from_db()
        self.assertEqual(profile.specialty, "Nail art")

        delete_response = self.client.post(
            reverse("services:staff_delete", args=(profile.pk,))
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(StaffProfile.objects.filter(pk=profile.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_search_filters_and_pagination_compose(self):
        gel_category = ServiceCategory.objects.create(name="Gel")
        for index in range(14):
            self.create_service(f"Classic Service {index:02d}")
        Service.objects.create(
            name="Gel Signature",
            category=gel_category,
            duration_minutes=60,
            price="700.00",
            is_active=False,
        )
        self.client.force_login(self.owner)

        page = self.client.get(reverse("services:index"), {"q": "Classic", "page": 2})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["page_obj"].paginator.count, 14)
        self.assertEqual(page.context["page_obj"].number, 2)

        filtered = self.client.get(
            reverse("services:index"),
            {"category": gel_category.pk, "status": "inactive"},
        )
        self.assertEqual(list(filtered.context["page_obj"]), list(Service.objects.filter(name="Gel Signature")))

    def test_valid_image_uses_safe_name_and_invalid_image_is_rejected(self):
        self.client.force_login(self.owner)
        valid_response = self.client.post(
            reverse("services:service_create"),
            {
                "name": "Photo Service",
                "category": self.category.pk,
                "duration_minutes": 30,
                "price": "300.00",
                "is_active": "on",
                "image": image_upload("../../customer-name.png"),
            },
        )
        self.assertEqual(
            valid_response.status_code,
            302,
            valid_response.context["form"].errors if valid_response.context else "",
        )
        service = Service.objects.get(name="Photo Service")
        self.assertRegex(service.image.name, r"^service-images/[0-9a-f]{32}\.png$")
        self.assertTrue(os.path.exists(service.image.path))

        invalid_response = self.client.post(
            reverse("services:service_create"),
            {
                "name": "Unsafe Service",
                "category": self.category.pk,
                "duration_minutes": 30,
                "price": "300.00",
                "is_active": "on",
                "image": SimpleUploadedFile(
                    "attack.png",
                    b"<script>alert(1)</script>",
                    content_type="image/png",
                ),
            },
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Upload a valid image")
        self.assertFalse(Service.objects.filter(name="Unsafe Service").exists())

    def test_direct_model_image_validation_and_file_cleanup(self):
        service = Service(
            name="Direct Image",
            category=self.category,
            duration_minutes=30,
            price="300.00",
            image=image_upload(),
        )
        service.save()
        old_path = service.image.path
        self.assertTrue(os.path.exists(old_path))

        service.image = image_upload("replacement.jpg", "JPEG", "image/jpeg")
        with self.captureOnCommitCallbacks(execute=True):
            service.save()
        new_path = service.image.path
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))

        with self.captureOnCommitCallbacks(execute=True):
            service.delete()
        self.assertFalse(os.path.exists(new_path))

        invalid = Service(
            name="Invalid Direct Image",
            category=self.category,
            duration_minutes=30,
            price="300.00",
            image=SimpleUploadedFile("bad.png", b"bad", content_type="image/png"),
        )
        with self.assertRaises(ValidationError):
            invalid.save()

    def test_failed_database_save_removes_newly_stored_image(self):
        self.create_service("Unique Collision")
        collision = Service(
            name="unique collision",
            category=self.category,
            duration_minutes=30,
            price="300.00",
            image=image_upload(),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            collision.save()
        self.assertTrue(collision.image.name)
        self.assertFalse(collision.image.storage.exists(collision.image.name))

    def test_fixture_loads_realistic_catalog(self):
        Service.objects.all().delete()
        ServiceCategory.objects.all().delete()
        call_command("loaddata", "stage1_catalog", verbosity=0)
        self.assertEqual(ServiceCategory.objects.count(), 5)
        self.assertGreaterEqual(Service.objects.count(), 15)
        self.assertTrue(Service.objects.filter(name="Classic Manicure", price="350.00").exists())

    def test_browser_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(
            client.post(reverse("services:category_create"), {"name": "Blocked"}).status_code,
            403,
        )
        self.assertEqual(
            client.post(reverse("services:service_create"), {}).status_code,
            403,
        )

    def test_admin_is_registered_and_owner_restricted(self):
        for model in (ServiceCategory, Service, StaffProfile):
            model_admin = admin.site._registry[model]
            owner_request = RequestFactory().get("/admin/")
            owner_request.user = self.owner
            cashier_request = RequestFactory().get("/admin/")
            cashier_request.user = self.cashier
            self.assertTrue(model_admin.has_view_permission(owner_request))
            self.assertFalse(model_admin.has_view_permission(cashier_request))
            self.assertFalse(model_admin.has_delete_permission(owner_request))
