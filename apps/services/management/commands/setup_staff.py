import os
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Appointment
from apps.services.models import Service, ServiceCategory, StaffProfile, StaffSchedule

User = get_user_model()

STAFF_ROSTER = [
    {
        "nickname": "Nory",
        "first_name": "Leonor (Nory)",
        "last_name": "Pecaso",
        "email": "nory.pecaso@getnailed.com",
        "phone_number": "+63 917 101 0001",
        "specialty": "Nail Technician",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
        ],
        "extra_services": [
            "GN6",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Rita",
        "first_name": "Rita",
        "last_name": "Inoferio",
        "email": "rita.inoferio@getnailed.com",
        "phone_number": "+63 917 101 0002",
        "specialty": "Nail Technician / Nail Art",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Nail Art",
        ],
        "extra_services": [
            "GN6",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Stef",
        "first_name": "Stefanie (Stef)",
        "last_name": "Datur",
        "email": "stef.datur@getnailed.com",
        "phone_number": "+63 917 101 0003",
        "specialty": "Nail Technician / Nail Art",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Nail Art",
        ],
        "extra_services": [
            "GN6",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Alona",
        "first_name": "Alona",
        "last_name": "Dela Cruz",
        "email": "alona.delacruz@getnailed.com",
        "phone_number": "+63 917 101 0004",
        "specialty": "Nail Technician / Nail Art",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Nail Art",
        ],
        "extra_services": [
            "GN6",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Verna",
        "first_name": "Vernalyn (Verna)",
        "last_name": "Agustin",
        "email": "verna.agustin@getnailed.com",
        "phone_number": "+63 917 101 0005",
        "specialty": "Nail Tech / Lash Tech / Wax / Lash Lift / Cashier",
        "is_cashier": True,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Lashes",
            "Waxing",
        ],
        "extra_services": [
            "GN1",
            "GN2",
            "GN3",
            "GN6",
            "GN8",
            "GN11",
            "GN13",
            "GN14",
            "GN15",
            "GN16",
        ],
    },
    {
        "nickname": "Jessa",
        "first_name": "Jessa",
        "last_name": "Manuel",
        "email": "jessa.manuel@getnailed.com",
        "phone_number": "+63 917 101 0006",
        "specialty": "Nail Tech / Lash Lift / Threading / Wax",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Waxing",
        ],
        "extra_services": [
            "Eyelash Lift",
            "Eyelash Lift with Tint",
            "GN1",
            "GN2",
            "GN3",
            "GN6",
            "GN8",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Manilyn",
        "first_name": "Manilyn",
        "last_name": "Brigais",
        "email": "manilyn.brigais@getnailed.com",
        "phone_number": "+63 917 101 0007",
        "specialty": "Nail Tech / Lash Lift / Threading / Wax",
        "is_cashier": False,
        "categories": [
            "Nail Care",
            "Russian / E-File Cleaning",
            "Hands & Feet",
            "Kiddie Nails",
            "Add Ons",
            "Waxing",
        ],
        "extra_services": [
            "Eyelash Lift",
            "Eyelash Lift with Tint",
            "GN1",
            "GN2",
            "GN3",
            "GN6",
            "GN8",
            "GN11",
            "GN14",
            "GN15",
        ],
    },
    {
        "nickname": "Phen",
        "first_name": "Josephine (Phen)",
        "last_name": "Abiño",
        "email": "phen.abino@getnailed.com",
        "phone_number": "+63 917 101 0008",
        "specialty": "Therapist / Cashier",
        "is_cashier": True,
        "categories": [
            "Spa & Massage",
            "Hands & Feet",
        ],
        "extra_services": [
            "Kiddie Foot Spa",
            "Kiddie Hand Spa",
            "Kiddie Massage",
            "GN4",
            "GN5",
            "GN7",
            "GN9",
            "GN10",
            "GN12",
        ],
    },
    {
        "nickname": "Ann",
        "first_name": "Mary Ann (Ann)",
        "last_name": "Olarte",
        "email": "ann.olarte@getnailed.com",
        "phone_number": "+63 917 101 0009",
        "specialty": "Therapist",
        "is_cashier": False,
        "categories": [
            "Spa & Massage",
            "Hands & Feet",
        ],
        "extra_services": [
            "Kiddie Foot Spa",
            "Kiddie Hand Spa",
            "Kiddie Massage",
            "GN4",
            "GN5",
            "GN7",
            "GN9",
            "GN10",
            "GN12",
        ],
    },
    {
        "nickname": "Sheng",
        "first_name": "Chrischel (Sheng)",
        "last_name": "Lucilla",
        "email": "sheng.lucilla@getnailed.com",
        "phone_number": "+63 917 101 0010",
        "specialty": "Foot Spa / Cashier",
        "is_cashier": True,
        "categories": [],
        "extra_services": [
            "Foot Spa",
            "Foot Massage",
            "Reflexology",
            "Paraffin Wax",
            "Basic Pedicure + Foot Spa",
            "Foot Spa + Foot Massage",
            "Basic Pedicure + Foot Massage",
            "Basic Pedicure + Foot Reflex",
            "Kiddie Foot Spa",
            "GN4",
            "GN5",
            "GN7",
            "GN9",
            "GN10",
            "GN12",
        ],
    },
    {
        "nickname": "Aila",
        "first_name": "Aila Marie (Aila)",
        "last_name": "Ramos",
        "email": "aila.ramos@getnailed.com",
        "phone_number": "+63 917 101 0011",
        "specialty": "Foot Spa / Cashier",
        "is_cashier": True,
        "categories": [],
        "extra_services": [
            "Foot Spa",
            "Foot Massage",
            "Reflexology",
            "Paraffin Wax",
            "Basic Pedicure + Foot Spa",
            "Foot Spa + Foot Massage",
            "Basic Pedicure + Foot Massage",
            "Basic Pedicure + Foot Reflex",
            "Kiddie Foot Spa",
            "GN4",
            "GN5",
            "GN7",
            "GN9",
            "GN10",
            "GN12",
        ],
    },
]


class Command(BaseCommand):
    help = "Replace salon staff roster with updated staff, specialty qualifications, shifts, and cashier access."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-old",
            action="store_true",
            help="Do not remove existing staff members outside the new roster.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset staff passwords to the value of GETNAILED_STAFF_PASSWORD.",
        )

    def handle(self, *args, **options):
        staff_password = os.environ.get("GETNAILED_STAFF_PASSWORD")
        if not staff_password:
            raise CommandError("Set GETNAILED_STAFF_PASSWORD before running this command.")

        self.stdout.write(self.style.NOTICE("Setting up updated staff roster..."))

        new_emails = {entry["email"].lower() for entry in STAFF_ROSTER}

        with transaction.atomic():
            # 1. First, create/ensure Nory exists so we can reassign any legacy appointments
            first_entry = STAFF_ROSTER[0]
            nory_user, _ = User.objects.get_or_create(
                email=first_entry["email"].lower(),
                defaults={
                    "first_name": first_entry["first_name"],
                    "last_name": first_entry["last_name"],
                    "role": User.Role.STAFF,
                    "is_active": True,
                    "is_active_staff_member": True,
                    "email_verified_at": timezone.now(),
                    "phone_number": first_entry["phone_number"],
                },
            )

            # 2. Reassign appointments from old staff to Nory before removing them
            old_staff_qs = User.objects.filter(role=User.Role.STAFF).exclude(
                email__in=new_emails
            )
            for old_staff in old_staff_qs:
                reassigned_count = Appointment.objects.filter(
                    assigned_staff=old_staff
                ).update(assigned_staff=nory_user)
                if reassigned_count:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Reassigned {reassigned_count} appointments from {old_staff.email} to {nory_user.email}."
                        )
                    )

            # 3. Remove old staff if not kept
            if not options["keep_old"]:
                old_count = old_staff_qs.count()
                if old_count:
                    for old_staff in list(old_staff_qs):
                        old_email = old_staff.email
                        old_staff.delete()
                        self.stdout.write(
                            self.style.WARNING(f"Removed previous staff member: {old_email}")
                        )
                else:
                    self.stdout.write("No previous staff members to remove.")

            # 4. Create or update each of the 11 staff members
            for spec in STAFF_ROSTER:
                email = spec["email"].lower()
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "first_name": spec["first_name"],
                        "last_name": spec["last_name"],
                        "role": User.Role.STAFF,
                        "is_active": True,
                        "is_active_staff_member": True,
                        "email_verified_at": timezone.now(),
                        "phone_number": spec["phone_number"],
                        "can_use_pos": spec["is_cashier"],
                        "can_manage_bookings": spec["is_cashier"],
                        "can_manage_customers": spec["is_cashier"],
                        "can_assign_services": spec["is_cashier"],
                    },
                )

                # Update info if already existed
                user.first_name = spec["first_name"]
                user.last_name = spec["last_name"]
                user.role = User.Role.STAFF
                user.is_active = True
                user.is_active_staff_member = True
                user.phone_number = spec["phone_number"]
                user.can_use_pos = spec["is_cashier"]
                if spec["is_cashier"]:
                    user.can_manage_bookings = True
                    user.can_manage_customers = True
                    user.can_assign_services = True
                user.set_password(staff_password)
                user.save()

                # Ensure StaffProfile exists
                profile, _ = StaffProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "specialty": spec["specialty"],
                        "availability_status": StaffProfile.Availability.AVAILABLE,
                        "is_active": True,
                    },
                )
                profile.specialty = spec["specialty"]
                profile.availability_status = StaffProfile.Availability.AVAILABLE
                profile.is_active = True
                profile.save()

                # Calculate qualified services
                qualified_services = set()
                for cat_name in spec.get("categories", []):
                    cat_services = Service.objects.filter(
                        category__name=cat_name, is_active=True
                    )
                    qualified_services.update(cat_services)

                for svc_name in spec.get("extra_services", []):
                    matching = Service.objects.filter(name=svc_name, is_active=True)
                    qualified_services.update(matching)

                profile.skills.set(qualified_services)

                action_str = "Created" if created else "Updated"
                pos_str = " [Cashier/POS]" if spec["is_cashier"] else ""
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[OK] {action_str} {spec['nickname']} ({user.get_full_name()}): "
                        f"{spec['specialty']}{pos_str} with {len(qualified_services)} qualified services."
                    )
                )

            # Apply weekly schedules (Monday-Sunday, 1 leave per staff, lunch 12pm-1pm)
            from apps.services.schedules import apply_staff_weekly_schedules, sync_staff_time_blocks
            sched_count = apply_staff_weekly_schedules()
            tb_count = sync_staff_time_blocks(weeks=4)
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] Configured {sched_count} shift schedules across Monday-Sunday with 1 designated leave day per staff and 12:00 PM - 1:00 PM lunch."
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] Synchronized {tb_count} calendar time blocks (Lunch & Leave) for the visual planner."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSuccessfully set up all {len(STAFF_ROSTER)} staff members!\n"
                "Passwords were set from GETNAILED_STAFF_PASSWORD."
            )
        )
