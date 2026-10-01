from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.bookings.models import Appointment, Booking


class Command(BaseCommand):
    help = "Expire unverified public booking requests after their configured lifetime."

    def handle(self, *args, **options):
        legacy_count = Booking.objects.filter(
            status=Booking.Status.UNVERIFIED,
            expires_at__lte=timezone.now(),
        ).update(
            status=Booking.Status.EXPIRED,
            verification_code_digest="",
        )
        appointment_count = Appointment.objects.filter(
            status=Appointment.Status.UNVERIFIED,
            expires_at__lte=timezone.now(),
        ).update(
            status=Appointment.Status.EXPIRED,
            verification_code_digest="",
        )
        count = legacy_count + appointment_count
        self.stdout.write(self.style.SUCCESS(f"Expired {count} booking request(s)."))
