from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Appointment, AppointmentService
from apps.customers.models import Customer
from apps.notifications.models import Notification
from apps.pos.models import Payment, Sale
from apps.pos.services import create_sale, void_sale
from apps.services.models import Service, ServiceCategory, StaffProfile

from .services import (
    build_report,
    cashier_dashboard_data,
    owner_dashboard_data,
    staff_dashboard_data,
)


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(MFA_ENFORCE_OWNER=False, MFA_REQUIRE_INTERNAL_USERS=False)
class ReportsAndDashboardTests(TestCase):
    def setUp(self):
        self.owner = self.create_user("owner@example.com", User.Role.OWNER)
        self.cashier = self.create_user("cashier@example.com", User.Role.CASHIER)
        self.other_cashier = self.create_user("other-cashier@example.com", User.Role.CASHIER)
        self.staff = self.create_user("staff@example.com", User.Role.STAFF)
        self.customer_user = self.create_user("login-customer@example.com", User.Role.CUSTOMER)
        StaffProfile.objects.create(user=self.staff)
        category = ServiceCategory.objects.create(name="Reports")
        self.service = Service.objects.create(
            category=category,
            name="Report manicure",
            duration_minutes=45,
            price=Decimal("100.00"),
        )
        self.customer = Customer.objects.create(
            first_name="Report",
            last_name="Customer",
            email="report-customer@example.com",
        )
        self.appointment = Appointment.objects.create(
            customer=self.customer,
            customer_name_snapshot=self.customer.full_name,
            customer_email_snapshot=self.customer.email,
            appointment_date=timezone.localdate(),
            start_time=time(10, 0),
            end_time=time(10, 45),
            assigned_staff=self.staff,
            status=Appointment.Status.ONGOING,
            expires_at=timezone.now() + timedelta(hours=1),
            verified_at=timezone.now(),
        )
        self.work = AppointmentService.objects.create(
            appointment=self.appointment,
            service=self.service,
            service_name=self.service.name,
            duration_minutes=self.service.duration_minutes,
            price=self.service.price,
            assigned_staff=self.staff,
            status=AppointmentService.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        self.completed_sale = self.make_sale(self.cashier, Decimal("100.00"))
        self.voided_sale = self.make_sale(self.cashier, Decimal("100.00"))
        void_sale(self.voided_sale, actor=self.owner, reason="Test void")
        self.other_sale = self.make_sale(self.other_cashier, Decimal("100.00"))

    def create_user(self, email, role):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def make_sale(self, cashier, tendered):
        return create_sale(
            cashier=cashier,
            raw_items=[
                {"service": self.service, "assigned_staff": self.staff, "quantity": 1}
            ],
            customer=self.customer,
            payment_method=Payment.Method.CASH,
            amount_tendered=tendered,
        )

    def test_all_sales_period_reports_exclude_voids(self):
        today = timezone.localdate()
        for report_type in ("daily", "weekly", "monthly", "annual"):
            with self.subTest(report_type=report_type):
                report = build_report(report_type, today, today)
                self.assertEqual(report.totals["transactions"], 2)
                self.assertEqual(report.totals["gross"], Decimal("200.00"))
                self.assertEqual(report.totals["net"], Decimal("200.00"))
                self.assertEqual(sum(row["Transactions"] for row in report.rows), 2)

    def test_service_sales_uses_only_completed_nonvoided_sale_items(self):
        today = timezone.localdate()
        report = build_report("service-sales", today, today)
        self.assertEqual(len(report.rows), 1)
        self.assertEqual(report.rows[0]["Quantity"], 2)
        self.assertEqual(report.rows[0]["Gross Service Sales"], Decimal("200.00"))

    def test_operational_reports_count_appointment_status_and_staff_work(self):
        today = timezone.localdate()
        status_report = build_report("appointment-status", today, today)
        self.assertEqual(status_report.totals["appointments"], 1)
        self.assertEqual(status_report.rows[0]["Status"], "Ongoing")
        workload = build_report("staff-workload", today, today)
        self.assertEqual(workload.rows[0]["Staff"], str(self.staff))
        self.assertEqual(workload.rows[0]["Completed Services"], 1)

    def test_owner_dashboard_contains_live_kpis_rankings_and_trend(self):
        data = owner_dashboard_data()
        self.assertEqual(data["today_sales"]["transactions"], 2)
        self.assertEqual(data["today_sales"]["net"], Decimal("200.00"))
        self.assertEqual(data["customer_count"], 1)
        self.assertEqual(data["appointment_count"], 1)
        self.assertEqual(data["top_services"][0]["quantity"], 2)
        self.assertEqual(data["top_staff"][0].completed_services, 1)
        self.assertEqual(len(data["sales_trend"]), 7)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:owner_dashboard"))
        self.assertContains(response, "₱200.00")
        self.assertNotContains(response, "Connect this card")

    def test_cashier_dashboard_is_scoped_to_that_cashier(self):
        data = cashier_dashboard_data(self.cashier)
        self.assertEqual(data["pos_totals"]["transactions"], 1)
        self.assertEqual(data["pos_totals"]["net"], Decimal("100.00"))
        self.assertEqual(data["bookings_count"], 1)
        self.client.force_login(self.cashier)
        response = self.client.get(reverse("core:staff_dashboard"))
        self.assertTemplateUsed(response, "dashboards/cashier.html")
        self.assertContains(response, self.completed_sale.receipt_number)
        self.assertNotContains(response, self.other_sale.receipt_number)

    def test_staff_dashboard_has_assigned_work_and_notifications(self):
        Notification.objects.create(
            recipient=self.staff,
            appointment=self.appointment,
            event_type=Notification.EventType.NEW,
            title="Assigned work",
            message="A service is ready.",
        )
        data = staff_dashboard_data(self.staff)
        self.assertEqual(data["assigned_count"], 1)
        self.assertEqual(data["completed_count"], 1)
        self.assertEqual(data["unread_notifications"], 1)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("core:staff_dashboard"))
        self.assertContains(response, self.service.name)
        self.assertContains(response, "Assigned work")

    def test_owner_report_pages_accept_date_filters(self):
        self.client.force_login(self.owner)
        params = {
            "start_date": timezone.localdate().isoformat(),
            "end_date": timezone.localdate().isoformat(),
        }
        for url_name in (
            "reports:daily",
            "reports:weekly",
            "reports:monthly",
            "reports:annual",
            "reports:service_sales",
            "reports:appointment_status",
            "reports:staff_workload",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name), params)
                self.assertEqual(response.status_code, 200)
                self.assertIsNotNone(response.context["report"])

    def test_csv_xlsx_and_branded_pdf_exports(self):
        self.client.force_login(self.owner)
        params = {
            "start_date": timezone.localdate().isoformat(),
            "end_date": timezone.localdate().isoformat(),
        }
        expected = {
            "csv": ("text/csv", b"Period"),
            "xlsx": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                b"PK",
            ),
            "pdf": ("application/pdf", b"%PDF"),
        }
        for export_format, (content_type, signature) in expected.items():
            with self.subTest(export_format=export_format):
                response = self.client.get(
                    reverse(
                        "reports:export",
                        kwargs={"report_type": "daily", "export_format": export_format},
                    ),
                    params,
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Content-Type"].startswith(content_type))
                self.assertIn(signature, response.content)
                self.assertIn("attachment", response["Content-Disposition"])

    def test_report_and_export_routes_are_owner_only(self):
        protected = (
            "reports:index",
            "reports:daily",
            "reports:weekly",
            "reports:monthly",
            "reports:annual",
            "reports:service_sales",
            "reports:appointment_status",
            "reports:staff_workload",
        )
        for user in (self.cashier, self.staff, self.customer_user):
            self.client.force_login(user)
            for url_name in protected:
                with self.subTest(user=user.role, url_name=url_name):
                    self.assertEqual(self.client.get(reverse(url_name)).status_code, 403)
            self.assertEqual(
                self.client.get(
                    reverse(
                        "reports:export",
                        kwargs={"report_type": "daily", "export_format": "csv"},
                    )
                ).status_code,
                403,
            )
