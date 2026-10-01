"""
Management command to seed realistic demo data for QA and defense demonstrations.

Dataset:
- 1 OWNER account
- 1 CASHIER account
- 8 STAFF accounts with varied permissions
- 50 customers
- 5-10 services across categories
- 150 appointments with varied statuses and workflows
- 300+ POS transactions spanning multiple months
- Audit events and notifications

No plaintext production passwords. All accounts use test-specific passwords.
"""

import random
from datetime import datetime, timedelta, time
from decimal import Decimal
from typing import List, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.customers.models import Customer
from apps.services.models import Service, ServiceCategory, StaffProfile
from apps.bookings.models import Appointment, AppointmentService
from apps.pos.models import Sale, SaleItem, ReceiptSequence, Payment
from apps.audittrail.models import SecurityEvent
from apps.notifications.models import Notification


User = get_user_model()
FAKE_NAMES_FIRST = [
    "Maria", "Juan", "José", "Carmen", "Carlos", "Ana", "Miguel", "Rosa",
    "Pedro", "Elena", "Diego", "Sophia", "Luis", "Isabella", "Ricardo", "Emma",
    "Alejandro", "Sofia", "Gabriel", "Mía",
]
FAKE_NAMES_LAST = [
    "Garcia", "Rodriguez", "Martinez", "Lopez", "Gonzalez", "Santos", "Rivera",
    "Reyes", "Cruz", "Morales", "Gutierrez", "Flores", "Ortiz", "Rojas", "Castro",
]

STAFF_PERMISSIONS = [
    {
        "name": "Manicure Specialist",
        "permissions": {"can_use_pos": True, "can_assign_services": True},
    },
    {
        "name": "Pedicure Specialist",
        "permissions": {"can_use_pos": True, "can_assign_services": True},
    },
    {
        "name": "Nail Art Designer",
        "permissions": {"can_use_pos": True, "can_assign_services": True},
    },
    {
        "name": "Massage Therapist",
        "permissions": {"can_use_pos": True, "can_assign_services": True},
    },
    {
        "name": "Booking Manager",
        "permissions": {"can_manage_bookings": True, "can_assign_services": True},
    },
    {
        "name": "Front Desk",
        "permissions": {"can_manage_customers": True, "can_manage_bookings": True},
    },
    {
        "name": "Waxing Specialist",
        "permissions": {"can_use_pos": True, "can_assign_services": True},
    },
    {
        "name": "Full Service Staff",
        "permissions": {
            "can_use_pos": True,
            "can_manage_bookings": True,
            "can_manage_customers": True,
            "can_assign_services": True,
        },
    },
]

SERVICE_CATALOG = {
    "Manicures": [
        {"name": "Basic Manicure", "duration": 30, "price": Decimal("25.00")},
        {"name": "Gel Manicure", "duration": 45, "price": Decimal("35.00")},
        {"name": "Nail Art Manicure", "duration": 60, "price": Decimal("45.00")},
        {"name": "Luxury Manicure", "duration": 60, "price": Decimal("55.00")},
    ],
    "Pedicures": [
        {"name": "Basic Pedicure", "duration": 40, "price": Decimal("30.00")},
        {"name": "Gel Pedicure", "duration": 50, "price": Decimal("40.00")},
        {"name": "Luxury Pedicure", "duration": 60, "price": Decimal("55.00")},
        {"name": "Spa Pedicure", "duration": 75, "price": Decimal("65.00")},
    ],
    "Massage": [
        {"name": "30-Minute Massage", "duration": 30, "price": Decimal("40.00")},
        {"name": "60-Minute Massage", "duration": 60, "price": Decimal("70.00")},
        {"name": "90-Minute Massage", "duration": 90, "price": Decimal("100.00")},
    ],
    "Waxing": [
        {"name": "Eyebrow Waxing", "duration": 15, "price": Decimal("12.00")},
        {"name": "Full Leg Waxing", "duration": 45, "price": Decimal("50.00")},
        {"name": "Brazilian Waxing", "duration": 45, "price": Decimal("60.00")},
    ],
}

APPOINTMENT_STATUSES = [
    "PENDING",
    "APPROVED",
    "ONGOING",
    "COMPLETED",
    "CANCELLED",
    "REJECTED",
    "NO_SHOW",
    "RESCHEDULED",
]

CANCELLATION_REASONS = [
    "Customer requested",
    "Staff unavailable",
    "Double booking",
    "Customer no-show",
    "Rescheduled to different date",
]


class Command(BaseCommand):
    help = "Seed realistic demo data for QA and defense demonstration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before seeding (careful!)",
        )
        parser.add_argument(
            "--customers",
            type=int,
            default=50,
            help="Number of customers to create (default: 50)",
        )
        parser.add_argument(
            "--appointments",
            type=int,
            default=150,
            help="Number of appointments to create (default: 150)",
        )
        parser.add_argument(
            "--transactions",
            type=int,
            default=300,
            help="Number of POS transactions to create (default: 300)",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(
                self.style.WARNING(
                    "Clearing existing data... (this cannot be undone)"
                )
            )
            self._clear_data()

        self.stdout.write(self.style.SUCCESS("Starting demo data seed..."))

        try:
            # Seed in order
            users = self._create_users()
            self.stdout.write(
                self.style.SUCCESS(f"Created {len(users)} user accounts")
            )

            categories = self._create_service_catalog()
            self.stdout.write(
                self.style.SUCCESS(f"Created service categories and services")
            )

            customers = self._create_customers(options["customers"])
            self.stdout.write(
                self.style.SUCCESS(f"Created {len(customers)} customers")
            )

            appointments = self._create_appointments(
                users, customers, options["appointments"]
            )
            self.stdout.write(
                self.style.SUCCESS(f"Created {len(appointments)} appointments")
            )

            transactions = self._create_pos_transactions(users, options["transactions"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {len(transactions)} POS transactions"
                )
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "\n" + "=" * 60
                )
            )
            self.stdout.write(
                self.style.SUCCESS("Demo data seeding completed successfully!")
            )
            self._print_summary(users, customers, appointments, transactions)

        except Exception as e:
            raise CommandError(f"Error during seeding: {str(e)}")

    def _clear_data(self):
        """Clear existing data (use with caution)"""
        Sale.objects.all().delete()
        Appointment.objects.all().delete()
        Customer.objects.all().delete()
        Service.objects.all().delete()
        ServiceCategory.objects.all().delete()
        User.objects.filter(role__in=("OWNER", "CASHIER", "STAFF")).delete()
        self.stdout.write(self.style.SUCCESS("Cleared existing data"))

    def _create_users(self) -> dict:
        """Create OWNER, CASHIER, and STAFF accounts"""
        users = {}

        # OWNER
        owner, _ = User.objects.get_or_create(
            email="owner@getnailed.local",
            defaults={
                "first_name": "Owner",
                "last_name": "Administrator",
                "role": User.Role.OWNER,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "is_active_staff_member": True,
                "email_verified_at": timezone.now(),
                "phone_number": "+63.1.234.5678",
                "can_use_pos": True,
                "can_manage_bookings": True,
                "can_manage_customers": True,
                "can_assign_services": True,
            },
        )
        if not owner.has_usable_password():
            owner.set_password("DemoOwner@123456")
            owner.save()
        users["OWNER"] = owner

        # CASHIER
        cashier, _ = User.objects.get_or_create(
            email="cashier@getnailed.local",
            defaults={
                "first_name": "Maria",
                "last_name": "Cashier",
                "role": User.Role.CASHIER,
                "is_staff": True,
                "is_active": True,
                "is_active_staff_member": True,
                "email_verified_at": timezone.now(),
                "phone_number": "+63.2.123.4567",
                "can_use_pos": True,
                "can_manage_bookings": True,
                "can_manage_customers": True,
            },
        )
        if not cashier.has_usable_password():
            cashier.set_password("DemoCashier@123456")
            cashier.save()
        users["CASHIER"] = cashier

        # STAFF members
        staff_list = []
        for i, staff_spec in enumerate(STAFF_PERMISSIONS):
            staff, _ = User.objects.get_or_create(
                email=f"staff{i}@getnailed.local",
                defaults={
                    "first_name": random.choice(FAKE_NAMES_FIRST),
                    "last_name": random.choice(FAKE_NAMES_LAST),
                    "role": User.Role.STAFF,
                    "is_staff": True,
                    "is_active": True,
                    "is_active_staff_member": True,
                    "email_verified_at": timezone.now(),
                    "phone_number": f"+63.{random.randint(9, 99)}.{random.randint(100, 999)}.{random.randint(1000, 9999)}",
                    **staff_spec["permissions"],
                },
            )
            if not staff.has_usable_password():
                staff.set_password(f"DemoStaff{i}@123456")
                staff.save()

            # Create staff profile
            StaffProfile.objects.get_or_create(
                user=staff,
                defaults={
                    "specialty": staff_spec["name"],
                    "availability_status": StaffProfile.Availability.AVAILABLE,
                },
            )
            staff_list.append(staff)

        users["STAFF"] = staff_list
        return users

    def _create_service_catalog(self) -> List[ServiceCategory]:
        """Create services and categories"""
        categories = []
        for category_name, services in SERVICE_CATALOG.items():
            category, _ = ServiceCategory.objects.get_or_create(
                name=category_name,
                defaults={"description": f"{category_name} services"},
            )
            categories.append(category)

            for service_spec in services:
                Service.objects.get_or_create(
                    category=category,
                    name=service_spec["name"],
                    defaults={
                        "duration_minutes": service_spec["duration"],
                        "price": service_spec["price"],
                        "description": f"Professional {service_spec['name']}",
                        "is_active": True,
                    },
                )
        return categories

    def _create_customers(self, count: int) -> List[Customer]:
        """Create demo customers"""
        customers = []
        for i in range(count):
            first_name = random.choice(FAKE_NAMES_FIRST)
            last_name = random.choice(FAKE_NAMES_LAST)
            email = f"customer{i}@example.local"
            phone = f"+63.{random.randint(9, 99)}.{random.randint(100, 999)}.{random.randint(1000, 9999)}"

            customer, _ = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                    "notes": f"Preferred services: {random.choice(list(SERVICE_CATALOG.keys()))}",
                },
            )
            customers.append(customer)
        return customers

    def _create_appointments(
        self, users: dict, customers: List[Customer], count: int
    ) -> List[Appointment]:
        """Create demo appointments with varied statuses and workflows"""
        appointments = []
        staff = users["STAFF"]
        now = timezone.now()
        tz = timezone.get_current_timezone()

        for i in range(count):
            customer = random.choice(customers)
            assigned_staff = random.choice(staff)
            service = random.choice(Service.objects.all())

            # Vary appointment dates: past, present, future
            days_offset = random.randint(-60, 30)
            appointment_date = (now + timedelta(days=days_offset)).date()

            # Random time slot (9 AM to 6 PM)
            hour = random.randint(9, 17)
            minute = random.choice([0, 15, 30, 45])
            start_time = time(hour, minute)

            # Calculate end time based on service duration
            start_dt = datetime.combine(appointment_date, start_time)
            end_dt = start_dt + timedelta(minutes=service.duration_minutes)
            end_time = end_dt.time()

            # Random status distribution
            status_weight = random.random()
            if status_weight < 0.4:
                status = Appointment.Status.COMPLETED
            elif status_weight < 0.55:
                status = Appointment.Status.APPROVED
            elif status_weight < 0.65:
                status = Appointment.Status.PENDING
            elif status_weight < 0.75:
                status = Appointment.Status.CANCELLED
            elif status_weight < 0.82:
                status = Appointment.Status.NO_SHOW
            elif status_weight < 0.88:
                status = Appointment.Status.RESCHEDULED
            else:
                status = Appointment.Status.REJECTED

            expires_at = now + timedelta(hours=48)

            appointment = Appointment.objects.create(
                customer=customer,
                customer_name_snapshot=customer.full_name,
                customer_email_snapshot=customer.email,
                customer_phone_snapshot=customer.phone,
                appointment_date=appointment_date,
                start_time=start_time,
                end_time=end_time,
                assigned_staff=assigned_staff if status != Appointment.Status.PENDING else None,
                status=status,
                booking_source=random.choice(
                    [Appointment.BookingSource.PUBLIC, Appointment.BookingSource.WALK_IN]
                ),
                notes=f"Demo appointment {i}",
                created_by=random.choice(staff) if status != Appointment.Status.PENDING else None,
                expires_at=expires_at,
                verified_at=now if status != Appointment.Status.UNVERIFIED else None,
            )

            # Add service to appointment
            AppointmentService.objects.create(
                appointment=appointment,
                service=service,
                service_name=service.name,
                duration_minutes=service.duration_minutes,
                price=service.price,
            )

            # Set cancellation reason if cancelled
            if status in (Appointment.Status.CANCELLED, Appointment.Status.RESCHEDULED):
                appointment.cancellation_reason = random.choice(CANCELLATION_REASONS)
                appointment.save()

            appointments.append(appointment)

        return appointments

    def _create_pos_transactions(self, users: dict, count: int) -> List[Sale]:
        """Create demo POS transactions spanning multiple months"""
        transactions = []
        cashier = users["CASHIER"]
        now = timezone.now()

        # Ensure ReceiptSequence exists
        receipt_seq, _ = ReceiptSequence.objects.get_or_create(defaults={"last_value": 0})

        for i in range(count):
            # Vary dates over past 6 months
            days_ago = random.randint(0, 180)
            created_at = now - timedelta(days=days_ago)

            # Generate receipt number
            receipt_seq.last_value += 1
            receipt_seq.save()
            receipt_number = f"REC-{created_at.strftime('%Y%m%d')}-{receipt_seq.last_value:06d}"

            # Random sale details - keep it simple: no discount
            subtotal_cents = random.randint(2500, 50000)  # 25.00 to 500.00
            subtotal = Decimal(subtotal_cents) / Decimal("100")
            
            # For simplicity, start without discounts to avoid constraint issues
            discount_type = Sale.DiscountType.NONE
            discount_amount = Decimal("0.00")
            discount_value = Decimal("0.00")
            total = subtotal

            status = random.choice([Sale.Status.COMPLETED, Sale.Status.VOIDED])

            void_reason = ""
            voided_by = None
            voided_at = None
            if status == Sale.Status.VOIDED:
                void_reason = "Demo void for testing"
                voided_by = cashier
                voided_at = created_at + timedelta(minutes=random.randint(1, 60))

            sale = Sale.objects.create(
                receipt_number=receipt_number,
                customer_name_snapshot="Walk-in customer" if random.random() > 0.4 else (Customer.objects.order_by('?').first().full_name if Customer.objects.exists() else "Customer"),
                subtotal=subtotal,
                discount_type=discount_type,
                discount_value=discount_value,
                discount_amount=discount_amount,
                total=total,
                status=status,
                void_reason=void_reason,
                voided_by=voided_by,
                voided_at=voided_at,
                cashier=cashier,
                cashier_name_snapshot=f"{cashier.first_name} {cashier.last_name}",
            )

            # Add line items
            num_items = random.randint(1, 3)
            position = 0
            for _ in range(num_items):
                service = random.choice(Service.objects.all())
                quantity = random.randint(1, 2)
                item_total = service.price * quantity

                SaleItem.objects.create(
                    sale=sale,
                    service=service,
                    service_name=service.name,
                    service_category=service.category.name,
                    unit_price=service.price,
                    quantity=quantity,
                    line_total=item_total,
                    position=position,
                )
                position += 1

            # Create payment record
            payment_method = random.choice([Payment.Method.CASH, Payment.Method.CARD, Payment.Method.GCASH])
            amount_tendered = total if payment_method != Payment.Method.CASH else total + Decimal(str(random.randint(0, 50)))
            change = (amount_tendered - total).quantize(Decimal("0.01")) if payment_method == Payment.Method.CASH else Decimal("0.00")

            Payment.objects.create(
                sale=sale,
                payment_method=payment_method,
                amount_tendered=amount_tendered,
                change=change,
                reference=f"REF-{i}" if random.random() > 0.5 else "",
                recorded_by=cashier,
            )

            transactions.append(sale)

        return transactions

    def _print_summary(self, users, customers, appointments, transactions):
        """Print a summary of seeded data"""
        self.stdout.write(
            self.style.SUCCESS("\nDemo Data Summary")
        )
        self.stdout.write("=" * 60)

        self.stdout.write("\nAccounts:")
        self.stdout.write(f"  Owner: {users['OWNER'].email}")
        self.stdout.write(f"  Cashier: {users['CASHIER'].email}")
        self.stdout.write(f"  Staff: {len(users['STAFF'])} accounts")
        for staff in users['STAFF']:
            profile = staff.staff_profile if hasattr(staff, 'staff_profile') else None
            spec_name = profile.specialty if profile else "Staff"
            self.stdout.write(f"    - {staff.email} ({spec_name})")

        self.stdout.write(f"\nServices: {Service.objects.count()} total")
        for category in ServiceCategory.objects.all():
            count = category.services.count()
            self.stdout.write(f"  - {category.name}: {count} services")

        self.stdout.write(f"\nCustomers: {len(customers)}")

        self.stdout.write(f"\nAppointments: {len(appointments)}")
        status_counts = {}
        for appt in appointments:
            status_counts[appt.status] = status_counts.get(appt.status, 0) + 1
        for status, count in sorted(status_counts.items()):
            self.stdout.write(f"  - {status}: {count}")

        self.stdout.write(f"\nPOS Transactions: {len(transactions)}")
        total_revenue = sum(t.total for t in transactions)
        self.stdout.write(f"  - Total Revenue: ${total_revenue}")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            self.style.SUCCESS("Login Credentials (DEMO ONLY):")
        )
        self.stdout.write(f"  Owner: {users['OWNER'].email} / DemoOwner@123456")
        self.stdout.write(f"  Cashier: {users['CASHIER'].email} / DemoCashier@123456")
        self.stdout.write("  Staff: staff0@...8 / DemoStaff0@...8@123456")
