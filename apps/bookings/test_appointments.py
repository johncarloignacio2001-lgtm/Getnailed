import re
from datetime import time, timedelta
from decimal import Decimal

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.customers.models import Customer
from apps.notifications.models import Notification
from apps.services.models import (
    Service,
    ServiceCategory,
    StaffProfile,
    StaffSchedule,
    StaffTimeBlock,
)

from .models import Appointment, AppointmentService
from .services import (
    create_public_appointment,
    transition_appointment,
    update_appointment_schedule,
    verify_public_booking,
)


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="",
    MFA_ENFORCE_OWNER=False,
    MFA_REQUIRE_INTERNAL_USERS=False,
)
class AppointmentWorkflowTests(TestCase):
    def setUp(self):
        self.category = ServiceCategory.objects.create(name="Nails")
        self.service = Service.objects.create(
            category=self.category,
            name="Gel manicure",
            duration_minutes=45,
            price="850.00",
        )
        self.staff = self.create_user("staff@example.com", User.Role.STAFF)
        StaffProfile.objects.create(user=self.staff)
        self.owner = self.create_user("owner@example.com", User.Role.OWNER)
        self.cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        self.request = RequestFactory().post("/bookings/new/review/")

    def create_user(self, email, role):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def appointment_data(self, email="guest@example.com", start_time=time(10, 0)):
        return {
            "first_name": "Guest",
            "last_name": "Customer",
            "email": email,
            "phone": "09171234567",
            "notes": "Quiet appointment",
            "appointment_date": timezone.localdate() + timedelta(days=2),
            "start_time": start_time,
            "assigned_staff": self.staff,
        }

    def create_appointment(self, **overrides):
        data = self.appointment_data()
        data.update(overrides)
        return create_public_appointment(data, [self.service], self.request)

    def test_creation_uses_canonical_service_snapshots_and_calculates_end_time(self):
        appointment = self.create_appointment()

        self.assertEqual(appointment.status, Appointment.Status.UNVERIFIED)
        self.assertEqual(appointment.end_time, time(10, 45))
        self.assertEqual(appointment.total_price, Decimal("850.00"))
        self.assertEqual(Customer.objects.count(), 1)
        row = AppointmentService.objects.get(appointment=appointment)
        self.assertEqual(row.service, self.service)
        self.assertEqual(row.service_name, "Gel manicure")

        self.service.name = "Renamed service"
        self.service.price = "900.00"
        self.service.save()
        row.refresh_from_db()
        self.assertEqual(row.service_name, "Gel manicure")
        self.assertEqual(str(row.price), "850.00")

    def test_overlapping_staff_appointment_is_rejected(self):
        first = self.create_appointment()
        first.status = Appointment.Status.APPROVED
        first.save(update_fields=("status",))

        with self.assertRaisesMessage(ValidationError, "already has an appointment"):
            self.create_appointment(email="second@example.com", start_time=time(10, 30))

        self.assertEqual(Appointment.objects.count(), 1)

    def test_verification_moves_request_to_pending_and_notifies_internal_users(self):
        appointment = self.create_appointment()
        code = re.search(r"\n(\d{8})\n", mail.outbox[-1].body).group(1)

        verified, token = verify_public_booking(appointment.reference, code, self.request)

        self.assertEqual(verified.status, Appointment.Status.PENDING)
        self.assertTrue(verified.accepts_public_access_token(token))
        self.assertEqual(
            set(Notification.objects.values_list("recipient__email", flat=True)),
            {self.owner.email, self.cashier.email, self.staff.email},
        )

    def test_customer_record_is_hidden_from_management_until_verification(self):
        appointment = self.create_appointment(email="hidden@example.com")
        self.client.force_login(self.cashier)
        self.assertNotContains(
            self.client.get(reverse("customers:index")), "hidden@example.com"
        )

        code = re.search(r"\n(\d{8})\n", mail.outbox[-1].body).group(1)
        verify_public_booking(appointment.reference, code, self.request)

        self.assertContains(
            self.client.get(reverse("customers:index")), "hidden@example.com"
        )

    def test_notifications_can_only_be_read_by_their_recipient(self):
        appointment = self.create_appointment()
        code = re.search(r"\n(\d{8})\n", mail.outbox[-1].body).group(1)
        verify_public_booking(appointment.reference, code, self.request)
        owner_notification = Notification.objects.get(
            appointment=appointment, recipient=self.owner
        )
        cashier_notification = Notification.objects.get(
            appointment=appointment, recipient=self.cashier
        )

        self.client.force_login(self.owner)
        denied = self.client.post(
            reverse("notifications:mark_read", kwargs={"pk": cashier_notification.pk})
        )
        self.assertEqual(denied.status_code, 404)
        response = self.client.post(
            reverse("notifications:mark_read", kwargs={"pk": owner_notification.pk})
        )
        self.assertRedirects(
            response,
            reverse("bookings:detail", kwargs={"reference": appointment.reference}),
            fetch_redirect_response=False,
        )
        owner_notification.refresh_from_db()
        self.assertIsNotNone(owner_notification.read_at)

    def test_staff_can_only_transition_their_assigned_appointment(self):
        appointment = self.create_appointment()
        appointment.status = Appointment.Status.APPROVED
        appointment.save(update_fields=("status",))

        transition_appointment(appointment, Appointment.Status.ONGOING, self.staff)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.ONGOING)

        other_staff = self.create_user("other@example.com", User.Role.STAFF)
        StaffProfile.objects.create(user=other_staff)
        with self.assertRaises(PermissionDenied):
            transition_appointment(appointment, Appointment.Status.COMPLETED, other_staff)

    def test_manager_assignment_uses_overlap_validation(self):
        first = self.create_appointment()
        first.status = Appointment.Status.APPROVED
        first.save(update_fields=("status",))
        second = self.create_appointment(
            email="unassigned@example.com", start_time=time(12, 0), assigned_staff=None
        )

        with self.assertRaisesMessage(ValidationError, "already has an appointment"):
            update_appointment_schedule(
                second,
                appointment_date=first.appointment_date,
                start_time=time(10, 15),
                assigned_staff=self.staff,
                actor=self.owner,
            )

    def test_public_wizard_creates_an_appointment(self):
        response = self.client.post(
            reverse("bookings:index"),
            {
                "first_name": "Web",
                "last_name": "Guest",
                "email": "web@example.com",
                "phone": "09171234567",
            },
        )
        self.assertRedirects(response, reverse("bookings:select_services"))
        response = self.client.post(
            reverse("bookings:select_services"), {"services": [self.service.pk]}
        )
        self.assertRedirects(response, reverse("bookings:select_schedule"))
        response = self.client.post(
            reverse("bookings:select_schedule"),
            {
                "appointment_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
                "start_time": "14:00",
                "assigned_staff": self.staff.pk,
            },
        )
        self.assertRedirects(response, reverse("bookings:review"))
        response = self.client.post(reverse("bookings:review"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Appointment.objects.filter(customer_email_snapshot="web@example.com").exists())

    def test_management_and_detail_views_enforce_role_scope(self):
        appointment = self.create_appointment()
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse("bookings:manage")).status_code, 200)
        self.assertNotContains(
            self.client.get(reverse("bookings:manage")), appointment.reference
        )

        appointment.status = Appointment.Status.PENDING
        appointment.save(update_fields=("status",))

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("bookings:manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("bookings:assigned")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("bookings:detail", kwargs={"reference": appointment.reference})
            ).status_code,
            200,
        )

        other_staff = self.create_user("scoped@example.com", User.Role.STAFF)
        StaffProfile.objects.create(user=other_staff)
        self.client.force_login(other_staff)
        self.assertEqual(
            self.client.get(
                reverse("bookings:detail", kwargs={"reference": appointment.reference})
            ).status_code,
            404,
        )

    def test_shift_working_hours_constraint_blocks_appointment(self):
        target_date = timezone.localdate() + timedelta(days=2)
        weekday = target_date.weekday()
        StaffSchedule.objects.create(
            staff=self.staff,
            day_of_week=weekday,
            start_time=time(11, 0),
            end_time=time(18, 0),
            is_working=True,
        )

        with self.assertRaisesMessage(ValidationError, "working hours"):
            self.create_appointment(
                appointment_date=target_date,
                start_time=time(10, 0),
                assigned_staff=self.staff,
            )

        appt = self.create_appointment(
            appointment_date=target_date,
            start_time=time(11, 0),
            assigned_staff=self.staff,
        )
        self.assertEqual(appt.start_time, time(11, 0))

    def test_staff_time_block_blocks_appointment(self):
        target_date = timezone.localdate() + timedelta(days=2)
        StaffTimeBlock.objects.create(
            staff=self.staff,
            date=target_date,
            start_time=time(12, 0),
            end_time=time(13, 0),
            reason="Lunch break",
        )

        with self.assertRaisesMessage(ValidationError, "scheduled leave or time block"):
            self.create_appointment(
                appointment_date=target_date,
                start_time=time(12, 0),
                assigned_staff=self.staff,
            )

    def test_unqualified_staff_skill_constraint_blocks_appointment(self):
        target_date = timezone.localdate() + timedelta(days=2)
        other_service = Service.objects.create(
            category=self.category,
            name="Eyelash Extension",
            duration_minutes=60,
            price="1200.00",
        )
        profile = self.staff.staff_profile
        profile.skills.add(self.service)

        with self.assertRaisesMessage(ValidationError, "not qualified"):
            create_public_appointment(
                self.appointment_data(start_time=time(10, 0)),
                [other_service],
                self.request,
            )

    def test_multi_service_duration_block_and_api_slots(self):
        from .services import get_available_time_slots
        pedicure = Service.objects.create(
            category=self.category,
            name="Deluxe Pedicure",
            duration_minutes=60,
            price="500.00",
        )
        appt = create_public_appointment(
            self.appointment_data(start_time=time(10, 0)),
            [self.service, pedicure],
            self.request,
        )
        self.assertEqual(appt.total_duration_minutes, 105)
        self.assertEqual(appt.end_time, time(11, 45))

        target_date = timezone.localdate() + timedelta(days=2)
        slots = get_available_time_slots(
            target_date, [self.service.pk, pedicure.pk], staff_id=self.staff.pk
        )
        self.assertIsInstance(slots, list)
        self.assertTrue(len(slots) > 0)

