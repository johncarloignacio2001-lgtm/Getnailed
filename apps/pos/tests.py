from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Appointment, AppointmentService
from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory, StaffProfile

from .models import Payment, ReceiptSequence, Sale, SaleItem
from .services import create_sale, void_sale


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(MFA_ENFORCE_OWNER=False, MFA_REQUIRE_INTERNAL_USERS=False)
class PosTransactionTests(TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", User.Role.OWNER)
        self.cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        self.staff = self.create_user("staff@example.com", User.Role.STAFF)
        self.denied_staff = self.create_user("denied@example.com", User.Role.STAFF)
        StaffProfile.objects.create(user=self.staff)
        StaffProfile.objects.create(user=self.denied_staff)
        category = ServiceCategory.objects.create(name="POS Services")
        self.manicure = Service.objects.create(
            category=category,
            name="Manicure",
            duration_minutes=45,
            price=Decimal("1000.00"),
        )
        self.pedicure = Service.objects.create(
            category=category,
            name="Pedicure",
            duration_minutes=60,
            price=Decimal("500.00"),
        )
        self.customer = Customer.objects.create(
            first_name="Test",
            last_name="Customer",
            email="customer@example.com",
        )

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

    def items(self):
        return [
            {"service": self.manicure, "assigned_staff": self.staff, "quantity": 2},
            {"service": self.pedicure, "assigned_staff": self.staff, "quantity": 1},
        ]

    def create_cash_sale(self, **overrides):
        data = {
            "cashier": self.cashier,
            "raw_items": self.items(),
            "customer": self.customer,
            "payment_method": Payment.Method.CASH,
            "amount_tendered": Decimal("3000.00"),
        }
        data.update(overrides)
        return create_sale(**data)

    def create_appointment(self):
        appointment = Appointment.objects.create(
            customer=self.customer,
            customer_name_snapshot=self.customer.full_name,
            customer_email_snapshot=self.customer.email,
            appointment_date=timezone.localdate() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(10, 45),
            assigned_staff=self.staff,
            status=Appointment.Status.APPROVED,
            expires_at=timezone.now() + timedelta(days=1),
        )
        AppointmentService.objects.create(
            appointment=appointment,
            service=self.manicure,
            service_name=self.manicure.name,
            duration_minutes=self.manicure.duration_minutes,
            price=self.manicure.price,
        )
        return appointment

    def test_percentage_totals_change_and_historical_snapshots(self):
        sale = self.create_cash_sale(
            discount_type=Sale.DiscountType.PERCENT,
            discount_value=Decimal("10.00"),
        )

        self.assertEqual(sale.subtotal, Decimal("2500.00"))
        self.assertEqual(sale.discount_amount, Decimal("250.00"))
        self.assertEqual(sale.total, Decimal("2250.00"))
        self.assertEqual(sale.payment.amount_tendered, Decimal("3000.00"))
        self.assertEqual(sale.payment.change, Decimal("750.00"))

        self.manicure.name = "Renamed Manicure"
        self.manicure.price = Decimal("1200.00")
        self.manicure.save()
        item = sale.items.get(service=self.manicure)
        self.assertEqual(item.service_name, "Manicure")
        self.assertEqual(item.unit_price, Decimal("1000.00"))

    def test_fixed_discount_and_non_cash_exact_payment(self):
        sale = self.create_cash_sale(
            discount_type=Sale.DiscountType.FIXED,
            discount_value=Decimal("125.50"),
            payment_method=Payment.Method.GCASH,
            amount_tendered=Decimal("2374.50"),
            payment_reference="LOCAL-REF-1",
        )
        self.assertEqual(sale.total, Decimal("2374.50"))
        self.assertEqual(sale.payment.change, Decimal("0.00"))
        self.assertEqual(sale.payment.reference, "LOCAL-REF-1")

    def test_negative_or_excessive_discounts_and_insufficient_cash_are_rejected(self):
        invalid = (
            {
                "discount_type": Sale.DiscountType.FIXED,
                "discount_value": Decimal("3000.00"),
            },
            {
                "discount_type": Sale.DiscountType.PERCENT,
                "discount_value": Decimal("101.00"),
            },
            {"amount_tendered": Decimal("2499.99")},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.create_cash_sale(**values)
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(ReceiptSequence.objects.get(pk=1).last_value, 0)

    def test_receipt_numbers_are_unique_and_immutable(self):
        first = self.create_cash_sale()
        second = self.create_cash_sale(customer=None)
        self.assertNotEqual(first.receipt_number, second.receipt_number)
        self.assertRegex(first.receipt_number, r"^GN-\d{8}-\d{8}$")

        first.receipt_number = "CHANGED"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            first.save()

    def test_permission_is_rechecked_in_transaction_service(self):
        with self.assertRaises(PermissionDenied):
            self.create_cash_sale(cashier=self.denied_staff)
        granted = self.create_user(
            "granted@example.com", User.Role.STAFF, can_use_pos=True
        )
        sale = self.create_cash_sale(cashier=granted)
        self.assertEqual(sale.cashier, granted)

    def test_linked_appointment_is_completed_atomically(self):
        appointment = self.create_appointment()
        sale = self.create_cash_sale(appointment=appointment)
        appointment.refresh_from_db()
        self.assertEqual(sale.appointment, appointment)
        self.assertEqual(appointment.status, Appointment.Status.COMPLETED)
        self.assertTrue(
            appointment.status_history.filter(
                to_status=Appointment.Status.COMPLETED, actor=self.cashier
            ).exists()
        )

    def test_payment_failure_rolls_back_sale_sequence_items_and_appointment(self):
        appointment = self.create_appointment()
        with patch("apps.pos.services.Payment.objects.create", side_effect=RuntimeError("fail")):
            with self.assertRaises(RuntimeError):
                self.create_cash_sale(appointment=appointment)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.APPROVED)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(SaleItem.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(ReceiptSequence.objects.get(pk=1).last_value, 0)

    def test_database_rejects_negative_historical_totals(self):
        with self.assertRaises(IntegrityError):
            Sale.objects.create(
                receipt_number="GN-INVALID-00000001",
                subtotal=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                total=Decimal("-0.01"),
                cashier=self.cashier,
                cashier_name_snapshot=str(self.cashier),
            )

    def test_void_is_owner_only_and_preserves_financial_history(self):
        sale = self.create_cash_sale()
        with self.assertRaises(PermissionDenied):
            void_sale(sale, actor=self.cashier, reason="Mistake")
        void_sale(sale, actor=self.owner, reason="Duplicate transaction")
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.VOIDED)
        self.assertEqual(sale.items.count(), 2)
        self.assertTrue(hasattr(sale, "payment"))
        self.client.force_login(self.owner)
        summary = self.client.get(reverse("reports:daily_summary"))
        self.assertEqual(summary.context["totals"]["transactions"], 0)
        self.assertEqual(summary.context["totals"]["voided"], 1)

    def test_checkout_receipt_history_and_daily_summary_views(self):
        self.client.force_login(self.cashier)
        data = {
            "customer": "",
            "appointment": "",
            "discount_type": Sale.DiscountType.NONE,
            "discount_value": "0.00",
            "payment_method": Payment.Method.CASH,
            "amount_tendered": "1000.00",
            "payment_reference": "",
            "mark_appointment_completed": "on",
            "items-TOTAL_FORMS": "6",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "12",
            "items-0-service": str(self.manicure.pk),
            "items-0-assigned_staff": str(self.staff.pk),
            "items-0-quantity": "1",
        }
        for position in range(1, 6):
            data[f"items-{position}-service"] = ""
            data[f"items-{position}-assigned_staff"] = ""
            data[f"items-{position}-quantity"] = "1"
        response = self.client.post(reverse("pos:index"), data)
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get()
        self.assertRedirects(
            response,
            reverse("pos:receipt", kwargs={"receipt_number": sale.receipt_number}),
            fetch_redirect_response=False,
        )
        self.assertContains(
            self.client.get(
                reverse("pos:receipt", kwargs={"receipt_number": sale.receipt_number})
            ),
            "Get Nailed",
        )
        self.assertContains(self.client.get(reverse("pos:history")), sale.receipt_number)
        summary = self.client.get(reverse("reports:daily_summary"))
        self.assertContains(summary, sale.receipt_number)
        self.assertContains(summary, "1000.00")

    def test_cashiers_cannot_read_each_others_receipts(self):
        sale = self.create_cash_sale()
        other = self.create_user("other-cashier@example.com", User.Role.CASHIER)
        self.client.force_login(other)
        response = self.client.get(
            reverse("pos:receipt", kwargs={"receipt_number": sale.receipt_number})
        )
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(
                reverse("pos:receipt", kwargs={"receipt_number": sale.receipt_number})
            ).status_code,
            200,
        )
